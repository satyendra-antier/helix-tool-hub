"""Filter junk / aggregate articles — keep actionable company-level leads."""

from __future__ import annotations

import re

from sources.base import RawLead
from text_utils import clean_description

AGGREGATE_PATTERNS = [
    r"the week'?s?\s+\d+\s+biggest",
    r"biggest funding rounds",
    r"\d+\s+biggest funding",
    r"funding rounds:",
    r"roundup",
    r"weekly (digest|roundup)",
    r"top \d+ (funding|startups|deals)",
    r"global startup investment",
    r"crunchbase data:",
    r"this week in",
    r"newsletter",
    r"market wrap",
    r"daily digest",
]

COMPANY_RAISE_SEPARATORS = [
    " Raises ", " raises ", " Lands ", " lands ",
    " Secures ", " secures ", " Closes ", " closes ",
    " Bags ", " bags ", " Nabs ", " nabs ",
]

JUNK_EXACT_NAMES = {
    "discussion", "search", "home", "login", "register",
    "select sorting option", "mis reports tenders by location tenders",
    "eprocurement system government of india",
}

PORTAL_NAME_PREFIXES = (
    "cppp:", "gem tender:",
)


def is_aggregate_title(text: str) -> bool:
    if not text or len(text.strip()) < 3:
        return True
    t = text.lower().strip()
    for pat in AGGREGATE_PATTERNS:
        if re.search(pat, t):
            return True
    if len(t) > 72 and not any(sep.lower() in t for sep in COMPANY_RAISE_SEPARATORS):
        if "?" not in t and t.count(",") >= 2:
            return True
    return False


def extract_company_from_headline(title: str) -> str | None:
    if is_aggregate_title(title):
        return None
    for sep in COMPANY_RAISE_SEPARATORS:
        if sep in title:
            company = title.split(sep)[0].strip()
            if company and len(company) >= 2 and not is_aggregate_title(company):
                return company[:200]
    if len(title) <= 72 and not is_aggregate_title(title):
        return title.strip()[:200]
    return None


def is_valid_lead_name(name: str) -> bool:
    if not name or len(name.strip()) < 2:
        return False
    n = name.strip()
    nl = n.lower()
    if nl in JUNK_EXACT_NAMES:
        return False
    if any(nl.startswith(p.lower()) for p in PORTAL_NAME_PREFIXES) and len(n) > 120:
        return False
    if is_aggregate_title(n):
        return False
    if n.count("|") >= 2 and len(n) > 150:
        return False
    return True


def is_valid_lead(raw: RawLead) -> bool:
    name = (raw.name or "").strip()
    desc = (raw.description or "").strip()
    if not is_valid_lead_name(name):
        return False
    if desc and is_aggregate_title(desc) and name.lower() == desc.lower():
        return False
    if raw.source == "crunchbase_rss" and is_aggregate_title(name):
        return False
    if raw.source in ("crunchbase_rss", "news.crunchbase.com"):
        if not extract_company_from_headline(name) and not extract_company_from_headline(desc):
            return False
    return True


def sanitize_raw_lead(raw: RawLead) -> RawLead | None:
    if raw.source == "crunchbase_rss":
        title = (raw.raw_payload or {}).get("title") or raw.description
        company = extract_company_from_headline(title or raw.name)
        if not company:
            return None
        raw.name = company
        raw.description = clean_description(title or company, 500)
    elif raw.signal_type in ("funding", "news") and is_aggregate_title(raw.name):
        company = extract_company_from_headline(raw.description or raw.name)
        if not company:
            return None
        raw.name = company

    if not is_valid_lead(raw):
        return None
    return raw


def entity_is_junk(name: str, description: str | None = None) -> bool:
    """Check stored entity — for pruning existing bad leads."""
    if not is_valid_lead_name(name):
        return True
    if description and is_aggregate_title(description) and name.lower() == description.lower():
        return True
    if is_aggregate_title(name):
        return True
    return False
