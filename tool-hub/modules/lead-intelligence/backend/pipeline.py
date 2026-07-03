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
from scoring.lead_score import score_lead, DEFAULT_KEYWORDS, DEFAULT_WEIGHTS
from outreach import generate_outreach_draft


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


PORTAL_DOMAINS = {
    "grants.gov", "sam.gov", "gem.gov.in", "eprocure.gov.in",
    "ted.europa.eu", "worldbank.org", "bidplus.gem.gov.in",
}


def _is_portal_domain(domain: str | None) -> bool:
    if not domain:
        return True
    return _normalize_domain(domain) in PORTAL_DOMAINS


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
    desc_parts = [existing.description or "", raw.description]
    existing.description = " | ".join(p for p in desc_parts if p)[:1000]
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


def process_lead(db: Session, raw, profile: LeadFitProfile) -> LeadEntity:
    norm_domain = _normalize_domain(raw.domain)
    existing = find_existing_entity(db, raw.name, norm_domain)

    if existing:
        merge_signals(existing, raw)
        entity = existing
    else:
        entity = LeadEntity(
            name=raw.name,
            track=raw.track,
            domain=norm_domain,
            description=raw.description,
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

    contacts_data = enrich_entity(raw.name, norm_domain or raw.domain)
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
            },
            [{"full_name": c.full_name, "role_title": c.role_title, "email": c.email} for c in contacts],
        )
        pipeline.outreach_draft = json.dumps(draft)

    return entity


def run_discovery(job_id: str, db: Session) -> None:
    from database import LeadJob
    job = db.query(LeadJob).filter(LeadJob.id == job_id).first()
    if not job:
        return
    try:
        job.status = "fetching"
        db.commit()

        profile = get_or_create_fit_profile(db)
        raw_leads = fetch_all_sources()
        count = 0

        job.status = "processing"
        db.commit()

        for raw in raw_leads:
            process_lead(db, raw, profile)
            count += 1

        db.commit()
        job.status = "done"
        job.entities_found = count
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
