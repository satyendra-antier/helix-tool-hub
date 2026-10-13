"""Push leads, stage and reply outcome to HubSpot and/or Twenty CRM."""

from __future__ import annotations

import httpx

from config import settings

HUBSPOT_STATUS = {
    "awaiting_approval": "NEW",
    "active": "ATTEMPTED_TO_CONTACT",
    "replied": "CONNECTED",
    "interested": "CONNECTED",
    "meeting": "IN_PROGRESS",
    "snoozed": "OPEN",
    "stopped": "UNQUALIFIED",
    "unsubscribed": "UNQUALIFIED",
    "bounced": "BAD_TIMING",
    "completed": "ATTEMPTED_TO_CONTACT",
}


def configured() -> dict[str, bool]:
    return {
        "hubspot": bool(settings.hubspot_access_token),
        "twenty": bool(settings.twenty_api_url and settings.twenty_api_key),
    }


def _split(name: str | None) -> tuple[str, str]:
    parts = (name or "").strip().split(" ", 1)
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")


def _hubspot(enr) -> str:
    first, last = _split(enr.contact_name)
    props = {
        "email": enr.contact_email,
        "firstname": first,
        "lastname": last,
        "jobtitle": enr.contact_title or "",
        "company": enr.lead_name or "",
        "website": enr.company_domain or "",
        "hs_lead_status": HUBSPOT_STATUS.get(enr.status, "OPEN"),
    }
    headers = {"Authorization": f"Bearer {settings.hubspot_access_token}"}
    base = "https://api.hubapi.com/crm/v3/objects/contacts"
    with httpx.Client(timeout=20, headers=headers) as client:
        resp = client.post(base, json={"properties": props})
        if resp.status_code == 409:
            resp = client.patch(f"{base}/{enr.contact_email}?idProperty=email", json={"properties": props})
        resp.raise_for_status()
    return "ok"


def _twenty(enr) -> str:
    first, last = _split(enr.contact_name)
    headers = {"Authorization": f"Bearer {settings.twenty_api_key}"}
    base = settings.twenty_api_url.rstrip("/")
    with httpx.Client(timeout=20, headers=headers) as client:
        company_id = None
        if enr.lead_name:
            resp = client.post(f"{base}/rest/companies", json={
                "name": enr.lead_name,
                "domainName": {"primaryLinkUrl": f"https://{enr.company_domain}"} if enr.company_domain else None,
            })
            if resp.status_code < 300:
                company_id = (resp.json().get("data") or {}).get("createCompany", {}).get("id")
        person = {
            "name": {"firstName": first, "lastName": last},
            "emails": {"primaryEmail": enr.contact_email},
            "jobTitle": enr.contact_title or "",
        }
        if company_id:
            person["companyId"] = company_id
        resp = client.post(f"{base}/rest/people", json=person)
        if resp.status_code >= 400 and resp.status_code != 409:
            resp.raise_for_status()
    return "ok"


def sync_enrollment(enr) -> dict[str, str]:
    out: dict[str, str] = {}
    cfg = configured()
    for name, fn in (("hubspot", _hubspot), ("twenty", _twenty)):
        if not cfg[name]:
            continue
        try:
            out[name] = fn(enr)
        except Exception as e:  # noqa: BLE001
            out[name] = f"error: {e}"[:200]
    return out
