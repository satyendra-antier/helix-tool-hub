"""
Live market signal fetchers.

Each function returns a RawSignal with a numeric value used by the scoring engine.
Values are never fabricated — unavailable sources are marked available=False.
"""

import re
import math
import time
from datetime import datetime, timedelta

import httpx

from config import settings
from sources.base import RawSignal


def _parse_funding_amount(title: str) -> float:
    """Extract disclosed USD from headlines like '$50M' or '$1.2B'."""
    match = re.search(r"\$\s*([\d,.]+)\s*([KMB])?", title, re.IGNORECASE)
    if not match:
        return 0.0
    try:
        amount = float(match.group(1).replace(",", ""))
    except ValueError:
        return 0.0
    suffix = (match.group(2) or "").upper()
    multiplier = {"K": 1e3, "M": 1e6, "B": 1e9}.get(suffix, 1.0)
    return amount * multiplier


def fetch_github_momentum(keywords: list[str]) -> RawSignal:
    if not settings.github_token:
        return RawSignal(
            source="developer_momentum",
            value=0,
            unit="repos",
            available=False,
            note="GITHUB_TOKEN not configured",
        )

    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }
    query = " OR ".join(keywords[:3])
    since = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
    used_date_filter = True

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://api.github.com/search/repositories",
                headers=headers,
                params={
                    "q": f"{query} created:>{since}",
                    "sort": "stars",
                    "per_page": 30,
                },
            )
            if resp.status_code == 403:
                time.sleep(2)
                used_date_filter = False
                resp = client.get(
                    "https://api.github.com/search/repositories",
                    headers=headers,
                    params={"q": query, "sort": "stars", "per_page": 30},
                )
            resp.raise_for_status()
            data = resp.json()

        total = data.get("total_count", 0)
        items = data.get("items", [])
        avg_stars = (
            sum(i.get("stargazers_count", 0) for i in items) / len(items)
            if items
            else 0
        )
        top_repos = [
            {
                "name": i.get("name", ""),
                "full_name": i.get("full_name", ""),
                "description": i.get("description") or "",
                "stars": i.get("stargazers_count", 0),
                "url": i.get("html_url", ""),
                "language": i.get("language", ""),
            }
            for i in items[:10]
        ]
        return RawSignal(
            source="developer_momentum",
            value=float(total),
            unit="new_repos_90d" if used_date_filter else "matching_repos",
            raw_data={
                "total_count": total,
                "avg_stars": round(avg_stars, 2),
                "sample_repos": len(items),
                "top_repos": top_repos,
                "query": query,
                "date_filter_90d": used_date_filter,
            },
            note=None if used_date_filter else "Rate-limited: using all-time repo count instead of 90-day window",
        )
    except Exception as e:
        return RawSignal(
            source="developer_momentum",
            value=0,
            unit="repos",
            available=False,
            note=str(e),
        )


