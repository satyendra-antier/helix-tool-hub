from datetime import datetime
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import (
    BuildReadinessProfile,
    BuildReadinessCapability,
    BuildReadinessVerdict,
    BuildReadinessJob,
    BuildReadinessChunk,
    BuildReadinessIndexRun,
    BuildReadinessAnalysisRun,
    get_db,
    run_migrations,
)
from pipeline import (
    get_or_create_profile,
    run_index_website,
    run_index_videos,
    run_analyze,
)
from domain_seed import ensure_market_domains, missing_verdict_domains
from market_bridge import fetch_latest_market_scores, get_market_meta
from pipeline_status import get_pipeline_status, get_latest_batch_id, resolve_verdict_batch_id
from config import settings
from verdict import ensure_strengthen_suggestions

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


def _run_index_website_job(job_id: str, full: bool = False):
    from database import SessionLocal
    session = SessionLocal()
    try:
        run_index_website(job_id, session, full=full)
    finally:
        session.close()


@app.on_event("startup")
def startup():
    run_migrations()
    from database import SessionLocal, BuildReadinessJob
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=45)
        stale = db.query(BuildReadinessJob).filter(
            BuildReadinessJob.status.in_(["queued", "analyzing", "crawling", "fetching", "embedding"]),
            BuildReadinessJob.created_at < cutoff,
        ).all()
        for job in stale:
            job.status = "failed"
            job.error = "Job timed out — please re-run (partial verdicts are preserved)"
            job.completed_at = datetime.utcnow()
        if stale:
            db.commit()
    finally:
        db.close()
    db = next(get_db())
    try:
        get_or_create_profile(db)
        ensure_market_domains(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def get_config():
    key = settings.resolve_api_key()
    return {
        "openai_configured": bool(key),
        "chat_model": settings.resolve_chat_model(),
        "embedding_model": settings.embedding_model,
        "max_crawl_pages": settings.max_crawl_pages,
        "indexing": "incremental by default — only new/changed pages are re-embedded",
    }


@app.get("/pipeline/status")
def pipeline_status(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    return get_pipeline_status(db, profile)


@app.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    chunk_count = db.query(BuildReadinessChunk).filter(
        BuildReadinessChunk.profile_id == profile.id
    ).count()
    cap_count = db.query(BuildReadinessCapability).filter(
        BuildReadinessCapability.profile_id == profile.id
    ).count()
    return {
        "id": str(profile.id),
        "company_name": profile.company_name,
        "website_url": profile.website_url,
        "last_indexed_at": profile.last_indexed_at.isoformat() if profile.last_indexed_at else None,
        "pages_indexed": profile.pages_indexed,
        "chunks_indexed": chunk_count,
        "capabilities_count": cap_count,
        "videos_indexed": profile.videos_indexed,
        "storage": "persistent — re-index replaces chunks; analysis runs are versioned",
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
def index_website(
    background_tasks: BackgroundTasks,
    full: bool = False,
    db: Session = Depends(get_db),
):
    if not settings.resolve_api_key():
        raise HTTPException(
            400,
            "BUILD_READINESS_OPENAI_API_KEY or OPENAI_API_KEY required — add to tool-hub/.env and restart",
        )
    job = BuildReadinessJob(
        job_type="index_website",
        status="queued",
        progress={"full": full, "mode": "full" if full else "incremental"},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_index_website_job, str(job.id), full)
    return {"job_id": str(job.id), "mode": "full" if full else "incremental"}


@app.post("/index/videos")
def index_videos(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not settings.resolve_api_key():
        raise HTTPException(
            400,
            "BUILD_READINESS_OPENAI_API_KEY or OPENAI_API_KEY required — add to tool-hub/.env and restart",
        )
    job = BuildReadinessJob(job_type="index_videos", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_job, run_index_videos, str(job.id))
    return {"job_id": str(job.id)}


@app.post("/analyze")
def analyze(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not settings.resolve_api_key():
        raise HTTPException(
            400,
            "BUILD_READINESS_OPENAI_API_KEY or OPENAI_API_KEY required — add to tool-hub/.env and restart",
        )
    profile = get_or_create_profile(db)
    ensure_market_domains(db)
    missing = missing_verdict_domains(db, profile.id)

    running = (
        db.query(BuildReadinessJob)
        .filter(
            BuildReadinessJob.job_type == "analyze",
            BuildReadinessJob.status.in_(["queued", "analyzing"]),
        )
        .order_by(desc(BuildReadinessJob.created_at))
        .first()
    )
    if running:
        return {
            "job_id": str(running.id),
            "missing_domains": missing,
            "already_running": True,
        }

    status = get_pipeline_status(db, profile)
    if not status["can_analyze"]:
        raise HTTPException(
            400,
            "Pipeline incomplete — refresh Market Depth and Index Website first",
        )
    job = BuildReadinessJob(job_type="analyze", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_job, run_analyze, str(job.id))
    return {"job_id": str(job.id), "missing_domains": missing}


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


@app.get("/history/index-runs")
def index_history(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    runs = (
        db.query(BuildReadinessIndexRun)
        .filter(BuildReadinessIndexRun.profile_id == profile.id)
        .order_by(desc(BuildReadinessIndexRun.indexed_at))
        .limit(20)
        .all()
    )
    return {
        "runs": [
            {
                "id": str(r.id),
                "source_type": r.source_type,
                "pages_indexed": r.pages_indexed,
                "chunks_indexed": r.chunks_indexed,
                "capabilities_found": r.capabilities_found,
                "indexed_at": r.indexed_at.isoformat() if r.indexed_at else None,
            }
            for r in runs
        ],
    }


@app.get("/history/analysis-runs")
def analysis_history(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    runs = (
        db.query(BuildReadinessAnalysisRun)
        .filter(BuildReadinessAnalysisRun.profile_id == profile.id)
        .order_by(desc(BuildReadinessAnalysisRun.analyzed_at))
        .limit(20)
        .all()
    )
    return {
        "runs": [
            {
                "id": str(r.id),
                "domains_analyzed": r.domains_analyzed,
                "go_count": r.go_count,
                "market_fetched_at": r.market_fetched_at.isoformat() if r.market_fetched_at else None,
                "company_indexed_at": r.company_indexed_at.isoformat() if r.company_indexed_at else None,
                "analyzed_at": r.analyzed_at.isoformat() if r.analyzed_at else None,
            }
            for r in runs
        ],
    }


@app.get("/capabilities")
def list_capabilities(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    caps = (
        db.query(BuildReadinessCapability)
        .filter(BuildReadinessCapability.profile_id == profile.id)
        .order_by(desc(BuildReadinessCapability.depth_score))
        .limit(80)
        .all()
    )
    by_category: dict[str, list] = {}
    for c in caps:
        by_category.setdefault(c.category, []).append({
            "name": c.name,
            "evidence_count": c.evidence_count,
            "depth_score": float(c.depth_score or 0),
            "sample_urls": list(c.sample_urls or [])[:2],
            "extracted_at": c.extracted_at.isoformat() if c.extracted_at else None,
        })
    return {
        "categories": by_category,
        "total": len(caps),
        "indexed_at": profile.last_indexed_at.isoformat() if profile.last_indexed_at else None,
    }


@app.get("/domains/status")
def domains_status(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    ensure_market_domains(db)
    market = fetch_latest_market_scores(db)
    missing = missing_verdict_domains(db, profile.id)
    return {
        "active_domains": len(market),
        "verdicts_in_latest_batch": len(market) - len(missing),
        "missing_verdicts": missing,
    }


def _serialize_verdict(v: BuildReadinessVerdict) -> dict:
    return {
        "domain_name": v.domain_name,
        "track": v.track,
        "verdict": v.verdict,
        "status": "done",
        "market_score": float(v.market_score),
        "capability_score": float(v.capability_score),
        "opportunity_score": float(v.opportunity_score),
        "verdict_detail": ensure_strengthen_suggestions(
            {**(v.verdict_json or {}), "verdict": v.verdict},
            v.domain_name,
        ),
        "citations": v.citations,
        "market_fetched_at": v.market_fetched_at.isoformat() if v.market_fetched_at else None,
        "company_indexed_at": v.company_indexed_at.isoformat() if v.company_indexed_at else None,
        "analyzed_at": v.analyzed_at.isoformat() if v.analyzed_at else None,
    }


def _active_analyze_batch_id(db: Session) -> str | None:
    job = (
        db.query(BuildReadinessJob)
        .filter(
            BuildReadinessJob.job_type == "analyze",
            BuildReadinessJob.status.in_(["queued", "analyzing"]),
        )
        .order_by(desc(BuildReadinessJob.created_at))
        .first()
    )
    if job and job.progress and job.progress.get("batch_id"):
        return str(job.progress["batch_id"])
    return None


@app.get("/verdicts/latest")
def latest_verdicts(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    ensure_market_domains(db)
    market = fetch_latest_market_scores(db)

    batch_id = resolve_verdict_batch_id(db, profile.id, len(market))

    verdict_map: dict[str, BuildReadinessVerdict] = {}
    analysis_run = None
    if batch_id:
        rows = (
            db.query(BuildReadinessVerdict)
            .filter(
                BuildReadinessVerdict.profile_id == profile.id,
                BuildReadinessVerdict.analysis_batch_id == batch_id,
            )
            .all()
        )
        verdict_map = {v.domain_name: v for v in rows}
        analysis_run = db.query(BuildReadinessAnalysisRun).filter(
            BuildReadinessAnalysisRun.id == batch_id
        ).first()

    active_job = (
        db.query(BuildReadinessJob)
        .filter(
            BuildReadinessJob.job_type == "analyze",
            BuildReadinessJob.status.in_(["queued", "analyzing"]),
        )
        .order_by(desc(BuildReadinessJob.created_at))
        .first()
    )
    progress = (active_job.progress if active_job else None) or {}

    merged: list[dict] = []
    for domain_name in sorted(market.keys()):
        if domain_name in verdict_map:
            merged.append(_serialize_verdict(verdict_map[domain_name]))
        else:
            m = market[domain_name]
            is_current = progress.get("current_domain") == domain_name
            merged.append({
                "domain_name": domain_name,
                "track": m.get("track", ""),
                "verdict": "PENDING",
                "status": "processing" if is_current else "pending",
                "market_score": float(m.get("market_score", 0)),
                "capability_score": 0,
                "opportunity_score": 0,
                "verdict_detail": {
                    "headline": (
                        f"Analyzing {domain_name}…"
                        if is_current
                        else "Awaiting Fit Analysis — click Run Fit Analysis"
                    ),
                },
                "citations": [],
            })

    merged.sort(key=lambda x: (-x.get("opportunity_score", 0), x["domain_name"]))

    return {
        "company": profile.company_name,
        "website_url": profile.website_url,
        "batch_id": batch_id,
        "analyzed_at": analysis_run.analyzed_at.isoformat() if analysis_run and analysis_run.analyzed_at else None,
        "market_fetched_at": analysis_run.market_fetched_at.isoformat() if analysis_run and analysis_run.market_fetched_at else None,
        "company_indexed_at": analysis_run.company_indexed_at.isoformat() if analysis_run and analysis_run.company_indexed_at else None,
        "go_count": analysis_run.go_count if analysis_run else sum(1 for v in merged if v.get("verdict") == "GO"),
        "verdicts": merged,
        "total_domains": len(market),
        "analyze_in_progress": active_job is not None,
        "analyze_progress": progress if active_job else None,
    }
