import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
import csv
import io

from database import (
    MarketDepthDomain,
    MarketDepthSnapshot,
    MarketDepthReport,
    MarketDepthJob,
    MarketDepthWeights,
    MarketDepthCompensation,
    get_db,
    run_migrations,
)
from pipeline import seed_domains, get_weights, run_refresh, recompute_from_latest
from scoring.engine import DEFAULT_WEIGHTS

app = FastAPI(title="Market Depth Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DomainCreate(BaseModel):
    name: str
    track: str
    keywords: list[str]


class WeightsUpdate(BaseModel):
    weights: dict[str, float]


def score_to_dict(score, product_landscape=None) -> dict:
    return {
        "domain": score.domain,
        "domain_id": score.domain_id,
        "track": score.track,
        "composite_score": score.composite_score,
        "components": score.components,
        "raw_evidence": {
            k: {
                "value": v.value,
                "unit": v.unit,
                "available": v.available,
                "raw_data": v.raw_data,
                "note": v.note,
            }
            for k, v in score.raw_evidence.items()
        },
        "product_landscape": product_landscape,
    }


def _landscape_for_domain(db: Session, domain_id: str) -> dict | None:
    snap = (
        db.query(MarketDepthSnapshot)
        .filter(MarketDepthSnapshot.domain_id == domain_id)
        .order_by(MarketDepthSnapshot.fetched_at.desc())
        .first()
    )
    return snap.product_landscape if snap and snap.product_landscape else None


@app.on_event("startup")
def startup():
    run_migrations()
    db = next(get_db())
    try:
        seed_domains(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/domains")
def list_domains(db: Session = Depends(get_db)):
    domains = db.query(MarketDepthDomain).all()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "track": d.track,
            "keywords": d.keywords,
            "active": d.active,
        }
        for d in domains
    ]


@app.post("/domains")
def create_domain(body: DomainCreate, db: Session = Depends(get_db)):
    domain = MarketDepthDomain(
        name=body.name,
        track=body.track,
        keywords=body.keywords,
        active=True,
    )
    db.add(domain)
    db.commit()
    return {"id": str(domain.id)}


@app.get("/weights")
def get_current_weights(db: Session = Depends(get_db)):
    return {"weights": get_weights(db)}


@app.patch("/weights")
def update_weights(body: WeightsUpdate, db: Session = Depends(get_db)):
    row = MarketDepthWeights(weights=body.weights, updated_at=datetime.utcnow())
    db.add(row)
    db.commit()

    scores = recompute_from_latest(db, body.weights)
    return {
        "weights": body.weights,
        "scores": [
            score_to_dict(s, _landscape_for_domain(db, str(s.domain_id)))
            for s in scores
        ],
    }


@app.post("/refresh")
def refresh(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = MarketDepthJob(status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    def task():
        from database import SessionLocal
        session = SessionLocal()
        try:
            run_refresh(str(job.id), session)
        finally:
            session.close()

    background_tasks.add_task(task)
    return {"job_id": str(job.id)}


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(MarketDepthJob).filter(MarketDepthJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "id": str(job.id),
        "status": job.status,
        "error": job.error,
        "snapshot_batch_id": str(job.snapshot_batch_id) if job.snapshot_batch_id else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.get("/snapshots/latest")
def latest_snapshots(db: Session = Depends(get_db)):
    domains = db.query(MarketDepthDomain).filter(MarketDepthDomain.active == True).all()
    weights = get_weights(db)
    scores = recompute_from_latest(db, weights)

    latest_fetch = (
        db.query(MarketDepthSnapshot.fetched_at)
        .order_by(MarketDepthSnapshot.fetched_at.desc())
        .first()
    )
    fetched_at = latest_fetch[0].isoformat() if latest_fetch and latest_fetch[0] else None

    if scores:
        return {
            "scores": [
                score_to_dict(s, _landscape_for_domain(db, str(s.domain_id)))
                for s in scores
            ],
            "weights": weights,
            "fetched_at": fetched_at,
            "methodology": {
                "scoring": "min-max normalization (0-100) across domains; weighted composite of available signals only",
                "signals": list(DEFAULT_WEIGHTS.keys()),
                "default_weights": DEFAULT_WEIGHTS,
            },
        }

    result = []
    latest_time = None
    for domain in domains:
        snap = (
            db.query(MarketDepthSnapshot)
            .filter(MarketDepthSnapshot.domain_id == domain.id)
            .order_by(MarketDepthSnapshot.fetched_at.desc())
            .first()
        )
        if snap:
            if not latest_time or snap.fetched_at > latest_time:
                latest_time = snap.fetched_at
            result.append({
                "domain": domain.name,
                "domain_id": str(domain.id),
                "track": domain.track,
                "composite_score": float(snap.composite_score),
                "components": snap.component_scores,
                "raw_evidence": snap.raw_evidence,
                "product_landscape": snap.product_landscape,
            })

    return {
        "scores": sorted(result, key=lambda x: x["composite_score"], reverse=True),
        "weights": weights,
        "fetched_at": latest_time.isoformat() if latest_time else None,
        "methodology": {
            "scoring": "min-max normalization (0-100) across domains; weighted composite of available signals only",
            "signals": list(DEFAULT_WEIGHTS.keys()),
            "default_weights": DEFAULT_WEIGHTS,
        },
    }


@app.get("/reports/latest")
def latest_report(db: Session = Depends(get_db)):
    report = (
        db.query(MarketDepthReport)
        .order_by(MarketDepthReport.created_at.desc())
        .first()
    )
    if not report:
        return {"report": None}
    return {
        "report": report.gemini_output,
        "validation_passed": report.validation_passed,
        "validation_notes": report.validation_notes,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@app.post("/compensation/import")
async def import_compensation(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    count = 0
    for row in reader:
        db.add(MarketDepthCompensation(
            domain_name=row.get("domain", row.get("domain_name", "")),
            role=row.get("role", ""),
            salary_median=float(row.get("salary_median", row.get("salary", 0)) or 0),
            currency=row.get("currency", "USD"),
            source=row.get("source", "csv_import"),
        ))
        count += 1
    db.commit()
    return {"imported": count}
