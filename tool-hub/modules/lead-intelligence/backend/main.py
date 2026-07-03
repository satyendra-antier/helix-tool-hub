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
    LeadFitProfile, LeadSuppression, LeadJob,
    get_db, run_migrations,
)
from pipeline import run_discovery, get_or_create_fit_profile, process_lead
from scoring.lead_score import score_lead, DEFAULT_KEYWORDS, DEFAULT_WEIGHTS
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
        "description": entity.description,
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
            }
            for c in contacts
        ],
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
    db: Session = Depends(get_db),
):
    query = db.query(LeadEntity).order_by(LeadEntity.created_at.desc())
    if track and track != "all":
        query = query.filter(LeadEntity.track == track)
    entities = query.limit(200).all()
    results = [entity_to_dict(e, db) for e in entities]
    if stage:
        results = [r for r in results if r["stage"] == stage]
    return {"leads": results}


@app.get("/leads/government")
def government_calendar(db: Session = Depends(get_db)):
    entities = (
        db.query(LeadEntity)
        .filter(LeadEntity.track == "government")
        .order_by(LeadEntity.deadline.asc().nullslast())
        .all()
    )
    return {"opportunities": [entity_to_dict(e, db) for e in entities]}


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

    entities = db.query(LeadEntity).all()
    for entity in entities:
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
        )
        db.add(LeadScore(
            entity_id=entity.id,
            score=composite,
            breakdown=breakdown,
            fit_profile_version=version,
        ))
    db.commit()
    return {"version": version, "keywords": body.keywords, "weights": body.weights}


@app.post("/suppression")
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
    writer.writerow(["name", "track", "domain", "signal_type", "score", "stage", "deadline", "source"])
    for entity in entities:
        data = entity_to_dict(entity, db)
        writer.writerow([
            data["name"], data["track"], data["domain"], data["signal_type"],
            data["score"], data["stage"], data["deadline"], data["source"],
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads-export.csv"},
    )
