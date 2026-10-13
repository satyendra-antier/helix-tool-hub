"""The heartbeat: every N minutes do the most important outreach jobs, in priority order.

1. read new replies (and act on them)
2. send follow-ups that are due
3. send approved first emails
4. draft first emails for new hot leads (they wait for approval)
5. ask Find Leads for contacts when the queue runs low
(+ wake snoozed leads, finish completed sequences, start due AI calls)
"""

from __future__ import annotations

import logging
import math
import random
import re
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import alerts
import calls
import crm
import hub_clients
import mailer
import replies as reply_sorter
import reports
from database import Enrollment, Mailbox, Message, Reply
from store import default_sequence, get_settings, log_event
from writer import write_answer, write_email

log = logging.getLogger("outreach-autopilot")
_lock = threading.Lock()

EXEC_WORDS = ("ceo", "founder", "cto", "chief", "president", "owner", "vp", "head of", "director")
ACTIVE_STATES = ("awaiting_approval", "active", "snoozed", "replied", "interested")


# ---------- choosing who to email ----------

def _title_rank(title: str | None) -> int:
    t = (title or "").lower()
    for i, w in enumerate(EXEC_WORDS):
        if w in t:
            return i
    return 50


def pick_contact(lead: dict, suppressed: set[str], exclude: set[str] | None = None) -> dict | None:
    exclude = exclude or set()
    options = []
    for c in lead.get("contacts") or []:
        email = (c.get("email") or "").lower()
        if not email or email in suppressed or email in exclude:
            continue
        if c.get("enrichment_source") == "domain-inferred":
            continue
        local = email.split("@")[0]
        if local in ("support", "noreply", "no-reply", "privacy", "legal", "abuse", "security", "careers", "jobs"):
            continue
        conf = c.get("confidence")
        conf = 0.6 if conf is None else float(conf)
        if conf < 0.5:
            continue
        options.append((0 if c.get("full_name") else 1, _title_rank(c.get("role_title")), -conf, c))
    if not options:
        return None
    options.sort(key=lambda o: o[:3])
    return options[0][3]


def choose_mailbox(db: Session, company_domain: str | None) -> Mailbox | None:
    if company_domain:
        prior = (
            db.query(Enrollment)
            .filter(Enrollment.company_domain == company_domain, Enrollment.mailbox_id.isnot(None))
            .order_by(Enrollment.created_at.asc())
            .first()
        )
        if prior:
            mb = db.query(Mailbox).filter(Mailbox.id == prior.mailbox_id, Mailbox.active.is_(True)).first()
            if mb:
                return mb
    boxes = db.query(Mailbox).filter(Mailbox.active.is_(True)).all()
    if not boxes:
        return None
    return sorted(boxes, key=lambda m: (m.sent_today or 0) / max(1, mailer.daily_cap(m)))[0]


def _lead_context(lead: dict) -> dict:
    return {
        "name": lead.get("name"),
        "description": (lead.get("description") or "")[:800],
        "signal_type": lead.get("signal_type"),
        "signal_value": lead.get("signal_value"),
        "deadline": lead.get("deadline"),
        "fit_reason": lead.get("fit_reason"),
        "domain_context": lead.get("domain_context") or {},
        "score": lead.get("score"),
    }


def _contact_view(enr: Enrollment) -> dict:
    return {"name": enr.contact_name, "title": enr.contact_title, "email": enr.contact_email}


def enroll_lead(db: Session, lead: dict, contact: dict, cfg: dict, *, referred_by: str | None = None) -> Enrollment:
    domain = (lead.get("domain") or (contact.get("email") or "").split("@")[-1] or "").lower() or None
    mb = choose_mailbox(db, domain)
    seq = default_sequence(db)
    ctx = _lead_context(lead)
    if referred_by:
        ctx["referred_by"] = referred_by
    enr = Enrollment(
        lead_id=str(lead.get("id")),
        lead_name=lead.get("name"),
        company_domain=domain,
        contact_email=(contact.get("email") or "").lower(),
        contact_name=contact.get("full_name"),
        contact_title=contact.get("role_title"),
        phone=contact.get("phone"),
        mailbox_id=mb.id if mb else None,
        sequence_id=seq.id,
        current_step=0,
        status="awaiting_approval",
        lead_score=lead.get("score"),
        fit_reason=lead.get("fit_reason"),
        context=ctx,
    )
    db.add(enr)
    db.flush()
    draft = write_email("opener", {**lead, "referred_by": referred_by}, _contact_view(enr), cfg,
                        learnings=reports.learnings(db))
    needs_approval = bool(cfg.get("approve_first_message", True))
    db.add(Message(
        enrollment_id=enr.id, step=1, kind="opener",
        status="draft" if needs_approval else "approved",
        subject=draft["subject"], body=draft["body"], needs_approval=needs_approval,
    ))
    if not needs_approval:
        enr.status = "active"
        enr.next_action_at = datetime.utcnow()
    log_event(db, "enrolled", enr.id, lead=enr.lead_name, contact=enr.contact_email, method=draft.get("method"))
    return enr


