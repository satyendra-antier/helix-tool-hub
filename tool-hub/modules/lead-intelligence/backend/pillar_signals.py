"""Growth Pillars feedback: warm paths and account momentum raise a lead's priority."""

from __future__ import annotations

import httpx

from config import settings

MAX_WARM_PATH_POINTS = 8.0
MAX_MOMENTUM_POINTS = 6.0


def fetch_pillar_signals() -> dict:
    """{"leads": {lead_id: {...}}, "partner_domains": {domain: score}}; empty when unavailable."""
    empty = {"leads": {}, "partner_domains": {}}
    if not settings.growth_pillars_api_url:
        return empty
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{settings.growth_pillars_api_url.rstrip('/')}/signals")
        if resp.status_code != 200:
            return empty
        data = resp.json()
        return {
            "leads": data.get("leads") or {},
            "partner_domains": data.get("partner_domains") or {},
        }
    except (httpx.HTTPError, ValueError):
        return empty


def pillar_signal_for(entity_id: str, matched_domains: list | None, signals: dict | None) -> dict | None:
    if not signals:
        return None
    lead = (signals.get("leads") or {}).get(str(entity_id)) or {}
    partner_domains = signals.get("partner_domains") or {}
    domain_names = [
        m.get("domain_name") for m in matched_domains or [] if isinstance(m, dict) and m.get("domain_name")
    ]
    partner_score = max((partner_domains.get(d, 0.0) for d in domain_names), default=0.0)
    expert_score = float(lead.get("expert_path_score") or 0)
    alerts = int(lead.get("insider_alerts_14d") or 0)
    high_alerts = int(lead.get("high_alerts_14d") or 0)
    if not (expert_score or partner_score or alerts):
        return None

    warm_path = min(1.0, max(expert_score, partner_score) / 100.0)
    momentum = min(1.0, 0.25 * alerts + 0.25 * high_alerts)
    return {
        "points": round(MAX_WARM_PATH_POINTS * warm_path + MAX_MOMENTUM_POINTS * momentum, 2),
        "warm_path": round(warm_path * 100, 1),
        "momentum": round(momentum * 100, 1),
    }
