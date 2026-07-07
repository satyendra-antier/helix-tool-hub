"""Pipeline status — links Market Depth + Company Depth readiness."""

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import (
    BuildReadinessProfile,
    BuildReadinessChunk,
    BuildReadinessCapability,
    BuildReadinessVerdict,
    BuildReadinessIndexRun,
    BuildReadinessAnalysisRun,
)
from market_bridge import get_market_meta
from domain_seed import missing_verdict_domains


def _naive_utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt


def get_pipeline_status(db: Session, profile: BuildReadinessProfile) -> dict:
    market = get_market_meta(db)
    chunk_count = db.query(BuildReadinessChunk).filter(
        BuildReadinessChunk.profile_id == profile.id
    ).count()
    cap_count = db.query(BuildReadinessCapability).filter(
        BuildReadinessCapability.profile_id == profile.id
    ).count()

    latest_index = (
        db.query(BuildReadinessIndexRun)
        .filter(BuildReadinessIndexRun.profile_id == profile.id)
        .order_by(desc(BuildReadinessIndexRun.indexed_at))
        .first()
    )
    latest_analysis = (
        db.query(BuildReadinessAnalysisRun)
        .filter(BuildReadinessAnalysisRun.profile_id == profile.id)
        .order_by(desc(BuildReadinessAnalysisRun.analyzed_at))
        .first()
    )

    market_ready = market.get("ready", False)
    company_ready = chunk_count > 0 and profile.last_indexed_at is not None
    analysis_ready = latest_analysis is not None
    missing_domains = missing_verdict_domains(db, profile.id)

    warnings: list[str] = []
    if missing_domains:
        warnings.append(
            f"Missing verdicts for {len(missing_domains)} domain(s): "
            + ", ".join(missing_domains[:4])
            + ("…" if len(missing_domains) > 4 else "")
        )
    if analysis_ready and latest_analysis and profile.last_indexed_at:
        if _naive_utc(profile.last_indexed_at) > _naive_utc(latest_analysis.analyzed_at):
            warnings.append("Company site re-indexed after last analysis — re-run Fit Analysis")
    if analysis_ready and market.get("latest_fetch") and latest_analysis:
        from datetime import datetime
        mf = datetime.fromisoformat(market["latest_fetch"].replace("Z", "+00:00")).replace(tzinfo=None)
        if mf > _naive_utc(latest_analysis.analyzed_at):
            warnings.append("Market data refreshed after last analysis — re-run Fit Analysis")
    stale_warning = " | ".join(warnings) if warnings else None

    return {
        "direction": "market_demand → company_depth → fit_verdict",
        "steps": [
            {
                "step": 1,
                "name": "Market Depth",
                "description": "Live demand signals — hiring, capital, funding, trends",
                "ready": market_ready,
                "latest_at": market.get("latest_fetch"),
                "stats": {
                    "domains": market.get("domain_count", 0),
                    "snapshots": market.get("snapshot_count", 0),
                },
                "action": "Refresh in Market Depth Analyzer",
                "tool_route": "/tools/market-depth-analyzer",
            },
            {
                "step": 2,
                "name": "Company Depth",
                "description": "RAG index of your website + video transcripts",
                "ready": company_ready,
                "latest_at": profile.last_indexed_at.isoformat() if profile.last_indexed_at else None,
                "stats": {
                    "pages": profile.pages_indexed,
                    "chunks": chunk_count,
                    "capabilities": cap_count,
                    "videos": profile.videos_indexed,
                },
                "action": (
                    f"Index Website for {profile.company_name}"
                    if not company_ready
                    else "Index Website (re-index anytime)"
                ),
            },
            {
                "step": 3,
                "name": "Fit Verdict",
                "description": "Cross-market demand vs your proven depth",
                "ready": analysis_ready,
                "latest_at": latest_analysis.analyzed_at.isoformat() if latest_analysis else None,
                "stats": {
                    "domains_analyzed": latest_analysis.domains_analyzed if latest_analysis else 0,
                    "go_count": latest_analysis.go_count if latest_analysis else 0,
                    "batch_id": str(latest_analysis.id) if latest_analysis else None,
                },
                "action": "Run Fit Analysis",
            },
        ],
        "can_analyze": market_ready and company_ready,
        "stale_warning": stale_warning,
        "missing_verdict_domains": missing_domains,
        "company": {
            "name": profile.company_name,
            "website_url": profile.website_url,
        },
    }


def get_latest_batch_id(db: Session, profile_id) -> str | None:
    """Prefer newest completed analysis run; fall back to newest verdict batch."""
    from sqlalchemy import func

    run = (
        db.query(BuildReadinessAnalysisRun)
        .filter(BuildReadinessAnalysisRun.profile_id == profile_id)
        .order_by(desc(BuildReadinessAnalysisRun.analyzed_at))
        .first()
    )
    if run:
        return str(run.id)

    row = (
        db.query(BuildReadinessVerdict.analysis_batch_id)
        .filter(BuildReadinessVerdict.profile_id == profile_id)
        .order_by(desc(BuildReadinessVerdict.analyzed_at))
        .first()
    )
    return str(row.analysis_batch_id) if row else None


def find_incomplete_batch_id(db: Session, profile_id, domain_count: int):
    """Newest verdict batch that still has fewer than all active market domains."""
    from sqlalchemy import func

    if domain_count <= 0:
        return None
    row = (
        db.query(
            BuildReadinessVerdict.analysis_batch_id,
            func.max(BuildReadinessVerdict.analyzed_at).label("last_at"),
            func.count().label("cnt"),
        )
        .filter(BuildReadinessVerdict.profile_id == profile_id)
        .group_by(BuildReadinessVerdict.analysis_batch_id)
        .order_by(desc("last_at"))
        .first()
    )
    if row and row.cnt < domain_count:
        return row.analysis_batch_id
    return None


def resolve_verdict_batch_id(db: Session, profile_id, domain_count: int) -> str | None:
    """Prefer in-flight analyze batch, then newest incomplete batch, then last completed run."""
    from database import BuildReadinessJob

    active_job = (
        db.query(BuildReadinessJob)
        .filter(
            BuildReadinessJob.job_type == "analyze",
            BuildReadinessJob.status.in_(["queued", "analyzing"]),
        )
        .order_by(desc(BuildReadinessJob.created_at))
        .first()
    )
    if active_job and active_job.progress and active_job.progress.get("batch_id"):
        return str(active_job.progress["batch_id"])

    incomplete = find_incomplete_batch_id(db, profile_id, domain_count)
    if incomplete:
        return str(incomplete)

    return get_latest_batch_id(db, profile_id)
