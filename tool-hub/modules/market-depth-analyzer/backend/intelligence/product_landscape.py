"""
Deterministic product intelligence — derived from raw signals, not LLM opinion.
"""

from __future__ import annotations

from typing import Any

# Product-type patterns detected in repo names, job titles, protocol categories
PRODUCT_PATTERNS: list[tuple[str, list[str]]] = [
    ("AI Agents & Copilots", ["agent", "copilot", "assistant", "autonomous"]),
    ("RAG / Knowledge Apps", ["rag", "retrieval", "knowledge base", "embedding"]),
    ("LLM APIs & Dev Tools", ["llm", "langchain", "inference", "model serving", "llmops"]),
    ("Smart Contract Platforms", ["solidity", "smart contract", "contract"]),
    ("DeFi Protocols (DEX/Lending)", ["defi", "amm", "swap", "lending", "liquidity"]),
    ("Stablecoins & Payment Rails", ["stablecoin", "usdc", "usdt", "payment", "remittance", "fiat-backed", "cbdc"]),
    ("RWA & Asset Tokenization", ["rwa", "tokenization", "real world asset", "security token", "asset-backed"]),
    ("Blockchain Security / Auditing", ["audit", "security", "exploit", "formal verification"]),
    ("L2 / Rollup Infrastructure", ["rollup", "layer 2", "l2", "zk", "optimistic"]),
    ("Tokenomics / Growth Tools", ["tokenomics", "airdrop", "growth", "marketing"]),
    ("MLOps / Data Pipelines", ["mlops", "pipeline", "feature store", "data engineering"]),
    ("AI Safety / Red-teaming", ["red team", "prompt injection", "guardrail", "ai security"]),
    ("Wallets & Custody", ["wallet", "custody", "signer"]),
    ("Analytics & Dashboards", ["analytics", "dashboard", "indexer", "explorer"]),
]

