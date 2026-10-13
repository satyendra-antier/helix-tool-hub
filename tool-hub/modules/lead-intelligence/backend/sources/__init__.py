import re
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from config import settings
from sources.base import RawLead
from text_utils import clean_description
from sources.market_aligned import fetch_market_aligned_sources

_last_request: dict[str, float] = {}


def _rate_limit(domain: str) -> None:
    now = time.time()
    last = _last_request.get(domain, 0)
    wait = settings.rate_limit_seconds - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_request[domain] = time.time()


def _robots_ok(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch("*", url)
    except Exception:
        return True


def _extract_domain(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path).lower().replace("www.", "")
    return host or None


def fetch_sam_gov() -> list[RawLead]:
    leads: list[RawLead] = []
    if not settings.sam_gov_api_key:
        return leads
    try:
        _rate_limit("api.sam.gov")
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://api.sam.gov/opportunities/v2/search",
                params={
                    "api_key": settings.sam_gov_api_key,
                    "limit": 25,
                    "postedFrom": (datetime.utcnow() - timedelta(days=30)).strftime("%m/%d/%Y"),
                    "postedTo": datetime.utcnow().strftime("%m/%d/%Y"),
                },
            )
            if resp.status_code != 200:
                return leads
            data = resp.json()
        for opp in data.get("opportunitiesData", data.get("data", []))[:25]:
            title = opp.get("title") or opp.get("opportunityTitle", "Federal Opportunity")
            deadline_str = opp.get("responseDeadLine") or opp.get("reponseDeadLine")
            deadline = None
            if deadline_str:
                try:
                    deadline = datetime.strptime(deadline_str[:10], "%Y-%m-%d").date()
                except ValueError:
                    pass
            value = opp.get("award", {}).get("amount") if isinstance(opp.get("award"), dict) else None
            leads.append(RawLead(
                name=title[:200],
                track="government",
                domain="sam.gov",
                description=clean_description(opp.get("description", title), 500),
                source="sam.gov",
                signal_type="tender",
                signal_value=float(value) if value else None,
                signal_date=date.today(),
                deadline=deadline,
                raw_payload=opp,
            ))
    except Exception:
        pass
    return leads


def fetch_grants_gov() -> list[RawLead]:
    leads: list[RawLead] = []
    try:
        _rate_limit("api.grants.gov")
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.grants.gov/v1/api/search2",
                json={"rows": 15, "keyword": "technology", "oppStatuses": "posted"},
            )
            if resp.status_code != 200:
                return leads
            data = resp.json()
        hits = data.get("data", {}).get("oppHits", data.get("oppHits", []))
        for opp in hits[:15]:
            close = opp.get("closeDate")
            deadline = None
            if close:
                try:
                    deadline = datetime.strptime(close[:10], "%Y-%m-%d").date()
                except ValueError:
                    pass
            leads.append(RawLead(
                name=opp.get("title", "Federal Grant")[:200],
                track="government",
                domain="grants.gov",
                description=f"{opp.get('agency', '')} — {opp.get('title', '')}"[:500],
                source="grants.gov",
                signal_type="grant",
                signal_date=date.today(),
                deadline=deadline,
                raw_payload=opp,
            ))
    except Exception:
        pass
    return leads


def fetch_gem_tenders() -> list[RawLead]:
    """Respectful GeM portal scrape — public government listings only."""
    leads: list[RawLead] = []
    base = "https://bidplus.gem.gov.in/all-bids"
    if not _robots_ok(base):
        return leads
    try:
        _rate_limit("bidplus.gem.gov.in")
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(
                base,
                headers={"User-Agent": "ToolHub-LeadBot/1.0 (government procurement research)"},
            )
            if resp.status_code != 200:
                return leads
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tbody tr, .bid-card, .card-body")[:15]
            for i, row in enumerate(rows):
                text = row.get_text(" ", strip=True)
                if len(text) < 20:
                    continue
                title = text[:150]
                leads.append(RawLead(
                    name=f"GeM Tender: {title[:80]}",
                    track="government",
                    domain="gem.gov.in",
                    description=text[:500],
                    source="gem.gov.in",
                    signal_type="tender",
                    signal_date=date.today(),
                    deadline=date.today() + timedelta(days=14 + i),
                    raw_payload={"text": text[:300]},
                ))
    except Exception:
        pass
    return leads


def fetch_world_bank() -> list[RawLead]:
    leads: list[RawLead] = []
    try:
        _rate_limit("search.worldbank.org")
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://search.worldbank.org/api/v2/procurement",
                params={"format": "json", "rows": 10, "qterm": "technology"},
            )
            if resp.status_code != 200:
                return leads
            docs = resp.json().get("response", {}).get("docs", [])
        for doc in docs[:10]:
            leads.append(RawLead(
                name=(doc.get("project_name") or doc.get("bid_description") or "World Bank Procurement")[:200],
                track="government",
                domain="worldbank.org",
                description=(doc.get("bid_description") or doc.get("project_name", ""))[:500],
                source="worldbank",
                signal_type="tender",
                signal_date=date.today(),
                raw_payload=doc,
            ))
    except Exception:
        pass
    return leads


