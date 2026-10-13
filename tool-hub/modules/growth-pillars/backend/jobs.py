"""Background job runner shared by all pillars."""

from __future__ import annotations

import threading
import traceback
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from database import PillarJob, SessionLocal


def create_job(db: Session, job_type: str) -> PillarJob:
    job = PillarJob(job_type=job_type, status="queued", progress={}, result={})
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_job_in_thread(job_id, fn: Callable[[Session, Callable[[dict], None]], dict]) -> None:
    """Run fn(db, report_progress) in a daemon thread and persist the outcome on the job row."""

    def target():
        db = SessionLocal()
        try:
            job = db.get(PillarJob, job_id)
            job.status = "running"
            db.commit()

            def report(progress: dict) -> None:
                job.progress = {**(job.progress or {}), **progress}
                db.commit()

            result = fn(db, report)
            job.status = "done"
            job.result = result or {}
            job.completed_at = datetime.utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job = db.get(PillarJob, job_id)
            if job:
                job.status = "failed"
                job.error = f"{exc}\n{traceback.format_exc(limit=3)}"[:4000]
                job.completed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()

    threading.Thread(target=target, daemon=True).start()


def job_to_dict(job: PillarJob) -> dict:
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress or {},
        "result": job.result or {},
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