# Revenue models mapped from detected product types (algorithmic, not per-domain hardcoding)
PRODUCT_TYPE_REVENUE_MODELS: dict[str, list[dict[str, str]]] = {
    "AI Agents & Copilots": [
        {"model": "Agent runtime SaaS", "note": "Hosted agent execution and orchestration"},
        {"model": "Workflow automation", "note": "Per-task or per-workflow pricing"},
        {"model": "Marketplace take-rate", "note": "Commission on agent/tool marketplace"},
    ],
    "RAG / Knowledge Apps": [
        {"model": "SaaS subscription", "note": "Per-seat knowledge workspace pricing"},
        {"model": "Usage-based API", "note": "Per-query or per-document retrieval billing"},
        {"model": "Enterprise licenses", "note": "Private deployment with SLAs"},
    ],
    "LLM APIs & Dev Tools": [
        {"model": "Usage-based API", "note": "Per-token or per-request billing"},
        {"model": "Dev tooling SaaS", "note": "SDK, eval, and deployment subscriptions"},
        {"model": "Enterprise licenses", "note": "Annual contracts with support"},
    ],
    "Smart Contract Platforms": [
        {"model": "Protocol fees", "note": "On-chain revenue from deployed contracts"},
        {"model": "Dev tooling SaaS", "note": "IDE, deployment, and monitoring tools"},
        {"model": "Consulting / implementation", "note": "Custom contract development"},
    ],
    "DeFi Protocols (DEX/Lending)": [
        {"model": "Trading / swap fees", "note": "DEX and aggregator fee capture"},
        {"model": "Lending spread", "note": "Borrow/lend rate differential"},
        {"model": "Liquidity incentives", "note": "Token emissions to liquidity providers"},
    ],
    "Stablecoins & Payment Rails": [
        {"model": "Payment API fees", "note": "Per-transaction or volume-based B2B payment rails"},
        {"model": "Reserve yield / issuance spread", "note": "Treasury yield on fiat reserves backing stablecoins"},
        {"model": "Cross-border remittance fees", "note": "FX and settlement fees on international transfers"},
        {"model": "Compliance & attestation SaaS", "note": "Reserve proof, KYC/AML, and regulatory reporting tools"},
    ],
    "RWA & Asset Tokenization": [
        {"model": "Tokenization platform fees", "note": "Per-asset or AUM-based tokenization SaaS"},
        {"model": "Issuance & lifecycle management", "note": "Mint, transfer restriction, and redemption tooling"},
        {"model": "Compliance & investor onboarding", "note": "KYC/AML and accredited-investor workflows for RWAs"},
    ],
    "Blockchain Security / Auditing": [
        {"model": "Audit fees", "note": "Per-engagement security assessments"},
        {"model": "Continuous monitoring SaaS", "note": "On-chain alert subscriptions"},
        {"model": "Bug bounties / retainer", "note": "Ongoing security partnerships"},
    ],
    "L2 / Rollup Infrastructure": [
        {"model": "Sequencer / infra fees", "note": "Per-transaction rollup fees"},
        {"model": "RPC / node SaaS", "note": "Developer infrastructure subscriptions"},
        {"model": "Enterprise chain licenses", "note": "Private L2 deployments"},
    ],
    "Tokenomics / Growth Tools": [
        {"model": "Marketing retainers", "note": "Launch and community growth campaigns"},
        {"model": "Token advisory", "note": "Tokenomics design consulting"},
        {"model": "Performance-based grants", "note": "Success-fee on TVL or users"},
    ],
    "MLOps / Data Pipelines": [
        {"model": "Data platform SaaS", "note": "Warehouse, ETL, and feature stores"},
        {"model": "GPU cloud / inference API", "note": "Per-hour or per-token compute"},
        {"model": "Observability tools", "note": "Monitoring, eval, and tracing"},
    ],
    "AI Safety / Red-teaming": [
        {"model": "Red-team engagements", "note": "Per-assessment security audits"},
        {"model": "Guardrail SaaS", "note": "Real-time prompt filtering APIs"},
        {"model": "Compliance tooling", "note": "AI governance and policy platforms"},
    ],
    "Wallets & Custody": [
        {"model": "Transaction fees", "note": "Swap, bridge, or transfer fees"},
        {"model": "Custody SaaS", "note": "Institutional wallet subscriptions"},
        {"model": "Enterprise licenses", "note": "White-label wallet deployments"},
    ],
    "Analytics & Dashboards": [
        {"model": "SaaS subscription", "note": "Dashboard and analytics tiers"},
        {"model": "API access", "note": "Indexed on-chain data feeds"},
        {"model": "Enterprise licenses", "note": "Custom analytics deployments"},
    ],
}

DEFAULT_REVENUE_MODELS = [
    {"model": "SaaS subscription", "fit": "medium", "note": "Recurring software revenue", "derived_from": "baseline"},
    {"model": "Professional services", "fit": "medium", "note": "Implementation and consulting", "derived_from": "baseline"},
    {"model": "Usage-based pricing", "fit": "medium", "note": "Pay-per-use API or compute", "derived_from": "baseline"},
]


def _fit_from_strength(strength: int) -> str:
    if strength >= 3:
        return "high"
    if strength >= 2:
        return "medium"
    return "low"


def _derive_revenue_models(product_types: list[dict], domain_name: str) -> list[dict[str, Any]]:
    """Build revenue model list from detected product types, ranked by signal strength."""
    derived: list[dict[str, Any]] = []
    seen: set[str] = set()

    for pt in product_types:
        product_type = pt["product_type"]
        strength = pt.get("signal_strength", 1)
        fit = _fit_from_strength(strength)
        for rm in PRODUCT_TYPE_REVENUE_MODELS.get(product_type, []):
            if rm["model"] in seen:
                continue
            seen.add(rm["model"])
            derived.append({
                "model": rm["model"],
                "fit": fit,
                "note": rm["note"],
                "derived_from": product_type,
                "signal_strength": strength,
            })

    if len(derived) < 3:
        for rm in DEFAULT_REVENUE_MODELS:
            if rm["model"] not in seen:
                seen.add(rm["model"])
                derived.append(dict(rm))

    return derived[:5]


