"""Market Depth–aligned lead sources (keywords from live domain snapshots)."""

from __future__ import annotations

import re
import time
from datetime import date
from urllib.parse import urlparse

import httpx
import feedparser

from config import settings
from sources.base import RawLead
from text_utils import clean_description
from track_utils import normalize_lead_track
from lead_quality import extract_company_from_headline, is_aggregate_title

_last_request: dict[str, float] = {}


def _rate_limit(domain: str) -> None:
    now = time.time()
    last = _last_request.get(domain, 0)
    wait = settings.rate_limit_seconds - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_request[domain] = time.time()


def _extract_domain(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path).lower().replace("www.", "")
    return host or None


def _parse_funding_amount(title: str) -> float:
    m = re.search(r"\$([\d,.]+)\s*([MBK])?", title, re.I)
    if not m:
        return 0.0
    raw = m.group(1).replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return 0.0
    suffix = (m.group(2) or "").upper()
    if suffix == "B":
        return val * 1_000_000_000
    if suffix == "M":
        return val * 1_000_000
    if suffix == "K":
        return val * 1_000
    return val


def _keyword_hit(text: str, keywords: list[str]) -> list[str]:
    blob = text.lower()
    hits = []
    for kw in keywords:
        k = kw.lower().strip()
        if k and k in blob:
            hits.append(kw)
    return hits


def fetch_market_depth_builders(intel_ctx: dict) -> list[RawLead]:
    """Hiring companies + live protocols from Market Depth product_landscape."""
    leads: list[RawLead] = []
    for domain_name, m in (intel_ctx.get("market_domains") or {}).items():
        pl = m.get("product_landscape") or {}
        track = normalize_lead_track(m.get("track"))
        for builder in pl.get("builders") or []:
            if not isinstance(builder, dict):
                continue
            btype = (builder.get("type") or "").lower()
            name = (builder.get("name") or "").strip()
            if not name or name.startswith("http"):
                continue
            if "hiring" in btype or "company" in btype:
                metric = builder.get("metric", "")
                leads.append(RawLead(
                    name=name[:200],
                    track=track,
                    domain=_extract_domain(builder.get("url", "")),
                    description=clean_description(
                        f"Hiring signal for {domain_name}: {metric}. "
                        f"Market score {m.get('market_score', 0):.0f}."
                    ),
                    source="market_depth_hiring",
                    signal_type="hiring",
                    signal_value=float(re.search(r"(\d+)", str(metric)).group(1))
                    if re.search(r"(\d+)", str(metric)) else None,
                    signal_date=date.today(),
                    raw_payload={
                        "target_domain": domain_name,
                        "builder_type": btype,
                        "metric": metric,
                    },
                ))
        for sample in pl.get("sample_products") or []:
            if not isinstance(sample, dict):
                continue
            cat = (sample.get("category") or "").lower()
            if cat not in ("live protocol", "protocol"):
                continue
            pname = (sample.get("name") or "").strip()
            if not pname:
                continue
            leads.append(RawLead(
                name=pname[:200],
                track="web3",
                domain=_extract_domain(sample.get("url", "")),
                description=clean_description(
                    f"{domain_name} protocol: {sample.get('description', '')}"
                ),
                source="market_depth_protocol",
                signal_type="protocol",
                signal_date=date.today(),
                raw_payload={"target_domain": domain_name, "url": sample.get("url")},
            ))
    return leads


def fetch_defillama_protocols(keywords: list[str], limit: int = 20) -> list[RawLead]:
    leads: list[RawLead] = []
    if not keywords:
        return leads
    try:
        _rate_limit("api.llama.fi")
        with httpx.Client(timeout=30) as client:
            resp = client.get("https://api.llama.fi/protocols")
            resp.raise_for_status()
            protocols = resp.json()
        kw_lower = [k.lower() for k in keywords]
        matched = [
            p for p in protocols
            if isinstance(p, dict) and any(
                k in (p.get("name") or "").lower()
                or k in (p.get("category") or "").lower()
                or k in " ".join(p.get("chains") or []).lower()
                for k in kw_lower
            )
        ]
        matched.sort(key=lambda p: p.get("tvl", 0) or 0, reverse=True)
        for p in matched[:limit]:
            tvl = float(p.get("tvl") or 0)
            if tvl <= 0:
                continue
            name = p.get("name", "Unknown Protocol")
            category = p.get("category", "DeFi")
            leads.append(RawLead(
                name=name[:200],
                track="web3",
                domain=_extract_domain(p.get("url", "")),
                description=clean_description(
                    f"{category} protocol on DefiLlama — ${tvl / 1e6:.1f}M TVL"
                ),
                source="defillama_protocols",
                signal_type="protocol",
                signal_value=tvl,
                signal_date=date.today(),
                raw_payload={
                    "slug": p.get("slug"),
                    "category": category,
                    "chains": p.get("chains"),
                },
            ))
    except Exception:
        pass
    return leads


