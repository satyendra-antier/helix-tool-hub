"""Match external lead signals to Market Depth domains + Build Readiness verdicts."""

from __future__ import annotations

import re

DOMAIN_SYNONYMS: dict[str, list[str]] = {
    "Stablecoin & Payments Engineering": [
        "stablecoin", "usdc", "usdt", "dai", "payment rail", "remittance",
        "cross-border", "fiat-backed", "cbdc", "circle", "tether",
    ],
    "RWA / Tokenization Engineering": [
        "rwa", "tokenization", "real world asset", "asset tokenization",
        "security token", "sto", "fractional ownership",
    ],
    "DeFi Protocol Engineering": ["defi", "dex", "amm", "lending", "liquidity", "yield"],
    "Smart Contract Engineering": ["solidity", "smart contract", "ethereum", "evm", "dapp"],
    "L2 / Infra Engineering": ["layer 2", "l2", "rollup", "zk", "blockchain infrastructure"],
    "Blockchain Security / Auditing": ["audit", "security", "exploit", "formal verification"],
    "Web3 Growth/Tokenomics": ["tokenomics", "web3 growth", "crypto marketing", "token launch"],
    "AI Agent Orchestration": ["ai agent", "agent orchestration", "multi-agent", "autonomous agent"],
    "LLM Application Engineering": ["llm", "langchain", "rag", "chatbot", "copilot"],
    "Applied ML / Data Engineering": ["machine learning", "data engineering", "mlops"],
    "LLMOps / Inference Infra": ["llmops", "inference", "model serving"],
    "AI Security / Red-teaming": ["ai security", "prompt injection", "red team", "llm red team"],
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _term_in_blob(term: str, blob: str) -> bool:
    t = _norm(term)
    if not t:
        return False
    if t in blob:
        return True
    # Short tokens need word boundaries (usdc, defi, dai)
    if len(t) <= 5:
        return bool(re.search(rf"\b{re.escape(t)}\b", blob)) or t in blob
    return False


def match_domains(
    description: str,
    market_domains: dict[str, dict],
    verdicts: dict[str, dict],
    *,
    name: str = "",
    capability_by_domain: dict[str, list[str]] | None = None,
    target_domain: str | None = None,
) -> list[dict]:
    blob = _norm(f"{name} {description}")
    if not blob and not target_domain:
        return []

    if target_domain and target_domain in market_domains:
        m = market_domains[target_domain]
        v = verdicts.get(target_domain, {})
        return [{
            "domain_name": target_domain,
            "track": m.get("track"),
            "market_score": float(m.get("market_score") or 0),
            "verdict": v.get("verdict"),
            "capability_score": float(v.get("capability_score") or 0),
            "opportunity_score": float(v.get("opportunity_score") or m.get("market_score") or 0),
            "matched_terms": ["market_depth_source"],
            "our_strengths": v.get("our_strengths") or [],
            "gaps": v.get("gaps") or [],
            "strengthen_suggestions": v.get("strengthen_suggestions") or [],
        }]

    matches: list[dict] = []
    cap_map = capability_by_domain or {}

    for name_key, m in market_domains.items():
        terms = [_norm(k) for k in (m.get("keywords") or [])]
        terms.extend(_norm(s) for s in DOMAIN_SYNONYMS.get(name_key, []))
        terms.extend(_norm(c) for c in cap_map.get(name_key, []))

        pl = m.get("product_landscape") or {}
        for pt in pl.get("product_types_in_demand") or []:
            if isinstance(pt, dict):
                if pt.get("product_type"):
                    terms.append(_norm(pt["product_type"]))
                terms.extend(_norm(k) for k in (pt.get("matched_keywords") or []))

        hit_terms = list(dict.fromkeys(
            t for t in terms if t and _term_in_blob(t, blob)
        ))
        if not hit_terms:
            continue

        v = verdicts.get(name_key, {})
        matches.append({
            "domain_name": name_key,
            "track": m.get("track"),
            "market_score": float(m.get("market_score") or 0),
            "verdict": v.get("verdict"),
            "capability_score": float(v.get("capability_score") or 0),
            "opportunity_score": float(v.get("opportunity_score") or m.get("market_score") or 0),
            "matched_terms": hit_terms[:6],
            "our_strengths": v.get("our_strengths") or [],
            "gaps": v.get("gaps") or [],
            "strengthen_suggestions": v.get("strengthen_suggestions") or [],
        })

    matches.sort(key=lambda x: (len(x["matched_terms"]), x["opportunity_score"]), reverse=True)
    return matches


def classify_orientation(matches: list[dict], market_domains: dict) -> tuple[str, dict | None]:
    """
    demand — market demand + proven depth (GO / strong CONDITIONAL)
    future — market heating up but capability gap (NO_GO / weak depth / no verdict)
    generic — no domain match or weak market signal
    """
    if not matches:
        return "generic", None

    best = matches[0]
    verdict = best.get("verdict")
    cap = float(best.get("capability_score") or 0)
    mkt = float(best.get("market_score") or 0)

    if verdict == "GO":
        return "demand", best
    if verdict == "CONDITIONAL" and cap >= 35:
        return "demand", best
    if mkt >= 30 and (verdict == "NO_GO" or cap < 35 or not verdict):
        return "future", best
    if mkt >= 40:
        return "future", best
    return "generic", best
