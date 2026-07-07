"""Keep Market Depth domains in sync with Build Readiness / Lead Intelligence."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# Must stay aligned with market-depth-analyzer/backend/pipeline.py SEED_DOMAINS
MARKET_DOMAINS = [
    {"name": "Smart Contract Engineering", "track": "blockchain", "keywords": ["solidity", "smart contract", "ethereum"]},
    {"name": "DeFi Protocol Engineering", "track": "blockchain", "keywords": ["defi", "amm", "liquidity protocol"]},
    {"name": "Stablecoin & Payments Engineering", "track": "blockchain", "keywords": ["stablecoin", "usdc", "usdt", "payment rail", "fiat-backed token"]},
    {"name": "RWA / Tokenization Engineering", "track": "blockchain", "keywords": ["rwa", "tokenization", "real world asset", "asset tokenization", "security token"]},
    {"name": "Blockchain Security / Auditing", "track": "blockchain", "keywords": ["blockchain audit", "smart contract security"]},
    {"name": "L2 / Infra Engineering", "track": "blockchain", "keywords": ["layer 2", "rollup", "blockchain infrastructure"]},
    {"name": "Web3 Growth/Tokenomics", "track": "blockchain", "keywords": ["tokenomics", "web3 growth", "crypto marketing"]},
    {"name": "LLM Application Engineering", "track": "ai", "keywords": ["llm", "langchain", "rag application"]},
    {"name": "AI Agent Orchestration", "track": "ai", "keywords": ["ai agent", "agent orchestration", "autonomous agent"]},
    {"name": "LLMOps / Inference Infra", "track": "ai", "keywords": ["llmops", "inference", "model serving"]},
    {"name": "AI Security / Red-teaming", "track": "ai", "keywords": ["ai security", "llm red team", "prompt injection"]},
    {"name": "Applied ML / Data Engineering", "track": "ai", "keywords": ["machine learning", "data engineering", "mlops"]},
]


def ensure_market_domains(db: Session) -> int:
    """Insert any missing active domains into market_depth_domains."""
    existing = {
        r[0]
        for r in db.execute(text("SELECT name FROM market_depth_domains")).fetchall()
    }
    added = 0
    for d in MARKET_DOMAINS:
        if d["name"] in existing:
            continue
        db.execute(
            text("""
                INSERT INTO market_depth_domains (name, track, keywords, active)
                VALUES (:name, :track, :keywords, true)
            """),
            {"name": d["name"], "track": d["track"], "keywords": d["keywords"]},
        )
        added += 1
    if added:
        db.commit()
    return added


def missing_verdict_domains(db: Session, profile_id) -> list[str]:
    """Domains with market snapshots but no verdict in latest (or in-flight) analysis batch."""
    from pipeline_status import resolve_verdict_batch_id
    from market_bridge import fetch_latest_market_scores

    market = fetch_latest_market_scores(db)
    batch = resolve_verdict_batch_id(db, profile_id, len(market))

    verdict_names: set[str] = set()
    if batch:
        rows = db.execute(text("""
            SELECT domain_name FROM build_readiness_verdicts
            WHERE profile_id = :pid AND analysis_batch_id = :batch
        """), {"pid": str(profile_id), "batch": batch}).fetchall()
        verdict_names = {r[0] for r in rows}

    return sorted(name for name in market.keys() if name not in verdict_names)