def _detect_product_types(text_blobs: list[str]) -> list[dict[str, Any]]:
    combined = " ".join(text_blobs).lower()
    hits: list[dict[str, Any]] = []
    for product_type, keywords in PRODUCT_PATTERNS:
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            matched = [kw for kw in keywords if kw in combined]
            hits.append({
                "product_type": product_type,
                "signal_strength": score,
                "matched_keywords": matched,
            })
    hits.sort(key=lambda x: x["signal_strength"], reverse=True)
    return hits[:6]


def _extract_builders(signals: dict) -> list[dict[str, Any]]:
    builders: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(name: str, builder_type: str, source: str, metric: str, url: str = ""):
        key = name.lower().strip()
        if not name or key in seen or len(name) < 2:
            return
        seen.add(key)
        builders.append({
            "name": name,
            "type": builder_type,
            "source": source,
            "metric": metric,
            "url": url,
        })

    dev = signals.get("developer_momentum")
    if dev and dev.available and dev.raw_data:
        for repo in dev.raw_data.get("top_repos", [])[:8]:
            add(
                repo.get("full_name", repo.get("name", "")),
                "open-source project",
                "GitHub",
                f"{repo.get('stars', 0)} stars",
                repo.get("url", ""),
            )

    hire = signals.get("hiring_demand")
    if hire and hire.available and hire.raw_data:
        for co in hire.raw_data.get("top_companies", [])[:8]:
            add(co.get("name", ""), "hiring company", "Job postings", co.get("jobs", "active hiring"))

    cap = signals.get("capital_flow")
    if cap and cap.available and cap.raw_data:
        for p in cap.raw_data.get("top_protocols", cap.raw_data.get("top_coins", []))[:6]:
            add(
                p.get("name", ""),
                "protocol" if cap.raw_data.get("source") == "defillama" else "project",
                cap.raw_data.get("source", "market data"),
                p.get("metric", ""),
                p.get("url", ""),
            )

    fund = signals.get("funding_signal")
    if fund and fund.available and fund.raw_data:
        for r in fund.raw_data.get("recent_rounds", [])[:6]:
            title = r.get("title", "")
            company = title.split(" raises")[0].split(" Raises")[0].split(" lands")[0].strip()
            if company:
                add(company, "funded startup", "Funding news", r.get("amount", "recent round"), r.get("link", ""))

    return builders[:12]


def _market_indicators(signals: dict, track: str) -> dict[str, Any]:
    indicators: dict[str, Any] = {"track": track}
    hire = signals.get("hiring_demand")
    dev = signals.get("developer_momentum")
    cap = signals.get("capital_flow")
    fund = signals.get("funding_signal")
    interest = signals.get("public_interest")

    if hire and hire.available:
        indicators["job_postings"] = int(hire.value)
        indicators["adzuna_count"] = hire.raw_data.get("adzuna_max_count")
        indicators["remoteok_count"] = hire.raw_data.get("remoteok_matched")
        indicators["hiring_sources"] = hire.raw_data.get("sources", [])
    if dev and dev.available:
        indicators["new_repos_90d"] = int(dev.raw_data.get("total_count", dev.value))
        indicators["avg_repo_stars"] = dev.raw_data.get("avg_stars")
        indicators["github_date_filter_90d"] = dev.raw_data.get("date_filter_90d", True)
    if cap and cap.available:
        if cap.unit == "tvl_usd":
            indicators["total_tvl_usd"] = cap.value
            indicators["matched_protocols"] = cap.raw_data.get("matched_protocols")
        else:
            indicators["market_cap_usd"] = cap.value
            indicators["coins_tracked"] = cap.raw_data.get("coins_matched")
    if fund and fund.available:
        indicators["funding_mentions"] = fund.raw_data.get("mentions", int(fund.value))
        indicators["disclosed_capital_usd"] = fund.raw_data.get("disclosed_capital_usd")
    if interest and interest.available:
        indicators["search_interest_index"] = interest.raw_data.get("avg_interest")
        indicators["search_trend_delta"] = interest.raw_data.get("trend_delta")
        indicators["trends_keywords_queried"] = interest.raw_data.get("keywords_queried")

    indicators["signals_available"] = sum(1 for s in signals.values() if s.available)
    indicators["signals_total"] = len(signals)
    return indicators


