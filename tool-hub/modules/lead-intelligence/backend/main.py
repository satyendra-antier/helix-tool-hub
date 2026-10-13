import csv
import io
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import (
    LeadEntity, LeadContact, LeadScore, LeadPipeline,
    LeadFitProfile, LeadSuppression, LeadJob, LeadFeedback,
    get_db, run_migrations,
)
from pipeline import (
    run_discovery, get_or_create_fit_profile, process_lead,
    sync_fit_profile_from_intelligence, rescore_all_leads, prune_junk_leads,
    prune_fake_contacts,
    re_enrich_missing_contacts,
    ingest_external_lead,
    find_and_save_contacts,
    latest_score_value,
    apply_sales_check,
    learn_weights_from_feedback,
)
from pillar_signals import fetch_pillar_signals, pillar_signal_for
from enrichment.contact_policy import is_portal_domain
from scoring.lead_score import score_lead, DEFAULT_KEYWORDS, DEFAULT_WEIGHTS
from scoring.domain_match import match_domains, classify_orientation
from intelligence_bridge import build_intelligence_context
from pipeline_status import get_pipeline_status
from text_utils import clean_description
from track_utils import track_filter_values, normalize_lead_track
from sources.base import RawLead
from sources import fetch_all_sources

app = FastAPI(title="Lead Intelligence API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STAGES = ["new", "qualified", "contacted", "replied", "won", "lost"]


class FitProfileUpdate(BaseModel):
    keywords: list[str]
    weights: dict[str, float]


class StageUpdate(BaseModel):
    stage: str
    notes: Optional[str] = None


class OutreachUpdate(BaseModel):
    outreach_draft: str


class SuppressRequest(BaseModel):
    email: str
    reason: str = "unsubscribe"


class IngestRequest(BaseModel):
    name: str
    domain: Optional[str] = None
    description: str = ""
    track: str = "web2"
    source: str = "partner"
    signal_type: str = "referral"
    signal_value: Optional[float] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    raw_payload: dict = {}


def _portal_link(entity: LeadEntity) -> str | None:
    payload = entity.raw_payload or {}
    for key in ("link", "url"):
        val = payload.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    opp = payload.get("opp")
    if isinstance(opp, dict):
        opp_id = opp.get("id") or opp.get("oppId") or opp.get("number")
        if opp_id:
            return f"https://www.grants.gov/search-results-detail/{opp_id}"
    if entity.domain and is_portal_domain(entity.domain):
        portal_urls = {
            "grants.gov": "https://www.grants.gov",
            "sam.gov": "https://sam.gov",
            "gem.gov.in": "https://gem.gov.in",
            "eprocure.gov.in": "https://eprocure.gov.in",
            "worldbank.org": "https://www.worldbank.org/en/projects-operations/procurement",
            "ted.europa.eu": "https://ted.europa.eu",
        }
        return portal_urls.get(entity.domain.lower().replace("www.", ""))
    return None


def _latest_feedback(entity_id, db: Session) -> str | None:
    row = (
        db.query(LeadFeedback)
        .filter(LeadFeedback.entity_id == entity_id)
        .order_by(LeadFeedback.created_at.desc())
        .first()
    )
    return row.verdict if row else None


def entity_to_dict(entity: LeadEntity, db: Session) -> dict:
    latest_score = (
        db.query(LeadScore)
        .filter(LeadScore.entity_id == entity.id)
        .order_by(LeadScore.computed_at.desc())
        .first()
    )
    pipeline = db.query(LeadPipeline).filter(LeadPipeline.entity_id == entity.id).first()
    contacts = db.query(LeadContact).filter(LeadContact.entity_id == entity.id).all()
    draft = None
    if pipeline and pipeline.outreach_draft:
        try:
            draft = json.loads(pipeline.outreach_draft)
        except json.JSONDecodeError:
            draft = {"body": pipeline.outreach_draft}

    return {
        "id": str(entity.id),
        "name": entity.name,
        "track": entity.track,
        "domain": entity.domain,
        "description": clean_description(entity.description),
        "source": entity.source,
        "signal_type": entity.signal_type,
        "signal_value": float(entity.signal_value) if entity.signal_value else None,
        "signal_date": entity.signal_date.isoformat() if entity.signal_date else None,
        "deadline": entity.deadline.isoformat() if entity.deadline else None,
        "score": float(latest_score.score) if latest_score else 0,
        "breakdown": latest_score.breakdown if latest_score else {},
        "stage": pipeline.stage if pipeline else "new",
        "outreach_draft": draft,
        "outreach_sent_at": pipeline.outreach_sent_at.isoformat() if pipeline and pipeline.outreach_sent_at else None,
        "notes": pipeline.notes if pipeline else None,
        "contacts": [
            {
                "id": str(c.id),
                "full_name": c.full_name,
                "role_title": c.role_title,
                "email": c.email,
                "email_verified": c.email_verified,
                "enrichment_source": c.enrichment_source,
                "consent_basis": c.consent_basis,
                "confidence": float(c.confidence) if c.confidence is not None else None,
                "source_url": c.source_url,
                "phone": c.phone,
            }
            for c in sorted(contacts, key=lambda c: -float(c.confidence or 0))
        ],
        "fit_reason": entity.fit_reason,
        "sales_check": entity.sales_check or None,
        "sources": entity.sources or [],
        "feedback": _latest_feedback(entity.id, db),
        "lead_orientation": entity.lead_orientation or "generic",
        "matched_domains": entity.matched_domains or [],
        "domain_context": entity.domain_context or {},
        "portal_link": _portal_link(entity),
        "is_portal_lead": is_portal_domain(entity.domain),
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
    }


@app.on_event("startup")
def startup():
    run_migrations()
    db = next(get_db())
    try:
        get_or_create_fit_profile(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def config_status():
    from config import settings
    return {
        "openai_configured": bool(settings.resolve_api_key()),
        "chat_model": settings.resolve_chat_model(),
        "apollo_configured": bool(settings.apollo_api_key),
        "hunter_configured": bool(settings.hunter_api_key),
        "sam_gov_configured": bool(settings.sam_gov_api_key),
        "growth_pillars_signals": bool(settings.growth_pillars_api_url),
    }


@app.get("/pipeline/status")
def pipeline_status(db: Session = Depends(get_db)):
    return get_pipeline_status(db)


@app.post("/discover")
def discover(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = LeadJob(status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    def task():
        from database import SessionLocal
        session = SessionLocal()
        try:
            run_discovery(str(job.id), session)
        finally:
            session.close()

    background_tasks.add_task(task)
    return {"job_id": str(job.id)}


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(LeadJob).filter(LeadJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "id": str(job.id),
        "status": job.status,
        "error": job.error,
        "entities_found": int(job.entities_found or 0),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.get("/leads")
def list_leads(
    track: Optional[str] = None,
    stage: Optional[str] = None,
    orientation: Optional[str] = None,
    page: int = 1,
    page_size: int = 24,
    sort: str = "score",
    db: Session = Depends(get_db),
):
    from sqlalchemy import text

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    offset = (page - 1) * page_size

    track_vals = track_filter_values(track) if track and track != "all" else None
    orient_val = orientation if orientation in ("demand", "future", "generic") else None

    count_sql = """
        SELECT COUNT(*) FROM leads_entities e
        LEFT JOIN leads_pipeline p ON p.entity_id = e.id
        WHERE (:track_vals IS NULL OR e.track = ANY(:track_vals))
          AND (:orientation IS NULL OR e.lead_orientation = :orientation)
          AND (:stage IS NULL OR p.stage = :stage)
    """
    total = db.execute(text(count_sql), {
        "track_vals": track_vals,
        "orientation": orient_val,
        "stage": stage,
    }).scalar() or 0

    order_clause = (
        "score DESC NULLS LAST, e.created_at DESC"
        if sort == "score"
        else "e.created_at DESC"
    )
    ids_sql = f"""
        SELECT e.id::text
        FROM leads_entities e
        LEFT JOIN leads_pipeline p ON p.entity_id = e.id
        LEFT JOIN LATERAL (
            SELECT score FROM leads_scores ls
            WHERE ls.entity_id = e.id
            ORDER BY ls.computed_at DESC
            LIMIT 1
        ) s ON true
        WHERE (:track_vals IS NULL OR e.track = ANY(:track_vals))
          AND (:orientation IS NULL OR e.lead_orientation = :orientation)
          AND (:stage IS NULL OR p.stage = :stage)
        ORDER BY {order_clause}
        LIMIT :limit OFFSET :offset
    """
    id_rows = db.execute(text(ids_sql), {
        "track_vals": track_vals,
        "orientation": orient_val,
        "stage": stage,
        "limit": page_size,
        "offset": offset,
    }).fetchall()

    if not id_rows:
        return {
            "leads": [],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "pages": max(1, (int(total) + page_size - 1) // page_size),
        }

    from uuid import UUID as PyUUID
    entity_ids = [PyUUID(r[0]) for r in id_rows]
    entities = (
        db.query(LeadEntity)
        .filter(LeadEntity.id.in_(entity_ids))
        .all()
    )
    order_map = {str(eid): i for i, eid in enumerate(entity_ids)}
    entities.sort(key=lambda e: order_map.get(str(e.id), 999))

    return {
        "leads": [entity_to_dict(e, db) for e in entities],
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "pages": max(1, (int(total) + page_size - 1) // page_size),
    }


@app.get("/leads/government")
def government_calendar(limit: int = 50, db: Session = Depends(get_db)):
    """Bounded calendar — avoid unbounded N+1 that hangs the UI."""
    limit = max(1, min(limit, 100))
    entities = (
        db.query(LeadEntity)
        .filter(LeadEntity.track == "government")
        .order_by(LeadEntity.deadline.asc().nullslast())
        .limit(limit)
        .all()
    )
    return {"opportunities": [entity_to_dict(e, db) for e in entities], "limit": limit}


@app.get("/leads/{entity_id}")
def get_lead(entity_id: UUID, db: Session = Depends(get_db)):
    entity = db.query(LeadEntity).filter(LeadEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(404, "Lead not found")
    return entity_to_dict(entity, db)


@app.patch("/leads/{entity_id}/stage")
def update_stage(entity_id: UUID, body: StageUpdate, db: Session = Depends(get_db)):
    if body.stage not in STAGES:
        raise HTTPException(400, f"Invalid stage. Must be one of: {STAGES}")
    pipeline = db.query(LeadPipeline).filter(LeadPipeline.entity_id == entity_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline entry not found")
    pipeline.stage = body.stage
    if body.notes is not None:
        pipeline.notes = body.notes
    pipeline.updated_at = datetime.utcnow()
    db.commit()
    return {"stage": pipeline.stage}


@app.patch("/leads/{entity_id}/outreach")
def update_outreach(entity_id: UUID, body: OutreachUpdate, db: Session = Depends(get_db)):
    pipeline = db.query(LeadPipeline).filter(LeadPipeline.entity_id == entity_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline entry not found")
    pipeline.outreach_draft = body.outreach_draft
    pipeline.updated_at = datetime.utcnow()
    db.commit()
    return {"updated": True}


@app.post("/leads/{entity_id}/mark-sent")
def mark_sent(entity_id: UUID, db: Session = Depends(get_db)):
    """Human action only — no auto-send exists in this codebase."""
    pipeline = db.query(LeadPipeline).filter(LeadPipeline.entity_id == entity_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline entry not found")
    pipeline.stage = "contacted"
    pipeline.outreach_sent_at = datetime.utcnow()
    pipeline.updated_at = datetime.utcnow()
    db.commit()
    return {"sent_at": pipeline.outreach_sent_at.isoformat()}


class FeedbackRequest(BaseModel):
    verdict: str


@app.post("/leads/{entity_id}/feedback")
def lead_feedback(
    entity_id: UUID,
    body: FeedbackRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if body.verdict not in ("good", "bad"):
        raise HTTPException(400, "verdict must be 'good' or 'bad'")
    entity = db.query(LeadEntity).filter(LeadEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(404, "Lead not found")
    latest = (
        db.query(LeadScore)
        .filter(LeadScore.entity_id == entity_id)
        .order_by(LeadScore.computed_at.desc())
        .first()
    )
    db.add(LeadFeedback(entity_id=entity_id, verdict=body.verdict, breakdown=(latest.breakdown if latest else {})))
    if body.verdict == "bad":
        pipeline = db.query(LeadPipeline).filter(LeadPipeline.entity_id == entity_id).first()
        if pipeline and pipeline.stage == "new":
            pipeline.stage = "lost"
            pipeline.notes = (pipeline.notes or "") + "\nMarked not a fit."
    db.commit()

    learned = learn_weights_from_feedback(db)
    if learned:
        def task():
            from database import SessionLocal
            session = SessionLocal()
            try:
                rescore_all_leads(session)
            finally:
                session.close()
        background_tasks.add_task(task)
    return {"saved": True, "weights_updated": bool(learned), "version": learned.version if learned else None}


@app.post("/leads/{entity_id}/explain")
def explain_lead(entity_id: UUID, db: Session = Depends(get_db)):
    """Ask the AI for a sharper 'why this lead' line and BANT/MEDDIC check (needs OPENAI_API_KEY)."""
    from scoring.sales_check import ai_explain

    entity = db.query(LeadEntity).filter(LeadEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(404, "Lead not found")
    data = entity_to_dict(entity, db)
    result = ai_explain({
        k: data.get(k) for k in (
            "name", "description", "signal_type", "signal_value", "signal_date",
            "deadline", "domain_context", "contacts", "track",
        )
    })
    if not result:
        raise HTTPException(503, "AI isn't set up. Add OPENAI_API_KEY to .env to get AI explanations.")
    check, reason = result
    entity.sales_check = check
    if reason:
        entity.fit_reason = reason
    db.commit()
    return entity_to_dict(entity, db)


@app.post("/leads/{entity_id}/find-contacts")
def find_contacts_for_lead(entity_id: UUID, db: Session = Depends(get_db)):
    entity = db.query(LeadEntity).filter(LeadEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(404, "Lead not found")
    added = find_and_save_contacts(db, entity)
    return {"added": len(added), "lead": entity_to_dict(entity, db)}


@app.post("/contacts/find-top")
def find_contacts_for_top_leads(limit: int = 10, min_score: float = 50, db: Session = Depends(get_db)):
    """Contact discovery for the best leads that don't yet have a confident contact."""
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT e.id FROM leads_entities e
        LEFT JOIN LATERAL (
            SELECT score FROM leads_scores ls WHERE ls.entity_id = e.id
            ORDER BY ls.computed_at DESC LIMIT 1
        ) s ON true
        WHERE COALESCE(s.score, 0) >= :min_score
          AND NOT EXISTS (
            SELECT 1 FROM leads_contacts c
            WHERE c.entity_id = e.id AND COALESCE(c.confidence, 0) >= 0.8
          )
        ORDER BY s.score DESC NULLS LAST
        LIMIT :limit
    """), {"min_score": min_score, "limit": max(1, min(limit, 50))}).fetchall()
    total = 0
    for (eid,) in rows:
        entity = db.query(LeadEntity).filter(LeadEntity.id == eid).first()
        if entity:
            total += len(find_and_save_contacts(db, entity))
    return {"leads_checked": len(rows), "contacts_added": total}


@app.get("/fit-profile")
def get_fit_profile(db: Session = Depends(get_db)):
    profile = get_or_create_fit_profile(db)
    return {
        "keywords": list(profile.keywords),
        "weights": dict(profile.weights),
        "version": profile.version,
    }


@app.patch("/fit-profile")
def update_fit_profile(body: FitProfileUpdate, db: Session = Depends(get_db)):
    version = f"v{datetime.utcnow().strftime('%Y%m%d%H%M')}"
    profile = LeadFitProfile(
        keywords=body.keywords,
        weights=body.weights,
        version=version,
    )
    db.add(profile)
    db.commit()

    intel_ctx = build_intelligence_context(db)
    pillar_signals = fetch_pillar_signals()
    entities = db.query(LeadEntity).all()
    for entity in entities:
        target = (entity.domain_context or {}).get("domain_name")
        matches = match_domains(
            entity.description or "",
            intel_ctx.get("market_domains") or {},
            intel_ctx.get("verdicts") or {},
            name=entity.name or "",
            capability_by_domain=intel_ctx.get("capability_by_domain"),
            target_domain=target,
        )
        orient, best = classify_orientation(matches, intel_ctx.get("market_domains") or {})
        entity.lead_orientation = orient
        entity.matched_domains = matches[:5]
        entity.domain_context = best or {}
        if best and best.get("track"):
            entity.track = normalize_lead_track(best["track"])

        latest_score = (
            db.query(LeadScore)
            .filter(LeadScore.entity_id == entity.id)
            .order_by(LeadScore.computed_at.desc())
            .first()
        )
        contacts = db.query(LeadContact).filter(LeadContact.entity_id == entity.id).all()
        email_verified_score = 1.0 if any(c.email_verified for c in contacts) else 0.5 if contacts else 0.0
        composite, breakdown = score_lead(
            description=entity.description or "",
            track=entity.track,
            signal_value=float(entity.signal_value) if entity.signal_value else None,
            signal_date=entity.signal_date,
            deadline=entity.deadline,
            email_verified_score=email_verified_score,
            keywords=body.keywords,
            weights=body.weights,
            orientation=orient,
            best_match=best,
            pillar_signal=pillar_signal_for(entity.id, entity.matched_domains, pillar_signals),
        )
        composite, breakdown = apply_sales_check(
            entity, composite, breakdown, best, contacts, body.weights,
        )
        db.add(LeadScore(
            entity_id=entity.id,
            score=composite,
            breakdown=breakdown,
            fit_profile_version=version,
        ))
    db.commit()
    return {"version": version, "keywords": body.keywords, "weights": body.weights}


@app.post("/fit-profile/sync")
def sync_fit_profile(db: Session = Depends(get_db)):
    """Sync keywords from Market Depth GO domains + future opportunities; re-score all leads."""
    profile = sync_fit_profile_from_intelligence(db)
    rescored = rescore_all_leads(db, profile)
    removed = prune_junk_leads(db)
    return {
        "version": profile.version,
        "keywords": list(profile.keywords),
        "weights": dict(profile.weights),
        "rescored_leads": rescored,
        "junk_removed": removed,
    }


@app.post("/leads/ingest")
def ingest_lead(body: IngestRequest, db: Session = Depends(get_db)):
    """Add one externally sourced lead (channel-partner referral) and score it like any other."""
    domain = (body.domain or "").lower().strip()
    domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] or None
    raw = RawLead(
        name=body.name.strip(),
        track=normalize_lead_track(body.track),
        domain=domain,
        description=body.description,
        source=body.source,
        signal_type=body.signal_type,
        signal_value=body.signal_value,
        signal_date=datetime.utcnow().date(),
        raw_payload=body.raw_payload or {},
    )
    contact = {"full_name": body.contact_name, "email": body.contact_email} if body.contact_email else None
    entity = ingest_external_lead(db, raw, contact)
    if entity is None:
        raise HTTPException(400, "Lead rejected by quality filter (name looks invalid)")
    return entity_to_dict(entity, db)


@app.post("/leads/rescore")
def rescore_leads(db: Session = Depends(get_db)):
    """Re-score all leads with the current fit profile, intelligence and Growth Pillars signals."""
    return {"rescored_leads": rescore_all_leads(db)}


@app.post("/leads/cleanup")
def cleanup_junk_leads(db: Session = Depends(get_db)):
    junk_removed = prune_junk_leads(db)
    fake_contacts_removed = prune_fake_contacts(db)
    contacts_added = re_enrich_missing_contacts(db)
    return {
        "removed": junk_removed,
        "fake_contacts_removed": fake_contacts_removed,
        "contacts_added": contacts_added,
    }


@app.get("/suppressions")
def list_suppressions(db: Session = Depends(get_db)):
    return {"emails": [s.email for s in db.query(LeadSuppression).all()]}


@app.post("/suppressions")
def add_suppression(body: SuppressRequest, db: Session = Depends(get_db)):
    existing = db.query(LeadSuppression).filter(LeadSuppression.email == body.email.lower()).first()
    if not existing:
        db.add(LeadSuppression(email=body.email.lower(), reason=body.reason))
        db.commit()
    return {"suppressed": True}


@app.get("/export/csv")
def export_csv(db: Session = Depends(get_db)):
    entities = db.query(LeadEntity).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
            "name", "track", "domain", "signal_type", "score", "stage",
            "orientation", "matched_domain", "deadline", "source",
        ])
    for entity in entities:
        data = entity_to_dict(entity, db)
        matched = (data.get("domain_context") or {}).get("domain_name") or ""
        writer.writerow([
            data["name"], data["track"], data["domain"], data["signal_type"],
            data["score"], data["stage"], data.get("lead_orientation"),
            matched, data["deadline"], data["source"],
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads-export.csv"},
    )
