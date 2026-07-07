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
from lead_quality import sanitize_raw_lead, entity_is_junk
from text_utils import clean_description
from track_utils import normalize_lead_track


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
    profile = LeadFitProfile(
        keywords=keywords,
        weights=DEFAULT_WEIGHTS,
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


def rescore_all_leads(db: Session, profile: LeadFitProfile | None = None) -> int:
    """Re-match and re-score all leads against current Market Depth + Build Readiness."""
    intel_ctx = build_intelligence_context(db)
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
