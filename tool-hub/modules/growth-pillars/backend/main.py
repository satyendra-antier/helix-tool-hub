import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import PillarJob, SessionLocal, get_db, run_migrations
from hub_clients import module_health, trigger_lead_rescore
from jobs import create_job, job_to_dict, run_job_in_thread
from llm_client import llm_available
from pillars import advisory, dealroom, experts, insider, partners, visibility
from signals import build_signals

log = logging.getLogger("growth-pillars")


async def _insider_scheduler() -> None:
    interval = max(0.25, settings.insider_scan_interval_hours) * 3600
    while True:
        await asyncio.sleep(interval)
        db = SessionLocal()
        try:
            await asyncio.to_thread(insider.scan_watchlist, db)
            await asyncio.to_thread(dealroom.run_recipes, db)
        except Exception:  # noqa: BLE001
            log.exception("Scheduled insider scan failed")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    db = SessionLocal()
    try:
        dealroom.seed_recipes(db)
    finally:
        db.close()
    task = asyncio.create_task(_insider_scheduler())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Growth Pillars API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(experts.router)
app.include_router(insider.router)
app.include_router(partners.router)
app.include_router(visibility.router)
app.include_router(advisory.router)
app.include_router(dealroom.router)


class RunRequest(BaseModel):
    watchlist_size: int = 25
    min_lead_score: float = 40
    advisory_top_n: int = 10
    rescore_leads: bool = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def config_status():
    return {
        "openai_configured": llm_available(),
        "chat_model": settings.resolve_chat_model(),
        "perplexity_configured": bool(settings.perplexity_api_key),
        "adzuna_configured": bool(settings.adzuna_app_id and settings.adzuna_app_key),
        "company_name": settings.default_company_name,
        "insider_scan_interval_hours": settings.insider_scan_interval_hours,
    }


@app.get("/status")
def status(db: Session = Depends(get_db)):
    return {
        "upstream": module_health(),
        "llm_available": llm_available(),
        "counts": {
            "experts": experts.count_active(db),
            "intros_pending": experts.count_pending_intros(db),
            "watched_accounts": insider.count_watched(db),
            "unread_alerts": insider.count_unread(db),
            "partners": partners.count_partners(db),
            "visibility_queries": visibility.count_queries(db),
            "advice": advisory.count_advice(db),
            "handoffs": db.query(dealroom.DealDoc).filter(dealroom.DealDoc.kind == "handoff").count(),
            "recipes": db.query(dealroom.SignalRecipe).filter(dealroom.SignalRecipe.active.is_(True)).count(),
        },
        "visibility_share": visibility.latest_share(db),
    }


@app.get("/signals")
def signals(lead_ids: Optional[str] = None, db: Session = Depends(get_db)):
    """Per-lead relationship and momentum signals that Lead Intelligence folds into its score."""
    ids = [i.strip() for i in lead_ids.split(",") if i.strip()] if lead_ids else None
    return build_signals(db, ids)


@app.post("/run")
def run_all(body: RunRequest | None = None, db: Session = Depends(get_db)):
    """Pipeline step: refresh watchlist, scan, match experts, advise top leads, rescore."""
    body = body or RunRequest()
    job = create_job(db, "run_all")

    def work(session: Session, report) -> dict:
        result: dict = {}
        report({"step": "watchlist"})
        result["watchlist"] = insider.sync_watchlist(session, body.watchlist_size, body.min_lead_score)
        report({"step": "insider_scan"})
        result["insider"] = insider.scan_watchlist(session)
        report({"step": "expert_matching"})
        result["experts"] = experts.match_top_leads(session, body.watchlist_size, body.min_lead_score)
        report({"step": "sales_advisory"})
        result["advisory"] = advisory.advise_top_leads(session, body.advisory_top_n, body.min_lead_score)
        report({"step": "signal_recipes"})
        result["recipes"] = dealroom.run_recipes(session)
        if body.rescore_leads:
            report({"step": "lead_rescore"})
            result["rescore"] = trigger_lead_rescore()
        return result

    run_job_in_thread(job.id, work)
    return {"job_id": str(job.id)}


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.get(PillarJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job_to_dict(job)
