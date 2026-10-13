import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from database import (
    LeadEntity, LeadContact, LeadScore, LeadPipeline,
    LeadFitProfile, LeadSuppression,
)
from sources import fetch_all_sources
from enrichment import enrich_entity
from enrichment.contact_policy import is_portal_domain, is_synthetic_email
from scoring.lead_score import score_lead, DEFAULT_KEYWORDS, DEFAULT_WEIGHTS
from scoring.domain_match import match_domains, classify_orientation
from intelligence_bridge import build_intelligence_context
from outreach import generate_outreach_draft
from pillar_signals import fetch_pillar_signals, pillar_signal_for
from lead_quality import sanitize_raw_lead, entity_is_junk
from text_utils import clean_description
from track_utils import normalize_lead_track


SALES_CHECK_DEFAULT_WEIGHT = 0.15


def _lead_sources(entity: LeadEntity, contacts: list) -> list[dict]:
    sources: list[dict] = []
    payload = entity.raw_payload or {}
    for key in ("link", "url", "source_url"):
        val = payload.get(key)
        if isinstance(val, str) and val.startswith("http"):
            sources.append({"label": entity.source or "signal", "url": val})
            break
    for c in contacts:
        url = getattr(c, "source_url", None)
        if url and all(s["url"] != url for s in sources):
            sources.append({"label": "contact page", "url": url})
    return sources[:5]


def apply_sales_check(
    entity: LeadEntity,
    composite: float,
    breakdown: dict,
    best: dict | None,
    contacts: list,
    weights: dict,
) -> tuple[float, dict]:
    """Blend the BANT/MEDDIC check into the score and store the 'why this lead' line."""
    from scoring.sales_check import rule_sales_check

    check, reason = rule_sales_check(
        name=entity.name,
        signal_type=entity.signal_type,
        signal_value=float(entity.signal_value) if entity.signal_value else None,
        signal_date=entity.signal_date,
        deadline=entity.deadline,
        breakdown=breakdown,
        best_match=best,
        contacts=[{"role_title": c.role_title, "email": c.email} for c in contacts],
    )
    if (entity.sales_check or {}).get("method") == "ai":
        check = {**entity.sales_check}
    else:
        entity.sales_check = check
    if not entity.fit_reason or (entity.sales_check or {}).get("method") != "ai":
        entity.fit_reason = reason
    entity.sources = _lead_sources(entity, contacts)

    w = float(weights.get("sales_check", SALES_CHECK_DEFAULT_WEIGHT))
    blended = round(composite * (1 - w) + float(check["score"]) * w, 2)
    breakdown = {**breakdown, "sales_check": check["score"]}
    return blended, breakdown


def _normalize_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    d = domain.lower().strip().replace("www.", "")
    return d or None


def _normalize_name(name: str) -> str:
    return name.lower().strip()[:100]


