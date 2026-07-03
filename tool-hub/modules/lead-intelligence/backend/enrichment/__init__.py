import httpx
from config import settings


def enrich_entity(name: str, domain: str | None) -> list[dict]:
    """Enrich via licensed APIs only — Apollo, Hunter, Clearbit. No LinkedIn."""
    contacts: list[dict] = []

    if domain and settings.apollo_api_key:
        contacts.extend(_apollo_enrich(name, domain))
    if domain and settings.hunter_api_key and not contacts:
        contacts.extend(_hunter_enrich(domain))
    if domain and settings.clearbit_api_key and not contacts:
        contacts.extend(_clearbit_enrich(domain))

    if not contacts and domain:
        contacts.append({
            "full_name": None,
            "role_title": "General Inquiry",
            "email": f"info@{domain}",
            "email_verified": False,
            "enrichment_source": "domain-inferred",
            "consent_basis": "publicly-listed-company-contact",
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
                if not email:
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
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": settings.hunter_api_key, "limit": 3},
            )
            if resp.status_code != 200:
                return contacts
            for e in resp.json().get("data", {}).get("emails", [])[:3]:
                contacts.append({
                    "full_name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                    "role_title": e.get("position"),
                    "email": e.get("value"),
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
            contacts.append({
                "full_name": None,
                "role_title": "Company Contact",
                "email": data.get("email") or f"contact@{domain}",
                "email_verified": bool(data.get("email")),
                "enrichment_source": "clearbit",
                "consent_basis": "licensed-api-clearbit",
            })
    except Exception:
        pass
    return contacts