# ---------- sending ----------

def _sends_per_heartbeat(mb: Mailbox, cfg: dict, minutes: float) -> int:
    hours = max(1, int(cfg.get("send_end_hour", 18)) - int(cfg.get("send_start_hour", 9)))
    beats = max(1.0, hours * 60 / max(1.0, minutes))
    return max(1, math.ceil(mailer.daily_cap(mb) / beats))


PLACEHOLDER = re.compile(r"\[(write|add|insert|your)\b[^\]]*\]", re.I)


def has_placeholder(msg: Message) -> bool:
    return bool(PLACEHOLDER.search(f"{msg.subject or ''}\n{msg.body or ''}"))


def send_message(db: Session, msg: Message, enr: Enrollment, mb: Mailbox, cfg: dict) -> bool:
    if has_placeholder(msg):
        msg.status, msg.error = "draft", "Fill in the [bracketed] part before sending."
        return False
    if enr.contact_email in hub_clients.suppressed_emails():
        enr.status = "unsubscribed"
        msg.status, msg.error = "rejected", "On the do-not-contact list."
        log_event(db, "blocked_suppressed", enr.id, email=enr.contact_email)
        return False
    email_msg = mailer.build_message(
        mb,
        to_email=enr.contact_email,
        to_name=enr.contact_name,
        subject=msg.subject or f"Re: {enr.subject or enr.lead_name}",
        body=msg.body or "",
        enrollment_id=str(enr.id),
        in_reply_to=enr.thread_message_id if msg.step > 1 or msg.kind == "answer" else None,
    )
    try:
        mailer.send(mb, email_msg)
    except Exception as e:  # noqa: BLE001
        msg.status, msg.error = "failed", str(e)[:400]
        mb.last_error = str(e)[:400]
        log_event(db, "send_failed", enr.id, error=msg.error)
        return False
    now = datetime.utcnow()
    mailer.record_sent(mb)
    msg.status, msg.sent_at, msg.message_id = "sent", now, email_msg["Message-ID"]
    if msg.kind != "answer":
        enr.current_step = max(enr.current_step or 0, msg.step)
    if not enr.thread_message_id:
        enr.thread_message_id = email_msg["Message-ID"]
        enr.subject = msg.subject
    enr.last_sent_at = now
    if enr.status == "awaiting_approval":
        enr.status = "active"
    steps = _steps(db, enr)
    nxt = next((s for s in steps if s["step"] == enr.current_step + 1), None)
    enr.next_action_at = now + timedelta(days=float(nxt["wait_days"] if nxt else 5))
    enr.updated_at = now
    if msg.step == 1:
        hub_clients.set_stage(enr.lead_id, "contacted")
    log_event(db, "sent", enr.id, step=msg.step, kind=msg.kind, mailbox=mb.email, sandbox=mb.kind == "sandbox")
    return True


def _steps(db: Session, enr: Enrollment) -> list[dict]:
    from database import Sequence

    seq = db.query(Sequence).filter(Sequence.id == enr.sequence_id).first() if enr.sequence_id else None
    return (seq or default_sequence(db)).steps


def _thread(db: Session, enr: Enrollment) -> list[dict]:
    msgs = db.query(Message).filter(Message.enrollment_id == enr.id, Message.status == "sent").order_by(Message.sent_at).all()
    reps = db.query(Reply).filter(Reply.enrollment_id == enr.id).order_by(Reply.received_at).all()
    items = [{"at": m.sent_at, "from": "us", "text": m.body} for m in msgs]
    items += [{"at": r.received_at, "from": "lead", "text": r.body} for r in reps]
    return [{"from": i["from"], "text": (i["text"] or "")[:800]} for i in sorted(items, key=lambda i: i["at"] or datetime.min)]