def fetch_crypto_news_rss(keywords: list[str], limit: int = 15) -> list[RawLead]:
    leads: list[RawLead] = []
    feeds = [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
    ]
    seen: set[str] = set()
    for feed_url in feeds:
        try:
            _rate_limit(urlparse(feed_url).netloc)
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = (entry.get("title") or "").strip()
                if not title or is_aggregate_title(title):
                    continue
                summary = clean_description(entry.get("summary", ""), 400)
                blob = f"{title} {summary}"
                hits = _keyword_hit(blob, keywords)
                if not hits and not any(
                    w in blob.lower()
                    for w in ("defi", "stablecoin", "blockchain", "crypto", "web3", "bitcoin", "ethereum")
                ):
                    continue
                amount = _parse_funding_amount(title)
                signal_type = "funding" if amount > 0 or "raise" in title.lower() else "news"
                if signal_type == "funding":
                    company = extract_company_from_headline(title)
                    if not company:
                        continue
                else:
                    # Skip generic market news — only funding company headlines
                    continue
                key = title[:80].lower()
                if key in seen:
                    continue
                seen.add(key)
                leads.append(RawLead(
                    name=company[:100],
                    track="web3",
                    domain=_extract_domain(entry.get("link", "")),
                    description=clean_description(f"{title}. {summary}"[:500]),
                    source=urlparse(feed_url).netloc,
                    signal_type=signal_type,
                    signal_value=amount if amount > 0 else None,
                    signal_date=date.today(),
                    raw_payload={"link": entry.get("link"), "matched_keywords": hits[:5]},
                ))
                if len(leads) >= limit:
                    return leads
        except Exception:
            continue
    return leads


def fetch_remoteok_jobs(keywords: list[str], limit: int = 15) -> list[RawLead]:
    leads: list[RawLead] = []
    if not keywords:
        return leads
    try:
        _rate_limit("remoteok.com")
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://remoteok.com/api",
                headers={"User-Agent": "ToolHub-LeadBot/1.0"},
            )
            if resp.status_code != 200:
                return leads
            jobs = resp.json()
        if not isinstance(jobs, list):
            return leads
        kw_lower = [k.lower() for k in keywords]
        company_counts: dict[str, dict] = {}
        for j in jobs[1:101]:
            if not isinstance(j, dict):
                continue
            position = str(j.get("position", ""))
            tags = " ".join(j.get("tags") or [])
            blob = f"{position} {tags}".lower()
            hits = [k for k in kw_lower if k in blob]
            if not hits:
                continue
            company = (j.get("company") or "Unknown").strip()
            if company not in company_counts:
                company_counts[company] = {
                    "count": 0, "titles": [], "hits": set(),
                    "url": j.get("company_url") or "",
                }
            company_counts[company]["count"] += 1
            company_counts[company]["hits"].update(hits)
            if len(company_counts[company]["titles"]) < 3:
                company_counts[company]["titles"].append(position)

        for company, info in sorted(company_counts.items(), key=lambda x: -x[1]["count"])[:limit]:
            leads.append(RawLead(
                name=company[:200],
                track="web3" if any(
                    h in {"defi", "solidity", "ethereum", "web3", "blockchain", "stablecoin", "crypto"}
                    for h in info["hits"]
                ) else "ai",
                domain=_extract_domain(info["url"]),
                description=clean_description(
                    f"Hiring: {info['count']} remote roles — {', '.join(info['titles'][:2])}"
                ),
                source="remoteok",
                signal_type="hiring",
                signal_value=float(info["count"]),
                signal_date=date.today(),
                raw_payload={"open_roles": info["count"], "matched_keywords": list(info["hits"])},
            ))
    except Exception:
        pass
    return leads


