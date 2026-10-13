"""Free-first contact discovery: company pages -> email pattern guess -> MX/SMTP check -> paid APIs.

Paid lookups (Hunter / Apollo) only run for leads whose score clears `paid_min_score`.
"""

from __future__ import annotations

import re
import smtplib
import socket
from datetime import datetime
from html import unescape

import httpx
from bs4 import BeautifulSoup

from config import settings
from enrichment.contact_policy import (
    GENERIC_LOCALPARTS,
    is_aggregator_domain,
    is_portal_domain,
)

PAGE_PATHS = ("", "/team", "/our-team", "/about", "/about-us", "/leadership", "/company", "/contact", "/contact-us")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TITLE_WORDS = (
    "ceo", "cto", "coo", "cfo", "cmo", "cpo", "founder", "co-founder", "cofounder",
    "president", "vp", "vice president", "head of", "director", "chief", "partner",
    "managing director", "general manager", "lead",
)
NAME_RE = re.compile(r"^[A-Z][a-zA-Z'\-]+(?: [A-Z][a-zA-Z'\-]+){1,2}$")
PATTERNS = ("{f}.{l}", "{f}", "{f}{l}", "{fi}{l}", "{f}_{l}", "{l}")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LeadGenAI/1.0; +contact-discovery)"}


def _clean_domain(domain: str | None) -> str | None:
    d = (domain or "").lower().strip()
    d = d.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    return d or None


def _fetch_pages(domain: str) -> list[tuple[str, str]]:
    pages: list[tuple[str, str]] = []
    with httpx.Client(timeout=8, follow_redirects=True, headers=HEADERS) as client:
        for path in PAGE_PATHS:
            url = f"https://{domain}{path}"
            try:
                resp = client.get(url)
            except Exception:
                continue
            if resp.status_code == 200 and "html" in resp.headers.get("content-type", ""):
                pages.append((url, resp.text[:400_000]))
            if len(pages) >= 5:
                break
    return pages


NOT_NAME_WORDS = {
    "app", "apps", "marketplace", "platform", "contact", "sales", "support", "team", "about",
    "company", "careers", "press", "news", "blog", "privacy", "terms", "policy", "learn", "more",
    "get", "started", "sign", "log", "in", "up", "home", "product", "products", "pricing",
    "solutions", "resources", "partners", "customers", "docs", "developers", "our", "the", "and",
    "us", "inc", "llc", "ltd", "global", "group", "labs", "network", "protocol", "foundation",
}


def _people_from_html(html: str, company: str = "") -> list[dict]:
    """Find 'Name' + adjacent job-title pairs on team/about pages."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [unescape(t).strip() for t in soup.get_text("\n").split("\n")]
    lines = [l for l in lines if 2 < len(l) < 80]
    company_words = {w for w in re.findall(r"[a-z]+", company.lower())}
    people: list[dict] = []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        if not NAME_RE.match(line):
            continue
        words = {w.lower() for w in line.split()}
        if words & NOT_NAME_WORDS or words & company_words or words & set(TITLE_WORDS):
            continue
        title_line = next(
            (
                l for l in lines[i + 1: i + 3]
                if len(l) < 60 and re.search(r"\b(" + "|".join(map(re.escape, TITLE_WORDS)) + r")\b", l.lower())
            ),
            None,
        )
        if not title_line:
            continue
        if line in seen:
            continue
        seen.add(line)
        people.append({"full_name": line, "role_title": title_line})
        if len(people) >= 8:
            break
    return people


def _rank_title(title: str | None) -> int:
    t = (title or "").lower()
    for i, w in enumerate(("ceo", "founder", "cto", "chief", "president", "vp", "head of", "director")):
        if w in t:
            return i
    return 99


def has_mx(domain: str) -> bool:
    try:
        import dns.resolver  # type: ignore

        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        return len(answers) > 0
    except Exception:
        return False


def _mx_host(domain: str) -> str | None:
    try:
        import dns.resolver  # type: ignore

        answers = sorted(dns.resolver.resolve(domain, "MX", lifetime=5), key=lambda r: r.preference)
        return str(answers[0].exchange).rstrip(".")
    except Exception:
        return None


def smtp_probe(email: str) -> bool | None:
    """RCPT TO check. Returns None when the server can't tell us (catch-all, blocked port 25)."""
    if not settings.contact_smtp_probe:
        return None
    host = _mx_host(email.split("@")[-1])
    if not host:
        return False
    try:
        with smtplib.SMTP(host, 25, timeout=8) as smtp:
            smtp.helo("leadgen.local")
            smtp.mail("probe@leadgen.local")
            code, _ = smtp.rcpt(email)
            if code in (250, 251):
                return True
            if code == 550:
                return False
    except (OSError, smtplib.SMTPException, socket.timeout):
        return None
    return None


