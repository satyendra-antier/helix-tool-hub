import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from database import (
    MarketDepthDomain,
    MarketDepthSnapshot,
    MarketDepthReport,
    MarketDepthJob,
    MarketDepthWeights,
)
from sources import fetch_all_signals
from scoring.engine import DEFAULT_WEIGHTS, score_all_domains
from narrative import generate_narrative
from intelligence.product_landscape import build_product_landscape

SEED_DOMAINS = [
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


def seed_domains(db: Session) -> None:
    existing_names = {d.name for d in db.query(MarketDepthDomain).all()}
    for d in SEED_DOMAINS:
        if d["name"] not in existing_names:
            db.add(MarketDepthDomain(
                name=d["name"],
                track=d["track"],
                keywords=d["keywords"],
                active=True,
            ))
    if db.query(MarketDepthWeights).count() == 0:
        db.add(MarketDepthWeights(weights=DEFAULT_WEIGHTS))
    db.commit()


def get_weights(db: Session) -> dict:
    row = db.query(MarketDepthWeights).order_by(MarketDepthWeights.updated_at.desc()).first()
    return row.weights if row else DEFAULT_WEIGHTS


def run_refresh(job_id: str, db: Session) -> None:
    job = db.query(MarketDepthJob).filter(MarketDepthJob.id == job_id).first()
    if not job:
        return

    try:
        seed_domains(db)
        job.status = "fetching"
        db.commit()

        domains = db.query(MarketDepthDomain).filter(MarketDepthDomain.active == True).all()
        weights = get_weights(db)
        batch_id = uuid.uuid4()

        all_raw = []
        landscapes: dict[str, dict] = {}
        for domain in domains:
            signals = fetch_all_signals(domain.keywords, domain.track)
            all_raw.append(({
                "id": str(domain.id),
                "name": domain.name,
                "track": domain.track,
                "keywords": domain.keywords,
            }, signals))
            landscapes[str(domain.id)] = build_product_landscape(
                domain.name, domain.track, list(domain.keywords), signals
            )

        job.status = "scoring"
        db.commit()

        scores = score_all_domains(
            [d for d, _ in all_raw],
            all_raw,
            weights,
        )

        for score in scores:
            snap = MarketDepthSnapshot(
                domain_id=score.domain_id,
                snapshot_batch_id=batch_id,
                raw_evidence={
                    k: {"value": v.value, "unit": v.unit, "available": v.available, "raw_data": v.raw_data, "note": v.note}
                    for k, v in score.raw_evidence.items()
                },
                component_scores=score.components,
                composite_score=score.composite_score,
                weights_used=weights,
                product_landscape=landscapes.get(str(score.domain_id)),
                fetched_at=datetime.utcnow(),
            )
            db.add(snap)

        job.status = "narrating"
        db.commit()

        narrative, passed, notes = generate_narrative(scores, landscapes)
        report = MarketDepthReport(
            snapshot_batch_id=batch_id,
            gemini_output=narrative,
            validation_passed=passed,
            validation_notes=notes,
        )
        db.add(report)

        job.snapshot_batch_id = batch_id
        job.status = "done"
        job.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()


def recompute_from_latest(db: Session, weights: dict) -> list:
    domains = db.query(MarketDepthDomain).filter(MarketDepthDomain.active == True).all()
    latest_by_domain = {}
    for domain in domains:
        snap = (
            db.query(MarketDepthSnapshot)
            .filter(MarketDepthSnapshot.domain_id == domain.id)
            .order_by(MarketDepthSnapshot.fetched_at.desc())
            .first()
        )
        if snap:
            latest_by_domain[str(domain.id)] = snap

    if not latest_by_domain:
        return []

    from sources.base import RawSignal

    all_raw = []
    for domain in domains:
        snap = latest_by_domain.get(str(domain.id))
        if not snap:
            continue
        signals = {}
        for k, v in snap.raw_evidence.items():
            signals[k] = RawSignal(
                source=k,
                value=v.get("value", 0),
                unit=v.get("unit", ""),
                raw_data=v.get("raw_data", {}),
                available=v.get("available", True),
                note=v.get("note"),
            )
        all_raw.append(({
            "id": str(domain.id),
            "name": domain.name,
            "track": domain.track,
        }, signals))

    return score_all_domains([d for d, _ in all_raw], all_raw, weights)
