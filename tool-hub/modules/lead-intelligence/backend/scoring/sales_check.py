"""BANT + MEDDIC style sales check and a one-line "why this lead" reason.

The rule-based version always runs (no API key needed). `ai_explain` refines it with the LLM.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional

EXEC_WORDS = ("ceo", "founder", "cto", "coo", "cfo", "chief", "president", "owner", "managing director")
MANAGER_WORDS = ("vp", "vice president", "head of", "director", "lead", "manager")


def _authority(contacts: list[dict]) -> float:
    best = 0.0
    for c in contacts:
        t = (c.get("role_title") or "").lower()
        if any(w in t for w in EXEC_WORDS):
            best = max(best, 1.0)
        elif any(w in t for w in MANAGER_WORDS):
            best = max(best, 0.7)
        elif c.get("email"):
            best = max(best, 0.3)
    return best


def _timeline(signal_date: Optional[date], deadline: Optional[date]) -> float:
    today = date.today()
    if deadline:
        days = (deadline - today).days
        if days < 0:
            return 0.0
        return 1.0 if days <= 30 else 0.7 if days <= 90 else 0.4
    if signal_date:
        days = (today - signal_date).days
        return 1.0 if days <= 14 else 0.7 if days <= 45 else 0.4 if days <= 120 else 0.2
    return 0.3


def _money(v: Optional[float]) -> str:
    if not v:
        return ""
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


def rule_sales_check(
    *,
    name: str,
    signal_type: Optional[str],
    signal_value: Optional[float],
    signal_date: Optional[date],
    deadline: Optional[date],
    breakdown: dict,
    best_match: Optional[dict],
    contacts: list[dict],
) -> tuple[dict, str]:
    budget = min(1.0, (signal_value or 0) / 5_000_000) if signal_value else (0.5 if signal_type in ("funding", "tender") else 0.2)
    authority = _authority(contacts)
    need = max(float(breakdown.get("keyword_fit", 0)), float(breakdown.get("market_demand_fit", 0))) / 100
    timeline = _timeline(signal_date, deadline)
    champion = 1.0 if authority >= 0.7 else 0.4 if contacts else 0.0
    pain = need
    bant = {"budget": budget, "authority": authority, "need": need, "timeline": timeline}
    meddic = {
        "metrics": budget,
        "economic_buyer": authority,
        "identify_pain": pain,
        "champion": champion,
    }
    score = round((sum(bant.values()) / 4 * 0.6 + sum(meddic.values()) / 4 * 0.4) * 100, 1)
    gaps = [k.replace("_", " ") for k, v in {**bant, "champion": champion}.items() if v < 0.4]

    reason_parts: list[str] = []
    sig = (signal_type or "signal").replace("_", " ").lower()
    money = _money(signal_value)
    when = ""
    if signal_date:
        days = (date.today() - signal_date).days
        when = "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"
    if deadline:
        reason_parts.append(f"open tender{' worth ' + money if money else ''}, due {deadline.isoformat()}")
    elif "fund" in sig or "raise" in sig:
        reason_parts.append(f"raised {money or 'funding'} {when}".strip())
    elif "hir" in sig or "job" in sig:
        reason_parts.append(f"is hiring for this work {when}".strip())
    elif sig in ("protocol", "tvl", "defi"):
        reason_parts.append(f"has {money} locked on-chain (TVL)" if money else "runs a live on-chain protocol")
    elif money or when:
        reason_parts.append(f"{sig} signal{' of ' + money if money else ''} {when}".strip())
    if best_match and best_match.get("domain_name"):
        verdict = best_match.get("verdict")
        reason_parts.append(
            f"fits our {best_match['domain_name']} market"
            + (f" (we're a {verdict})" if verdict else "")
        )
    if authority >= 1.0:
        reason_parts.append("we have a decision-maker contact")
    if len(reason_parts) > 1:
        joined = ", ".join(reason_parts[:-1]) + " and " + reason_parts[-1]
    else:
        joined = reason_parts[0] if reason_parts else ""
    reason = f"{name} {joined}." if joined else f"{name} matches our target keywords."

    check = {
        "score": score,
        "bant": {k: round(v * 100) for k, v in bant.items()},
        "meddic": {k: round(v * 100) for k, v in meddic.items()},
        "gaps": gaps,
        "method": "rules",
    }
    return check, reason


AI_PROMPT = """You qualify a B2B lead for a technology services company. Use ONLY the facts in the JSON.
Return JSON:
{
  "fit_reason": "one plain sentence (max 30 words) on why this lead fits right now",
  "bant": {"budget": 0-100, "authority": 0-100, "need": 0-100, "timeline": 0-100},
  "meddic": {"metrics": 0-100, "economic_buyer": 0-100, "identify_pain": 0-100, "champion": 0-100},
  "gaps": ["what we still need to learn"],
  "questions": ["2-3 discovery questions to ask"]
}
Never invent facts not present in the input."""


def ai_explain(lead: dict) -> tuple[dict, str] | None:
    from config import settings
    from llm_client import chat, parse_json

    if not settings.resolve_api_key():
        return None
    try:
        out = parse_json(chat(f"{AI_PROMPT}\n\nLead:\n{json.dumps(lead, default=str)[:6000]}", json_mode=True))
    except Exception:
        return None
    bant = out.get("bant") or {}
    meddic = out.get("meddic") or {}
    vals_b = [float(v) for v in bant.values() if isinstance(v, (int, float))]
    vals_m = [float(v) for v in meddic.values() if isinstance(v, (int, float))]
    if not vals_b:
        return None
    score = round((sum(vals_b) / len(vals_b)) * 0.6 + ((sum(vals_m) / len(vals_m)) if vals_m else 0) * 0.4, 1)
    check = {
        "score": score,
        "bant": bant,
        "meddic": meddic,
        "gaps": out.get("gaps") or [],
        "questions": out.get("questions") or [],
        "method": "ai",
    }
    return check, (out.get("fit_reason") or "").strip()
