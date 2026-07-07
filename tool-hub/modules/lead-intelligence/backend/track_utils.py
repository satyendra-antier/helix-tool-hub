"""Normalize tracks between Market Depth (blockchain) and Lead Intelligence (web3)."""

from __future__ import annotations

LEAD_TRACKS = frozenset({"government", "web3", "web2", "ai"})

TRACK_ALIASES: dict[str, list[str]] = {
    "web3": ["web3", "blockchain"],
    "blockchain": ["web3", "blockchain"],
    "ai": ["ai"],
    "government": ["government"],
    "web2": ["web2"],
}


def normalize_lead_track(track: str | None) -> str:
    if not track:
        return "web2"
    t = track.lower().strip()
    if t in ("blockchain", "web3", "crypto", "defi"):
        return "web3"
    if t in LEAD_TRACKS:
        return t
    return "web2"


def track_filter_values(track: str) -> list[str]:
    """Expand UI track filter to DB values."""
    t = track.lower().strip()
    return TRACK_ALIASES.get(t, [t])
