from datetime import datetime
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from database import VideoScraperItem, VideoScraperJob, get_db, run_migrations
from pipeline import run_pipeline
from config import settings

app = FastAPI(title="Video Scraper API", version="1.1.0")

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


def item_to_dict(item: VideoScraperItem) -> dict:
    return {
        "id": str(item.id),
        "video_url": item.video_url,
        "sort_order": item.sort_order,
        "status": item.status,
        "error": item.error,
        "title": item.title,
        "channel_or_author": item.channel_or_author,
        "duration_seconds": item.duration_seconds,
        "thumbnail_url": item.thumbnail_url,
        "transcript": item.transcript,
        "transcript_source": item.transcript_source,
        "summary_json": item.summary_json,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def job_to_dict(job: VideoScraperJob, include_items: bool = True) -> dict:
    progress = job.progress_json or {}
    data = {
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
        "is_batch": bool(job.is_batch),
        "progress": progress,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
    if include_items and job.is_batch:
        items = sorted(job.items or [], key=lambda i: i.sort_order)
        data["items"] = [item_to_dict(i) for i in items]
        data["items_count"] = len(items)
    return data


@app.on_event("startup")
def startup():
    run_migrations()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def config_status():
    return {
        "openai_configured": bool(settings.resolve_api_key()),
        "using_dedicated_openai_key": settings.using_dedicated_key(),
        "transcription_provider": settings.transcription_provider,
        "transcription_model": settings.transcription_model,
        "local_whisper_model": settings.local_whisper_model,
        "chat_model": settings.resolve_chat_model(),
        "max_videos_per_page": settings.max_videos_per_page,
        "note": (
            "Transcription uses local faster-whisper; OpenAI (gpt-5-mini) is only used for summarization."
            if settings.transcription_provider == "local"
            else "Transcription uses OpenAI Audio API"
        ),
    }


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
    job = (
        db.query(VideoScraperJob)
        .options(joinedload(VideoScraperJob.items))
        .filter(VideoScraperJob.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(404, "Job not found")
    return job_to_dict(job)


@app.get("/jobs/{job_id}/items")
def get_job_items(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(VideoScraperJob).filter(VideoScraperJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    items = (
        db.query(VideoScraperItem)
        .filter(VideoScraperItem.job_id == job.id)
        .order_by(VideoScraperItem.sort_order)
        .all()
    )
    return {"items": [item_to_dict(i) for i in items], "progress": job.progress_json or {}}


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
        "jobs": [job_to_dict(j, include_items=False) for j in jobs],
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
