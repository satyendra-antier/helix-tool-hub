from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class RawLead:
    name: str
    track: str
    domain: Optional[str]
    description: str
    source: str
    signal_type: str
    signal_value: Optional[float] = None
    signal_date: Optional[date] = None
    deadline: Optional[date] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
