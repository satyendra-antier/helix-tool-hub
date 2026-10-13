"""Settings, default sequence and the audit log."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from config import settings as env
from database import Event, OutreachSetting, Sequence

DEFAULT_SETTINGS: dict = {
    "autopilot_enabled": False,
    "paused": False,
    "approve_first_message": True,
    "min_lead_score": 60,
    "new_leads_per_day": 10,
    "max_contacts_per_company": 2,
    "sender_name": "",
    "company_name": env.default_company_name,
    "company_url": env.default_company_url,
    "value_prop": "We design, build and audit blockchain, AI and fintech products for growing companies.",
    "signature": "",
    "booking_link": "",
    "timezone": "Asia/Kolkata",
    "send_start_hour": 9,
    "send_end_hour": 18,
    "send_weekends": False,
    "snooze_days": 30,
    "ooo_delay_days": 7,
    "max_bounce_rate": 0.05,
    "alerts_enabled": True,
    "crm_sync_enabled": False,
    "calls_enabled": False,
    "call_after_step": 2,
    "call_wait_days": 2,
    "dnd_numbers": [],
    "daily_report_enabled": True,
    "last_daily_report": "",
}

DEFAULT_SEQUENCE = [
    {"step": 1, "wait_days": 0, "kind": "opener", "label": "Curious question, no pitch"},
    {"step": 2, "wait_days": 4, "kind": "follow_up", "label": "Short follow-up"},
    {"step": 3, "wait_days": 5, "kind": "insight", "label": "Share one useful idea"},
    {"step": 4, "wait_days": 5, "kind": "soft_close", "label": "Soft close with booking link"},
]


def get_settings(db: Session) -> dict:
    rows = {r.key: r.value for r in db.query(OutreachSetting).all()}
    merged = dict(DEFAULT_SETTINGS)
    for key, val in rows.items():
        merged[key] = val.get("v") if isinstance(val, dict) and "v" in val else val
    return merged


def update_settings(db: Session, values: dict) -> dict:
    for key, val in values.items():
        if key not in DEFAULT_SETTINGS:
            continue
        row = db.query(OutreachSetting).filter(OutreachSetting.key == key).first()
        if row:
            row.value = {"v": val}
            row.updated_at = datetime.utcnow()
        else:
            db.add(OutreachSetting(key=key, value={"v": val}))
    db.commit()
    return get_settings(db)


def default_sequence(db: Session) -> Sequence:
    seq = db.query(Sequence).filter(Sequence.is_default.is_(True)).first()
    if seq:
        return seq
    seq = Sequence(name="4 emails over 14 days", steps=DEFAULT_SEQUENCE, is_default=True)
    db.add(seq)
    db.commit()
    db.refresh(seq)
    return seq


def log_event(db: Session, event_kind: str, enrollment_id=None, /, **detail) -> None:
    db.add(Event(enrollment_id=enrollment_id, kind=event_kind, detail=detail))