def send_approved(db: Session, cfg: dict, minutes: float) -> int:
    sent = 0
    budget: dict = {}
    rows = (
        db.query(Message, Enrollment)
        .join(Enrollment, Enrollment.id == Message.enrollment_id)
        .filter(Message.status == "approved", Enrollment.status.in_(("awaiting_approval", "active", "replied", "interested")))
        .order_by(Message.created_at)
        .limit(200)
        .all()
    )
    for msg, enr in rows:
        mb = db.query(Mailbox).filter(Mailbox.id == enr.mailbox_id).first() if enr.mailbox_id else choose_mailbox(db, enr.company_domain)
        if not mb:
            continue
        enr.mailbox_id = mb.id
        ok, _why = mailer.can_send(mb, cfg)
        left = budget.setdefault(mb.id, _sends_per_heartbeat(mb, cfg, minutes))
        if not ok or left <= 0:
            continue
        if send_message(db, msg, enr, mb, cfg):
            sent += 1
            budget[mb.id] = left - 1
            db.commit()
            if mb.kind != "sandbox":
                time.sleep(random.uniform(4, 20))
    db.commit()
    return sent


def send_due_followups(db: Session, cfg: dict, minutes: float) -> dict:
    now = datetime.utcnow()
    out = {"sent": 0, "completed": 0}
    rows = (
        db.query(Enrollment)
        .filter(Enrollment.status == "active", Enrollment.next_action_at <= now, Enrollment.current_step >= 1)
        .order_by(Enrollment.next_action_at)
        .limit(100)
        .all()
    )
    budget: dict = {}
    for enr in rows:
        steps = _steps(db, enr)
        nxt = next((s for s in steps if s["step"] == enr.current_step + 1), None)
        if not nxt:
            enr.status = "completed"
            out["completed"] += 1
            log_event(db, "sequence_completed", enr.id)
            continue
        mb = db.query(Mailbox).filter(Mailbox.id == enr.mailbox_id).first()
        if not mb:
            continue
        ok, _why = mailer.can_send(mb, cfg)
        left = budget.setdefault(mb.id, _sends_per_heartbeat(mb, cfg, minutes))
        if not ok or left <= 0:
            continue
        lead = {**(enr.context or {}), "id": enr.lead_id}
        draft = write_email(nxt["kind"], lead, _contact_view(enr), cfg,
                            previous_subject=enr.subject, thread=_thread(db, enr), learnings=reports.learnings(db))
        msg = Message(enrollment_id=enr.id, step=nxt["step"], kind=nxt["kind"], status="approved",
                      subject=draft["subject"], body=draft["body"], needs_approval=False)
        db.add(msg)
        db.flush()
        if send_message(db, msg, enr, mb, cfg):
            out["sent"] += 1
            budget[mb.id] = left - 1
            db.commit()
            if mb.kind != "sandbox":
                time.sleep(random.uniform(4, 20))
    db.commit()
    return out


def wake_snoozed(db: Session) -> int:
    rows = db.query(Enrollment).filter(Enrollment.status == "snoozed", Enrollment.next_action_at <= datetime.utcnow()).all()
    for enr in rows:
        enr.status = "active"
        log_event(db, "woke_up", enr.id)
    db.commit()
    return len(rows)


# ---------- drafting for new hot leads ----------

def draft_for_hot_leads(db: Session, cfg: dict, limit: int | None = None, min_score: float | None = None,
                        *, respect_daily: bool = True) -> dict:
    limit = int(limit if limit is not None else cfg.get("new_leads_per_day", 10))
    min_score = float(min_score if min_score is not None else cfg.get("min_lead_score", 60))
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if limit <= 0:
        return {"drafted": 0, "needs_contacts": 0}
    drafted_today = db.query(Enrollment).filter(Enrollment.created_at >= today).count() if respect_daily else 0
    room = max(0, limit - drafted_today)
    out = {"drafted": 0, "needs_contacts": 0, "skipped_company_cap": 0}
    if room == 0:
        return out
    suppressed = hub_clients.suppressed_emails()
    enrolled = {lid for (lid,) in db.query(Enrollment.lead_id).all()}
    max_per_company = int(cfg.get("max_contacts_per_company", 2))
    for lead in hub_clients.top_leads(limit=100, min_score=min_score):
        if out["drafted"] >= room:
            break
        if str(lead.get("id")) in enrolled or lead.get("is_portal_lead") or lead.get("stage") in ("won", "lost"):
            continue
        domain = (lead.get("domain") or "").lower()
        if domain and db.query(Enrollment).filter(Enrollment.company_domain == domain).count() >= max_per_company:
            out["skipped_company_cap"] += 1
            continue
        contact = pick_contact(lead, suppressed)
        if not contact:
            out["needs_contacts"] += 1
            continue
        enroll_lead(db, lead, contact, cfg)
        out["drafted"] += 1
        db.commit()
    return out


