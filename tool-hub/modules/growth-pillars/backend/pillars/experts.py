"""Pillar 1 - Experts Intro (Curated): warm paths to leads through people we know."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import Expert, IntroRequest, get_db
from hub_clients import fetch_top_leads
from jobs import create_job, run_job_in_thread
from llm_client import chat_json, llm_available
from text_match import lead_domains, normalize_domain, overlap, same_company

router = APIRouter(tags=["experts"])

INTRO_STATUSES = ["draft", "approved", "requested", "introduced", "declined"]
MIN_MATCH_SCORE = 25.0

INTRO_PROMPT = """You help a technical services firm get warm introductions to prospects.
You receive one prospect (with the real signal that makes it relevant) and up to 3 people from
our network who might know them. Pick the single best person and draft a short note TO THAT PERSON
asking whether they'd be open to introducing us.

Rules:
1. Only use facts present in the input. Never invent a relationship, title, or event.
2. Explain in one sentence why this person is the right connector (shared company, domain, etc.).
3. The note: under 110 words, warm and specific, one clear ask, easy to say no.
4. Output JSON: {"expert_id": string, "rationale": string, "subject": string, "body": string}

This is a DRAFT for human review. It will never be sent automatically."""


class ExpertIn(BaseModel):
    full_name: str
    title: Optional[str] = None
    organization: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    domains: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    relationship_strength: int = Field(default=3, ge=1, le=5)
    notes: Optional[str] = None


class ExpertPatch(BaseModel):
    full_name: Optional[str] = None
    title: Optional[str] = None
    organization: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    domains: Optional[list[str]] = None
    companies: Optional[list[str]] = None
    relationship_strength: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None
    active: Optional[bool] = None


class CsvImport(BaseModel):
    csv: str


class MatchRequest(BaseModel):
    lead_limit: int = Field(default=25, ge=1, le=200)
    min_lead_score: float = 0


class IntroPatch(BaseModel):
    status: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


def expert_to_dict(e: Expert) -> dict:
    return {
        "id": str(e.id),
        "full_name": e.full_name,
        "title": e.title,
        "organization": e.organization,
        "email": e.email,
        "linkedin_url": e.linkedin_url,
        "domains": e.domains or [],
        "companies": e.companies or [],
        "relationship_strength": e.relationship_strength,
        "notes": e.notes,
        "active": e.active,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def intro_to_dict(i: IntroRequest, expert: Expert | None) -> dict:
    return {
        "id": str(i.id),
        "lead_id": i.lead_id,
        "lead_name": i.lead_name,
        "expert_id": str(i.expert_id),
        "expert_name": expert.full_name if expert else None,
        "expert_email": expert.email if expert else None,
        "expert_linkedin": expert.linkedin_url if expert else None,
        "match_score": round(i.match_score or 0, 1),
        "rationale": i.rationale,
        "subject": i.subject,
        "body": i.body,
        "status": i.status,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
    }


def score_expert_for_lead(expert: Expert, lead: dict) -> tuple[float, list[str]]:
    """0-100 likelihood that this expert can make a credible intro to the lead."""
    reasons: list[str] = []
    lead_name = lead.get("name") or ""
    lead_domain = normalize_domain(lead.get("domain"))

    company_hit = 0.0
    for company in expert.companies or []:
        if same_company(company, lead_name) or (lead_domain and normalize_domain(company) == lead_domain):
            company_hit = 1.0
            reasons.append(f"knows people at {company}")
            break
    if not company_hit and expert.organization and same_company(expert.organization, lead_name):
        company_hit = 1.0
        reasons.append(f"works at {expert.organization}")

    domains = lead_domains(lead)
    domain_fit = max(
        overlap(expert.domains or [], domains) if domains else 0.0,
        overlap(expert.domains or [], lead.get("description") or "") * 0.8,
    )
    if domain_fit > 0:
        reasons.append(f"active in {', '.join((expert.domains or [])[:2])}")

    strength = (expert.relationship_strength or 3) / 5
    score = 100 * (0.55 * company_hit + 0.30 * min(1.0, domain_fit) + 0.15 * strength)
    if not company_hit and domain_fit == 0:
        score = 0.0
    return round(score, 1), reasons


def _template_draft(expert: Expert, lead: dict, reasons: list[str]) -> dict:
    first = (expert.full_name or "there").split()[0]
    signal = lead.get("signal_type") or "recent activity"
    return {
        "expert_id": str(expert.id),
        "rationale": "; ".join(reasons) or "Domain overlap",
        "subject": f"Quick intro to {lead.get('name')}?",
        "body": (
            f"Hi {first},\n\nWe've been following {lead.get('name')} ({signal}) and think "
            f"{settings.default_company_name} could genuinely help them. Since you {reasons[0] if reasons else 'know this space well'}, "
            "would you be open to a short intro? Totally fine if the timing isn't right.\n\nThanks!"
        ),
    }


def _draft_intro(candidates: list[tuple[Expert, float, list[str]]], lead: dict) -> dict:
    best_expert, _, best_reasons = candidates[0]
    if not llm_available():
        return _template_draft(best_expert, lead, best_reasons)
    payload = {
        "our_company": settings.default_company_name,
        "prospect": {
            "name": lead.get("name"),
            "domain": lead.get("domain"),
            "description": (lead.get("description") or "")[:500],
            "signal_type": lead.get("signal_type"),
            "matched_domains": lead_domains(lead)[:3],
        },
        "candidates": [
            {
                "expert_id": str(e.id),
                "name": e.full_name,
                "title": e.title,
                "organization": e.organization,
                "domains": e.domains,
                "companies": e.companies,
                "relationship_strength_1_to_5": e.relationship_strength,
                "why_matched": reasons,
            }
            for e, _, reasons in candidates
        ],
    }
    try:
        draft = chat_json(f"{INTRO_PROMPT}\n\nInput:\n{json.dumps(payload, default=str)}")
    except Exception:  # noqa: BLE001
        return _template_draft(best_expert, lead, best_reasons)
    valid_ids = {str(e.id) for e, _, _ in candidates}
    if draft.get("expert_id") not in valid_ids or not draft.get("body"):
        return _template_draft(best_expert, lead, best_reasons)
    return draft


def match_leads(db: Session, leads: list[dict]) -> dict:
    experts = db.query(Expert).filter(Expert.active.is_(True)).all()
    if not experts:
        return {"leads_checked": len(leads), "intros_created": 0, "note": "No experts in network yet"}

    created = 0
    for lead in leads:
        lead_id = str(lead.get("id"))
        scored = []
        for expert in experts:
            score, reasons = score_expert_for_lead(expert, lead)
            if score >= MIN_MATCH_SCORE:
                scored.append((expert, score, reasons))
        if not scored:
            continue
        scored.sort(key=lambda x: -x[1])
        top = scored[:3]

        existing = {
            str(i.expert_id)
            for i in db.query(IntroRequest).filter(IntroRequest.lead_id == lead_id).all()
        }
        if str(top[0][0].id) in existing:
            continue

        draft = _draft_intro(top, lead)
        chosen_id = UUID(draft["expert_id"])
        if str(chosen_id) in existing:
            continue
        score = next(s for e, s, _ in top if e.id == chosen_id)
        db.add(IntroRequest(
            lead_id=lead_id,
            lead_name=lead.get("name"),
            expert_id=chosen_id,
            match_score=score,
            rationale=draft.get("rationale"),
            subject=draft.get("subject"),
            body=draft.get("body"),
            status="draft",
        ))
        db.commit()
        created += 1
    return {"leads_checked": len(leads), "intros_created": created}


def match_top_leads(db: Session, lead_limit: int = 25, min_lead_score: float = 0) -> dict:
    return match_leads(db, fetch_top_leads(lead_limit, min_lead_score))


def count_active(db: Session) -> int:
    return db.query(Expert).filter(Expert.active.is_(True)).count()


def count_pending_intros(db: Session) -> int:
    return db.query(IntroRequest).filter(IntroRequest.status == "draft").count()


def expert_paths_by_lead(db: Session) -> dict[str, float]:
    """Best open intro score per lead (declined intros don't count)."""
    best: dict[str, float] = {}
    for intro in db.query(IntroRequest).filter(IntroRequest.status != "declined").all():
        best[intro.lead_id] = max(best.get(intro.lead_id, 0.0), intro.match_score or 0.0)
    return best


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").replace("|", ";").split(";") if v.strip()]


@router.get("/experts")
def list_experts(db: Session = Depends(get_db)):
    experts = db.query(Expert).filter(Expert.active.is_(True)).order_by(Expert.full_name).all()
    return {"experts": [expert_to_dict(e) for e in experts]}


@router.post("/experts")
def create_expert(body: ExpertIn, db: Session = Depends(get_db)):
    expert = Expert(**body.model_dump())
    db.add(expert)
    db.commit()
    db.refresh(expert)
    return expert_to_dict(expert)


@router.post("/experts/import-csv")
def import_experts_csv(body: CsvImport, db: Session = Depends(get_db)):
    """Columns: full_name,title,organization,email,linkedin_url,domains,companies,relationship_strength,notes
    (domains / companies separated by ';')."""
    reader = csv.DictReader(io.StringIO(body.csv.strip()))
    if not reader.fieldnames or "full_name" not in [f.strip() for f in reader.fieldnames]:
        raise HTTPException(400, "CSV needs a header row with at least a full_name column")
    added, skipped = 0, 0
    for row in reader:
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        if not row.get("full_name"):
            skipped += 1
            continue
        try:
            strength = min(5, max(1, int(row.get("relationship_strength") or 3)))
        except ValueError:
            strength = 3
        db.add(Expert(
            full_name=row["full_name"],
            title=row.get("title") or None,
            organization=row.get("organization") or None,
            email=row.get("email") or None,
            linkedin_url=row.get("linkedin_url") or None,
            domains=_split(row.get("domains")),
            companies=_split(row.get("companies")),
            relationship_strength=strength,
            notes=row.get("notes") or None,
        ))
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped}


