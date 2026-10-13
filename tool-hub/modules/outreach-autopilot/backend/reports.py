"""Results: what got sent, what got replies, and simple lessons fed back to the writer."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import Call, Enrollment, Message, Reply

POSITIVE = ("interested", "question", "referral")
_cache: dict = {"at": 0.0, "value": []}


def _attribute(db: Session, since: datetime | None = None):
    """Pair each reply with the last email we sent before it."""
    q = db.query(Message).filter(Message.status == "sent")
    if since:
        q = q.filter(Message.sent_at >= since)
    sent = q.all()
    by_enr: dict = defaultdict(list)
    for m in sent:
        by_enr[m.enrollment_id].append(m)
    for msgs in by_enr.values():
        msgs.sort(key=lambda m: m.sent_at or datetime.min)
    rq = db.query(Reply).filter(Reply.enrollment_id.isnot(None))
    if since:
        rq = rq.filter(Reply.received_at >= since)
    pairs = []
    for r in rq.all():
        before = [m for m in by_enr.get(r.enrollment_id, []) if (m.sent_at or datetime.min) <= (r.received_at or datetime.max)]
        pairs.append((r, before[-1] if before else None))
    return sent, pairs


def summary(db: Session, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    sent, pairs = _attribute(db, since)
    first_subject = {
        m.enrollment_id: m.subject for m in sent if m.step == 1 and m.kind == "opener"
    }

    by_step: dict = defaultdict(lambda: {"sent": 0, "replies": 0, "positive": 0})
    by_subject: dict = defaultdict(lambda: {"sent": 0, "replies": 0, "positive": 0})
    for m in sent:
        if m.kind == "answer":
            continue
        by_step[m.step]["sent"] += 1
    for subj in first_subject.values():
        by_subject[subj or "(no subject)"]["sent"] += 1
    replied_enr = set()
    interested_enr = set()
    step_seen = set()
    for r, m in pairs:
        if m is None:
            continue
        if r.category == "interested":
            interested_enr.add(r.enrollment_id)
        if m.kind != "answer" and (r.enrollment_id, m.step) not in step_seen:
            step_seen.add((r.enrollment_id, m.step))
            by_step[m.step]["replies"] += 1
            if r.category in POSITIVE:
                by_step[m.step]["positive"] += 1
        if r.enrollment_id not in replied_enr:
            replied_enr.add(r.enrollment_id)
            subj = first_subject.get(r.enrollment_id)
            if subj is not None:
                by_subject[subj]["replies"] += 1
                if r.category in POSITIVE:
                    by_subject[subj]["positive"] += 1

    categories: dict = defaultdict(int)
    for r, _ in pairs:
        categories[r.category or "unknown"] += 1

    daily: dict = defaultdict(lambda: {"sent": 0, "replies": 0})
    for m in sent:
        if m.sent_at:
            daily[m.sent_at.date().isoformat()]["sent"] += 1
    for r, _ in pairs:
        if r.received_at:
            daily[r.received_at.date().isoformat()]["replies"] += 1

    enrolled = db.query(Enrollment).filter(Enrollment.created_at >= since).count()
    statuses: dict = defaultdict(int)
    for (status,) in db.query(Enrollment.status).filter(Enrollment.created_at >= since).all():
        statuses[status] += 1
    calls = db.query(Call).filter(Call.created_at >= since).all()
    total_sent = sum(1 for m in sent if m.kind != "answer")
    total_replies = len(replied_enr)

    def rate(d):
        return round(d["replies"] / d["sent"], 3) if d["sent"] else 0.0

    return {
        "days": days,
        "totals": {
            "enrolled": enrolled,
            "emails_sent": total_sent,
            "people_replied": total_replies,
            "reply_rate": round(total_replies / max(1, len({m.enrollment_id for m in sent})), 3) if sent else 0.0,
            "interested": len(interested_enr),
            "bounced": statuses.get("bounced", 0),
            "unsubscribed": statuses.get("unsubscribed", 0),
            "calls": len(calls),
            "calls_interested": sum(1 for c in calls if c.outcome == "interested"),
        },
        "by_step": [{"step": s, **v, "reply_rate": rate(v)} for s, v in sorted(by_step.items())],
        "by_subject": sorted(
            ({"subject": s, **v, "reply_rate": rate(v)} for s, v in by_subject.items()),
            key=lambda x: (-x["reply_rate"], -x["sent"]),
        )[:15],
        "reply_types": dict(categories),
        "daily": [{"date": d, **v} for d, v in sorted(daily.items())],
        "learnings": learnings(db, fresh=True),
    }


def learnings(db: Session, fresh: bool = False) -> list[str]:
    """Plain-English lessons from the last 60 days. Cached for 10 minutes."""
    if not fresh and time.time() - _cache["at"] < 600:
        return _cache["value"]
    out: list[str] = []
    try:
        sent, pairs = _attribute(db, datetime.utcnow() - timedelta(days=60))
        firsts = {m.enrollment_id: m for m in sent if m.step == 1 and m.kind == "opener"}
        replied = {r.enrollment_id for r, _ in pairs if r.category in POSITIVE}
        subj_stats: dict = defaultdict(lambda: [0, 0])
        len_stats = {"short": [0, 0], "long": [0, 0]}
        for enr_id, m in firsts.items():
            hit = 1 if enr_id in replied else 0
            subj_stats[m.subject or ""][0] += 1
            subj_stats[m.subject or ""][1] += hit
            bucket = "short" if len((m.body or "").split()) <= 70 else "long"
            len_stats[bucket][0] += 1
            len_stats[bucket][1] += hit
        good = [(s, n, h) for s, (n, h) in subj_stats.items() if n >= 5 and h / n >= 0.1]
        for s, n, h in sorted(good, key=lambda x: -x[2] / x[1])[:3]:
            out.append(f"Subject lines like '{s}' got positive replies {h}/{n} times.")
        (sn, sh), (ln, lh) = len_stats["short"], len_stats["long"]
        if sn >= 5 and ln >= 5:
            better = "Shorter" if sh / sn >= lh / ln else "Longer"
            out.append(f"{better} first emails (around 70 words) are getting more replies.")
        step_hits: dict = defaultdict(int)
        for r, m in pairs:
            if m is not None and r.category in POSITIVE:
                step_hits[m.kind] += 1
        if sum(step_hits.values()) >= 5:
            best = max(step_hits.items(), key=lambda x: x[1])[0]
            out.append(f"Most positive replies come after the '{best}' email. Keep that style.")
    except Exception:  # noqa: BLE001
        out = []
    _cache.update(at=time.time(), value=out)
    return out
