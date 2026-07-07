"""Bridge to Market Depth + Build Readiness (shared Postgres)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from track_utils import normalize_lead_track

# Capability categories → Market Depth domain names
CAPABILITY_DOMAIN_MAP: dict[str, str] = {
    "stablecoins_payments": "Stablecoin & Payments Engineering",
    "rwa_tokenization": "RWA / Tokenization Engineering",
    "blockchain_core": "Smart Contract Engineering",
    "blockchain_security": "Blockchain Security / Auditing",
    "ai_ml": "AI Agent Orchestration",
    "ai_governance": "AI Security / Red-teaming",
    "infrastructure": "L2 / Infra Engineering",
    "gaming_metaverse": "Web3 Growth/Tokenomics",
}


def fetch_market_scores(db: Session) -> dict[str, dict]:
    rows = db.execute(text("""
        SELECT DISTINCT ON (d.id)
            d.id::text AS domain_id,
            d.name,
            d.track,
            d.keywords,
            s.composite_score,
            s.product_landscape,
            s.fetched_at
        FROM market_depth_domains d
        JOIN market_depth_snapshots s ON s.domain_id = d.id
        WHERE d.active = true
        ORDER BY d.id, s.fetched_at DESC
    """)).mappings().all()
    return {
        r["name"]: {
            "domain_id": r["domain_id"],
            "domain_name": r["name"],
            "track": r["track"],
            "lead_track": normalize_lead_track(r["track"]),
            "keywords": list(r["keywords"] or []),
            "market_score": float(r["composite_score"] or 0),
            "product_landscape": r["product_landscape"] or {},
            "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
        }
        for r in rows
    }


def fetch_latest_verdicts(db: Session) -> dict[str, dict]:
    batch = db.execute(text("""
        SELECT id::text FROM build_readiness_analysis_runs
        ORDER BY analyzed_at DESC NULLS LAST
        LIMIT 1
    """)).scalar()
    if not batch:
        return {}

    rows = db.execute(text("""
        SELECT
            domain_name,
            verdict,
            market_score,
            capability_score,
            opportunity_score,
            verdict_json
        FROM build_readiness_verdicts
        WHERE analysis_batch_id = :batch
    """), {"batch": batch}).mappings().all()

    result: dict[str, dict] = {}
    for r in rows:
        vj = r["verdict_json"] or {}
        result[r["domain_name"]] = {
            "verdict": r["verdict"],
            "market_score": float(r["market_score"] or 0),
            "capability_score": float(r["capability_score"] or 0),
            "opportunity_score": float(r["opportunity_score"] or 0),
            "our_strengths": vj.get("our_strengths") or vj.get("matched_capabilities") or [],
            "gaps": vj.get("gaps") or [],
            "strengthen_suggestions": vj.get("strengthen_suggestions") or [],
            "headline": vj.get("headline"),
        }
    return result


def fetch_company_capabilities(db: Session, limit: int = 40) -> list[dict]:
    rows = db.execute(text("""
        SELECT category, name, depth_score, evidence_count
        FROM build_readiness_capabilities
        ORDER BY depth_score DESC NULLS LAST
        LIMIT :lim
    """), {"lim": limit}).mappings().all()
    return [dict(r) for r in rows]


def _collect_domain_terms(m: dict) -> list[str]:
    terms: list[str] = list(m.get("keywords") or [])
    pl = m.get("product_landscape") or {}
    for pt in pl.get("product_types_in_demand") or []:
        if isinstance(pt, dict):
            if pt.get("product_type"):
                terms.append(pt["product_type"])
            terms.extend(pt.get("matched_keywords") or [])
    return terms


def build_intelligence_context(db: Session) -> dict:
    market = fetch_market_scores(db)
    verdicts = fetch_latest_verdicts(db)
    capabilities = fetch_company_capabilities(db)

    demand_domains: list[dict] = []
    future_domains: list[dict] = []

    for name, m in market.items():
        v = verdicts.get(name, {})
        entry = {
            **m,
            "verdict": v.get("verdict"),
            "capability_score": v.get("capability_score", 0),
            "opportunity_score": v.get("opportunity_score", m["market_score"]),
            "our_strengths": v.get("our_strengths", []),
            "gaps": v.get("gaps", []),
            "strengthen_suggestions": v.get("strengthen_suggestions", []),
        }
        verdict = v.get("verdict")
        cap = float(v.get("capability_score") or 0)
        mkt = float(m.get("market_score") or 0)

        if verdict == "GO" or (verdict == "CONDITIONAL" and cap >= 35):
            demand_domains.append(entry)
        elif mkt >= 30 and (verdict == "NO_GO" or cap < 35 or not verdict):
            future_domains.append(entry)

    demand_domains.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)
    future_domains.sort(key=lambda x: x.get("market_score", 0), reverse=True)

    # Keywords from ALL active domains (not just top N)
    keywords: list[str] = []
    domain_keywords: dict[str, list[str]] = {}
    track_keywords: dict[str, list[str]] = {"web3": [], "ai": [], "government": [], "web2": []}

    for name, m in market.items():
        terms = _collect_domain_terms(m)
        domain_keywords[name] = terms
        keywords.extend(terms)
        lt = m.get("lead_track") or normalize_lead_track(m.get("track"))
        if lt in track_keywords:
            track_keywords[lt].extend(terms)

    # Capability terms mapped to domains
    cap_by_domain: dict[str, list[str]] = {}
    for cap in capabilities:
        cat = cap.get("category", "")
        domain_name = CAPABILITY_DOMAIN_MAP.get(cat)
        if domain_name:
            cap_by_domain.setdefault(domain_name, []).append(cap["name"])
            keywords.append(cap["name"])

    for name, extra in cap_by_domain.items():
        domain_keywords.setdefault(name, []).extend(extra)

    for lt in track_keywords:
        track_keywords[lt] = list(dict.fromkeys(kw.strip() for kw in track_keywords[lt] if kw and kw.strip()))

    sync_keywords = list(dict.fromkeys(kw.strip() for kw in keywords if kw and kw.strip()))

    return {
        "market_ready": len(market) > 0,
        "verdicts_ready": len(verdicts) > 0,
        "market_domains": market,
        "verdicts": verdicts,
        "capabilities": capabilities,
        "capability_by_domain": cap_by_domain,
        "domain_keywords": domain_keywords,
        "track_keywords": track_keywords,
        "demand_domains": demand_domains,
        "future_domains": future_domains,
        "sync_keywords": sync_keywords,
    }