# ---------- replies ----------

def match_enrollment(db: Session, item: dict) -> Enrollment | None:
    refs = " ".join([item.get("in_reply_to") or "", item.get("references") or ""])
    for mid in [r for r in refs.split() if r.startswith("<")]:
        msg = db.query(Message).filter(Message.message_id == mid).first()
        if msg:
            return db.query(Enrollment).filter(Enrollment.id == msg.enrollment_id).first()
    sender = (item.get("from_email") or "").lower()
    if sender:
        return (
            db.query(Enrollment)
            .filter(Enrollment.contact_email == sender)
            .order_by(Enrollment.created_at.desc())
            .first()
        )
    return None


def handle_bounce(db: Session, mb: Mailbox, item: dict) -> None:
    mb.bounced_total = (mb.bounced_total or 0) + 1
    addr = mailer.bounced_address(item)
    enr = None
    if addr:
        enr = db.query(Enrollment).filter(Enrollment.contact_email == addr).order_by(Enrollment.created_at.desc()).first()
        hub_clients.suppress(addr, "bounced")
    if enr:
        enr.status = "bounced"
    log_event(db, "bounced", enr.id if enr else None, address=addr, mailbox=mb.email)


def record_reply(db: Session, enr: Enrollment | None, mb_id, item: dict, cfg: dict) -> Reply | None:
    if db.query(Reply).filter(Reply.message_id == item["message_id"]).first():
        return None
    result = reply_sorter.classify(item.get("subject") or "", item.get("body") or "")
    reply = Reply(
        enrollment_id=enr.id if enr else None,
        mailbox_id=mb_id,
        message_id=item["message_id"],
        from_email=item.get("from_email"),
        subject=item.get("subject"),
        body=item.get("body"),
        category=result["category"],
        confidence=result.get("confidence"),
        reasoning=result.get("reasoning"),
    )
    db.add(reply)
    db.flush()
    if enr:
        act_on_reply(db, enr, reply, result, cfg)
    else:
        reply.action_taken = "Couldn't match this reply to a lead. Please read it."
    db.commit()
    return reply