def fetch_ted_eu() -> list[RawLead]:
    leads: list[RawLead] = []
    try:
        _rate_limit("ted.europa.eu")
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://ted.europa.eu/api/v2.0/notices/search",
                json={"query": "technology", "page": 1, "limit": 10, "scope": "ACTIVE"},
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                return leads
            notices = resp.json().get("notices", resp.json().get("results", []))
        for n in notices[:10]:
            if not isinstance(n, dict):
                continue
            title = n.get("title", n.get("notice-title", "EU Procurement Notice"))
            if isinstance(title, dict):
                title = title.get("eng", list(title.values())[0] if title else "EU Notice")
            leads.append(RawLead(
                name=str(title)[:200],
                track="government",
                domain="ted.europa.eu",
                description=str(title)[:500],
                source="ted.eu",
                signal_type="tender",
                signal_date=date.today(),
                raw_payload=n,
            ))
    except Exception:
        pass
    return leads


def fetch_cppp_tenders() -> list[RawLead]:
    leads: list[RawLead] = []
    base = "https://eprocure.gov.in/eprocure/app"
    if not _robots_ok(base):
        return leads
    try:
        _rate_limit("eprocure.gov.in")
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(
                "https://eprocure.gov.in/eprocure/app?page=FrontEndLatestActiveTenders&service=page",
                headers={"User-Agent": "ToolHub-LeadBot/1.0 (government procurement research)"},
            )
            if resp.status_code != 200:
                return leads
            soup = BeautifulSoup(resp.text, "html.parser")
            count = 0
            for row in soup.select("table tr"):
                cells = [c.get_text(" ", strip=True) for c in row.select("td")]
                if len(cells) < 4:
                    continue
                title = next((c for c in cells if len(c) > 20 and "Search" not in c), None)
                if not title:
                    continue
                leads.append(RawLead(
                    name=f"CPPP: {title[:100]}",
                    track="government",
                    domain="eprocure.gov.in",
                    description=" | ".join(cells)[:500],
                    source="cppp",
                    signal_type="tender",
                    signal_date=date.today(),
                    deadline=date.today() + timedelta(days=10 + count),
                    raw_payload={"cells": cells},
                ))
                count += 1
                if count >= 10:
                    break
    except Exception:
        pass
    return leads


def fetch_defillama_raises() -> list[RawLead]:
    leads: list[RawLead] = []
    try:
        _rate_limit("api.llama.fi")
        with httpx.Client(timeout=30) as client:
            resp = client.get("https://api.llama.fi/raises")
            resp.raise_for_status()
            data = resp.json()
        for r in data.get("raises", data)[:20]:
            if not isinstance(r, dict):
                continue
            name = r.get("name", "Unknown Protocol")
            amount = r.get("amount")
            domain = _extract_domain(r.get("url", ""))
            leads.append(RawLead(
                name=name,
                track="web3",
                domain=domain,
                description=f"Raised ${amount}M — {r.get('round', 'funding round')}",
                source="defillama_raises",
                signal_type="funding",
                signal_value=float(amount) * 1_000_000 if amount else None,
                signal_date=date.today(),
                raw_payload=r,
            ))
    except Exception:
        pass
    return leads


def fetch_web3_jobs() -> list[RawLead]:
    leads: list[RawLead] = []
    try:
        _rate_limit("web3.career")
        with httpx.Client(timeout=30) as client:
            resp = client.get("https://web3.career/api/v1/remote-jobs")
            if resp.status_code == 200:
                jobs = resp.json()
                if isinstance(jobs, list):
                    companies: dict[str, int] = {}
                    company_urls: dict[str, str] = {}
                    for j in jobs[:50]:
                        if not isinstance(j, dict):
                            continue
                        co = j.get("company", j.get("company_name", ""))
                        if co:
                            companies[co] = companies.get(co, 0) + 1
                            company_urls.setdefault(co, j.get("company_url") or "")
                    for co, count in sorted(companies.items(), key=lambda x: -x[1])[:15]:
                        leads.append(RawLead(
                            name=co,
                            track="web3",
                            domain=_extract_domain(company_urls.get(co, "")),
                            description=f"Hiring surge: {count} open roles on Web3.career",
                            source="web3.career",
                            signal_type="hiring",
                            signal_value=float(count),
                            signal_date=date.today(),
                            raw_payload={"open_roles": count},
                        ))
    except Exception:
        pass
    return leads


