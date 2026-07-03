from datetime import datetime
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from database import (
    BuildReadinessProfile,
    BuildReadinessCapability,
    BuildReadinessVerdict,
    BuildReadinessJob,
    BuildReadinessChunk,
    get_db,
    run_migrations,
)
from pipeline import (
    get_or_create_profile,
    run_index_website,
    run_index_videos,
    run_analyze,
)

app = FastAPI(title="Build Readiness Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProfileUpdate(BaseModel):
    company_name: str
    website_url: str


def _run_job(task_fn, job_id: str):
    from database import SessionLocal
    session = SessionLocal()
    try:
        task_fn(job_id, session)
    finally:
        session.close()


@app.on_event("startup")
def startup():
    run_migrations()
    db = next(get_db())
    try:
        get_or_create_profile(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    chunk_count = db.query(BuildReadinessChunk).filter(
        BuildReadinessChunk.profile_id == profile.id
    ).count()
    return {
        "id": str(profile.id),
        "company_name": profile.company_name,
        "website_url": profile.website_url,
        "last_indexed_at": profile.last_indexed_at.isoformat() if profile.last_indexed_at else None,
        "pages_indexed": profile.pages_indexed,
        "chunks_indexed": chunk_count,
        "videos_indexed": profile.videos_indexed,
    }


@app.put("/profile")
def update_profile(body: ProfileUpdate, db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    profile.company_name = body.company_name.strip()
    url = str(body.website_url).strip()
    if not url.startswith("http"):
        url = "https://" + url
    profile.website_url = url
    profile.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "website_url": profile.website_url}


@app.post("/index/website")
def index_website(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = BuildReadinessJob(job_type="index_website", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_job, run_index_website, str(job.id))
    return {"job_id": str(job.id)}


@app.post("/index/videos")
def index_videos(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = BuildReadinessJob(job_type="index_videos", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_job, run_index_videos, str(job.id))
    return {"job_id": str(job.id)}


@app.post("/analyze")
def analyze(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = BuildReadinessJob(job_type="analyze", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_job, run_analyze, str(job.id))
    return {"job_id": str(job.id)}


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(BuildReadinessJob).filter(BuildReadinessJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "error": job.error,
        "progress": job.progress,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.get("/capabilities")
def list_capabilities(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    caps = (
        db.query(BuildReadinessCapability)
        .filter(BuildReadinessCapability.profile_id == profile.id)
        .order_by(BuildReadinessCapability.depth_score.desc())
        .limit(50)
        .all()
    )
    by_category: dict[str, list] = {}
    for c in caps:
        by_category.setdefault(c.category, []).append({
            "name": c.name,
            "evidence_count": c.evidence_count,
            "depth_score": float(c.depth_score or 0),
            "sample_urls": list(c.sample_urls or [])[:2],
        })
    return {"categories": by_category, "total": len(caps)}


@app.get("/verdicts/latest")
def latest_verdicts(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    rows = (
        db.query(BuildReadinessVerdict)
        .filter(BuildReadinessVerdict.profile_id == profile.id)
        .order_by(BuildReadinessVerdict.opportunity_score.desc())
        .all()
    )
    if not rows:
        return {"verdicts": [], "analyzed_at": None}

    return {
        "company": profile.company_name,
        "website_url": profile.website_url,
        "analyzed_at": rows[0].analyzed_at.isoformat() if rows[0].analyzed_at else None,
        "verdicts": [
            {
                "domain_name": v.domain_name,
                "track": v.track,
                "verdict": v.verdict,
                "market_score": float(v.market_score),
                "capability_score": float(v.capability_score),
                "opportunity_score": float(v.opportunity_score),
                "verdict_detail": v.verdict_json,
                "citations": v.citations,
            }
            for v in rows
        ],
    }
