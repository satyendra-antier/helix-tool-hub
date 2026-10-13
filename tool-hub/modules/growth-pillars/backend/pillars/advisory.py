"""Pillar 5 - Sales Advisory: next best action, talking points, objections and deal risk per lead."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import ChannelPartner, Expert, InsiderAlert, IntroRequest, SalesAdvice, get_db
from hub_clients import fetch_lead, fetch_top_leads
from jobs import create_job, run_job_in_thread
from llm_client import chat_json, llm_available
from text_match import lead_domains

router = APIRouter(tags=["advisory"])

PATHS = ["direct", "expert_intro", "partner", "nurture"]
RISKS = ["low", "medium", "high"]

ADVISORY_PROMPT = """You are a senior B2B sales advisor for {company}, a technical services firm.
Given everything we know about one lead, tell the account owner exactly what to do next.

Rules:
1. Use only facts in the input. If something is unknown, say so instead of guessing.
2. recommended_path: "expert_intro" if a warm intro path exists and is credible, "partner" if an active
   channel partner covers this domain, "direct" if we have a reachable contact and a clear signal,
   otherwise "nurture".
3. deal_risk reflects capability fit (verdict), signal strength, contact access and timing.
4. Output JSON:
{{"next_best_action": str (one or two sentences, concrete, with who/what/when),
  "recommended_path": one of {paths},
  "talking_points": [str] (3-5, each tied to a real signal or strength),
  "objections": [{{"objection": str, "response": str}}] (2-4),
  "deal_risk": one of {risks},
  "risk_reasons": [str] (1-4)}}"""


class BatchRequest(BaseModel):
    top_n: int = Field(default=10, ge=1, le=50)
    min_lead_score: float = 0


def advice_to_dict(a: SalesAdvice) -> dict:
    return {
        "id": str(a.id),
        "lead_id": a.lead_id,
        "lead_name": a.lead_name,
        "next_best_action": a.next_best_action,
        "recommended_path": a.recommended_path,
        "talking_points": a.talking_points or [],
        "objections": a.objections or [],
        "deal_risk": a.deal_risk,
        "risk_reasons": a.risk_reasons or [],
        "inputs": a.inputs or {},
        "generated_by": a.generated_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def gather_context(db: Session, lead: dict) -> dict:
    lead_id = str(lead.get("id"))
    domains = lead_domains(lead)
    ctx = lead.get("domain_context") or {}

    since = datetime.utcnow() - timedelta(days=30)
    alerts = (
        db.query(InsiderAlert)
        .filter(InsiderAlert.lead_id == lead_id, InsiderAlert.created_at >= since)
        .order_by(InsiderAlert.created_at.desc())
        .limit(8)
        .all()
    )
    intros = (
        db.query(IntroRequest)
        .filter(IntroRequest.lead_id == lead_id, IntroRequest.status != "declined")
        .order_by(IntroRequest.match_score.desc())
        .limit(3)
        .all()
    )
    experts = {e.id: e for e in db.query(Expert).filter(Expert.id.in_([i.expert_id for i in intros])).all()} if intros else {}
    partners = [
        p for p in db.query(ChannelPartner).filter(ChannelPartner.stage.in_(["talking", "signed"])).all()
        if set(p.domains or []) & set(domains)
    ]

    days_to_deadline = None
    if lead.get("deadline"):
        try:
            days_to_deadline = (date.fromisoformat(lead["deadline"][:10]) - date.today()).days
        except ValueError:
            pass

    return {
        "lead": {
            "id": lead_id,
            "name": lead.get("name"),
            "track": lead.get("track"),
            "domain": lead.get("domain"),
            "description": (lead.get("description") or "")[:600],
            "signal_type": lead.get("signal_type"),
            "signal_value": lead.get("signal_value"),
            "score": lead.get("score"),
            "stage": lead.get("stage"),
            "orientation": lead.get("lead_orientation"),
            "days_to_deadline": days_to_deadline,
            "is_government_tender": bool(lead.get("is_portal_lead")),
        },
        "fit": {
            "matched_domains": domains[:3],
            "verdict": ctx.get("verdict"),
            "market_score": ctx.get("market_score"),
            "capability_score": ctx.get("capability_score"),
            "our_strengths": (ctx.get("our_strengths") or [])[:5],
            "gaps": (ctx.get("gaps") or [])[:4],
        },
        "contacts": [
            {"name": c.get("full_name"), "role": c.get("role_title"), "has_email": bool(c.get("email")),
             "verified": c.get("email_verified")}
            for c in (lead.get("contacts") or [])[:5]
        ],
        "insider_alerts": [{"type": a.alert_type, "severity": a.severity, "title": a.title} for a in alerts],
        "expert_paths": [
            {"expert": experts[i.expert_id].full_name if i.expert_id in experts else None,
             "match_score": i.match_score, "status": i.status, "why": i.rationale}
            for i in intros
        ],
        "partner_paths": [
            {"partner": p.name, "stage": p.stage, "fit_score": p.fit_score} for p in partners[:3]
        ],
    }


def heuristic_advice(ctx: dict) -> dict:
    lead, fit = ctx["lead"], ctx["fit"]
    name = lead.get("name") or "this lead"
    has_contact = any(c.get("has_email") for c in ctx["contacts"])
    strong_intro = next(
        (p for p in ctx["expert_paths"] if p["status"] in ("approved", "requested", "introduced") or (p["match_score"] or 0) >= 50),
        None,
    )
    partner = ctx["partner_paths"][0] if ctx["partner_paths"] else None

    if strong_intro:
        path = "expert_intro"
        action = f"Ask {strong_intro['expert']} for a warm intro to {name} this week, citing the latest signal."
    elif partner:
        path = "partner"
        action = f"Brief {partner['partner']} on {name} and ask whether they can co-pitch or refer us."
    elif has_contact:
        path = "direct"
        action = f"Send the personalised outreach to the best contact at {name} within 48 hours."
    else:
        path = "nurture"
        action = f"Find a named decision-maker at {name} (Apollo/Hunter or LinkedIn) before reaching out."

    risk_points = 0
    reasons: list[str] = []
    verdict = fit.get("verdict")
    if verdict == "NO_GO":
        risk_points += 2
        reasons.append("Build Readiness says NO_GO for this domain (capability gap)")
    elif verdict == "GO":
        risk_points -= 1
    elif not verdict:
        risk_points += 1
        reasons.append("No fit verdict for this domain yet")
    if not has_contact and not strong_intro:
        risk_points += 1
        reasons.append("No reachable contact or warm path")
    dtd = lead.get("days_to_deadline")
    if dtd is not None and dtd <= 5:
        risk_points += 1
        reasons.append(f"Deadline in {dtd} day(s)")
    if (lead.get("score") or 0) >= 70:
        risk_points -= 1
    if any(a["severity"] == "high" for a in ctx["insider_alerts"]):
        risk_points -= 1
    risk = "high" if risk_points >= 2 else "low" if risk_points <= -1 else "medium"

    points = []
    if lead.get("signal_type"):
        points.append(f"Reference their {lead['signal_type']} signal: {lead.get('description', '')[:140]}")
    for s in fit.get("our_strengths") or []:
        points.append(f"Our strength: {s}" if isinstance(s, str) else f"Our strength: {json.dumps(s)[:120]}")
    for a in ctx["insider_alerts"][:2]:
        points.append(f"Recent: {a['title']}")

    return {
        "next_best_action": action,
        "recommended_path": path,
        "talking_points": points[:5] or ["Lead with the specific signal that made them relevant now"],
        "objections": [
            {"objection": "We already have a vendor / in-house team",
             "response": "Offer a scoped second-opinion or audit so they can compare without switching."},
            {"objection": "Not the right time",
             "response": "Tie timing to their own signal (raise, tender, hiring) and propose a short discovery call."},
        ],
        "deal_risk": risk,
        "risk_reasons": reasons or ["No major risk factors found"],
    }


def generate_advice(db: Session, lead: dict) -> SalesAdvice:
    ctx = gather_context(db, lead)
    fallback = heuristic_advice(ctx)
    advice, source = fallback, "heuristic"
    if llm_available():
        try:
            prompt = ADVISORY_PROMPT.format(company=settings.default_company_name, paths=PATHS, risks=RISKS)
            result = chat_json(f"{prompt}\n\nInput:\n{json.dumps(ctx, default=str)}")
            advice = {
                "next_best_action": result.get("next_best_action") or fallback["next_best_action"],
                "recommended_path": result.get("recommended_path") if result.get("recommended_path") in PATHS else fallback["recommended_path"],
                "talking_points": [str(x) for x in result.get("talking_points") or []][:6] or fallback["talking_points"],
                "objections": [
                    {"objection": str(o.get("objection", "")), "response": str(o.get("response", ""))}
                    for o in result.get("objections") or [] if isinstance(o, dict)
                ][:5] or fallback["objections"],
                "deal_risk": result.get("deal_risk") if result.get("deal_risk") in RISKS else fallback["deal_risk"],
                "risk_reasons": [str(x) for x in result.get("risk_reasons") or []][:5] or fallback["risk_reasons"],
            }
            source = "llm"
        except Exception:  # noqa: BLE001
            advice, source = fallback, "heuristic"

    record = SalesAdvice(
        lead_id=ctx["lead"]["id"],
        lead_name=ctx["lead"]["name"],
        inputs=ctx,
        generated_by=source,
        **advice,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def advise_top_leads(db: Session, top_n: int = 10, min_lead_score: float = 0) -> dict:
    leads = fetch_top_leads(top_n, min_lead_score)
    risks = {"low": 0, "medium": 0, "high": 0}
    for lead in leads:
        advice = generate_advice(db, lead)
        risks[advice.deal_risk] = risks.get(advice.deal_risk, 0) + 1
    return {"advised": len(leads), "risk": risks}


def latest_advice_by_lead(db: Session) -> dict[str, SalesAdvice]:
    latest: dict[str, SalesAdvice] = {}
    for a in db.query(SalesAdvice).order_by(SalesAdvice.created_at.desc()).limit(1000).all():
        latest.setdefault(a.lead_id, a)
    return latest


def count_advice(db: Session) -> int:
    return len(latest_advice_by_lead(db))


@router.get("/advice")
def list_advice(lead_id: Optional[str] = None, db: Session = Depends(get_db)):
    if lead_id:
        rows = (
            db.query(SalesAdvice)
            .filter(SalesAdvice.lead_id == lead_id)
            .order_by(SalesAdvice.created_at.desc())
            .limit(10)
            .all()
        )
        return {"advice": [advice_to_dict(a) for a in rows]}
    latest = sorted(latest_advice_by_lead(db).values(), key=lambda a: a.created_at, reverse=True)
    return {"advice": [advice_to_dict(a) for a in latest[:100]]}


@router.get("/advice/leads")
def leads_with_advice(limit: int = 30, db: Session = Depends(get_db)):
    """Top leads from Lead Intelligence joined with their latest advice."""
    leads = fetch_top_leads(max(1, min(limit, 100)))
    latest = latest_advice_by_lead(db)
    return {
        "leads": [
            {
                "id": str(l.get("id")),
                "name": l.get("name"),
                "track": l.get("track"),
                "score": l.get("score"),
                "stage": l.get("stage"),
                "signal_type": l.get("signal_type"),
                "matched_domain": (l.get("domain_context") or {}).get("domain_name"),
                "verdict": (l.get("domain_context") or {}).get("verdict"),
                "advice": advice_to_dict(latest[str(l.get("id"))]) if str(l.get("id")) in latest else None,
            }
            for l in leads
        ]
    }


@router.post("/advice/batch")
def batch_advice(body: BatchRequest | None = None, db: Session = Depends(get_db)):
    body = body or BatchRequest()
    job = create_job(db, "advisory_batch")
    run_job_in_thread(job.id, lambda s, _r: advise_top_leads(s, body.top_n, body.min_lead_score))
    return {"job_id": str(job.id)}


@router.post("/advice/{lead_id}")
def advise_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = fetch_lead(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found in Lead Intelligence")
    return advice_to_dict(generate_advice(db, lead))
