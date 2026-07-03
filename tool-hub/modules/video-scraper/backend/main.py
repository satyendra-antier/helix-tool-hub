from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from database import VideoScraperJob, get_db
from pipeline import run_pipeline

app = FastAPI(title="Video Scraper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateJobRequest(BaseModel):
    url: str


class JobResponse(BaseModel):
    job_id: str


def job_to_dict(job: VideoScraperJob) -> dict:
    return {
        "id": str(job.id),
        "source_url": job.source_url,
        "source_type": job.source_type,
        "status": job.status,
        "error": job.error,
        "title": job.title,
        "channel_or_author": job.channel_or_author,
        "duration_seconds": job.duration_seconds,
        "thumbnail_url": job.thumbnail_url,
        "transcript": job.transcript,
        "transcript_source": job.transcript_source,
        "summary_json": job.summary_json,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobResponse)
def create_job(
    body: CreateJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = VideoScraperJob(source_url=body.url, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    def task():
        from database import SessionLocal
        session = SessionLocal()
        try:
            run_pipeline(str(job.id), session)
        finally:
            session.close()

    background_tasks.add_task(task)
    return {"job_id": str(job.id)}


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(VideoScraperJob).filter(VideoScraperJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job_to_dict(job)


@app.get("/jobs")
def list_jobs(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    offset = (page - 1) * limit
    jobs = (
        db.query(VideoScraperJob)
        .order_by(VideoScraperJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(VideoScraperJob).count()
    return {
        "jobs": [job_to_dict(j) for j in jobs],
        "total": total,
        "page": page,
        "limit": limit,
    }


@app.delete("/jobs/{job_id}")
def delete_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(VideoScraperJob).filter(VideoScraperJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    db.delete(job)
    db.commit()
    return {"deleted": True}