def get_or_create_fit_profile(db: Session) -> LeadFitProfile:
    profile = db.query(LeadFitProfile).order_by(LeadFitProfile.created_at.desc()).first()
    if profile:
        return profile
    profile = LeadFitProfile(
        keywords=DEFAULT_KEYWORDS,
        weights=DEFAULT_WEIGHTS,
        version="v1.0",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def sync_fit_profile_from_intelligence(db: Session) -> LeadFitProfile:
    """Rebuild fit keywords from Market Depth GO domains + Build Readiness capabilities."""
    ctx = build_intelligence_context(db)
    keywords = ctx["sync_keywords"] or DEFAULT_KEYWORDS
    version = f"sync-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
    previous = db.query(LeadFitProfile).order_by(LeadFitProfile.created_at.desc()).first()
    profile = LeadFitProfile(
        keywords=keywords,
        weights={**DEFAULT_WEIGHTS, **(dict(previous.weights) if previous else {})},
        version=version,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


PORTAL_DOMAINS = {
    "grants.gov", "sam.gov", "gem.gov.in", "eprocure.gov.in",
    "ted.europa.eu", "worldbank.org", "bidplus.gem.gov.in",
}


def _is_portal_domain(domain: str | None) -> bool:
    return is_portal_domain(domain)


def _resolve_enrich_domain(raw_domain: str | None, raw_payload: dict | None) -> str | None:
    """Pick a company domain for enrichment; skip gov portals when target_domain exists."""
    norm = _normalize_domain(raw_domain)
    payload = raw_payload or {}
    target = _normalize_domain(payload.get("target_domain"))
    if norm and not _is_portal_domain(norm):
        return norm
    if target and not _is_portal_domain(target):
        return target
    return None if _is_portal_domain(norm) else norm


def find_existing_entity(db: Session, name: str, domain: str | None) -> LeadEntity | None:
    norm_domain = _normalize_domain(domain)
    norm_name = _normalize_name(name)

    if norm_domain and not _is_portal_domain(norm_domain):
        existing = db.query(LeadEntity).filter(LeadEntity.domain == norm_domain).first()
        if existing:
            return existing

    existing = db.query(LeadEntity).filter(LeadEntity.name == name).first()
    if existing:
        return existing

    entities = db.query(LeadEntity).all()
    for e in entities:
        if _normalize_name(e.name) == norm_name:
            return e
        if norm_domain and not _is_portal_domain(norm_domain) and e.domain and _normalize_domain(e.domain) == norm_domain:
            return e
    return None


def merge_signals(existing: LeadEntity, raw) -> None:
    parts: list[str] = []
    for text in (existing.description, raw.description):
        clean = clean_description(text)
        if clean and clean not in parts:
            parts.append(clean)
    existing.description = " | ".join(parts)[:1000]
    if raw.signal_value and (not existing.signal_value or raw.signal_value > existing.signal_value):
        existing.signal_value = raw.signal_value
    if raw.deadline and (not existing.deadline or raw.deadline < existing.deadline):
        existing.deadline = raw.deadline
    if raw.signal_type and raw.signal_type not in (existing.signal_type or ""):
        existing.signal_type = f"{existing.signal_type}+{raw.signal_type}" if existing.signal_type else raw.signal_type
    payload = existing.raw_payload or {}
    sources = payload.get("sources", [])
    sources.append({"source": raw.source, "signal": raw.signal_type})
    payload["sources"] = sources
    existing.raw_payload = payload


def is_suppressed(db: Session, email: str | None) -> bool:
    if not email:
        return False
    return db.query(LeadSuppression).filter(LeadSuppression.email == email.lower()).first() is not None


def process_lead(db: Session, raw, profile: LeadFitProfile, intel_ctx: dict) -> LeadEntity | None:
    raw = sanitize_raw_lead(raw)
    if raw is None:
        return None

    norm_domain = _normalize_domain(raw.domain)
    existing = find_existing_entity(db, raw.name, norm_domain)

    if existing:
        merge_signals(existing, raw)
        entity = existing
    else:
        entity = LeadEntity(
            name=raw.name,
            track=normalize_lead_track(raw.track),
            domain=norm_domain,
            description=clean_description(raw.description),
            source=raw.source,
            signal_type=raw.signal_type,
            signal_value=raw.signal_value,
            signal_date=raw.signal_date,
            deadline=raw.deadline,
            raw_payload=raw.raw_payload,
        )
        db.add(entity)
        db.flush()

        pipeline = LeadPipeline(entity_id=entity.id, stage="new")
        db.add(pipeline)

    target_domain = (raw.raw_payload or {}).get("target_domain")
    matches = match_domains(
        entity.description or "",
        intel_ctx.get("market_domains") or {},
        intel_ctx.get("verdicts") or {},
        name=entity.name or "",
        capability_by_domain=intel_ctx.get("capability_by_domain"),
        target_domain=target_domain,
    )
    orientation, best = classify_orientation(matches, intel_ctx.get("market_domains") or {})
    entity.lead_orientation = orientation
    entity.matched_domains = matches[:5]
    entity.domain_context = best or {}

    if best and best.get("track"):
        entity.track = normalize_lead_track(best["track"])
    elif raw.track:
        entity.track = normalize_lead_track(raw.track)

    contacts_data = enrich_entity(
        raw.name,
        _resolve_enrich_domain(norm_domain or raw.domain, raw.raw_payload),
        track=entity.track,
    )
    email_verified_score = 0.0
    for c in contacts_data:
        if is_suppressed(db, c.get("email")):
            continue
        existing_contact = db.query(LeadContact).filter(
            LeadContact.entity_id == entity.id,
            LeadContact.email == c.get("email"),
        ).first()
        if existing_contact:
            continue
        contact = LeadContact(
            entity_id=entity.id,
            full_name=c.get("full_name"),
            role_title=c.get("role_title"),
            email=c.get("email"),
            email_verified=c.get("email_verified", False),
            enrichment_source=c.get("enrichment_source"),
            consent_basis=c.get("consent_basis", "publicly-listed-company-contact"),
        )
        db.add(contact)
        if c.get("email_verified"):
            email_verified_score = 1.0
        elif c.get("email"):
            email_verified_score = max(email_verified_score, 0.5)

    composite, breakdown = score_lead(
        description=entity.description or "",
        track=entity.track,
        signal_value=float(entity.signal_value) if entity.signal_value else None,
        signal_date=entity.signal_date,
        deadline=entity.deadline,
        email_verified_score=email_verified_score,
        keywords=list(profile.keywords),
        weights=dict(profile.weights),
        orientation=orientation,
        best_match=best,
        pillar_signal=pillar_signal_for(entity.id, entity.matched_domains, intel_ctx.get("pillar_signals")),
    )
    db.flush()
    all_contacts = db.query(LeadContact).filter(LeadContact.entity_id == entity.id).all()
    composite, breakdown = apply_sales_check(
        entity, composite, breakdown, best, all_contacts, dict(profile.weights),
    )

    db.add(LeadScore(
        entity_id=entity.id,
        score=composite,
        breakdown=breakdown,
        fit_profile_version=profile.version,
    ))

    pipeline = db.query(LeadPipeline).filter(LeadPipeline.entity_id == entity.id).first()
    if pipeline and not pipeline.outreach_draft:
        contacts = db.query(LeadContact).filter(LeadContact.entity_id == entity.id).all()
        draft = generate_outreach_draft(
            {
                "name": entity.name,
                "track": entity.track,
                "description": entity.description,
                "signal_type": entity.signal_type,
                "signal_value": float(entity.signal_value) if entity.signal_value else None,
                "deadline": str(entity.deadline) if entity.deadline else None,
                "orientation": orientation,
                "matched_domain": best.get("domain_name") if best else None,
                "verdict": best.get("verdict") if best else None,
                "our_strengths": best.get("our_strengths") if best else [],
            },
            [{"full_name": c.full_name, "role_title": c.role_title, "email": c.email} for c in contacts],
        )
        pipeline.outreach_draft = json.dumps(draft)

    return entity


def ingest_external_lead(db: Session, raw, contact: dict | None = None) -> LeadEntity | None:
    """Add a single lead from outside discovery (e.g. a channel-partner referral)."""
    intel_ctx = build_intelligence_context(db)
    intel_ctx["pillar_signals"] = fetch_pillar_signals()
    profile = get_or_create_fit_profile(db)
    entity = process_lead(db, raw, profile, intel_ctx)
    if entity is None:
        db.rollback()
        return None
    email = (contact or {}).get("email")
    if email and not is_suppressed(db, email):
        exists = db.query(LeadContact).filter(
            LeadContact.entity_id == entity.id, LeadContact.email == email,
        ).first()
        if not exists:
            db.add(LeadContact(
                entity_id=entity.id,
                full_name=(contact or {}).get("full_name"),
                role_title=(contact or {}).get("role_title"),
                email=email,
                email_verified=False,
                enrichment_source="partner-referral",
                consent_basis="partner-referral",
            ))
    db.commit()
    db.refresh(entity)
    return entity


def rescore_all_leads(db: Session, profile: LeadFitProfile | None = None) -> int:
    """Re-match and re-score all leads against current Market Depth + Build Readiness + Growth Pillars."""
    intel_ctx = build_intelligence_context(db)
    pillar_signals = fetch_pillar_signals()
    if profile is None:
        profile = get_or_create_fit_profile(db)
    count = 0
    for entity in db.query(LeadEntity).all():
        entity.description = clean_description(entity.description)
        target = (entity.domain_context or {}).get("domain_name")
        matches = match_domains(
            entity.description or "",
            intel_ctx.get("market_domains") or {},
            intel_ctx.get("verdicts") or {},
            name=entity.name or "",
            capability_by_domain=intel_ctx.get("capability_by_domain"),
            target_domain=target,
        )
        orientation, best = classify_orientation(matches, intel_ctx.get("market_domains") or {})
        entity.lead_orientation = orientation
        entity.matched_domains = matches[:5]
        entity.domain_context = best or {}
        if best and best.get("track"):
            entity.track = normalize_lead_track(best["track"])

        contacts = db.query(LeadContact).filter(LeadContact.entity_id == entity.id).all()
        email_verified_score = 1.0 if any(c.email_verified for c in contacts) else 0.5 if contacts else 0.0
        composite, breakdown = score_lead(
            description=entity.description or "",
            track=entity.track,
            signal_value=float(entity.signal_value) if entity.signal_value else None,
            signal_date=entity.signal_date,
            deadline=entity.deadline,
            email_verified_score=email_verified_score,
            keywords=list(profile.keywords),
            weights=dict(profile.weights),
            orientation=orientation,
            best_match=best,
            pillar_signal=pillar_signal_for(entity.id, entity.matched_domains, pillar_signals),
        )
        composite, breakdown = apply_sales_check(
            entity, composite, breakdown, best, contacts, dict(profile.weights),
        )
        db.add(LeadScore(
            entity_id=entity.id,
            score=composite,
            breakdown=breakdown,
            fit_profile_version=profile.version,
        ))
        count += 1
    db.commit()
    return count


def prune_fake_contacts(db: Session) -> int:
    """Remove invented info@portal emails stored before contact policy fix."""
    removed = 0
    for contact in db.query(LeadContact).all():
        entity = db.query(LeadEntity).filter(LeadEntity.id == contact.entity_id).first()
        if not entity:
            continue
        domain = entity.domain
        source = contact.enrichment_source or ""
        if source == "domain-inferred" and (
            _is_portal_domain(domain)
            or is_synthetic_email(contact.email, domain)
        ):
            db.delete(contact)
            removed += 1
        elif contact.email and _is_portal_domain(contact.email.split("@")[-1]):
            db.delete(contact)
            removed += 1
    if removed:
        db.commit()
    return removed


def re_enrich_missing_contacts(db: Session) -> int:
    """Fetch real contacts (Hunter/Apollo) for company leads with none."""
    added = 0
    for entity in db.query(LeadEntity).all():
        if _is_portal_domain(entity.domain):
            continue
        if db.query(LeadContact).filter(LeadContact.entity_id == entity.id).first():
            continue
        enrich_domain = _resolve_enrich_domain(entity.domain, entity.raw_payload)
        if not enrich_domain:
            continue
        for c in enrich_entity(entity.name, enrich_domain, track=entity.track):
            if is_suppressed(db, c.get("email")):
                continue
            if db.query(LeadContact).filter(
                LeadContact.entity_id == entity.id,
                LeadContact.email == c.get("email"),
            ).first():
                continue
            db.add(LeadContact(
                entity_id=entity.id,
                full_name=c.get("full_name"),
                role_title=c.get("role_title"),
                email=c.get("email"),
                email_verified=c.get("email_verified", False),
                enrichment_source=c.get("enrichment_source"),
                consent_basis=c.get("consent_basis", "publicly-listed-company-contact"),
            ))
            added += 1
    if added:
        db.commit()
    return added


def latest_score_value(db: Session, entity_id) -> float:
    row = (
        db.query(LeadScore)
        .filter(LeadScore.entity_id == entity_id)
        .order_by(LeadScore.computed_at.desc())
        .first()
    )
    return float(row.score) if row else 0.0


def find_and_save_contacts(db: Session, entity: LeadEntity) -> list[LeadContact]:
    """Run the free-first contact finder for one lead and store new contacts."""
    from enrichment.contact_finder import find_contacts

    if _is_portal_domain(entity.domain):
        return []
    domain = _resolve_enrich_domain(entity.domain, entity.raw_payload)
    found = find_contacts(entity.name, domain, lead_score=latest_score_value(db, entity.id))
    added: list[LeadContact] = []
    for c in found:
        email = (c.get("email") or "").lower()
        if not email or is_suppressed(db, email):
            continue
        existing = db.query(LeadContact).filter(
            LeadContact.entity_id == entity.id, LeadContact.email == email,
        ).first()
        verified_at = datetime.fromisoformat(c["verified_at"]) if c.get("verified_at") else None
        if existing:
            if (c.get("confidence") or 0) > float(existing.confidence or 0):
                existing.confidence = c.get("confidence")
                existing.email_verified = c.get("email_verified", False)
                existing.source_url = c.get("source_url")
                existing.verified_at = verified_at
                existing.full_name = existing.full_name or c.get("full_name")
                existing.role_title = existing.role_title or c.get("role_title")
            continue
        contact = LeadContact(
            entity_id=entity.id,
            full_name=c.get("full_name"),
            role_title=c.get("role_title"),
            email=email,
            email_verified=c.get("email_verified", False),
            enrichment_source=c.get("enrichment_source"),
            consent_basis=c.get("consent_basis", "publicly-listed-company-contact"),
            confidence=c.get("confidence"),
            source_url=c.get("source_url"),
            verified_at=verified_at,
        )
        db.add(contact)
        added.append(contact)
    # Drop the old unverified info@ guess once a better contact exists.
    if any((c.get("confidence") or 0) >= 0.8 for c in found):
        db.query(LeadContact).filter(
            LeadContact.entity_id == entity.id,
            LeadContact.enrichment_source == "domain-inferred",
        ).delete()
    db.commit()
    return added


LEARNABLE = ("recency", "budget_indicator", "keyword_fit", "urgency",
             "contact_confidence", "market_demand_fit", "capability_fit", "sales_check")


def learn_weights_from_feedback(db: Session, min_each: int = 3, rate: float = 0.15) -> LeadFitProfile | None:
    """Nudge weights toward components that separate 'good' from 'bad' marks.

    Returns a new fit profile when there is enough feedback, else None.
    """
    from database import LeadFeedback

    rows = db.query(LeadFeedback).order_by(LeadFeedback.created_at.desc()).limit(200).all()
    good = [r.breakdown or {} for r in rows if r.verdict == "good"]
    bad = [r.breakdown or {} for r in rows if r.verdict == "bad"]
    if len(good) < min_each or len(bad) < min_each:
        return None

    def avg(items: list[dict], key: str) -> float:
        vals = [float(i.get(key, 0) or 0) for i in items]
        return sum(vals) / len(vals) if vals else 0.0

    profile = get_or_create_fit_profile(db)
    weights = {**DEFAULT_WEIGHTS, "sales_check": SALES_CHECK_DEFAULT_WEIGHT, **dict(profile.weights)}
    total_before = sum(weights.get(k, 0) for k in LEARNABLE)
    for key in LEARNABLE:
        gap = (avg(good, key) - avg(bad, key)) / 100.0
        weights[key] = max(0.02, weights.get(key, 0) * (1 + rate * gap * 2))
    total_after = sum(weights[k] for k in LEARNABLE)
    for key in LEARNABLE:
        weights[key] = round(weights[key] * total_before / total_after, 4)

    new_profile = LeadFitProfile(
        keywords=list(profile.keywords),
        weights=weights,
        version=f"learned-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    return new_profile


def prune_junk_leads(db: Session) -> int:
    """Remove aggregate articles and invalid names from the database."""
    removed = 0
    for entity in db.query(LeadEntity).all():
        if entity_is_junk(entity.name or "", entity.description):
            db.query(LeadContact).filter(LeadContact.entity_id == entity.id).delete()
            db.query(LeadScore).filter(LeadScore.entity_id == entity.id).delete()
            db.query(LeadPipeline).filter(LeadPipeline.entity_id == entity.id).delete()
            db.delete(entity)
            removed += 1
    if removed:
        db.commit()
    return removed


def run_discovery(job_id: str, db: Session) -> None:
    from database import LeadJob
    job = db.query(LeadJob).filter(LeadJob.id == job_id).first()
    if not job:
        return
    try:
        job.status = "fetching"
        db.commit()

        intel_ctx = build_intelligence_context(db)
        intel_ctx["pillar_signals"] = fetch_pillar_signals()
        if intel_ctx.get("sync_keywords"):
            profile = sync_fit_profile_from_intelligence(db)
        else:
            profile = get_or_create_fit_profile(db)

        raw_leads = fetch_all_sources(intel_ctx)
        count = 0

        job.status = "processing"
        db.commit()

        for raw in raw_leads:
            if process_lead(db, raw, profile, intel_ctx) is not None:
                count += 1

        prune_junk_leads(db)
        prune_fake_contacts(db)
        db.commit()
        job.status = "done"
        job.entities_found = count
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        job = db.query(LeadJob).filter(LeadJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