def fetch_adzuna_jobs(keywords: list[str], limit: int = 12) -> list[RawLead]:
    leads: list[RawLead] = []
    if not settings.adzuna_app_id or not settings.adzuna_app_key or not keywords:
        return leads
    company_counts: dict[str, dict] = {}
    try:
        with httpx.Client(timeout=30) as client:
            for kw in keywords[:6]:
                _rate_limit("api.adzuna.com")
                resp = client.get(
                    "https://api.adzuna.com/v1/api/jobs/us/search/1",
                    params={
                        "app_id": settings.adzuna_app_id,
                        "app_key": settings.adzuna_app_key,
                        "what": kw,
                        "results_per_page": 20,
                    },
                )
                if resp.status_code != 200:
                    continue
                for job in resp.json().get("results", [])[:20]:
                    company = job.get("company", {}).get("display_name", "Unknown")
                    title = job.get("title", "")
                    if company not in company_counts:
                        company_counts[company] = {"count": 0, "titles": [], "keywords": set()}
                    company_counts[company]["count"] += 1
                    company_counts[company]["keywords"].add(kw)
                    if len(company_counts[company]["titles"]) < 2:
                        company_counts[company]["titles"].append(title)

        web3_kws = {
            "defi", "solidity", "ethereum", "web3", "blockchain", "stablecoin",
            "smart contract", "crypto", "layer 2", "rollup", "tokenomics",
        }
        ai_kws = {"llm", "ai", "machine learning", "mlops", "langchain", "agent", "rag"}

        for company, info in sorted(company_counts.items(), key=lambda x: -x[1]["count"])[:limit]:
            kws = {k.lower() for k in info["keywords"]}
            if kws & web3_kws:
                track = "web3"
            elif kws & ai_kws:
                track = "ai"
            else:
                track = "web2"
            leads.append(RawLead(
                name=company[:200],
                track=track,
                description=clean_description(
                    f"Hiring ({', '.join(sorted(info['keywords'])[:3])}): "
                    f"{info['count']} roles — {', '.join(info['titles'][:2])}"
                ),
                source="adzuna",
                signal_type="hiring",
                signal_value=float(info["count"]),
                signal_date=date.today(),
                raw_payload={"matched_keywords": list(info["keywords"])},
            ))
    except Exception:
        pass
    return leads


def fetch_grants_by_keywords(keywords: list[str], limit: int = 10) -> list[RawLead]:
    leads: list[RawLead] = []
    search_terms = keywords[:8] or ["blockchain", "artificial intelligence"]
    seen: set[str] = set()
    try:
        with httpx.Client(timeout=30) as client:
            for kw in search_terms:
                _rate_limit("api.grants.gov")
                resp = client.post(
                    "https://api.grants.gov/v1/api/search2",
                    json={"rows": 8, "keyword": kw, "oppStatuses": "posted"},
                )
                if resp.status_code != 200:
                    continue
                hits = resp.json().get("data", {}).get("oppHits", resp.json().get("oppHits", []))
                for opp in hits:
                    title = opp.get("title", "Federal Grant")[:200]
                    if title in seen:
                        continue
                    seen.add(title)
                    blob = f"{title} {kw}".lower()
                    track = "web3" if any(
                        w in blob for w in ("blockchain", "crypto", "defi", "stablecoin", "digital asset")
                    ) else "ai" if any(w in blob for w in ("ai", "artificial intelligence", "machine learning")) else "government"
                    leads.append(RawLead(
                        name=title,
                        track=track,
                        domain="grants.gov",
                        description=clean_description(
                            f"{opp.get('agency', 'Federal agency')} — keyword: {kw}"
                        ),
                        source="grants.gov",
                        signal_type="grant",
                        signal_date=date.today(),
                        raw_payload={"keyword": kw, "opp": opp},
                    ))
                    if len(leads) >= limit:
                        return leads
    except Exception:
        pass
    return leads


def fetch_product_hunt_ai(limit: int = 10) -> list[RawLead]:
    leads: list[RawLead] = []
    try:
        feed = feedparser.parse("https://www.producthunt.com/feed?category=artificial-intelligence")
        for entry in feed.entries[:limit]:
            title = entry.get("title", "Product Hunt Launch")[:100]
            summary = clean_description(entry.get("summary", ""), 300)
            blob = f"{title} {summary}".lower()
            track = "ai" if any(w in blob for w in ("ai", "llm", "agent", "ml", "gpt")) else "web2"
            leads.append(RawLead(
                name=title,
                track=track,
                domain=_extract_domain(entry.get("link", "")),
                description=summary or title,
                source="producthunt_ai",
                signal_type="launch",
                signal_date=date.today(),
                raw_payload={"link": entry.get("link")},
            ))
    except Exception:
        pass
    return leads


def fetch_market_aligned_sources(intel_ctx: dict) -> list[RawLead]:
    """Fetch leads using Market Depth domain keywords + builders."""
    keywords = intel_ctx.get("sync_keywords") or []
    web3_kws = intel_ctx.get("track_keywords", {}).get("web3", keywords)
    ai_kws = intel_ctx.get("track_keywords", {}).get("ai", keywords)

    leads: list[RawLead] = []
    leads.extend(fetch_market_depth_builders(intel_ctx))
    leads.extend(fetch_defillama_protocols(web3_kws))
    leads.extend(fetch_crypto_news_rss(web3_kws))
    leads.extend(fetch_remoteok_jobs(web3_kws + ai_kws))
    leads.extend(fetch_adzuna_jobs(web3_kws[:4] + ai_kws[:4]))
    leads.extend(fetch_grants_by_keywords(web3_kws[:3] + ["stablecoin", "blockchain"]))
    leads.extend(fetch_product_hunt_ai())
    return leads
