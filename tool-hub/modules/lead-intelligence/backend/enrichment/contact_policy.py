"""Which domains get real contact enrichment vs portal-only leads."""

from __future__ import annotations

# Government procurement portals — never invent info@ emails
PORTAL_DOMAINS = frozenset({
    "grants.gov", "sam.gov", "gem.gov.in", "eprocure.gov.in",
    "ted.europa.eu", "worldbank.org", "bidplus.gem.gov.in",
    "cppp", "eprocure.gov.in",
})

# News / RSS / aggregators — not outreach targets
AGGREGATOR_DOMAINS = frozenset({
    "news.crunchbase.com", "www.coindesk.com", "coindesk.com",
    "cointelegraph.com", "decrypt.co", "techcrunch.com",
})

GENERIC_LOCALPARTS = ("info", "contact", "hello", "sales", "support", "admin")


def _norm(domain: str | None) -> str | None:
    if not domain:
        return None
    d = domain.lower().strip().replace("www.", "")
    return d or None


def is_portal_domain(domain: str | None) -> bool:
    d = _norm(domain)
    if not d:
        return True
    if d in PORTAL_DOMAINS:
        return True
    if d.endswith(".gov") or d.endswith(".gov.in") or d.endswith(".mil"):
        return True
    if "europa.eu" in d and "ted" in d:
        return True
    return False


def is_aggregator_domain(domain: str | None) -> bool:
    d = _norm(domain)
    return bool(d and d in AGGREGATOR_DOMAINS)


def allows_inferred_contact(domain: str | None) -> bool:
    """Only private company sites may get a cautious info@ fallback."""
    d = _norm(domain)
    if not d or is_portal_domain(d) or is_aggregator_domain(d):
        return False
    if d.endswith(".gov") or d.endswith(".edu"):
        return False
    return True


def is_synthetic_email(email: str | None, domain: str | None) -> bool:
    """Detect guessed info@domain rows that should not be stored."""
    if not email or not domain:
        return False
    d = _norm(domain)
    local, _, host = email.lower().partition("@")
    if host != d:
        return False
    return local in GENERIC_LOCALPARTS
