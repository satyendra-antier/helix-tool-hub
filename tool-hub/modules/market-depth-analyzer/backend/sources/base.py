from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RawSignal:
    source: str
    value: float
    unit: str
    raw_data: dict[str, Any] = field(default_factory=dict)
    available: bool = True
    note: Optional[str] = None


@dataclass
class DomainScore:
    domain: str
    domain_id: str
    track: str
    composite_score: float
    components: dict[str, float]
    raw_evidence: dict[str, RawSignal]
    computed_at: str
