"""Discovery readiness — Market Depth + Build Readiness must be fresh for aligned leads."""

from __future__ import annotations

from sqlalchemy.orm import Session

from intelligence_bridge import build_intelligence_context


def get_pipeline_status(db: Session) -> dict:
    ctx = build_intelligence_context(db)
    demand = ctx.get("demand_domains") or []
    future = ctx.get("future_domains") or []

    market_ready = ctx.get("market_ready", False)
    verdicts_ready = ctx.get("verdicts_ready", False)
    can_discover = market_ready

    stale_warning = None
    if market_ready and not verdicts_ready:
        stale_warning = (
            "Market data available but no Build Readiness verdicts — "
            "run Fit Analysis for demand/future orientation"
        )
    elif not market_ready:
        stale_warning = "Refresh Market Depth Analyzer before discovery for aligned scoring"

    latest_fetch = None
    for m in (ctx.get("market_domains") or {}).values():
        if m.get("fetched_at") and (not latest_fetch or m["fetched_at"] > latest_fetch):
            latest_fetch = m["fetched_at"]

    return {
        "direction": "market_demand → company_strengths → lead_orientation",
        "orientations": {
            "demand": {
                "label": "Demand-oriented",
                "description": "Hot market + proven depth (GO / strong CONDITIONAL)",
                "domain_count": len(demand),
                "top_domains": [d["domain_name"] for d in demand[:5]],
            },
            "future": {
                "label": "Future-oriented",
                "description": "Hot market + capability gap (growth opportunity)",
                "domain_count": len(future),
                "top_domains": [d["domain_name"] for d in future[:5]],
            },
        },
        "steps": [
            {
                "step": 1,
                "name": "Market Depth",
                "description": "Live demand signals across tracked domains",
                "ready": market_ready,
                "latest_at": latest_fetch,
                "stats": {"domains": len(ctx.get("market_domains") or {})},
                "action": "Refresh in Market Depth Analyzer",
                "tool_route": "/tools/market-depth-analyzer",
            },
            {
                "step": 2,
                "name": "Build Readiness",
                "description": "Company capabilities + GO/NO_GO verdicts per domain",
                "ready": verdicts_ready,
                "stats": {
                    "verdicts": len(ctx.get("verdicts") or {}),
                    "capabilities": len(ctx.get("capabilities") or []),
                    "demand_domains": len(demand),
                    "future_domains": len(future),
                },
                "action": "Index website + Run Fit Analysis",
                "tool_route": "/tools/build-readiness",
            },
            {
                "step": 3,
                "name": "Lead Discovery",
                "description": "Score leads against demand + future domain fit",
                "ready": can_discover,
                "action": "Run Discovery (auto-syncs keywords from GO + future domains)",
            },
        ],
        "can_discover": can_discover,
        "aligned_scoring": market_ready and verdicts_ready,
        "stale_warning": stale_warning,
        "sync_keywords_preview": (ctx.get("sync_keywords") or [])[:12],
    }