def fetch_hiring_demand(keywords: list[str]) -> RawSignal:
    """
    Hiring demand = max(Adzuna counts per keyword) + RemoteOK exact matches.
    Adzuna uses max (not sum) to avoid double-counting overlapping listings.
    RemoteOK uses raw match count (no arbitrary multiplier).
    """
    adzuna_counts: list[int] = []
    sources_used: list[str] = []
    top_companies: list[dict] = []
    sample_jobs: list[dict] = []
    company_counts: dict[str, int] = {}

    if settings.adzuna_app_id and settings.adzuna_app_key:
        try:
            with httpx.Client(timeout=30) as client:
                for kw in keywords[:2]:
                    resp = client.get(
                        "https://api.adzuna.com/v1/api/jobs/us/search/1",
                        params={
                            "app_id": settings.adzuna_app_id,
                            "app_key": settings.adzuna_app_key,
                            "what": kw,
                            "results_per_page": 20,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        adzuna_counts.append(int(data.get("count", 0)))
                        sources_used.append("adzuna")
                        for job in data.get("results", [])[:15]:
                            company = job.get("company", {}).get("display_name", "Unknown")
                            title = job.get("title", "")
                            company_counts[company] = company_counts.get(company, 0) + 1
                            sample_jobs.append({"title": title, "company": company, "source": "adzuna"})
        except Exception:
            pass

    remoteok_matched = 0
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get("https://remoteok.com/api")
            if resp.status_code == 200:
                jobs = resp.json()
                if isinstance(jobs, list):
                    kw_lower = [k.lower() for k in keywords]
                    for j in jobs[1:51]:
                        if not isinstance(j, dict):
                            continue
                        if any(
                            k in str(j.get("position", "")).lower()
                            or k in str(j.get("tags", "")).lower()
                            for k in kw_lower
                        ):
                            remoteok_matched += 1
                            company = j.get("company", "Unknown")
                            company_counts[company] = company_counts.get(company, 0) + 1
                            sample_jobs.append({
                                "title": j.get("position", ""),
                                "company": company,
                                "source": "remoteok",
                            })
                    if remoteok_matched > 0:
                        sources_used.append("remoteok")
    except Exception:
        pass

    adzuna_jobs = max(adzuna_counts) if adzuna_counts else 0
    total_jobs = adzuna_jobs + remoteok_matched

    top_companies = [
        {"name": name, "jobs": f"{count} postings"}
        for name, count in sorted(company_counts.items(), key=lambda x: -x[1])[:10]
    ]

    if total_jobs == 0:
        return RawSignal(
            source="hiring_demand",
            value=0,
            unit="job_postings",
            available=False,
            note="No job API data available",
        )

    return RawSignal(
        source="hiring_demand",
        value=float(total_jobs),
        unit="job_postings",
        raw_data={
            "sources": sources_used,
            "total": total_jobs,
            "adzuna_max_count": adzuna_jobs,
            "remoteok_matched": remoteok_matched,
            "methodology": "max(adzuna_keyword_counts) + remoteok_exact_matches",
            "top_companies": top_companies,
            "sample_jobs": sample_jobs[:15],
        },
    )


def _fetch_coingecko_market_cap(keywords: list[str], client: httpx.Client) -> RawSignal:
    """Resolve real market caps via search → markets API (no synthetic fallback)."""
    kw_lower = [k.lower() for k in keywords]
    search_resp = client.get(
        "https://api.coingecko.com/api/v3/search",
        params={"query": keywords[0]},
    )
    search_resp.raise_for_status()
    search_data = search_resp.json()
    coins = search_data.get("coins", [])

    # Keep coins whose name or symbol matches any domain keyword
    relevant = [
        c for c in coins
        if isinstance(c, dict)
        and any(
            k in (c.get("name") or "").lower()
            or k in (c.get("symbol") or "").lower()
            or k in (c.get("id") or "").lower()
            for k in kw_lower
        )
    ][:10]

    if not relevant:
        relevant = [c for c in coins if isinstance(c, dict)][:8]

    coin_ids = [c.get("id") for c in relevant if c.get("id")]
    if not coin_ids:
        return RawSignal(
            source="capital_flow",
            value=0,
            unit="market_cap_usd",
            available=False,
            note="No matching projects found on CoinGecko",
        )

    markets_resp = client.get(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "usd",
            "ids": ",".join(coin_ids),
            "order": "market_cap_desc",
            "per_page": len(coin_ids),
            "page": 1,
            "sparkline": "false",
        },
    )
    markets_resp.raise_for_status()
    markets = markets_resp.json()

    total_mcap = sum(float(m.get("market_cap") or 0) for m in markets if isinstance(m, dict))
    top_coins = [
        {
            "name": m.get("name", ""),
            "metric": f"${(m.get('market_cap') or 0)/1e6:.1f}M mcap" if m.get("market_cap") else "mcap n/a",
            "market_cap": m.get("market_cap"),
            "url": f"https://www.coingecko.com/en/coins/{m.get('id', '')}",
        }
        for m in sorted(markets, key=lambda x: x.get("market_cap") or 0, reverse=True)[:6]
        if isinstance(m, dict)
    ]

    if total_mcap <= 0:
        return RawSignal(
            source="capital_flow",
            value=0,
            unit="market_cap_usd",
            available=False,
            note="CoinGecko returned no market cap data for matched projects",
            raw_data={
                "source": "coingecko",
                "coins_matched": len(relevant),
                "top_coins": top_coins,
            },
        )

    return RawSignal(
        source="capital_flow",
        value=float(total_mcap),
        unit="market_cap_usd",
        raw_data={
            "source": "coingecko",
            "coins_matched": len(markets),
            "methodology": "sum(market_cap) for keyword-matched coins via CoinGecko markets API",
            "top_coins": top_coins,
        },
    )


def fetch_capital_flow(keywords: list[str], track: str) -> RawSignal:
    try:
        with httpx.Client(timeout=30) as client:
            if track == "blockchain":
                resp = client.get("https://api.llama.fi/protocols")
                resp.raise_for_status()
                protocols = resp.json()
                kw_lower = [k.lower() for k in keywords]
                matched = [
                    p for p in protocols
                    if any(
                        k in p.get("name", "").lower()
                        or k in (p.get("category") or "").lower()
                        for k in kw_lower
                    )
                ]
                matched_tvl = sum(p.get("tvl", 0) or 0 for p in matched)
                top_protocols = sorted(matched, key=lambda p: p.get("tvl", 0) or 0, reverse=True)[:8]

                if matched_tvl <= 0:
                    return RawSignal(
                        source="capital_flow",
                        value=0,
                        unit="tvl_usd",
                        available=False,
                        note="No matching protocols with TVL on DefiLlama",
                        raw_data={"source": "defillama", "matched_protocols": 0},
                    )

                return RawSignal(
                    source="capital_flow",
                    value=float(matched_tvl),
                    unit="tvl_usd",
                    raw_data={
                        "source": "defillama",
                        "matched_protocols": len(matched),
                        "methodology": "sum(TVL) for keyword-matched protocols on DefiLlama",
                        "top_protocols": [
                            {
                                "name": p.get("name", ""),
                                "category": p.get("category", ""),
                                "metric": f"${(p.get('tvl') or 0)/1e6:.1f}M TVL",
                                "url": f"https://defillama.com/protocol/{p.get('slug', '')}",
                            }
                            for p in top_protocols
                        ],
                    },
                )
            return _fetch_coingecko_market_cap(keywords, client)
    except Exception as e:
        return RawSignal(
            source="capital_flow",
            value=0,
            unit="usd",
            available=False,
            note=str(e),
        )


def fetch_funding_signal(keywords: list[str]) -> RawSignal:
    import feedparser

    feeds = [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://techcrunch.com/category/crypto/feed/",
    ]
    mentions = 0
    disclosed_total = 0.0
    recent_rounds: list[dict] = []
    kw_lower = [k.lower() for k in keywords]

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                title_lower = title.lower()
                if any(k in title_lower for k in kw_lower):
                    mentions += 1
                    amount = _parse_funding_amount(title)
                    disclosed_total += amount
                    recent_rounds.append({
                        "title": title,
                        "amount": f"${amount/1e6:.1f}M" if amount >= 1e6 else (
                            f"${amount/1e3:.0f}K" if amount >= 1e3 else (
                                f"${amount:.0f}" if amount > 0 else "undisclosed"
                            )
                        ),
                        "amount_usd": amount,
                        "link": entry.get("link", ""),
                    })
        except Exception:
            continue

    # Score value: mention count + log-scaled disclosed capital (keeps cross-domain comparability)
    value = float(mentions) + (math.log10(disclosed_total + 1) if disclosed_total > 0 else 0)

    return RawSignal(
        source="funding_signal",
        value=round(value, 2),
        unit="funding_score",
        raw_data={
            "mentions": mentions,
            "disclosed_capital_usd": round(disclosed_total, 2),
            "methodology": "mention_count + log10(disclosed_usd+1); amounts parsed from headlines",
            "recent_rounds": recent_rounds[:10],
        },
        available=mentions > 0,
        note=None if mentions > 0 else "No funding mentions found in TechCrunch RSS (30-day window)",
    )


def fetch_public_interest(keywords: list[str]) -> RawSignal:
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360)
        interest_values: list[float] = []
        trend_deltas: list[float] = []
        keyword_results: list[dict] = []

        for kw in keywords[:3]:
            kw_trimmed = kw[:50]
            try:
                pytrends.build_payload([kw_trimmed], timeframe="today 12-m")
                data = pytrends.interest_over_time()
                if data.empty or kw_trimmed not in data.columns:
                    continue
                avg = float(data[kw_trimmed].mean())
                delta = float(data[kw_trimmed].iloc[-4:].mean() - data[kw_trimmed].iloc[:4].mean())
                interest_values.append(avg)
                trend_deltas.append(delta)
                keyword_results.append({"keyword": kw_trimmed, "avg": round(avg, 2), "trend_delta": round(delta, 2)})
                time.sleep(0.5)
            except Exception:
                continue

        if not interest_values:
            return RawSignal(
                source="public_interest",
                value=0,
                unit="search_index",
                available=False,
                note="No Google Trends data for domain keywords",
            )

        avg_interest = sum(interest_values) / len(interest_values)
        avg_trend = sum(trend_deltas) / len(trend_deltas)

        return RawSignal(
            source="public_interest",
            value=round(avg_interest, 2),
            unit="search_index_12m_avg",
            raw_data={
                "avg_interest": round(avg_interest, 2),
                "trend_delta": round(avg_trend, 2),
                "keywords_queried": len(keyword_results),
                "per_keyword": keyword_results,
                "methodology": "mean(12-month Google Trends index) across up to 3 domain keywords",
            },
        )
    except Exception as e:
        return RawSignal(
            source="public_interest",
            value=0,
            unit="search_index",
            available=False,
            note=str(e),
        )


def fetch_all_signals(keywords: list[str], track: str) -> dict[str, RawSignal]:
    return {
        "developer_momentum": fetch_github_momentum(keywords),
        "hiring_demand": fetch_hiring_demand(keywords),
        "capital_flow": fetch_capital_flow(keywords, track),
        "funding_signal": fetch_funding_signal(keywords),
        "public_interest": fetch_public_interest(keywords),
    }