def fetch_product_hunt() -> list[RawLead]:
    leads: list[RawLead] = []
    try:
        _rate_limit("api.producthunt.com")
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://api.producthunt.com/v2/api/graphql",
                headers={"Accept": "application/json"},
                json={
                    "query": "{ posts(order: VOTES, postedAfter: \"2024-01-01\") { edges { node { name tagline website votesCount } } } }"
                },
            )
            if resp.status_code != 200:
                return _fetch_product_hunt_fallback()
            data = resp.json()
            edges = data.get("data", {}).get("posts", {}).get("edges", [])
            for edge in edges[:10]:
                node = edge.get("node", {})
                name = node.get("name", "")
                track = "ai" if any(
                    w in (node.get("tagline", "") + name).lower()
                    for w in ["ai", "llm", "agent", "ml"]
                ) else "web2"
                leads.append(RawLead(
                    name=name,
                    track=track,
                    domain=_extract_domain(node.get("website", "")),
                    description=node.get("tagline", ""),
                    source="producthunt",
                    signal_type="launch",
                    signal_value=float(node.get("votesCount", 0)),
                    signal_date=date.today(),
                    raw_payload=node,
                ))
    except Exception:
        return _fetch_product_hunt_fallback()
    return leads


def _fetch_product_hunt_fallback() -> list[RawLead]:
    import feedparser
    leads: list[RawLead] = []
    try:
        feed = feedparser.parse("https://www.producthunt.com/feed")
        for entry in feed.entries[:10]:
            leads.append(RawLead(
                name=entry.get("title", "Product Hunt Launch")[:100],
                track="web2",
                domain=None,
                description=clean_description(entry.get("summary", ""), 300),
                source="producthunt_rss",
                signal_type="launch",
                signal_date=date.today(),
                raw_payload={"link": entry.get("link")},
            ))
    except Exception:
        pass
    return leads


def fetch_yc_ai() -> list[RawLead]:
    leads: list[RawLead] = []
    try:
        _rate_limit("ycombinator.com")
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://yc-oss.github.io/api/companies/industry/ai.json",
            )
            if resp.status_code == 200:
                companies = resp.json()
                for c in companies[:15]:
                    if not isinstance(c, dict):
                        continue
                    leads.append(RawLead(
                        name=c.get("name", "YC AI Startup"),
                        track="ai",
                        domain=_extract_domain(c.get("website", "")),
                        description=c.get("one_liner", c.get("description", ""))[:300],
                        source="yc_directory",
                        signal_type="funding",
                        signal_date=date.today(),
                        raw_payload=c,
                    ))
    except Exception:
        pass
    return leads


def fetch_crunchbase_rss() -> list[RawLead]:
    from lead_quality import extract_company_from_headline, is_aggregate_title
    import feedparser
    leads: list[RawLead] = []
    try:
        feed = feedparser.parse("https://news.crunchbase.com/feed/")
        for entry in feed.entries[:20]:
            title = (entry.get("title") or "").strip()
            if not title or is_aggregate_title(title):
                continue
            company = extract_company_from_headline(title)
            if not company:
                continue
            if not any(w in title.lower() for w in ["raise", "funding", "series", "million", "seed", "lands", "secures"]):
                continue
            match = re.search(r"(\$[\d.]+[MBK]?)", title)
            value = None
            if match:
                raw = match.group(1).replace("$", "").upper()
                mult = 1_000_000 if "M" in raw else 1_000 if "K" in raw else 1
                try:
                    value = float(raw.replace("M", "").replace("B", "").replace("K", "")) * mult
                except ValueError:
                    pass
            track = "ai" if any(w in title.lower() for w in [" ai", "llm", "agent", "ml "]) else "web2"
            leads.append(RawLead(
                name=company[:100],
                track=track,
                domain=None,
                description=clean_description(title, 500),
                source="crunchbase_rss",
                signal_type="funding",
                signal_value=value,
                signal_date=date.today(),
                raw_payload={"title": title, "link": entry.get("link")},
            ))
    except Exception:
        pass
    return leads


def fetch_all_sources(intel_ctx: dict | None = None) -> list[RawLead]:
    leads: list[RawLead] = []
    leads.extend(fetch_sam_gov())
    leads.extend(fetch_grants_gov())
    leads.extend(fetch_world_bank())
    leads.extend(fetch_ted_eu())
    leads.extend(fetch_gem_tenders())
    leads.extend(fetch_cppp_tenders())
    leads.extend(fetch_defillama_raises())
    leads.extend(fetch_web3_jobs())
    leads.extend(fetch_product_hunt())
    leads.extend(fetch_yc_ai())
    leads.extend(fetch_crunchbase_rss())
    if intel_ctx:
        leads.extend(fetch_market_aligned_sources(intel_ctx))
    return leads