def act_on_reply(db: Session, enr: Enrollment, reply: Reply, result: dict, cfg: dict) -> None:
    cat = result["category"]
    now = datetime.utcnow()
    lead = {**(enr.context or {}), "id": enr.lead_id}
    actions: list[str] = []

    if cat == "unsubscribe":
        enr.status = "unsubscribed"
        hub_clients.suppress(enr.contact_email, "unsubscribe-reply")
        hub_clients.set_stage(enr.lead_id, "lost", "Asked us to stop.")
        actions.append("Stopped and added to the do-not-contact list.")
        reply.handled = True
    elif cat == "not_interested":
        enr.status = "stopped"
        hub_clients.set_stage(enr.lead_id, "lost", "Replied not interested.")
        actions.append("Stopped the sequence.")
        reply.handled = True
    elif cat == "out_of_office":
        delay = int(cfg.get("ooo_delay_days", 7))
        back = result.get("return_date")
        try:
            target = datetime.fromisoformat(back) + timedelta(days=1) if back else now + timedelta(days=delay)
        except ValueError:
            target = now + timedelta(days=delay)
        enr.next_action_at = max(enr.next_action_at or now, target)
        actions.append(f"Out of office. Next email moved to {enr.next_action_at.date().isoformat()}.")
        reply.handled = True
    elif cat == "not_now":
        days = int(cfg.get("snooze_days", 30))
        enr.status = "snoozed"
        enr.next_action_at = now + timedelta(days=days)
        actions.append(f"Snoozed for {days} days.")
        reply.handled = True
    elif cat == "referral":
        enr.status = "stopped"
        ref_email = (result.get("referral_email") or "").lower()
        if ref_email and ref_email != enr.contact_email:
            exists = db.query(Enrollment).filter(Enrollment.lead_id == enr.lead_id, Enrollment.contact_email == ref_email).first()
            if not exists:
                new = enroll_lead(db, lead, {"email": ref_email, "full_name": result.get("referral_name")}, cfg,
                                  referred_by=enr.contact_name or enr.contact_email)
                new.mailbox_id = enr.mailbox_id
                actions.append(f"Drafted a first email to {ref_email} (waiting for your approval).")
        else:
            actions.append("They pointed to someone else but didn't share an email. Please read it.")
        reply.handled = bool(ref_email)
    else:  # interested | question
        enr.status = "interested" if cat == "interested" else "replied"
        hub_clients.set_stage(enr.lead_id, "replied")
        answer = write_answer(reply.body or "", lead, _contact_view(enr), cfg, enr.subject)
        for old in db.query(Message).filter(Message.enrollment_id == enr.id, Message.kind == "answer",
                                            Message.status == "draft"):
            old.status, old.error = "rejected", "Replaced by an answer to their newer reply."
        db.add(Message(enrollment_id=enr.id, step=(enr.current_step or 1), kind="answer", status="draft",
                       subject=answer["subject"], body=answer["body"], needs_approval=True))
        actions.append("Paused the sequence and drafted an answer for your approval.")
        if cat == "interested":
            on_hot_lead(db, enr, reply, cfg, actions)

    if enr.status in ("unsubscribed", "stopped", "snoozed"):
        db.query(Message).filter(
            Message.enrollment_id == enr.id, Message.status.in_(("draft", "approved"))
        ).update({"status": "rejected", "error": f"Dropped: lead is {enr.status}."}, synchronize_session=False)

    reply.action_taken = " ".join(actions)
    enr.updated_at = now
    log_event(db, "reply", enr.id, category=cat, action=reply.action_taken)


def on_hot_lead(db: Session, enr: Enrollment, reply: Reply, cfg: dict, actions: list[str]) -> None:
    if cfg.get("alerts_enabled", True) and any(alerts.channels().values()):
        sent = alerts.send_alert(
            f"Hot lead: {enr.lead_name}",
            [
                f"{enr.contact_name or enr.contact_email} ({enr.contact_title or 'contact'}) is interested",
                f"They said: {(reply.body or '')[:200]}",
                enr.fit_reason or "",
            ],
        )
        if any(sent.values()):
            actions.append("Team alerted.")
    handoff = hub_clients.handoff_to_deal_coach({
        "lead_id": enr.lead_id,
        "lead_name": enr.lead_name,
        "contact_name": enr.contact_name,
        "contact_title": enr.contact_title,
        "contact_email": enr.contact_email,
        "why_now": enr.fit_reason,
        "thread": _thread(db, enr),
    })
    if handoff:
        actions.append("Deal Coach hand-off summary ready in Win Leads.")
    if cfg.get("crm_sync_enabled") and any(crm.configured().values()):
        result = crm.sync_enrollment(enr)
        enr.crm_synced_at = datetime.utcnow()
        actions.append("Synced to CRM." if all(v == "ok" for v in result.values()) else f"CRM sync: {result}")


def read_replies(db: Session, cfg: dict) -> dict:
    out = {"replies": 0, "bounces": 0, "errors": 0}
    for mb in db.query(Mailbox).filter(Mailbox.kind != "sandbox").all():
        try:
            items = mailer.fetch_new_messages(mb)
            mb.last_error = None
        except Exception as e:  # noqa: BLE001
            mb.last_error = f"Reading replies failed: {e}"[:400]
            out["errors"] += 1
            continue
        for item in items:
            if mailer.is_bounce(item):
                handle_bounce(db, mb, item)
                out["bounces"] += 1
                continue
            enr = match_enrollment(db, item)
            if enr is None:
                continue  # unrelated inbox mail
            if record_reply(db, enr, mb.id, item, cfg):
                out["replies"] += 1
        db.commit()
    return out


# ---------- top-up and calls ----------

def top_up_contacts(cfg: dict, needs_contacts: int) -> dict | None:
    if needs_contacts <= 0:
        return None
    return hub_clients.find_contacts_for_top(limit=min(10, needs_contacts), min_score=float(cfg.get("min_lead_score", 60)))


