"""Reach Out API: approval queue, mailboxes, sequences, inbox and the always-on autopilot."""

from __future__ import annotations

import asyncio
import logging
import uuid as uuidlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import alerts
import autopilot
import calls
import crm
import hub_clients
import mailer
import reports
from config import settings
from crypto import encrypt, sign
from database import Call, Enrollment, Event, Job, Mailbox, Message, Reply, Sequence, SessionLocal, get_db, run_migrations
from llm_client import llm_available
from replies import LABELS
from store import default_sequence, get_settings, log_event, update_settings

log = logging.getLogger("outreach-autopilot")
STATE: dict = {"last_heartbeat": None, "last_result": None, "next_heartbeat": None}


def _run_heartbeat(force: bool = False) -> dict:
    db = SessionLocal()
    try:
        result = autopilot.heartbeat(db, force=force, minutes=settings.heartbeat_minutes)
    finally:
        db.close()
    STATE["last_heartbeat"] = datetime.utcnow()
    STATE["last_result"] = result
    return result


async def _heartbeat_loop():
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.to_thread(_run_heartbeat)
        except Exception:  # noqa: BLE001
            log.exception("heartbeat loop error")
        STATE["next_heartbeat"] = datetime.utcnow() + timedelta(minutes=settings.heartbeat_minutes)
        await asyncio.sleep(max(60, settings.heartbeat_minutes * 60))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    db = SessionLocal()
    try:
        default_sequence(db)
    finally:
        db.close()
    STATE["next_heartbeat"] = datetime.utcnow() + timedelta(seconds=20)
    task = asyncio.create_task(_heartbeat_loop())
    yield
    task.cancel()


