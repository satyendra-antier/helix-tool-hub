import httpx
from config import settings
from enrichment.contact_policy import (
    allows_inferred_contact,
    is_aggregator_domain,
    is_portal_domain,
    is_synthetic_email,
)


def enrich_entity(name: str, domain: str | None, track: str | None = None) -> list[dict]:
    """Enrich via licensed APIs. No invented emails on gov portals or news sites."""
    contacts: list[dict] = []
    domain = (domain or "").lower().strip().replace("www.", "") or None

    if not domain or is_portal_domain(domain) or is_aggregator_domain(domain):
        return contacts

    if settings.apollo_api_key:
        contacts.extend(_apollo_enrich(name, domain))
    if settings.hunter_api_key and not contacts:
        contacts.extend(_hunter_enrich(domain))
    if settings.clearbit_api_key and not contacts:
        contacts.extend(_clearbit_enrich(domain))

    contacts = [c for c in contacts if not is_synthetic_email(c.get("email"), domain)]

    # Last resort: unverified info@ only for real company domains (not gov/news)
    if not contacts and allows_inferred_contact(domain):
        contacts.append({
            "full_name": None,
            "role_title": "General Inquiry",
            "email": f"info@{domain}",
            "email_verified": False,
            "enrichment_source": "domain-inferred",
            "consent_basis": "unverified-domain-guess",
        })

    return contacts


def _apollo_enrich(name: str, domain: str) -> list[dict]:
    contacts: list[dict] = []
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.apollo.io/v1/mixed_people/search",
                headers={"X-Api-Key": settings.apollo_api_key},
                json={
                    "q_organization_name": name,
                    "q_organization_domains": domain,
                    "page": 1,
                    "per_page": 3,
                },
            )
            if resp.status_code != 200:
                return contacts
            people = resp.json().get("people", [])
            for p in people[:3]:
                email = p.get("email")
                if not email or is_synthetic_email(email, domain):
                    continue
                contacts.append({
                    "full_name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                    "role_title": p.get("title"),
                    "email": email,
                    "email_verified": p.get("email_status") == "verified",
                    "enrichment_source": "apollo",
                    "consent_basis": "licensed-api-apollo",
                })
    except Exception:
        pass
    return contacts


def _hunter_enrich(domain: str) -> list[dict]:
    contacts: list[dict] = []
    if is_portal_domain(domain):
        return contacts
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": settings.hunter_api_key, "limit": 3},
            )
            if resp.status_code != 200:
                return contacts
            for e in resp.json().get("data", {}).get("emails", [])[:3]:
                email = e.get("value")
                if not email or is_synthetic_email(email, domain):
                    continue
                contacts.append({
                    "full_name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                    "role_title": e.get("position"),
                    "email": email,
                    "email_verified": e.get("verification", {}).get("status") == "valid",
                    "enrichment_source": "hunter",
                    "consent_basis": "licensed-api-hunter",
                })
    except Exception:
        pass
    return contacts


def _clearbit_enrich(domain: str) -> list[dict]:
    contacts: list[dict] = []
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"https://company.clearbit.com/v2/companies/find?domain={domain}",
                headers={"Authorization": f"Bearer {settings.clearbit_api_key}"},
            )
            if resp.status_code != 200:
                return contacts
            data = resp.json()
            email = data.get("email")
            if email and not is_synthetic_email(email, domain):
                contacts.append({
                    "full_name": None,
                    "role_title": "Company Contact",
                    "email": email,
                    "email_verified": True,
                    "enrichment_source": "clearbit",
                    "consent_basis": "licensed-api-clearbit",
                })
    except Exception:
        pass
    return contacts