def guess_emails(full_name: str, domain: str) -> list[str]:
    parts = [p for p in re.sub(r"[^a-zA-Z \-]", "", full_name).lower().split() if p]
    if len(parts) < 2:
        return []
    f, l = parts[0], parts[-1]
    vals = {"f": f, "l": l, "fi": f[0]}
    return [p.format(**vals) + "@" + domain for p in PATTERNS]


def find_contacts(name: str, domain: str | None, *, lead_score: float = 0) -> list[dict]:
    """Return contact dicts shaped like `enrich_entity` output, plus `source_url` and `confidence`."""
    domain = _clean_domain(domain)
    if not domain or is_portal_domain(domain) or is_aggregator_domain(domain):
        return []

    found: list[dict] = []
    pages = _fetch_pages(domain)
    published: set[str] = set()
    people: list[dict] = []
    for url, html in pages:
        decoded = re.sub(r"\\u00([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), html)
        decoded = decoded.replace("&#64;", "@").replace("%40", "@")
        for email in EMAIL_RE.findall(decoded):
            email = email.lower().strip(".")
            if email.endswith("@" + domain) and not email.endswith((".png", ".jpg")):
                published.add(email)
        for p in _people_from_html(html, name):
            p["source_url"] = url
            people.append(p)

    mx_ok = has_mx(domain)
    now = datetime.utcnow().isoformat()

    for email in sorted(published):
        local = email.split("@")[0]
        found.append({
            "full_name": None,
            "role_title": "Published contact" if local in GENERIC_LOCALPARTS else None,
            "email": email,
            "email_verified": mx_ok,
            "enrichment_source": "website",
            "consent_basis": "publicly-listed-company-contact",
            "confidence": 0.9 if mx_ok else 0.6,
            "source_url": next((u for u, h in pages if email in h.lower()), None),
            "verified_at": now if mx_ok else None,
        })

    people.sort(key=lambda p: _rank_title(p.get("role_title")))
    for person in people[:3]:
        candidates = guess_emails(person["full_name"], domain)
        named = next((e for e in published if e.split("@")[0] in {c.split("@")[0] for c in candidates}), None)
        email, verified, confidence = None, False, 0.0
        if named:
            email, verified, confidence = named, mx_ok, 0.95
        elif mx_ok and candidates:
            for cand in candidates[:3]:
                probe = smtp_probe(cand)
                if probe is True:
                    email, verified, confidence = cand, True, 0.85
                    break
                if probe is None and email is None:
                    # Unverifiable guess: first.last is the most common B2B format.
                    email, confidence = candidates[0], 0.5
        if not email:
            continue
        found.append({
            "full_name": person["full_name"],
            "role_title": person.get("role_title"),
            "email": email,
            "email_verified": verified,
            "enrichment_source": "website-pattern" if not named else "website",
            "consent_basis": "publicly-listed-company-contact",
            "confidence": confidence,
            "source_url": person.get("source_url"),
            "verified_at": now if verified else None,
        })

    strong = [c for c in found if c["confidence"] >= 0.8]
    if not strong and lead_score >= settings.paid_lookup_min_score:
        from enrichment import _apollo_enrich, _hunter_enrich

        paid = []
        if settings.hunter_api_key:
            paid = _hunter_enrich(domain)
        if not paid and settings.apollo_api_key:
            paid = _apollo_enrich(name, domain)
        for c in paid:
            c["confidence"] = 0.9 if c.get("email_verified") else 0.6
            c["source_url"] = None
            c["verified_at"] = now if c.get("email_verified") else None
        found.extend(paid)

    unique: dict[str, dict] = {}
    for c in found:
        key = (c.get("email") or "").lower()
        if key and (key not in unique or c["confidence"] > unique[key]["confidence"]):
            unique[key] = c
    return sorted(unique.values(), key=lambda c: -c["confidence"])[:5]
