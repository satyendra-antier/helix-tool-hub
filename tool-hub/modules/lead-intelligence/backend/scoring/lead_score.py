from datetime import date, datetime, timezone
from typing import Optional

DEFAULT_KEYWORDS = [
    "blockchain security", "smart contract audit", "AI agent architecture",
    "multi-agent systems", "fintech compliance", "LLM governance",
    "defi protocol", "layer 2", "inference infrastructure", "web3 growth",
]

DEFAULT_WEIGHTS = {
    "recency": 0.20,
    "budget_indicator": 0.25,
    "keyword_fit": 0.30,
    "urgency": 0.15,
    "contact_confidence": 0.10,
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
    if not description:
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


def score_lead(
    description: str,
    track: str,
    signal_value: Optional[float],
    signal_date: Optional[date],
    deadline: Optional[date],
    email_verified_score: float,
    keywords: list[str],
    weights: dict[str, float],
) -> tuple[float, dict]:
    components = {
        "recency": recency_decay(signal_date),
        "budget_indicator": normalize_budget(signal_value),
        "keyword_fit": keyword_match_score(description, keywords),
        "urgency": deadline_proximity(deadline) if track == "government" else 0.5,
        "contact_confidence": email_verified_score,
    }
    weight_sum = sum(weights.get(k, 0) for k in components)
    composite = (
        sum(components[k] * weights.get(k, 0) for k in components) / weight_sum
        if weight_sum > 0 else 0
    )
    return round(composite * 100, 2), {k: round(v * 100, 2) for k, v in components.items()}
