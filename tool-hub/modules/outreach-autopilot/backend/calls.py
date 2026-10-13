"""AI phone calls through a self-hosted Dograh instance.

Dograh runs the voice agent (speech-to-text, LLM, text-to-speech, telephony).
We start a run with POST /api/v1/public/agent/workflow/{workflow_uuid} and Dograh's
webhook node posts the outcome back to POST /calls/webhook.

The Dograh agent prompt must open with an AI disclosure and recording notice,
e.g. "Hi {{contact_name}}, this is an AI assistant calling for {{company_name}}.
This call may be recorded." and offer to transfer to a person on request.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from config import settings
from database import Call, Enrollment
from mailer import local_now

OUTCOME_TO_REPLY = {
    "interested": "interested",
    "call_back": "not_now",
    "not_interested": "not_interested",
    "do_not_call": "unsubscribe",
    "wrong_number": "referral",
}


def configured() -> bool:
    return bool(settings.dograh_api_url and settings.dograh_api_key and settings.dograh_workflow_id)


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"[^\d+]", "", phone)
    if not digits.startswith("+"):
        return None  # E.164 required: we never guess country codes
    return digits if 8 <= len(digits) <= 16 else None


def call_window_ok(cfg: dict) -> bool:
    now = local_now(cfg.get("timezone") or "UTC")
    if now.weekday() >= 5:
        return False
    # Calls are stricter than email: 10:00-17:00 local only.
    return 10 <= now.hour < 17


def is_dnd(phone: str, cfg: dict) -> bool:
    blocked = {normalize_phone(p) for p in (cfg.get("dnd_numbers") or [])}
    return phone in blocked


def due_for_call(db: Session, cfg: dict) -> list[Enrollment]:
    """Active enrollments where touch N got no reply for `call_wait_days` and a phone is known."""
    if not cfg.get("calls_enabled") or not configured():
        return []
    after_step = int(cfg.get("call_after_step", 2))
    wait = timedelta(days=float(cfg.get("call_wait_days", 2)))
    cutoff = datetime.utcnow() - wait
    rows = (
        db.query(Enrollment)
        .filter(
            Enrollment.status == "active",
            Enrollment.current_step >= after_step,
            Enrollment.phone.isnot(None),
            Enrollment.call_status.is_(None),
            Enrollment.last_sent_at <= cutoff,
        )
        .limit(5)
        .all()
    )
    return rows


def start_call(db: Session, enr: Enrollment, cfg: dict) -> Call:
    phone = normalize_phone(enr.phone)
    call = Call(enrollment_id=enr.id, phone=enr.phone or "", status="queued")
    db.add(call)
    db.flush()
    if not phone:
        call.status, call.error = "skipped", "Phone number must be in +country format."
    elif is_dnd(phone, cfg):
        call.status, call.error = "skipped", "Number is on the do-not-call list."
    elif not call_window_ok(cfg):
        call.status, call.error = "queued", "Outside calling hours, will retry."
        db.commit()
        return call
    else:
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{settings.dograh_api_url.rstrip('/')}/api/v1/public/agent/workflow/{settings.dograh_workflow_id}",
                    headers={"X-API-Key": settings.dograh_api_key},
                    json={
                        "phone_number": phone,
                        "initial_context": {
                            "call_id": str(call.id),
                            "enrollment_id": str(enr.id),
                            "contact_name": enr.contact_name or "",
                            "contact_title": enr.contact_title or "",
                            "lead_company": enr.lead_name or "",
                            "why_now": enr.fit_reason or "",
                            "company_name": cfg.get("company_name") or "",
                            "sender_name": cfg.get("sender_name") or "",
                            "booking_link": cfg.get("booking_link") or "",
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            call.provider_call_id = str(data.get("workflow_run_id") or data.get("id") or "")
            call.status = "dialing"
        except Exception as e:  # noqa: BLE001
            call.status, call.error = "failed", str(e)[:300]
    enr.call_status = call.status
    db.commit()
    return call


def parse_webhook(payload: dict) -> dict:
    """Accept the shapes a Dograh webhook node commonly sends."""
    ctx = payload.get("initial_context") or payload.get("context") or {}
    extracted = payload.get("extracted_variables") or payload.get("gathered_context") or {}
    outcome = (
        payload.get("outcome") or payload.get("disposition") or extracted.get("outcome")
        or extracted.get("disposition") or ""
    )
    outcome = str(outcome).lower().replace(" ", "_").replace("-", "_")
    if outcome not in ("interested", "call_back", "not_interested", "do_not_call", "wrong_number", "no_answer"):
        outcome = "no_answer" if not outcome else outcome
    return {
        "call_id": payload.get("call_id") or ctx.get("call_id"),
        "run_id": str(payload.get("workflow_run_id") or payload.get("run_id") or ""),
        "outcome": outcome,
        "summary": payload.get("summary") or extracted.get("summary") or "",
        "transcript": payload.get("transcript") or "",
    }
