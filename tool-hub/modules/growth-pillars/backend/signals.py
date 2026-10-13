"""Relationship + momentum signals per lead, consumed by Lead Intelligence scoring."""

from __future__ import annotations

from sqlalchemy.orm import Session

from pillars.experts import expert_paths_by_lead
from pillars.insider import recent_alerts_by_lead
from pillars.partners import partner_paths_by_domain


def build_signals(db: Session, lead_ids: list[str] | None = None) -> dict:
    expert_paths = expert_paths_by_lead(db)
    alerts = recent_alerts_by_lead(db, days=14)

    wanted = set(lead_ids) if lead_ids else set(expert_paths) | set(alerts)
    leads: dict[str, dict] = {}
    for lead_id in wanted:
        lead_alerts = alerts.get(lead_id, [])
        expert_score = expert_paths.get(lead_id, 0.0)
        if not lead_alerts and not expert_score:
            continue
        leads[lead_id] = {
            "expert_path_score": round(expert_score, 1),
            "insider_alerts_14d": len(lead_alerts),
            "high_alerts_14d": sum(1 for a in lead_alerts if a.severity == "high"),
        }
    return {
        "leads": leads,
        # Lead Intelligence maps these onto each lead's matched market domains.
        "partner_domains": {d: round(s, 1) for d, s in partner_paths_by_domain(db).items()},
    }
