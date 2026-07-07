from datetime import date
from typing import Optional

DEFAULT_KEYWORDS = [
    "blockchain security", "smart contract audit", "AI agent architecture",
    "multi-agent systems", "fintech compliance", "LLM governance",
    "defi protocol", "layer 2", "inference infrastructure", "web3 growth",
    "stablecoin", "payment rail", "cross-border payments",
]

DEFAULT_WEIGHTS = {
    "recency": 0.12,
    "budget_indicator": 0.14,
    "keyword_fit": 0.14,
    "urgency": 0.10,
    "contact_confidence": 0.08,
    "market_demand_fit": 0.22,
    "capability_fit": 0.20,
}


def recency_decay(signal_date: Optional[date]) -> float:
    if not signal_date:
        return 0.3
    days = (date.today() - signal_date).days
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.8
    if days <= 90:
        return 0.5
    return 0.2


def normalize_budget(value: Optional[float], max_val: float = 50_000_000) -> float:
    if not value or value <= 0:
        return 0.2
    return min(1.0, value / max_val)


def keyword_match_score(description: str, keywords: list[str]) -> float:
    if not description or not keywords:
        return 0.0
    text = description.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text)
    return min(1.0, matches / max(len(keywords) * 0.3, 1))


def deadline_proximity(deadline: Optional[date]) -> float:
    if not deadline:
        return 0.3
    days = (deadline - date.today()).days
    if days < 0:
        return 0.0
    if days <= 5:
        return 1.0
    if days <= 14:
        return 0.8
    if days <= 30:
        return 0.6
    return 0.4


def market_demand_component(best_match: dict | None, orientation: str) -> float:
    if not best_match:
        return 0.2
    mkt = float(best_match.get("market_score") or 0) / 100.0
    opp = float(best_match.get("opportunity_score") or 0) / 100.0
    if orientation == "demand":
        return min(1.0, mkt * 0.5 + opp * 0.5)
    if orientation == "future":
        return min(1.0, mkt * 0.7 + 0.15)
    return min(1.0, mkt * 0.4)


def capability_component(best_match: dict | None, orientation: str) -> float:
    if not best_match:
        return 0.2
    cap = float(best_match.get("capability_score") or 0) / 100.0
    verdict = best_match.get("verdict")
    if orientation == "demand":
        if verdict == "GO":
            return min(1.0, cap + 0.2)
        if verdict == "CONDITIONAL":
            return min(1.0, cap)
        return cap * 0.6
    if orientation == "future":
        # High market but low depth = future opportunity to build
        mkt = float(best_match.get("market_score") or 0) / 100.0
        return min(1.0, max(0.3, mkt * 0.6 - cap * 0.3 + 0.2))
    return cap


def score_lead(
    description: str,
    track: str,
    signal_value: Optional[float],
    signal_date: Optional[date],
    deadline: Optional[date],
    email_verified_score: float,
    keywords: list[str],
    weights: dict[str, float],
    *,
    orientation: str = "generic",
    best_match: dict | None = None,
) -> tuple[float, dict]:
    components = {
        "recency": recency_decay(signal_date),
        "budget_indicator": normalize_budget(signal_value),
        "keyword_fit": keyword_match_score(description, keywords),
        "urgency": deadline_proximity(deadline) if track == "government" else 0.5,
        "contact_confidence": email_verified_score,
        "market_demand_fit": market_demand_component(best_match, orientation),
        "capability_fit": capability_component(best_match, orientation),
    }
    weight_sum = sum(weights.get(k, 0) for k in components)
    composite = (
        sum(components[k] * weights.get(k, 0) for k in components) / weight_sum
        if weight_sum > 0 else 0
    )
    breakdown = {k: round(v * 100, 2) for k, v in components.items()}
    breakdown["orientation"] = orientation
    if best_match:
        breakdown["matched_domain"] = best_match.get("domain_name")
        breakdown["verdict"] = best_match.get("verdict")
        breakdown["market_score"] = round(float(best_match.get("market_score") or 0), 1)
        breakdown["capability_score"] = round(float(best_match.get("capability_score") or 0), 1)
    return round(composite * 100, 2), breakdown
