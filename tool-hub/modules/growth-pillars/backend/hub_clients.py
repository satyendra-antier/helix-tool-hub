"""HTTP access to the other Tool Hub modules. Never read their tables directly."""

from __future__ import annotations

import httpx

from config import settings


def _get(base: str, path: str, params: dict | None = None) -> dict | list | None:
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            resp = client.get(f"{base.rstrip('/')}/{path.lstrip('/')}", params=params)
            if resp.status_code != 200:
                return None
            return resp.json()
    except httpx.HTTPError:
        return None


def _post(base: str, path: str, json: dict | None = None, timeout: float | None = None) -> dict | None:
    try:
        with httpx.Client(timeout=timeout or settings.http_timeout_seconds) as client:
            resp = client.post(f"{base.rstrip('/')}/{path.lstrip('/')}", json=json)
            if resp.status_code >= 400:
                return None
            return resp.json()
    except httpx.HTTPError:
        return None


def fetch_top_leads(limit: int = 25, min_score: float = 0) -> list[dict]:
    """Highest-scored leads from Lead Intelligence."""
    leads: list[dict] = []
    page = 1
    while len(leads) < limit:
        data = _get(
            settings.lead_intelligence_api_url,
            "/leads",
            {"page": page, "page_size": min(100, limit), "sort": "score"},
        )
        if not isinstance(data, dict):
            break
        batch = data.get("leads") or []
        leads.extend(l for l in batch if float(l.get("score") or 0) >= min_score)
        if page >= int(data.get("pages") or 1) or not batch:
            break
        if batch and float(batch[-1].get("score") or 0) < min_score:
            break
        page += 1
    return leads[:limit]


def fetch_lead(lead_id: str) -> dict | None:
    data = _get(settings.lead_intelligence_api_url, f"/leads/{lead_id}")
    return data if isinstance(data, dict) else None


def ingest_partner_lead(payload: dict) -> dict | None:
    return _post(settings.lead_intelligence_api_url, "/leads/ingest", payload)


def enroll_in_outreach(lead_id: str) -> tuple[bool, str]:
    """Ask Reach Out to draft a first email for this lead. The draft still waits for approval."""
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(f"{settings.outreach_api_url.rstrip('/')}/enrollments", json={"lead_id": lead_id})
        if resp.status_code < 400:
            return True, "drafted"
        detail = resp.json().get("detail") if resp.headers.get("content-type", "").startswith("application/json") else ""
        return False, str(detail or resp.status_code)
    except httpx.HTTPError as e:
        return False, f"Reach Out not reachable: {e}"


def trigger_lead_rescore() -> dict | None:
    return _post(settings.lead_intelligence_api_url, "/leads/rescore", timeout=300)


def fetch_market_domains() -> list[dict]:
    """Market Depth scores, best first: [{domain, track, composite_score}]."""
    data = _get(settings.market_depth_api_url, "/snapshots/latest")
    if not isinstance(data, dict):
        return []
    scores = data.get("scores") or []
    return sorted(
        (
            {
                "domain": s.get("domain"),
                "track": s.get("track"),
                "composite_score": float(s.get("composite_score") or 0),
            }
            for s in scores
            if s.get("domain")
        ),
        key=lambda s: -s["composite_score"],
    )


def fetch_verdicts() -> dict[str, dict]:
    """Build Readiness verdicts keyed by domain name."""
    data = _get(settings.build_readiness_api_url, "/verdicts/latest")
    if not isinstance(data, dict):
        return {}
    return {
        v["domain_name"]: v
        for v in data.get("verdicts") or []
        if v.get("domain_name") and v.get("verdict") != "PENDING"
    }


def go_domains() -> list[str]:
    """Domains we can win: GO / CONDITIONAL verdicts, else top market domains."""
    verdicts = fetch_verdicts()
    winnable = [name for name, v in verdicts.items() if v.get("verdict") in ("GO", "CONDITIONAL")]
    if winnable:
        return winnable
    return [d["domain"] for d in fetch_market_domains()[:8]]


def module_health() -> dict[str, bool]:
    result = {}
    for name, base in (
        ("lead-intelligence", settings.lead_intelligence_api_url),
        ("market-depth-analyzer", settings.market_depth_api_url),
        ("build-readiness", settings.build_readiness_api_url),
    ):
        data = _get(base, "/health")
        result[name] = isinstance(data, dict) and data.get("status") == "ok"
    return result