@router.patch("/experts/{expert_id}")
def update_expert(expert_id: UUID, body: ExpertPatch, db: Session = Depends(get_db)):
    expert = db.get(Expert, expert_id)
    if not expert:
        raise HTTPException(404, "Expert not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(expert, key, value)
    db.commit()
    return expert_to_dict(expert)


@router.delete("/experts/{expert_id}")
def delete_expert(expert_id: UUID, db: Session = Depends(get_db)):
    expert = db.get(Expert, expert_id)
    if not expert:
        raise HTTPException(404, "Expert not found")
    expert.active = False
    db.commit()
    return {"deleted": True}


@router.post("/experts/match")
def run_matching(body: MatchRequest | None = None, db: Session = Depends(get_db)):
    body = body or MatchRequest()
    job = create_job(db, "expert_match")
    run_job_in_thread(job.id, lambda s, _r: match_top_leads(s, body.lead_limit, body.min_lead_score))
    return {"job_id": str(job.id)}


@router.get("/intros")
def list_intros(status: Optional[str] = None, lead_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(IntroRequest)
    if status:
        q = q.filter(IntroRequest.status == status)
    if lead_id:
        q = q.filter(IntroRequest.lead_id == lead_id)
    intros = q.order_by(IntroRequest.match_score.desc(), IntroRequest.created_at.desc()).limit(200).all()
    experts = {e.id: e for e in db.query(Expert).all()}
    return {"intros": [intro_to_dict(i, experts.get(i.expert_id)) for i in intros], "statuses": INTRO_STATUSES}


@router.patch("/intros/{intro_id}")
def update_intro(intro_id: UUID, body: IntroPatch, db: Session = Depends(get_db)):
    intro = db.get(IntroRequest, intro_id)
    if not intro:
        raise HTTPException(404, "Intro not found")
    if body.status is not None:
        if body.status not in INTRO_STATUSES:
            raise HTTPException(400, f"status must be one of {INTRO_STATUSES}")
        intro.status = body.status
    if body.subject is not None:
        intro.subject = body.subject
    if body.body is not None:
        intro.body = body.body
    intro.updated_at = datetime.utcnow()
    db.commit()
    return intro_to_dict(intro, db.get(Expert, intro.expert_id))
