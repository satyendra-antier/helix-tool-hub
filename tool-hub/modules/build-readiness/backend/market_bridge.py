"""Bridge to Market Depth Analyzer data (shared Postgres)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def fetch_market_domains(db: Session) -> list[dict]:
    rows = db.execute(text("""
        SELECT id::text, name, track, keywords
        FROM market_depth_domains
        WHERE active = true
        ORDER BY name
    """)).mappings().all()
    return [dict(r) for r in rows]


def fetch_latest_market_scores(db: Session) -> dict[str, dict]:
    """Latest snapshot per domain with product landscape."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (d.id)
            d.id::text AS domain_id,
            d.name,
            d.track,
            d.keywords,
            s.composite_score,
            s.component_scores,
            s.raw_evidence,
            s.product_landscape,
            s.fetched_at
        FROM market_depth_domains d
        JOIN market_depth_snapshots s ON s.domain_id = d.id
        WHERE d.active = true
        ORDER BY d.id, s.fetched_at DESC
    """)).mappings().all()

    result: dict[str, dict] = {}
    for r in rows:
        result[r["name"]] = {
            "domain_id": r["domain_id"],
            "domain_name": r["name"],
            "track": r["track"],
            "keywords": list(r["keywords"] or []),
            "market_score": float(r["composite_score"] or 0),
            "components": r["component_scores"] or {},
            "raw_evidence": r["raw_evidence"] or {},
            "product_landscape": r["product_landscape"] or {},
            "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
        }
    return result