app = FastAPI(title="Reach Out API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


# ---------- serializers ----------

def mailbox_dict(mb: Mailbox) -> dict:
    return {
        "id": str(mb.id),
        "label": mb.label,
        "email": mb.email,
        "from_name": mb.from_name,
        "kind": mb.kind,
        "smtp_host": mb.smtp_host,
        "smtp_port": mb.smtp_port,
        "smtp_security": mb.smtp_security,
        "imap_host": mb.imap_host,
        "imap_port": mb.imap_port,
        "username": mb.username,
        "has_password": bool(mb.secret_enc),
        "daily_cap_start": mb.daily_cap_start,
        "daily_cap_max": mb.daily_cap_max,
        "ramp_per_day": mb.ramp_per_day,
        "daily_cap_today": mailer.daily_cap(mb),
        "active": mb.active,
        "paused_reason": mb.paused_reason,
        "sent_today": mb.sent_today or 0,
        "sent_total": mb.sent_total,
        "bounced_total": mb.bounced_total,
        "bounce_rate": round(mailer.bounce_rate(mb), 3),
        "last_error": mb.last_error,
        "created_at": iso(mb.created_at),
    }


def enrollment_dict(e: Enrollment) -> dict:
    return {
        "id": str(e.id),
        "lead_id": e.lead_id,
        "lead_name": e.lead_name,
        "company_domain": e.company_domain,
        "contact_email": e.contact_email,
        "contact_name": e.contact_name,
        "contact_title": e.contact_title,
        "phone": e.phone,
        "mailbox_id": str(e.mailbox_id) if e.mailbox_id else None,
        "current_step": e.current_step,
        "status": e.status,
        "next_action_at": iso(e.next_action_at),
        "subject": e.subject,
        "last_sent_at": iso(e.last_sent_at),
        "lead_score": float(e.lead_score) if e.lead_score is not None else None,
        "fit_reason": e.fit_reason,
        "call_status": e.call_status,
        "created_at": iso(e.created_at),
    }


def message_dict(m: Message) -> dict:
    return {
        "id": str(m.id),
        "enrollment_id": str(m.enrollment_id),
        "step": m.step,
        "kind": m.kind,
        "status": m.status,
        "subject": m.subject,
        "body": m.body,
        "sent_at": iso(m.sent_at),
        "error": m.error,
        "needs_approval": m.needs_approval,
        "created_at": iso(m.created_at),
    }


def reply_dict(r: Reply, enr: Enrollment | None = None) -> dict:
    return {
        "id": str(r.id),
        "enrollment_id": str(r.enrollment_id) if r.enrollment_id else None,
        "from_email": r.from_email,
        "subject": r.subject,
        "body": r.body,
        "category": r.category,
        "category_label": LABELS.get(r.category or "", r.category),
        "confidence": float(r.confidence) if r.confidence is not None else None,
        "reasoning": r.reasoning,
        "action_taken": r.action_taken,
        "handled": r.handled,
        "received_at": iso(r.received_at),
        "lead_name": enr.lead_name if enr else None,
        "contact_name": enr.contact_name if enr else None,
        "lead_id": enr.lead_id if enr else None,
    }


def call_dict(c: Call, enr: Enrollment | None = None) -> dict:
    return {
        "id": str(c.id),
        "enrollment_id": str(c.enrollment_id),
        "phone": c.phone,
        "status": c.status,
        "outcome": c.outcome,
        "summary": c.summary,
        "error": c.error,
        "created_at": iso(c.created_at),
        "completed_at": iso(c.completed_at),
        "lead_name": enr.lead_name if enr else None,
        "contact_name": enr.contact_name if enr else None,
    }


def _enrollment(db: Session, enrollment_id: UUID) -> Enrollment:
    enr = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
    if not enr:
        raise HTTPException(404, "Not found")
    return enr


# ---------- basics ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def config_status():
    return {
        "openai_configured": llm_available(),
        "chat_model": settings.resolve_chat_model(),
        "alerts": alerts.channels(),
        "crm": crm.configured(),
        "calls_configured": calls.configured(),
        "calls_webhook_url": f"{settings.outreach_public_url.rstrip('/')}/calls/webhook?t={sign('calls-webhook')}",
        "heartbeat_minutes": settings.heartbeat_minutes,
        "public_url": settings.outreach_public_url,
        "modules": hub_clients.module_health(),
    }


@app.get("/status")
def status(db: Session = Depends(get_db)):
    cfg = get_settings(db)
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {
        s: db.query(Enrollment).filter(Enrollment.status == s).count()
        for s in ("awaiting_approval", "active", "snoozed", "replied", "interested", "completed", "stopped", "bounced", "unsubscribed")
    }
    mailboxes = db.query(Mailbox).all()
    return {
        "autopilot_enabled": bool(cfg.get("autopilot_enabled")),
        "paused": bool(cfg.get("paused")),
        "approve_first_message": bool(cfg.get("approve_first_message", True)),
        "mailboxes": len(mailboxes),
        "mailboxes_active": sum(1 for m in mailboxes if m.active),
        "sandbox_only": bool(mailboxes) and all(m.kind == "sandbox" for m in mailboxes),
        "waiting_approval": db.query(Message).filter(Message.status == "draft").count(),
        "in_sequence": counts["active"],
        "hot_leads": counts["interested"],
        "counts": counts,
        "sent_today": db.query(Message).filter(Message.status == "sent", Message.sent_at >= today).count(),
        "replies_today": db.query(Reply).filter(Reply.received_at >= today).count(),
        "unread_replies": db.query(Reply).filter(Reply.handled.is_(False)).count(),
        "in_send_window": mailer.within_send_window(cfg),
        "last_heartbeat": iso(STATE["last_heartbeat"]),
        "next_heartbeat": iso(STATE["next_heartbeat"]),
        "last_result": STATE["last_result"],
    }


# ---------- settings ----------

@app.get("/settings")
def read_settings(db: Session = Depends(get_db)):
    return get_settings(db)


@app.patch("/settings")
def write_settings(body: dict, db: Session = Depends(get_db)):
    return update_settings(db, body)


class AutopilotUpdate(BaseModel):
    enabled: Optional[bool] = None
    paused: Optional[bool] = None


@app.post("/autopilot")
def set_autopilot(body: AutopilotUpdate, db: Session = Depends(get_db)):
    values = {}
    if body.enabled is not None:
        values["autopilot_enabled"] = body.enabled
    if body.paused is not None:
        values["paused"] = body.paused
    cfg = update_settings(db, values)
    log_event(db, "autopilot", None, **values)
    db.commit()
    return {"autopilot_enabled": cfg["autopilot_enabled"], "paused": cfg["paused"]}


@app.post("/autopilot/run-now")
async def run_now():
    return await asyncio.to_thread(_run_heartbeat, True)


# ---------- mailboxes ----------

class MailboxIn(BaseModel):
    label: Optional[str] = None
    email: Optional[str] = None
    from_name: Optional[str] = None
    kind: str = "smtp"
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_security: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    daily_cap_start: Optional[int] = None
    daily_cap_max: Optional[int] = None
    ramp_per_day: Optional[int] = None
    active: Optional[bool] = None


GMAIL_DEFAULTS = {"smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_security": "starttls",
                  "imap_host": "imap.gmail.com", "imap_port": 993}


def _apply_mailbox(mb: Mailbox, body: MailboxIn) -> None:
    data = body.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for key, val in data.items():
        setattr(mb, key, val)
    if password:
        mb.secret_enc = encrypt(password)
    if mb.kind == "smtp" and (mb.email or "").lower().endswith(("@gmail.com", "@googlemail.com")):
        for key, val in GMAIL_DEFAULTS.items():
            if not getattr(mb, key):
                setattr(mb, key, val)


@app.get("/mailboxes")
def list_mailboxes(db: Session = Depends(get_db)):
    return {"mailboxes": [mailbox_dict(m) for m in db.query(Mailbox).order_by(Mailbox.created_at).all()]}


@app.post("/mailboxes")
def create_mailbox(body: MailboxIn, db: Session = Depends(get_db)):
    if body.kind == "sandbox":
        body.label = body.label or "Test mailbox (nothing is really sent)"
        body.email = body.email or "sandbox@leadgen.test"
        body.from_name = body.from_name or "LeadGen AI Test"
    elif not body.email or not body.password:
        raise HTTPException(400, "Email and app password are required.")
    mb = Mailbox(label=body.label or body.email, email=body.email, kind=body.kind)
    _apply_mailbox(mb, body)
    if mb.kind == "smtp" and not (mb.smtp_host and mb.imap_host):
        raise HTTPException(400, "SMTP and IMAP server names are required for non-Gmail mailboxes.")
    db.add(mb)
    log_event(db, "mailbox_added", None, email=mb.email, kind=mb.kind)
    db.commit()
    db.refresh(mb)
    return mailbox_dict(mb)


@app.patch("/mailboxes/{mailbox_id}")
def update_mailbox(mailbox_id: UUID, body: MailboxIn, db: Session = Depends(get_db)):
    mb = db.query(Mailbox).filter(Mailbox.id == mailbox_id).first()
    if not mb:
        raise HTTPException(404, "Mailbox not found")
    _apply_mailbox(mb, body)
    if body.active:
        mb.paused_reason = None
    db.commit()
    db.refresh(mb)
    return mailbox_dict(mb)


@app.delete("/mailboxes/{mailbox_id}")
def delete_mailbox(mailbox_id: UUID, db: Session = Depends(get_db)):
    mb = db.query(Mailbox).filter(Mailbox.id == mailbox_id).first()
    if not mb:
        raise HTTPException(404, "Mailbox not found")
    db.delete(mb)
    db.commit()
    return {"deleted": True}


@app.post("/mailboxes/{mailbox_id}/test")
async def test_mailbox(mailbox_id: UUID, db: Session = Depends(get_db)):
    mb = db.query(Mailbox).filter(Mailbox.id == mailbox_id).first()
    if not mb:
        raise HTTPException(404, "Mailbox not found")
    result = await asyncio.to_thread(mailer.test_connection, mb)
    mb.last_error = result.get("error")
    db.commit()
    return result


# ---------- sequences ----------

@app.get("/sequences")
def list_sequences(db: Session = Depends(get_db)):
    default_sequence(db)
    return {"sequences": [
        {"id": str(s.id), "name": s.name, "steps": s.steps, "is_default": s.is_default}
        for s in db.query(Sequence).order_by(Sequence.created_at).all()
    ]}


class SequenceUpdate(BaseModel):
    name: Optional[str] = None
    steps: Optional[list[dict]] = None


@app.put("/sequences/{sequence_id}")
def update_sequence(sequence_id: UUID, body: SequenceUpdate, db: Session = Depends(get_db)):
    seq = db.query(Sequence).filter(Sequence.id == sequence_id).first()
    if not seq:
        raise HTTPException(404, "Sequence not found")
    if body.name:
        seq.name = body.name
    if body.steps is not None:
        steps = []
        for i, s in enumerate(body.steps, start=1):
            kind = s.get("kind") if s.get("kind") in ("opener", "follow_up", "insight", "soft_close") else "follow_up"
            steps.append({"step": i, "wait_days": max(0, float(s.get("wait_days") or 0)) if i > 1 else 0,
                          "kind": kind, "label": s.get("label") or kind})
        if not steps:
            raise HTTPException(400, "A sequence needs at least one step.")
        seq.steps = steps
    db.commit()
    return {"id": str(seq.id), "name": seq.name, "steps": seq.steps, "is_default": seq.is_default}


# ---------- approval queue ----------

@app.get("/queue")
def approval_queue(db: Session = Depends(get_db)):
    rows = (
        db.query(Message, Enrollment)
        .join(Enrollment, Enrollment.id == Message.enrollment_id)
        .filter(Message.status == "draft")
        .order_by(Enrollment.lead_score.desc().nullslast(), Message.created_at)
        .limit(200)
        .all()
    )
    return {"items": [{**message_dict(m), "enrollment": enrollment_dict(e)} for m, e in rows]}


class MessageEdit(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


@app.patch("/messages/{message_id}")
def edit_message(message_id: UUID, body: MessageEdit, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.status not in ("draft", "approved"):
        raise HTTPException(400, "Only drafts can be edited.")
    if body.subject is not None:
        msg.subject = body.subject
    if body.body is not None:
        msg.body = body.body
    db.commit()
    return message_dict(msg)


def _approve(db: Session, msg: Message, send_now: bool) -> dict:
    if autopilot.has_placeholder(msg):
        return {"id": str(msg.id), "status": msg.status, "sent": False,
                "note": "Fill in the [bracketed] part of this email first."}
    enr = db.query(Enrollment).filter(Enrollment.id == msg.enrollment_id).first()
    msg.status = "approved"
    if enr and enr.status == "awaiting_approval":
        enr.next_action_at = datetime.utcnow()
    log_event(db, "approved", msg.enrollment_id, step=msg.step, kind=msg.kind)
    db.commit()
    result = {"id": str(msg.id), "status": msg.status, "sent": False, "note": "Will send in the next sending window."}
    if send_now and enr:
        cfg = get_settings(db)
        mb = db.query(Mailbox).filter(Mailbox.id == enr.mailbox_id).first() if enr.mailbox_id else autopilot.choose_mailbox(db, enr.company_domain)
        if not mb:
            result["note"] = "Add a mailbox first. The email is approved and will send once a mailbox exists."
        else:
            enr.mailbox_id = mb.id
            ok, why = mailer.can_send(mb, cfg)
            if ok and autopilot.send_message(db, msg, enr, mb, cfg):
                result.update(sent=True, status="sent", note="Sent.")
            else:
                result["note"] = why or msg.error or "Could not send now. It will retry automatically."
            db.commit()
    return result


@app.post("/messages/{message_id}/approve")
def approve_message(message_id: UUID, send_now: bool = False, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(404, "Message not found")
    return _approve(db, msg, send_now)


class BulkIds(BaseModel):
    ids: list[UUID]
    send_now: bool = False


@app.post("/queue/approve")
def approve_many(body: BulkIds, db: Session = Depends(get_db)):
    out = []
    for mid in body.ids:
        msg = db.query(Message).filter(Message.id == mid, Message.status == "draft").first()
        if msg:
            out.append(_approve(db, msg, body.send_now))
    held = sum(1 for r in out if r["status"] == "draft")
    return {"approved": len(out) - held, "held": held, "sent": sum(1 for r in out if r["sent"]), "results": out}


@app.post("/messages/{message_id}/reject")
def reject_message(message_id: UUID, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(404, "Message not found")
    msg.status = "rejected"
    enr = db.query(Enrollment).filter(Enrollment.id == msg.enrollment_id).first()
    if enr and enr.status == "awaiting_approval":
        enr.status = "stopped"
    log_event(db, "rejected", msg.enrollment_id, step=msg.step)
    db.commit()
    return {"id": str(msg.id), "status": "rejected"}


@app.post("/messages/{message_id}/rewrite")
def rewrite_message(message_id: UUID, db: Session = Depends(get_db)):
    from writer import write_answer, write_email

    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg or msg.status != "draft":
        raise HTTPException(404, "Draft not found")
    enr = _enrollment(db, msg.enrollment_id)
    cfg = get_settings(db)
    lead = {**(enr.context or {}), "id": enr.lead_id}
    contact = {"name": enr.contact_name, "title": enr.contact_title}
    last_reply = (db.query(Reply).filter(Reply.enrollment_id == enr.id)
                  .order_by(Reply.received_at.desc()).first()) if msg.kind == "answer" else None
    if last_reply:
        draft = write_answer(last_reply.body or "", lead, contact, cfg, enr.subject)
    else:
        draft = write_email(msg.kind or "opener", lead, contact, cfg,
                            previous_subject=enr.subject, learnings=reports.learnings(db))
    msg.subject, msg.body = draft["subject"], draft["body"]
    db.commit()
    return {**message_dict(msg), "method": draft["method"]}


# ---------- enrollments ----------

@app.get("/enrollments")
def list_enrollments(status: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Enrollment)
    if status:
        q = q.filter(Enrollment.status.in_(status.split(",")))
    rows = q.order_by(Enrollment.updated_at.desc()).limit(min(500, max(1, limit))).all()
    return {"enrollments": [enrollment_dict(e) for e in rows]}


@app.get("/enrollments/{enrollment_id}")
def get_enrollment(enrollment_id: UUID, db: Session = Depends(get_db)):
    enr = _enrollment(db, enrollment_id)
    msgs = db.query(Message).filter(Message.enrollment_id == enr.id).order_by(Message.created_at).all()
    reps = db.query(Reply).filter(Reply.enrollment_id == enr.id).order_by(Reply.received_at).all()
    cls = db.query(Call).filter(Call.enrollment_id == enr.id).order_by(Call.created_at).all()
    return {
        **enrollment_dict(enr),
        "messages": [message_dict(m) for m in msgs],
        "replies": [reply_dict(r, enr) for r in reps],
        "calls": [call_dict(c, enr) for c in cls],
        "steps": autopilot._steps(db, enr),
    }


class EnrollIn(BaseModel):
    lead_id: str
    contact_email: Optional[str] = None


@app.post("/enrollments")
def enroll(body: EnrollIn, db: Session = Depends(get_db)):
    lead = hub_clients.get_lead(body.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found in Find Leads.")
    suppressed = hub_clients.suppressed_emails()
    if body.contact_email:
        email = body.contact_email.lower()
        if email in suppressed:
            raise HTTPException(400, "This email is on the do-not-contact list.")
        contact = next((c for c in lead.get("contacts") or [] if (c.get("email") or "").lower() == email),
                       {"email": email})
    else:
        contact = autopilot.pick_contact(lead, suppressed)
        if not contact and hub_clients.find_contacts(body.lead_id):
            lead = hub_clients.get_lead(body.lead_id) or lead
            contact = autopilot.pick_contact(lead, suppressed)
        if not contact:
            raise HTTPException(400, "No reliable contact found for this lead yet (we looked on their website).")
    if db.query(Enrollment).filter(Enrollment.lead_id == body.lead_id,
                                   Enrollment.contact_email == contact["email"].lower()).first():
        raise HTTPException(409, "This person is already in a sequence.")
    enr = autopilot.enroll_lead(db, lead, contact, get_settings(db))
    db.commit()
    return enrollment_dict(enr)


@app.post("/enrollments/{enrollment_id}/stop")
def stop_enrollment(enrollment_id: UUID, db: Session = Depends(get_db)):
    enr = _enrollment(db, enrollment_id)
    enr.status = "stopped"
    db.query(Message).filter(Message.enrollment_id == enr.id, Message.status.in_(("draft", "approved"))).update(
        {"status": "rejected"}, synchronize_session=False)
    log_event(db, "stopped", enr.id)
    db.commit()
    return enrollment_dict(enr)


@app.post("/enrollments/{enrollment_id}/resume")
def resume_enrollment(enrollment_id: UUID, db: Session = Depends(get_db)):
    enr = _enrollment(db, enrollment_id)
    if enr.status in ("unsubscribed", "bounced"):
        raise HTTPException(400, "This person can't be emailed again.")
    enr.status = "active" if (enr.current_step or 0) >= 1 else "awaiting_approval"
    enr.next_action_at = datetime.utcnow()
    log_event(db, "resumed", enr.id)
    db.commit()
    return enrollment_dict(enr)


# ---------- inbox and replies ----------

@app.get("/inbox")
def inbox(category: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Reply, Enrollment).outerjoin(Enrollment, Enrollment.id == Reply.enrollment_id)
    if category:
        q = q.filter(Reply.category == category)
    rows = q.order_by(Reply.received_at.desc()).limit(min(500, max(1, limit))).all()
    return {"replies": [reply_dict(r, e) for r, e in rows], "labels": LABELS}


@app.post("/replies/{reply_id}/handled")
def mark_handled(reply_id: UUID, db: Session = Depends(get_db)):
    r = db.query(Reply).filter(Reply.id == reply_id).first()
    if not r:
        raise HTTPException(404, "Reply not found")
    r.handled = True
    db.commit()
    return {"handled": True}


class SimulatedReply(BaseModel):
    enrollment_id: UUID
    body: str
    subject: Optional[str] = None


@app.post("/replies/simulate")
def simulate_reply(body: SimulatedReply, db: Session = Depends(get_db)):
    """Test the reply sorter end to end without a real inbox."""
    enr = _enrollment(db, body.enrollment_id)
    item = {
        "message_id": f"<sim-{uuidlib.uuid4().hex}@sandbox.leadgen>",
        "in_reply_to": enr.thread_message_id or "",
        "references": enr.thread_message_id or "",
        "from_email": enr.contact_email,
        "subject": body.subject or f"Re: {enr.subject or ''}",
        "body": body.body,
    }
    reply = autopilot.record_reply(db, enr, enr.mailbox_id, item, get_settings(db))
    if not reply:
        raise HTTPException(409, "Duplicate reply")
    db.refresh(enr)
    return {"reply": reply_dict(reply, enr), "enrollment": enrollment_dict(enr)}


def _unsubscribe(db: Session, e: str, t: str) -> bool:
    try:
        enr_id = UUID(e)
    except ValueError:
        return False
    if sign(str(enr_id)) != t:
        return False
    enr = db.query(Enrollment).filter(Enrollment.id == enr_id).first()
    if not enr:
        return False
    if enr.status != "unsubscribed":
        enr.status = "unsubscribed"
        hub_clients.suppress(enr.contact_email, "unsubscribe-link")
        db.query(Message).filter(Message.enrollment_id == enr.id, Message.status.in_(("draft", "approved"))).update(
            {"status": "rejected"}, synchronize_session=False)
        log_event(db, "unsubscribed", enr.id, via="link")
        db.commit()
    return True


UNSUB_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:system-ui,sans-serif;max-width:520px;margin:15vh auto;padding:0 20px;color:#1f2937">
<h2>{title}</h2><p>{text}</p></body></html>"""


@app.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(e: str = "", t: str = "", db: Session = Depends(get_db)):
    if _unsubscribe(db, e, t):
        return UNSUB_PAGE.format(title="You're unsubscribed", text="You won't get any more emails from us. Sorry for the bother.")
    return HTMLResponse(UNSUB_PAGE.format(title="Link not valid", text="Please reply to the email with 'stop' and we'll remove you."), status_code=400)


@app.post("/unsubscribe")
def unsubscribe_one_click(e: str = "", t: str = "", db: Session = Depends(get_db)):
    if not _unsubscribe(db, e, t):
        raise HTTPException(400, "Invalid link")
    return {"unsubscribed": True}


# ---------- pipeline run (drafts only) ----------

class RunIn(BaseModel):
    draftForTopN: int = 10
    minLeadScore: float = 60


@app.post("/run")
def run_pipeline_step(body: RunIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    job = Job(kind="draft", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    def task():
        s = SessionLocal()
        try:
            j = s.query(Job).filter(Job.id == job_id).first()
            j.status = "running"
            s.commit()
            cfg = get_settings(s)
            result = autopilot.draft_for_hot_leads(s, cfg, body.draftForTopN, body.minLeadScore, respect_daily=False)
            if result.get("needs_contacts") and result["drafted"] < body.draftForTopN:
                hub_clients.find_contacts_for_top(limit=min(10, result["needs_contacts"]), min_score=body.minLeadScore)
                more = autopilot.draft_for_hot_leads(s, cfg, body.draftForTopN - result["drafted"], body.minLeadScore,
                                                     respect_daily=False)
                result["drafted"] += more["drafted"]
                result["needs_contacts"] = more["needs_contacts"]
            j.status, j.result, j.completed_at = "completed", result, datetime.utcnow()
            s.commit()
        except Exception as e:  # noqa: BLE001
            s.rollback()
            j = s.query(Job).filter(Job.id == job_id).first()
            j.status, j.error, j.completed_at = "failed", str(e)[:500], datetime.utcnow()
            s.commit()
        finally:
            s.close()

    background.add_task(task)
    return {"job_id": str(job_id)}


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return {"id": str(job.id), "status": job.status, "result": job.result, "error": job.error,
            "created_at": iso(job.created_at), "completed_at": iso(job.completed_at)}


# ---------- today, events, reports ----------

EVENT_TEXT = {
    "enrolled": "Drafted a first email",
    "approved": "Approved",
    "rejected": "Rejected a draft",
    "sent": "Sent",
    "send_failed": "Sending failed",
    "reply": "Reply received",
    "bounced": "Email bounced",
    "unsubscribed": "Unsubscribed",
    "sequence_completed": "Finished the sequence with no reply",
    "woke_up": "Snooze ended, follow-ups resumed",
    "heartbeat": "Autopilot check",
    "heartbeat_failed": "Autopilot check failed",
    "call_started": "AI call started",
    "call_finished": "AI call finished",
    "stopped": "Stopped",
    "resumed": "Resumed",
    "mailbox_added": "Mailbox added",
    "autopilot": "Autopilot setting changed",
    "blocked_suppressed": "Blocked: on do-not-contact list",
}


@app.get("/events")
def events(limit: int = 50, include_heartbeats: bool = False, db: Session = Depends(get_db)):
    q = db.query(Event, Enrollment).outerjoin(Enrollment, Enrollment.id == Event.enrollment_id)
    if not include_heartbeats:
        q = q.filter(Event.kind != "heartbeat")
    rows = q.order_by(Event.created_at.desc()).limit(min(300, max(1, limit))).all()
    return {"events": [
        {
            "id": str(ev.id),
            "kind": ev.kind,
            "text": EVENT_TEXT.get(ev.kind, ev.kind),
            "detail": ev.detail,
            "lead_name": enr.lead_name if enr else None,
            "contact": (enr.contact_name or enr.contact_email) if enr else None,
            "created_at": iso(ev.created_at),
        }
        for ev, enr in rows
    ]}


@app.get("/today")
def today(db: Session = Depends(get_db)):
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    due = (
        db.query(Enrollment)
        .filter(Enrollment.status == "active", Enrollment.next_action_at <= datetime.utcnow() + timedelta(days=1))
        .order_by(Enrollment.next_action_at)
        .limit(50)
        .all()
    )
    hot = (
        db.query(Reply, Enrollment)
        .join(Enrollment, Enrollment.id == Reply.enrollment_id)
        .filter(Reply.category.in_(("interested", "question")), Reply.handled.is_(False))
        .order_by(Reply.received_at.desc())
        .limit(20)
        .all()
    )
    return {
        "sent_today": db.query(Message).filter(Message.status == "sent", Message.sent_at >= start).count(),
        "replies_today": db.query(Reply).filter(Reply.received_at >= start).count(),
        "drafted_today": db.query(Enrollment).filter(Enrollment.created_at >= start).count(),
        "waiting_approval": db.query(Message).filter(Message.status == "draft").count(),
        "due_next_24h": [enrollment_dict(e) for e in due],
        "hot_replies": [reply_dict(r, e) for r, e in hot],
    }


@app.get("/reports/summary")
def reports_summary(days: int = 30, db: Session = Depends(get_db)):
    return reports.summary(db, max(1, min(365, days)))


@app.get("/reports/daily")
def daily_report_preview(db: Session = Depends(get_db)):
    return {"title": "LeadGen AI: today's outreach", "lines": autopilot.daily_report_lines(db)}


@app.post("/reports/daily/send")
def daily_report_send(db: Session = Depends(get_db)):
    if not any(alerts.channels().values()):
        raise HTTPException(400, "Add SLACK_WEBHOOK_URL or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to .env first.")
    return {"sent": alerts.send_alert("LeadGen AI: today's outreach", autopilot.daily_report_lines(db))}


# ---------- alerts and CRM ----------

@app.post("/alerts/test")
def test_alert():
    if not any(alerts.channels().values()):
        raise HTTPException(400, "Add SLACK_WEBHOOK_URL or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to .env first.")
    return {"sent": alerts.send_alert("LeadGen AI test alert", ["Hot-lead alerts are working."])}


@app.post("/crm/sync")
def crm_sync(db: Session = Depends(get_db)):
    if not any(crm.configured().values()):
        raise HTTPException(400, "Add HUBSPOT_ACCESS_TOKEN or TWENTY_API_URL + TWENTY_API_KEY to .env first.")
    return {"synced": autopilot.sync_pending_crm(db)}


# ---------- AI calls ----------

@app.get("/calls")
def list_calls(limit: int = 100, db: Session = Depends(get_db)):
    rows = (
        db.query(Call, Enrollment)
        .join(Enrollment, Enrollment.id == Call.enrollment_id)
        .order_by(Call.created_at.desc())
        .limit(min(300, max(1, limit)))
        .all()
    )
    return {"calls": [call_dict(c, e) for c, e in rows], "configured": calls.configured()}


@app.post("/enrollments/{enrollment_id}/call")
def call_now(enrollment_id: UUID, db: Session = Depends(get_db)):
    if not calls.configured():
        raise HTTPException(400, "Add DOGRAH_API_URL, DOGRAH_API_KEY and DOGRAH_WORKFLOW_ID to .env first.")
    enr = _enrollment(db, enrollment_id)
    if not enr.phone:
        raise HTTPException(400, "No phone number for this contact.")
    call = calls.start_call(db, enr, get_settings(db))
    log_event(db, "call_started", enr.id, phone=enr.phone, status=call.status)
    db.commit()
    return call_dict(call, enr)


class PhoneIn(BaseModel):
    phone: str


@app.patch("/enrollments/{enrollment_id}/phone")
def set_phone(enrollment_id: UUID, body: PhoneIn, db: Session = Depends(get_db)):
    enr = _enrollment(db, enrollment_id)
    phone = calls.normalize_phone(body.phone)
    if not phone:
        raise HTTPException(400, "Use the international format, e.g. +14155550123.")
    enr.phone = phone
    db.commit()
    return enrollment_dict(enr)


@app.post("/calls/webhook")
def calls_webhook(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    header_ok = bool(settings.dograh_api_key) and request.headers.get("x-api-key") == settings.dograh_api_key
    if not header_ok and request.query_params.get("t") != sign("calls-webhook"):
        raise HTTPException(401, "Bad key")
    data = calls.parse_webhook(payload)
    call = None
    if data["call_id"]:
        try:
            call = db.query(Call).filter(Call.id == UUID(str(data["call_id"]))).first()
        except ValueError:
            call = None
    if call is None and data["run_id"]:
        call = db.query(Call).filter(Call.provider_call_id == data["run_id"]).first()
    if call is None:
        raise HTTPException(404, "Unknown call")
    if call.status == "completed":
        return {"ok": True, "duplicate": True}
    call.status, call.outcome = "completed", data["outcome"]
    call.summary, call.transcript = data["summary"][:4000], data["transcript"][:20000]
    call.completed_at = datetime.utcnow()
    enr = db.query(Enrollment).filter(Enrollment.id == call.enrollment_id).first()
    if enr:
        enr.call_status = data["outcome"]
        log_event(db, "call_finished", enr.id, outcome=data["outcome"])
        category = calls.OUTCOME_TO_REPLY.get(data["outcome"])
        if category:
            reply = Reply(enrollment_id=enr.id, message_id=f"call-{call.id}", from_email=enr.contact_email,
                          subject="AI call", body=data["summary"] or f"Call outcome: {data['outcome']}",
                          category=category, confidence=0.9, reasoning="From the AI call outcome.")
            db.add(reply)
            db.flush()
            if category == "unsubscribe":
                cfg = get_settings(db)
                cfg["dnd_numbers"] = list({*(cfg.get("dnd_numbers") or []), call.phone})
                update_settings(db, {"dnd_numbers": cfg["dnd_numbers"]})
            if category != "referral":
                autopilot.act_on_reply(db, enr, reply, {"category": category}, get_settings(db))
            else:
                reply.action_taken = "Wrong number. Phone removed."
                enr.phone = None
    db.commit()
    return {"ok": True}