def _sample_products(signals: dict, product_types: list[dict]) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    dev = signals.get("developer_momentum")
    if dev and dev.available and dev.raw_data:
        for repo in dev.raw_data.get("top_repos", [])[:4]:
            desc = repo.get("description") or repo.get("name", "")
            samples.append({
                "name": repo.get("full_name", repo.get("name", "")),
                "description": (desc or "")[:120],
                "category": "open-source",
                "url": repo.get("url", ""),
            })
    cap = signals.get("capital_flow")
    if cap and cap.available and cap.raw_data:
        for p in cap.raw_data.get("top_protocols", cap.raw_data.get("top_coins", []))[:3]:
            samples.append({
                "name": p.get("name", ""),
                "description": p.get("metric", p.get("category", "market data")),
                "category": "live protocol" if cap.unit == "tvl_usd" else "tracked project",
                "url": p.get("url", ""),
            })
    if not samples and product_types:
        samples.append({
            "name": product_types[0]["product_type"],
            "description": (
                f"Keyword evidence: {', '.join(product_types[0].get('matched_keywords', []))}"
            ),
            "category": "inferred from signals",
            "url": "",
        })
    return samples[:6]


def build_product_landscape(
    domain_name: str,
    track: str,
    keywords: list[str],
    signals: dict,
) -> dict[str, Any]:
    text_blobs = list(keywords)
    for sig in signals.values():
        if not sig.available:
            continue
        rd = sig.raw_data or {}
        for repo in rd.get("top_repos", []):
            text_blobs.append(repo.get("name", ""))
            text_blobs.append(repo.get("description", "") or "")
        for job in rd.get("sample_jobs", []):
            text_blobs.append(job.get("title", ""))
            text_blobs.append(job.get("company", ""))
        for p in rd.get("top_protocols", rd.get("top_coins", [])):
            text_blobs.append(p.get("name", ""))
            text_blobs.append(p.get("category", "") or "")
        for r in rd.get("recent_rounds", []):
            text_blobs.append(r.get("title", ""))

    product_types = _detect_product_types(text_blobs)
    builders = _extract_builders(signals)
    revenue_models = _derive_revenue_models(product_types, domain_name)
    market = _market_indicators(signals, track)
    samples = _sample_products(signals, product_types)
    demand_summary = _demand_summary(domain_name, product_types, market, builders)

    return {
        "domain": domain_name,
        "track": track,
        "demand_summary": demand_summary,
        "product_types_in_demand": product_types,
        "builders": builders,
        "revenue_models": revenue_models,
        "market_indicators": market,
        "sample_products": samples,
        "methodology": (
            "Product types from keyword frequency in live signals; "
            "revenue models mapped from detected product types; "
            "builders from GitHub, jobs, protocols, and funding headlines"
        ),
    }


def _demand_summary(
    domain: str,
    product_types: list[dict],
    market: dict,
    builders: list[dict],
) -> str:
    parts = [f"{domain}:"]
    if product_types:
        parts.append(f"top product demand is {product_types[0]['product_type']}")
    if market.get("job_postings"):
        parts.append(f"{market['job_postings']} open roles signal hiring demand")
    if market.get("total_tvl_usd"):
        tvl = market["total_tvl_usd"]
        parts.append(f"${tvl/1e9:.1f}B TVL in related protocols" if tvl > 1e9 else f"${tvl/1e6:.0f}M TVL")
    if market.get("market_cap_usd"):
        mcap = market["market_cap_usd"]
        parts.append(f"${mcap/1e9:.1f}B market cap in related projects" if mcap > 1e9 else f"${mcap/1e6:.0f}M market cap")
    if market.get("disclosed_capital_usd"):
        disclosed = market["disclosed_capital_usd"]
        if disclosed > 0:
            parts.append(
                f"${disclosed/1e6:.1f}M disclosed funding in recent headlines"
                if disclosed >= 1e6
                else f"${disclosed/1e3:.0f}K disclosed funding in recent headlines"
            )
    if builders:
        parts.append(f"{len(builders)} active builders identified from live data")
    avail = market.get("signals_available", 0)
    total = market.get("signals_total", 5)
    parts.append(f"{avail}/{total} data sources returned live signals")
    return ". ".join(parts) + "."
