"""Deal Coach documents (meeting prep, objection playbook, proposal, hand-off) and Account Watch
signal recipes that send matching leads to Reach Out.

Each document has a template version so it works without an AI key; with a key the AI writes it
from the same facts and the template fills any gaps.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import DealDoc, InsiderAlert, RecipeMatch, SalesAdvice, SignalRecipe, get_db
from hub_clients import enroll_in_outreach, fetch_lead, fetch_top_leads
from llm_client import chat_json, llm_available

router = APIRouter(tags=["deal-coach"])

KINDS = ("meeting_prep", "playbook", "proposal", "handoff")

DEFAULT_RECIPES = [
    {"name": "Raised funding", "description": "Companies that just raised money usually start building.",
     "signal_types": ["funding"], "alert_types": ["funding"], "keywords": ["raised", "series a", "series b", "seed round"],
     "min_score": 50, "auto_enroll": True},
    {"name": "Hiring engineers or a CTO", "description": "Open tech roles mean real work and a budget.",
     "signal_types": ["hiring"], "alert_types": ["hiring"], "keywords": ["cto", "head of engineering", "blockchain engineer", "ml engineer"],
     "min_score": 50, "auto_enroll": True},
    {"name": "New product launch", "description": "A fresh launch often needs scaling, audits and new features.",
     "signal_types": ["launch"], "alert_types": ["launch", "expansion"], "keywords": [],
     "min_score": 55, "auto_enroll": True},
    {"name": "Open tender or grant", "description": "Public tenders and grants with a deadline. Usually needs a bid, not an email.",
     "signal_types": ["tender", "grant"], "alert_types": [], "keywords": [],
     "min_score": 55, "auto_enroll": False},
]

COMMON_OBJECTIONS = [
    {"objection": "It's too expensive.",
     "response": "Start with a small, fixed-price discovery or pilot so they can judge value before a bigger commitment.",
     "proof": "Offer a phase-one scope with a clear deliverable and price."},
    {"objection": "We have an in-house team.",
     "response": "Position us as extra hands for the parts that slow them down, with a clean hand-over to their team.",
     "proof": "Share how we work alongside internal teams (shared repo, weekly demos)."},
    {"objection": "Now isn't the right time.",
     "response": "Tie timing to their own signal and agree a date to revisit, so the conversation stays warm.",
     "proof": "Mention what similar companies did in the 90 days after the same signal."},
    {"objection": "We already work with a vendor.",
     "response": "Offer a second opinion or an audit of one piece, so they can compare without switching.",
     "proof": "A short, scoped review with written findings."},
]

TRACK_OBJECTIONS = {
    "web3": [{"objection": "How do we know the code is secure?",
              "response": "Explain the audit and testing steps built into delivery, and offer an independent audit.",
              "proof": "Audit reports and security checklists from past launches."}],
    "government": [{"objection": "You need to be an approved or empanelled vendor.",
                    "response": "Confirm the bid requirements early; partner with an empanelled firm if needed.",
                    "proof": "Certifications, past public-sector references, or a partner who is approved."}],
    "ai": [{"objection": "We can't share our data.",
            "response": "Offer on-premise or private-cloud setups and start with anonymised or synthetic data.",
            "proof": "Data-handling policy and examples of private deployments."}],
}


# ---------- helpers ----------

def _latest_advice(db: Session, lead_id: str) -> Optional[SalesAdvice]:
    return (
        db.query(SalesAdvice).filter(SalesAdvice.lead_id == lead_id)
        .order_by(SalesAdvice.created_at.desc()).first()
    )


def _sentences(text: str, n: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(parts[:n])[:400]


GAP_LABELS = {
    "budget": "whether there is a budget",
    "authority": "who makes the decision",
    "need": "how urgent the need is",
    "timeline": "their timeline",
    "metrics": "how they will measure success",
    "economic_buyer": "who signs off on the spend",
    "identify_pain": "their main pain point",
    "champion": "who will champion us internally",
}


def _facts(lead: dict, advice: Optional[SalesAdvice]) -> dict:
    ctx = lead.get("domain_context") or {}
    check = lead.get("sales_check") or {}
    named = [c for c in lead.get("contacts") or [] if c.get("full_name")]
    return {
        "company": lead.get("name"),
        "website": lead.get("domain"),
        "track": lead.get("track"),
        "description": _sentences(lead.get("description") or "", 3),
        "why_now": lead.get("fit_reason"),
        "signal_type": lead.get("signal_type"),
        "score": lead.get("score"),
        "market": ctx.get("domain_name"),
        "verdict": ctx.get("verdict"),
        "our_strengths": [s if isinstance(s, str) else json.dumps(s)[:120] for s in (ctx.get("our_strengths") or [])][:5],
        "gaps": [GAP_LABELS.get(g, str(g).replace("_", " ")) for g in (check.get("gaps") or [])[:4]],
        "discovery_questions": (check.get("questions") or [])[:5],
        "contacts": [
            {"name": c.get("full_name"), "title": c.get("role_title"), "email": c.get("email")}
            for c in named[:3]
        ],
        "advice": {
            "next_best_action": advice.next_best_action if advice else None,
            "talking_points": (advice.talking_points or [])[:5] if advice else [],
            "objections": (advice.objections or [])[:4] if advice else [],
            "risks": (advice.risk_reasons or [])[:4] if advice else [],
        },
        "our_company": settings.default_company_name,
    }


def _ai(kind: str, facts: dict, shape: str) -> Optional[dict]:
    if not llm_available():
        return None
    prompt = (
        f"You are a senior B2B sales coach at {settings.default_company_name}, a technical services firm. "
        f"Write a {kind.replace('_', ' ')} using ONLY these facts. Never invent numbers, clients or names. "
        f"Plain, short sentences. Return JSON exactly in this shape: {shape}\n\nFacts:\n{json.dumps(facts, default=str)}"
    )
    try:
        out = chat_json(prompt)
        return out if isinstance(out, dict) and out else None
    except Exception:  # noqa: BLE001
        return None


def _merge(template: dict, ai: Optional[dict]) -> dict:
    if not ai:
        return template
    merged = dict(template)
    for key, val in ai.items():
        if key in template and val:
            merged[key] = val
    return merged


def doc_to_dict(d: DealDoc) -> dict:
    return {
        "id": str(d.id),
        "lead_id": d.lead_id,
        "lead_name": d.lead_name,
        "kind": d.kind,
        "content": d.content or {},
        "generated_by": d.generated_by,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _save(db: Session, lead: dict, kind: str, content: dict, by: str) -> DealDoc:
    doc = DealDoc(lead_id=str(lead.get("id")), lead_name=lead.get("name"), kind=kind, content=content, generated_by=by)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ---------- documents ----------

def build_meeting_prep(db: Session, lead: dict, handoff: Optional[dict] = None) -> DealDoc:
    advice = _latest_advice(db, str(lead.get("id")))
    f = _facts(lead, advice)
    market = f["market"] or "their roadmap"
    questions = f["discovery_questions"] or [
        f"What is driving your plans for {market} right now?",
        "Who else is involved in choosing a partner, and how do you usually decide?",
        "What timeline are you working towards?",
        "Is there a budget set aside, or does this need a business case first?",
        "What would make this project a clear success for you in 6 months?",
    ]
    template = {
        "headline": f"{f['company']}: 30-minute discovery call",
        "company_snapshot": f["description"] or f"{f['company']} ({f['website'] or 'website unknown'})",
        "why_now": f["why_now"] or "No clear trigger recorded yet. Ask what prompted the conversation.",
        "who_you_meet": [f"{c['name']}{' - ' + c['title'] if c['title'] else ''}" for c in f["contacts"]]
        or ["Contact not confirmed yet"],
        "their_words": (handoff or {}).get("what_they_said"),
        "goals": [
            f"Confirm how important {market} is for them this quarter.",
            "Find out who decides and who pays.",
            "Agree a concrete next step with a date.",
        ],
        "agenda": [
            "2 min - introductions",
            f"10 min - their plans and challenges around {market}",
            "8 min - how we have helped similar teams (one short example)",
            "7 min - their questions",
            "3 min - next step and date",
        ],
        "questions": questions,
        "talking_points": f["advice"]["talking_points"] or [f"Lead with their signal: {f['why_now'] or f['signal_type']}"],
        "proof_to_bring": f["our_strengths"] or ["One relevant case study and a short capability deck"],
        "risks": (f["advice"]["risks"] or []) + [f"We don't know {g} yet" for g in f["gaps"]],
        "next_step": f["advice"]["next_best_action"] or "Propose a scoped discovery workshop with a date and price.",
    }
    shape = "{" + ", ".join(f'"{k}": ...' for k in template) + "}"
    ai = _ai("meeting prep brief", {**f, "their_words": template["their_words"]}, shape)
    return _save(db, lead, "meeting_prep", _merge(template, ai), "llm" if ai else "template")


OBJECTION_TOPICS = {
    "price": ("expensive", "cost", "price", "budget"),
    "in_house": ("in-house", "in house", "internal team", "own team"),
    "vendor": ("vendor", "agency", "partner already"),
    "timing": ("time", "later", "next quarter"),
    "security": ("secure", "security", "audit"),
    "data": ("data",),
    "approval": ("approved", "empanelled", "certified"),
}


def _objection_topic(text: str) -> set[str]:
    t = (text or "").lower()
    return {topic for topic, words in OBJECTION_TOPICS.items() if any(w in t for w in words)} or {t}


def build_playbook(db: Session, lead: dict) -> DealDoc:
    advice = _latest_advice(db, str(lead.get("id")))
    f = _facts(lead, advice)
    items = [
        {"objection": o.get("objection", ""), "response": o.get("response", ""), "proof": ""}
        for o in f["advice"]["objections"] if isinstance(o, dict)
    ]
    for o in TRACK_OBJECTIONS.get(f["track"] or "", []) + COMMON_OBJECTIONS:
        topic = _objection_topic(o["objection"])
        if not any(_objection_topic(i["objection"]) & topic for i in items):
            items.append(dict(o))
    template = {
        "title": f"Objection playbook: {f['company']}",
        "objections": items[:7],
        "golden_rules": [
            "Agree with the concern first, then answer it.",
            "Answer with a fact from their own situation, not a generic claim.",
            "End every answer with a small, easy next step.",
        ],
    }
    ai = _ai("objection playbook", f, '{"title": str, "objections": [{"objection": str, "response": str, "proof": str}], "golden_rules": [str]}')
    return _save(db, lead, "playbook", _merge(template, ai), "llm" if ai else "template")


def build_proposal(db: Session, lead: dict) -> DealDoc:
    advice = _latest_advice(db, str(lead.get("id")))
    f = _facts(lead, advice)
    market = f["market"] or "the project"
    template = {
        "title": f"Proposal for {f['company']}: {market}",
        "prepared_by": settings.default_company_name,
        "date": datetime.utcnow().date().isoformat(),
        "summary": (
            f"{settings.default_company_name} proposes a phased engagement to help {f['company']} with {market}. "
            "We start small to confirm scope and value, then build and launch with a fixed team."
        ),
        "our_understanding": [x for x in [f["why_now"], f["description"]] if x]
        or ["To be confirmed in the discovery call."],
        "approach": [
            {"phase": "1. Discovery (1-2 weeks)", "detail": "Workshops, requirements, architecture and a fixed plan for phase 2."},
            {"phase": "2. Build (6-12 weeks)", "detail": f"Design and build the {market} solution in two-week sprints with demos."},
            {"phase": "3. Launch and support", "detail": "Security review, launch, monitoring and an agreed support period."},
        ],
        "why_us": f["our_strengths"] or [f"Hands-on experience delivering {market} projects."],
        "investment": "Phase 1 is a fixed fee. Phases 2 and 3 are quoted after discovery, once scope is clear.",
        "assumptions": ["Scope, timeline and price are confirmed after the discovery phase."]
        + [f"To confirm: {g}" for g in f["gaps"][:3]],
        "next_steps": ["Agree on phase 1 scope and dates", "Sign a short statement of work", "Kick-off workshop"],
    }
    shape = ('{"title": str, "summary": str, "our_understanding": [str], "approach": [{"phase": str, "detail": str}], '
             '"why_us": [str], "investment": str, "assumptions": [str], "next_steps": [str]}')
    ai = _ai("proposal draft", f, shape)
    return _save(db, lead, "proposal", _merge(template, ai), "llm" if ai else "template")


def _pdf_text(s: object) -> str:
    text = str(s or "")
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u2013", "-"), ("\u2014", "-"),
                 ("\u2022", "-"), ("\u2026", "..."), ("\u00a0", " ")):
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def proposal_pdf(content: dict) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 9, _pdf_text(content.get("title")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 6, _pdf_text(f"Prepared by {content.get('prepared_by', '')} - {content.get('date', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    def heading(t: str):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, _pdf_text(t), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)

    def para(t: object):
        pdf.multi_cell(0, 6, _pdf_text(t), new_x="LMARGIN", new_y="NEXT")

    def bullets(items):
        for item in items or []:
            pdf.multi_cell(0, 6, _pdf_text(f"- {item}"), new_x="LMARGIN", new_y="NEXT")

    heading("Summary")
    para(content.get("summary"))
    heading("Our understanding")
    bullets(content.get("our_understanding"))
    heading("Approach")
    for step in content.get("approach") or []:
        if isinstance(step, dict):
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, _pdf_text(step.get("phase")), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 11)
            para(step.get("detail"))
        else:
            para(step)
    heading("Why us")
    bullets(content.get("why_us"))
    heading("Investment")
    para(content.get("investment"))
    heading("Assumptions")
    bullets(content.get("assumptions"))
    heading("Next steps")
    bullets(content.get("next_steps"))
    return bytes(pdf.output())


# ---------- hand-off from Reach Out ----------

class HandoffIn(BaseModel):
    lead_id: str
    lead_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_email: Optional[str] = None
    why_now: Optional[str] = None
    thread: list[dict] = Field(default_factory=list)


def build_handoff(db: Session, body: HandoffIn) -> DealDoc:
    lead = fetch_lead(body.lead_id) or {"id": body.lead_id, "name": body.lead_name}
    their = [t.get("text", "") for t in body.thread if t.get("from") == "lead"]
    ours = [t for t in body.thread if t.get("from") == "us"]
    what_they_said = (their[-1] if their else "")[:600]
    who = f"{body.contact_name or body.contact_email}" + (f" ({body.contact_title})" if body.contact_title else "")
    template = {
        "summary": f"{who} at {lead.get('name') or body.lead_name} replied with interest after {len(ours)} email(s).",
        "contact": {"name": body.contact_name, "title": body.contact_title, "email": body.contact_email},
        "why_now": body.why_now or lead.get("fit_reason"),
        "what_they_said": what_they_said,
        "what_we_sent": [(t.get("text") or "")[:300] for t in ours][-3:],
        "recommended_next_step": "Reply within 2 hours, answer their question and propose two meeting times.",
    }
    ai = _ai("hand-off summary for the account owner",
             {"thread": body.thread[-6:], "contact": template["contact"], "why_now": template["why_now"]},
             '{"summary": str, "what_they_said": str, "recommended_next_step": str}')
    content = _merge(template, ai)
    prep = build_meeting_prep(db, lead, handoff=content) if lead.get("id") else None
    content["meeting_prep_id"] = str(prep.id) if prep else None
    doc = _save(db, lead, "handoff", content, "llm" if ai else "template")
    fingerprint = f"handoff-{body.lead_id}-{datetime.utcnow().date().isoformat()}"
    if not db.query(InsiderAlert).filter(InsiderAlert.fingerprint == fingerprint).first():
        db.add(InsiderAlert(
            lead_id=body.lead_id, account_name=lead.get("name") or body.lead_name, alert_type="hot_reply",
            severity="high", title=f"{who} replied interested", detail=what_they_said[:500], fingerprint=fingerprint,
        ))
        db.commit()
    return doc


@router.post("/advisory/handoff")
def handoff(body: HandoffIn, db: Session = Depends(get_db)):
    return doc_to_dict(build_handoff(db, body))


@router.get("/deal-handoffs")
def list_handoffs(limit: int = 30, db: Session = Depends(get_db)):
    rows = (
        db.query(DealDoc).filter(DealDoc.kind == "handoff")
        .order_by(DealDoc.created_at.desc()).limit(max(1, min(limit, 100))).all()
    )
    return {"handoffs": [doc_to_dict(d) for d in rows]}


# ---------- deal room endpoints ----------

@router.get("/deal/{lead_id}")
def deal_room(lead_id: str, db: Session = Depends(get_db)):
    latest: dict = {}
    for d in db.query(DealDoc).filter(DealDoc.lead_id == lead_id).order_by(DealDoc.created_at.desc()).limit(40).all():
        latest.setdefault(d.kind, doc_to_dict(d))
    return {"lead_id": lead_id, "docs": latest}


BUILDERS = {"meeting-prep": build_meeting_prep, "playbook": build_playbook, "proposal": build_proposal}


@router.post("/deal/{lead_id}/{kind}")
def make_doc(lead_id: str, kind: str, db: Session = Depends(get_db)):
    if kind not in BUILDERS:
        raise HTTPException(404, "Unknown document type")
    lead = fetch_lead(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found in Find Leads")
    return doc_to_dict(BUILDERS[kind](db, lead))


@router.get("/deal/{lead_id}/proposal.pdf")
def proposal_download(lead_id: str, db: Session = Depends(get_db)):
    doc = (
        db.query(DealDoc).filter(DealDoc.lead_id == lead_id, DealDoc.kind == "proposal")
        .order_by(DealDoc.created_at.desc()).first()
    )
    if not doc:
        lead = fetch_lead(lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        doc = build_proposal(db, lead)
    safe = re.sub(r"[^A-Za-z0-9]+", "-", doc.lead_name or "proposal").strip("-").lower()
    return Response(
        proposal_pdf(doc.content or {}),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="proposal-{safe}.pdf"'},
    )


# ---------- signal recipes ----------

class RecipeIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    signal_types: Optional[list[str]] = None
    alert_types: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    min_score: Optional[float] = None
    auto_enroll: Optional[bool] = None
    active: Optional[bool] = None


def recipe_to_dict(r: SignalRecipe) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "description": r.description,
        "signal_types": r.signal_types or [],
        "alert_types": r.alert_types or [],
        "keywords": r.keywords or [],
        "min_score": r.min_score,
        "auto_enroll": r.auto_enroll,
        "active": r.active,
        "matched_total": r.matched_total or 0,
        "enrolled_total": r.enrolled_total or 0,
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
    }


def seed_recipes(db: Session) -> None:
    if db.query(SignalRecipe).count():
        return
    for r in DEFAULT_RECIPES:
        db.add(SignalRecipe(**r))
    db.commit()


def _recipe_reason(recipe: SignalRecipe, lead: dict, alerts: list[InsiderAlert]) -> Optional[str]:
    if float(lead.get("score") or 0) < float(recipe.min_score or 0):
        return None
    if lead.get("signal_type") in (recipe.signal_types or []):
        return f"{lead.get('signal_type')} signal"
    hit = next((a for a in alerts if a.alert_type in (recipe.alert_types or [])), None)
    if hit:
        return f"Account Watch: {hit.title}"
    text = f"{lead.get('name', '')} {lead.get('description', '')}".lower()
    kw = next((k for k in recipe.keywords or [] if k and re.search(rf"\b{re.escape(k.lower())}\b", text)), None)
    if kw:
        return f"mentions '{kw}'"
    return None


def run_recipes(db: Session, max_enroll: int = 10) -> dict:
    seed_recipes(db)
    recipes = db.query(SignalRecipe).filter(SignalRecipe.active.is_(True)).all()
    if not recipes:
        return {"matched": 0, "enrolled": 0}
    leads = fetch_top_leads(100, min(float(r.min_score or 0) for r in recipes))
    since = datetime.utcnow() - timedelta(days=14)
    alerts_by_lead: dict = {}
    for a in db.query(InsiderAlert).filter(InsiderAlert.created_at >= since).all():
        alerts_by_lead.setdefault(a.lead_id, []).append(a)
    seen = {(str(m.recipe_id), m.lead_id) for m in db.query(RecipeMatch).all()}
    out = {"matched": 0, "enrolled": 0, "retried": 0, "by_recipe": {}}

    auto_ids = {r.id for r in recipes if r.auto_enroll}
    waiting = (
        db.query(RecipeMatch)
        .filter(RecipeMatch.enrolled.is_(False), RecipeMatch.created_at >= datetime.utcnow() - timedelta(days=14))
        .all()
    )
    for m in waiting:
        if m.recipe_id not in auto_ids or out["enrolled"] >= max_enroll or out["retried"] >= max_enroll:
            continue
        if "tender portal" in (m.note or "").lower():
            continue
        ok, note = enroll_in_outreach(m.lead_id)
        out["retried"] += 1
        m.enrolled = ok or "already in a sequence" in note.lower()
        m.note = "First email drafted in Reach Out (waiting for approval)." if ok else note
        if ok:
            out["enrolled"] += 1
    db.commit()
    for recipe in recipes:
        count = 0
        for lead in leads:
            lead_id = str(lead.get("id"))
            if (str(recipe.id), lead_id) in seen or lead.get("stage") in ("won", "lost"):
                continue
            reason = _recipe_reason(recipe, lead, alerts_by_lead.get(lead_id, []))
            if not reason:
                continue
            match = RecipeMatch(recipe_id=recipe.id, lead_id=lead_id, lead_name=lead.get("name"), reason=reason)
            if recipe.auto_enroll and lead.get("is_portal_lead"):
                match.note = "Public tender portal: prepare a bid instead of an email."
            elif recipe.auto_enroll and out["enrolled"] < max_enroll:
                ok, note = enroll_in_outreach(lead_id)
                match.enrolled = ok or "already in a sequence" in note.lower()
                match.note = "First email drafted in Reach Out (waiting for approval)." if ok else note
                if ok:
                    out["enrolled"] += 1
                    recipe.enrolled_total = (recipe.enrolled_total or 0) + 1
            elif not recipe.auto_enroll:
                match.note = "Saved for review (auto-send to Reach Out is off for this recipe)."
            db.add(match)
            seen.add((str(recipe.id), lead_id))
            recipe.matched_total = (recipe.matched_total or 0) + 1
            count += 1
        recipe.last_run_at = datetime.utcnow()
        out["by_recipe"][recipe.name] = count
        out["matched"] += count
        db.commit()
    return out


@router.get("/recipes")
def list_recipes(db: Session = Depends(get_db)):
    seed_recipes(db)
    return {"recipes": [recipe_to_dict(r) for r in db.query(SignalRecipe).order_by(SignalRecipe.created_at).all()]}


@router.post("/recipes")
def create_recipe(body: RecipeIn, db: Session = Depends(get_db)):
    if not body.name:
        raise HTTPException(400, "Give the recipe a name.")
    data = body.model_dump(exclude_none=True)
    r = SignalRecipe(**data)
    db.add(r)
    db.commit()
    db.refresh(r)
    return recipe_to_dict(r)


@router.patch("/recipes/{recipe_id}")
def update_recipe(recipe_id: UUID, body: RecipeIn, db: Session = Depends(get_db)):
    r = db.get(SignalRecipe, recipe_id)
    if not r:
        raise HTTPException(404, "Recipe not found")
    for key, val in body.model_dump(exclude_none=True).items():
        setattr(r, key, val)
    db.commit()
    return recipe_to_dict(r)


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: UUID, db: Session = Depends(get_db)):
    r = db.get(SignalRecipe, recipe_id)
    if not r:
        raise HTTPException(404, "Recipe not found")
    db.delete(r)
    db.commit()
    return {"deleted": True}


@router.post("/recipes/run")
def run_recipes_now(db: Session = Depends(get_db)):
    from jobs import create_job, run_job_in_thread

    job = create_job(db, "signal_recipes")
    run_job_in_thread(job.id, lambda s, _r: run_recipes(s))
    return {"job_id": str(job.id)}


@router.get("/recipes/matches")
def recipe_matches(limit: int = 50, db: Session = Depends(get_db)):
    names = {r.id: r.name for r in db.query(SignalRecipe).all()}
    rows = db.query(RecipeMatch).order_by(RecipeMatch.created_at.desc()).limit(max(1, min(limit, 200))).all()
    return {"matches": [
        {
            "id": str(m.id), "recipe": names.get(m.recipe_id), "lead_id": m.lead_id, "lead_name": m.lead_name,
            "reason": m.reason, "enrolled": m.enrolled, "note": m.note,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]}
