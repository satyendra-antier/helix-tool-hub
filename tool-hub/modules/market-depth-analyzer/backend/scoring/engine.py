"""
Deterministic scoring engine.

Normalization: min-max against the trailing batch of all domains (0-100 scale).
Composite: weighted sum of normalized component scores.
"""

from datetime import datetime, timezone
from sources.base import RawSignal, DomainScore

DEFAULT_WEIGHTS = {
    "hiring_demand": 0.30,
    "capital_flow": 0.25,
    "developer_momentum": 0.20,
    "funding_signal": 0.15,
    "public_interest": 0.10,
}


def normalize_0_to_100(
    signal: RawSignal,
    min_val: float,
    max_val: float,
) -> float:
    if not signal.available or signal.value is None:
        return 0.0
    if max_val == min_val:
        return 50.0
    return max(0.0, min(100.0, ((signal.value - min_val) / (max_val - min_val)) * 100))


def compute_domain_score(
    domain: str,
    domain_id: str,
    track: str,
    signals: dict[str, RawSignal],
    weights: dict[str, float],
    ranges: dict[str, tuple[float, float]],
) -> DomainScore:
    normalized = {
        name: normalize_0_to_100(sig, *ranges.get(name, (0, 1)))
        for name, sig in signals.items()
        if name in weights
    }
    # Only weight signals that returned real data — missing APIs must not penalize a domain
    active_keys = [k for k in normalized if signals[k].available]
    weight_sum = sum(weights.get(k, 0) for k in active_keys)
    composite = (
        sum(normalized[k] * weights.get(k, 0) for k in active_keys) / weight_sum
        if weight_sum > 0
        else 0
    )
    return DomainScore(
        domain=domain,
        domain_id=domain_id,
        track=track,
        composite_score=round(composite, 2),
        components={k: round(v, 2) for k, v in normalized.items()},
        raw_evidence=signals,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


def build_ranges(all_signals: list[dict[str, RawSignal]]) -> dict[str, tuple[float, float]]:
    ranges: dict[str, tuple[float, float]] = {}
    signal_names = DEFAULT_WEIGHTS.keys()
    for name in signal_names:
        values = [
            s[name].value
            for s in all_signals
            if name in s and s[name].available
        ]
        if values:
            ranges[name] = (min(values), max(values))
        else:
            ranges[name] = (0, 1)
    return ranges


def score_all_domains(
    domains: list[dict],
    all_raw: list[tuple[dict, dict[str, RawSignal]]],
    weights: dict[str, float],
) -> list[DomainScore]:
    signal_list = [raw for _, raw in all_raw]
    ranges = build_ranges(signal_list)
    results = []
    for (domain, raw) in all_raw:
        results.append(
            compute_domain_score(
                domain["name"],
                domain["id"],
                domain["track"],
                raw,
                weights,
                ranges,
            )
        )
    return sorted(results, key=lambda x: x.composite_score, reverse=True)