def run_calls(db: Session, cfg: dict) -> int:
    started = 0
    for enr in calls.due_for_call(db, cfg):
        call = calls.start_call(db, enr, cfg)
        if call.status == "dialing":
            started += 1
            log_event(db, "call_started", enr.id, phone=enr.phone)
    db.commit()
    return started


# ---------- the heartbeat ----------

def heartbeat(db: Session, *, force: bool = False, minutes: float = 15.0) -> dict:
    if not _lock.acquire(blocking=False):
        return {"skipped": "another heartbeat is running"}
    try:
        cfg = get_settings(db)
        if not force and (not cfg.get("autopilot_enabled") or cfg.get("paused")):
            return {"skipped": "autopilot is off or paused"}
        summary: dict = {"at": datetime.utcnow().isoformat()}
        summary["replies"] = read_replies(db, cfg)
        summary["woke"] = wake_snoozed(db)
        in_window = mailer.within_send_window(cfg)
        summary["in_send_window"] = in_window
        if in_window and not cfg.get("paused"):
            summary["follow_ups"] = send_due_followups(db, cfg, minutes)
            summary["first_emails"] = send_approved(db, cfg, minutes)
        drafted = draft_for_hot_leads(db, cfg)
        summary["drafted"] = drafted
        summary["top_up"] = bool(top_up_contacts(cfg, drafted.get("needs_contacts", 0)))
        summary["calls_started"] = run_calls(db, cfg)
        if cfg.get("crm_sync_enabled"):
            summary["crm_synced"] = sync_pending_crm(db)
        summary["daily_report"] = maybe_daily_report(db, cfg)
        log_event(db, "heartbeat", None, **{k: v for k, v in summary.items() if k != "at"})
        db.commit()
        return summary
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.exception("heartbeat failed")
        log_event(db, "heartbeat_failed", None, error=str(e)[:400])
        db.commit()
        return {"error": str(e)}
    finally:
        _lock.release()


def daily_report_lines(db: Session) -> list[str]:
    start = datetime.utcnow() - timedelta(hours=24)
    sent = db.query(Message).filter(Message.status == "sent", Message.sent_at >= start).count()
    reps = db.query(Reply, Enrollment).outerjoin(Enrollment, Enrollment.id == Reply.enrollment_id) \
        .filter(Reply.received_at >= start).all()
    by_type: dict = {}
    for r, _ in reps:
        by_type[r.category] = by_type.get(r.category, 0) + 1
    hot = [f"{e.lead_name} ({e.contact_name or e.contact_email})" for r, e in reps if e and r.category == "interested"]
    waiting = db.query(Message).filter(Message.status == "draft").count()
    lines = [f"Emails sent: {sent}", f"Replies: {len(reps)}"]
    if by_type:
        lines.append("Reply types: " + ", ".join(f"{reply_sorter.LABELS.get(k, k)} {v}" for k, v in by_type.items()))
    if hot:
        lines.append("Interested: " + "; ".join(hot[:5]))
    if waiting:
        lines.append(f"{waiting} first emails waiting for your approval")
    for lesson in reports.learnings(db)[:2]:
        lines.append(lesson)
    return lines


def maybe_daily_report(db: Session, cfg: dict) -> bool:
    if not cfg.get("daily_report_enabled", True) or not any(alerts.channels().values()):
        return False
    now = mailer.local_now(cfg.get("timezone") or "UTC")
    today = now.date().isoformat()
    if now.hour < int(cfg.get("send_end_hour", 18)) or cfg.get("last_daily_report") == today:
        return False
    from store import update_settings

    sent = alerts.send_alert("LeadGen AI: today's outreach", daily_report_lines(db))
    update_settings(db, {"last_daily_report": today})
    return any(sent.values())


def sync_pending_crm(db: Session) -> int:
    if not any(crm.configured().values()):
        return 0
    rows = (
        db.query(Enrollment)
        .filter((Enrollment.crm_synced_at.is_(None)) | (Enrollment.crm_synced_at < Enrollment.updated_at))
        .filter(Enrollment.status != "awaiting_approval")
        .limit(25)
        .all()
    )
    for enr in rows:
        crm.sync_enrollment(enr)
        enr.crm_synced_at = datetime.utcnow()
    db.commit()
    return len(rows)
