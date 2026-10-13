"""Pillar 3 - Channel Partners: firms that can refer deals in the domains we can win."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import ChannelPartner, get_db
from hub_clients import go_domains, ingest_partner_lead
from jobs import create_job, run_job_in_thread
from llm_client import chat_json, llm_available
from text_match import normalize_domain, overlap

router = APIRouter(tags=["partners"])

STAGES = ["prospect", "talking", "signed", "dropped"]
PARTNER_TYPES = ["agency", "consultancy", "integrator", "vc_platform", "accelerator", "other"]
TYPE_WEIGHT = {
    "consultancy": 1.0, "integrator": 1.0, "vc_platform": 0.9, "accelerator": 0.85,
    "agency": 0.8, "other": 0.5,
}

DISCOVER_PROMPT = """We are {company}, a technical services firm that builds in these domains:
{domains}

Suggest real, currently operating firms that could REFER clients to us in these domains because
they serve the same buyers but do NOT build what we build (they are complementary, not competitors).
Good examples: strategy / Big-4 style advisory, design & product agencies, cloud or SaaS integrators,
VC platform teams, accelerators, compliance/legal firms, ecosystem foundations.

Rules:
1. Only name firms you are confident exist. Include their main website URL.
2. Up to {per_domain} firms per domain. No duplicates across domains.
3. Output JSON: {{"partners": [{{"name": str, "website": str, "partner_type": one of {types},
   "services": [str], "domain": str (one of the domains above), "why": str}}]}}"""


class PartnerIn(BaseModel):
    name: str
    website: Optional[str] = None
    partner_type: str = "other"
    services: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class PartnerPatch(BaseModel):
    stage: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    services: Optional[list[str]] = None
    domains: Optional[list[str]] = None


class DiscoverRequest(BaseModel):
    per_domain: int = Field(default=4, ge=1, le=10)
    max_domains: int = Field(default=6, ge=1, le=20)


class ReferralIn(BaseModel):
    company_name: str
    domain: Optional[str] = None
    description: str = ""
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    track: str = "web2"


def partner_to_dict(p: ChannelPartner) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "website": p.website,
        "partner_type": p.partner_type,
        "services": p.services or [],
        "domains": p.domains or [],
        "fit_score": round(p.fit_score or 0, 1),
        "fit_reasons": p.fit_reasons or [],
        "verified": p.verified,
        "source": p.source,
        "stage": p.stage,
        "contact_name": p.contact_name,
        "contact_email": p.contact_email,
        "notes": p.notes,
        "referrals_received": p.referrals_received or 0,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def verify_website(url: str | None) -> bool:
    if not url:
        return False
    if not url.startswith("http"):
        url = f"https://{url}"
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "ToolHub-PartnerCheck/1.0"})
        return resp.status_code < 400
    except httpx.HTTPError:
        return False


def score_partner(partner: ChannelPartner, winnable: list[str]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    domains = partner.domains or []
    covered = [d for d in domains if d in winnable]
    relevance = min(1.0, len(covered) / 2) if covered else 0.3
    if covered:
        reasons.append(f"serves buyers in {', '.join(covered[:2])}")

    # High overlap between their services and our domains means they likely compete with us.
    competition = overlap(partner.services or [], winnable)
    complementarity = 1.0 - min(1.0, competition * 1.5)
    if complementarity >= 0.7:
        reasons.append("complementary services (low competition)")
    elif complementarity < 0.4:
        reasons.append("services overlap with ours, may compete")

    type_weight = TYPE_WEIGHT.get(partner.partner_type or "other", 0.5)
    if partner.verified:
        reasons.append("website verified")
    score = 100 * (0.4 * relevance + 0.3 * complementarity + 0.2 * (1.0 if partner.verified else 0.0) + 0.1 * type_weight)
    return round(score, 1), reasons


def _find_existing(db: Session, name: str, website: str | None) -> ChannelPartner | None:
    host = normalize_domain(website)
    for p in db.query(ChannelPartner).all():
        if p.name.strip().lower() == name.strip().lower():
            return p
        if host and normalize_domain(p.website) == host:
            return p
    return None


def discover_partners(db: Session, per_domain: int = 4, max_domains: int = 6) -> dict:
    winnable = go_domains()[:max_domains]
    if not winnable:
        return {"added": 0, "note": "No market domains yet. Refresh Market Depth and run Build Readiness first."}
    if not llm_available():
        return {"added": 0, "note": "Partner discovery needs an OpenAI key. You can still add partners manually."}

    prompt = DISCOVER_PROMPT.format(
        company=settings.default_company_name,
        domains="\n".join(f"- {d}" for d in winnable),
        per_domain=per_domain,
        types=PARTNER_TYPES,
    )
    suggestions = chat_json(prompt).get("partners") or []

    added, merged = 0, 0
    for s in suggestions:
        name = (s.get("name") or "").strip()
        if not name:
            continue
        domain = s.get("domain") if s.get("domain") in winnable else None
        existing = _find_existing(db, name, s.get("website"))
        if existing:
            if domain and domain not in (existing.domains or []):
                existing.domains = [*(existing.domains or []), domain]
                merged += 1
            continue
        partner_type = s.get("partner_type") if s.get("partner_type") in PARTNER_TYPES else "other"
        db.add(ChannelPartner(
            name=name[:200],
            website=s.get("website"),
            partner_type=partner_type,
            services=[str(x) for x in (s.get("services") or [])][:8],
            domains=[domain] if domain else [],
            notes=s.get("why"),
            source="ai_suggested",
            verified=verify_website(s.get("website")),
        ))
        added += 1
    db.commit()
    rescored = rescore_partners(db, winnable)
    return {"domains": winnable, "suggested": len(suggestions), "added": added, "merged": merged, "rescored": rescored}


def rescore_partners(db: Session, winnable: list[str] | None = None) -> int:
    winnable = winnable if winnable is not None else go_domains()
    partners = db.query(ChannelPartner).all()
    for p in partners:
        p.fit_score, p.fit_reasons = score_partner(p, winnable)
    db.commit()
    return len(partners)


def count_partners(db: Session) -> int:
    return db.query(ChannelPartner).filter(ChannelPartner.stage != "dropped").count()


def partner_paths_by_domain(db: Session) -> dict[str, float]:
    """Best fit score of an active (talking/signed) partner per market domain."""
    best: dict[str, float] = {}
    for p in db.query(ChannelPartner).filter(ChannelPartner.stage.in_(["talking", "signed"])).all():
        weight = 1.0 if p.stage == "signed" else 0.6
        for d in p.domains or []:
            best[d] = max(best.get(d, 0.0), (p.fit_score or 0) * weight)
    return best


@router.get("/partners")
def list_partners(stage: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(ChannelPartner)
    if stage:
        q = q.filter(ChannelPartner.stage == stage)
    partners = q.order_by(ChannelPartner.fit_score.desc()).all()
    return {"partners": [partner_to_dict(p) for p in partners], "stages": STAGES, "types": PARTNER_TYPES}


@router.post("/partners")
def create_partner(body: PartnerIn, db: Session = Depends(get_db)):
    if _find_existing(db, body.name, body.website):
        raise HTTPException(409, "Partner already exists")
    data = body.model_dump()
    if data["partner_type"] not in PARTNER_TYPES:
        data["partner_type"] = "other"
    partner = ChannelPartner(**data, source="manual", verified=verify_website(body.website))
    partner.fit_score, partner.fit_reasons = score_partner(partner, go_domains())
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner_to_dict(partner)


@router.patch("/partners/{partner_id}")
def update_partner(partner_id: UUID, body: PartnerPatch, db: Session = Depends(get_db)):
    partner = db.get(ChannelPartner, partner_id)
    if not partner:
        raise HTTPException(404, "Partner not found")
    data = body.model_dump(exclude_unset=True)
    if "stage" in data and data["stage"] not in STAGES:
        raise HTTPException(400, f"stage must be one of {STAGES}")
    for key, value in data.items():
        setattr(partner, key, value)
    partner.updated_at = datetime.utcnow()
    db.commit()
    return partner_to_dict(partner)


@router.delete("/partners/{partner_id}")
def delete_partner(partner_id: UUID, db: Session = Depends(get_db)):
    partner = db.get(ChannelPartner, partner_id)
    if not partner:
        raise HTTPException(404, "Partner not found")
    db.delete(partner)
    db.commit()
    return {"deleted": True}


@router.post("/partners/discover")
def discover_endpoint(body: DiscoverRequest | None = None, db: Session = Depends(get_db)):
    body = body or DiscoverRequest()
    job = create_job(db, "partner_discover")
    run_job_in_thread(job.id, lambda s, _r: discover_partners(s, body.per_domain, body.max_domains))
    return {"job_id": str(job.id)}


@router.post("/partners/rescore")
def rescore_endpoint(db: Session = Depends(get_db)):
    return {"rescored": rescore_partners(db)}


@router.post("/partners/{partner_id}/referrals")
def register_referral(partner_id: UUID, body: ReferralIn, db: Session = Depends(get_db)):
    """A partner referred a deal: push it into Lead Intelligence as a partner-sourced lead."""
    partner = db.get(ChannelPartner, partner_id)
    if not partner:
        raise HTTPException(404, "Partner not found")
    result = ingest_partner_lead({
        "name": body.company_name,
        "domain": body.domain,
        "description": body.description or f"Referred by {partner.name}",
        "track": body.track,
        "source": "partner",
        "signal_type": "referral",
        "contact_name": body.contact_name,
        "contact_email": body.contact_email,
        "raw_payload": {
            "partner_id": str(partner.id),
            "partner_name": partner.name,
            "referred_at": datetime.utcnow().isoformat(),
        },
    })
    if result is None:
        raise HTTPException(502, "Lead Intelligence did not accept the referral")
    partner.referrals_received = (partner.referrals_received or 0) + 1
    if partner.stage == "prospect":
        partner.stage = "talking"
    db.commit()
    return {"lead": result, "partner": partner_to_dict(partner)}
