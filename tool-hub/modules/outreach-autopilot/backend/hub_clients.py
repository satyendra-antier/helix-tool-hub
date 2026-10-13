"""HTTP access to other LeadGen AI modules. Never read their tables directly."""

from __future__ import annotations

import httpx

from config import settings


def _get(base: str, path: str, params: dict | None = None, timeout: float | None = None):
    if not base:
        return None
    try:
        with httpx.Client(timeout=timeout or settings.http_timeout_seconds) as client:
            resp = client.get(f"{base.rstrip('/')}/{path.lstrip('/')}", params=params)
            return resp.json() if resp.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _send(method: str, base: str, path: str, json: dict | None = None, timeout: float | None = None):
    if not base:
        return None
    try:
        with httpx.Client(timeout=timeout or settings.http_timeout_seconds) as client:
            resp = client.request(method, f"{base.rstrip('/')}/{path.lstrip('/')}", json=json)
            return resp.json() if resp.status_code < 400 else None
    except (httpx.HTTPError, ValueError):
        return None


LI = lambda: settings.lead_intelligence_api_url  # noqa: E731


def top_leads(limit: int = 50, min_score: float = 0) -> list[dict]:
    leads: list[dict] = []
    page = 1
    while len(leads) < limit:
        data = _get(LI(), "/leads", {"page": page, "page_size": 50, "sort": "score"})
        if not isinstance(data, dict):
            break
        batch = data.get("leads") or []
        leads.extend(l for l in batch if float(l.get("score") or 0) >= min_score)
        if not batch or page >= int(data.get("pages") or 1) or float(batch[-1].get("score") or 0) < min_score:
            break
        page += 1
    return leads[:limit]


def get_lead(lead_id: str) -> dict | None:
    data = _get(LI(), f"/leads/{lead_id}")
    return data if isinstance(data, dict) else None


def find_contacts_for_top(limit: int = 10, min_score: float = 50) -> dict | None:
    return _send("POST", LI(), f"/contacts/find-top?limit={limit}&min_score={min_score}", timeout=600)


def find_contacts(lead_id: str) -> dict | None:
    return _send("POST", LI(), f"/leads/{lead_id}/find-contacts", timeout=120)


def suppressed_emails() -> set[str]:
    data = _get(LI(), "/suppressions")
    if isinstance(data, dict):
        return {e.lower() for e in data.get("emails") or []}
    return set()


def suppress(email: str, reason: str) -> None:
    _send("POST", LI(), "/suppressions", {"email": email, "reason": reason})


def set_stage(lead_id: str, stage: str, notes: str | None = None) -> None:
    body = {"stage": stage}
    if notes:
        body["notes"] = notes
    _send("PATCH", LI(), f"/leads/{lead_id}/stage", body)


def ingest_referral(name: str, domain: str | None, contact_name: str | None, contact_email: str | None,
                    note: str) -> dict | None:
    return _send("POST", LI(), "/leads/ingest", {
        "name": name,
        "domain": domain,
        "description": note,
        "source": "reply-referral",
        "signal_type": "referral",
        "contact_name": contact_name,
        "contact_email": contact_email,
    })


def handoff_to_deal_coach(payload: dict) -> dict | None:
    return _send("POST", settings.growth_pillars_api_url, "/advisory/handoff", payload, timeout=120)


def module_health() -> dict[str, bool]:
    out = {}
    for name, base in (
        ("lead-intelligence", settings.lead_intelligence_api_url),
        ("growth-pillars", settings.growth_pillars_api_url),
    ):
        data = _get(base, "/health", timeout=5)
        out[name] = isinstance(data, dict) and data.get("status") == "ok"
    return out
