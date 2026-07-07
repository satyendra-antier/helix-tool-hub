"""Deterministic capability extraction from indexed content."""

from __future__ import annotations

import re
from collections import defaultdict

CAPABILITY_TAXONOMY: dict[str, list[str]] = {
    "blockchain_core": [
        "solidity", "smart contract", "ethereum", "evm", "web3", "dapp", "defi",
        "layer 2", "rollup", "zk", "substrate", "polkadot", "cosmos", "avalanche",
        "hyperledger", "tokenomics", "nft", "dao", "dex", "amm", "lending",
    ],
    "blockchain_security": [
        "audit", "security", "formal verification", "penetration", "exploit",
        "smart contract audit", "red team",
    ],
    "ai_ml": [
        "llm", "langchain", "rag", "generative ai", "machine learning", "mlops",
        "inference", "model serving", "chatbot", "agent", "copilot", "embedding",
        "predictive analytics", "data engineering", "fine-tuning",
    ],
    "ai_governance": [
        "ai governance", "guardrail", "prompt injection", "ai security", "compliance",
    ],
    "gaming_metaverse": [
        "game development", "metaverse", "p2e", "play to earn", "roblox", "unity",
        "web3 game", "nft gaming",
    ],
    "enterprise": [
        "enterprise", "supply chain", "healthcare", "fintech", "consulting",
        "offshore", "white label", "saas",
    ],
    "infrastructure": [
        "wallet", "exchange", "custody", "rpc", "node", "indexer", "oracle",
        "bridge", "payment", "staking",
    ],
    "stablecoins_payments": [
        "stablecoin", "usdc", "usdt", "dai", "payment rail", "remittance",
        "fiat-backed", "cbdc", "mint", "redeem", "reserve attestation",
        "cross-border payment", "merchant payment", "payroll", "treasury",
    ],
    "rwa_tokenization": [
        "rwa", "real world asset", "tokenization", "asset tokenization",
        "security token", "sto", "fractional ownership", "tokenized asset",
        "real estate token", "treasury tokenization",
    ],
}


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip())


def extract_capabilities(pages: list[dict]) -> list[dict]:
    """Count taxonomy hits across all page text; return ranked capabilities."""
    counts: dict[tuple[str, str], dict] = {}

    for page in pages:
        blob = _normalize(f"{page.get('title', '')} {page.get('text', '')}")
        url = page.get("url", "")
        for category, keywords in CAPABILITY_TAXONOMY.items():
            for kw in keywords:
                if kw in blob:
                    key = (category, kw)
                    if key not in counts:
                        counts[key] = {"category": category, "name": kw, "evidence_count": 0, "sample_urls": []}
                    counts[key]["evidence_count"] += blob.count(kw)
                    if url and url not in counts[key]["sample_urls"]:
                        counts[key]["sample_urls"].append(url)

    results = []
    for item in counts.values():
        depth = min(100.0, item["evidence_count"] * 8 + len(item["sample_urls"]) * 5)
        results.append({
            "category": item["category"],
            "name": item["name"],
            "evidence_count": item["evidence_count"],
            "sample_urls": item["sample_urls"][:5],
            "depth_score": round(depth, 2),
        })

    results.sort(key=lambda x: (-x["depth_score"], -x["evidence_count"]))
    return results[:80]


def capability_match_score(
    domain_keywords: list[str],
    product_types: list[str],
    capabilities: list[dict],
    retrieved_chunks: list[dict],
) -> tuple[float, list[str]]:
    """Algorithmic match: keyword overlap + capability depth + semantic retrieval."""
    query_terms = {_normalize(k) for k in domain_keywords}
    for pt in product_types:
        query_terms.add(_normalize(pt))

    cap_hits: list[str] = []
    keyword_score = 0.0
    for cap in capabilities:
        name = _normalize(cap["name"])
        if any(t in name or name in t for t in query_terms):
            keyword_score += float(cap["depth_score"]) * 0.15
            cap_hits.append(cap["name"])

    chunk_hits = 0
    for ch in retrieved_chunks:
        blob = _normalize(ch.get("content", ""))
        if any(t in blob for t in query_terms):
            chunk_hits += 1

    semantic_avg = (
        sum(ch.get("similarity", 0) for ch in retrieved_chunks) / len(retrieved_chunks)
        if retrieved_chunks else 0
    )

    score = min(100.0, keyword_score * 0.35 + semantic_avg * 100 * 0.45 + chunk_hits * 8 * 0.20)
    return round(score, 2), cap_hits[:12]
