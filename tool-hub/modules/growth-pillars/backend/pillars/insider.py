"""Pillar 2 - Insider Agent: watch target accounts and raise alerts when something changes."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus
from uuid import UUID

import feedparser
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import InsiderAlert, WatchedAccount, get_db
from hub_clients import fetch_lead, fetch_top_leads
from jobs import create_job, run_job_in_thread

router = APIRouter(tags=["insider"])
log = logging.getLogger("growth-pillars.insider")

SCORE_JUMP = 10.0
DEADLINE_WINDOW_DAYS = 7
NEWS_LOOKBACK_DAYS = 14

NEWS_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("funding", "high", ("raises", "raised", "funding", "series a", "series b", "series c", "seed round", "investment")),
    ("acquisition", "high", ("acquires", "acquired", "acquisition", "merger")),
    ("tender", "high", ("tender", "rfp", "contract award", "awarded contract")),
    ("leadership", "medium", ("appoints", "names new", "hires", "joins as", "new ceo", "new cto", "chief technology")),
    ("launch", "medium", ("launches", "unveils", "introduces", "partnership", "partners with", "mainnet", "rolls out")),
    ("expansion", "medium", ("expands", "opens office", "enters", "hiring")),
]


class SyncRequest(BaseModel):
    size: int = Field(default=25, ge=1, le=200)
    min_lead_score: float = 0


class AddRequest(BaseModel):
    lead_id: str


class AlertPatch(BaseModel):
    read: bool


def _fingerprint(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _baseline(lead: dict) -> dict:
    return {
        "score": float(lead.get("score") or 0),
        "signal_type": lead.get("signal_type") or "",
        "signal_value": lead.get("signal_value"),
        "deadline": lead.get("deadline"),
        "stage": lead.get("stage"),
        "is_portal": bool(lead.get("is_portal_lead")),
    }


def account_to_dict(a: WatchedAccount, unread: int = 0) -> dict:
    return {
        "id": str(a.id),
        "lead_id": a.lead_id,
        "name": a.name,
        "domain": a.domain,
        "track": a.track,
        "score": (a.baseline or {}).get("score"),
        "is_portal": (a.baseline or {}).get("is_portal", False),
        "active": a.active,
        "unread_alerts": unread,
        "last_checked_at": a.last_checked_at.isoformat() if a.last_checked_at else None,
    }


def alert_to_dict(a: InsiderAlert) -> dict:
    return {
        "id": str(a.id),
        "lead_id": a.lead_id,
        "account_name": a.account_name,
        "alert_type": a.alert_type,
        "severity": a.severity,
        "title": a.title,
        "detail": a.detail,
        "url": a.url,
        "read": a.read,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _add_account(db: Session, lead: dict) -> WatchedAccount | None:
    lead_id = str(lead.get("id"))
    existing = db.query(WatchedAccount).filter(WatchedAccount.lead_id == lead_id).first()
    if existing:
        if not existing.active:
            existing.active = True
        return None
    account = WatchedAccount(
        lead_id=lead_id,
        name=lead.get("name") or "Unknown",
        domain=lead.get("domain"),
        track=lead.get("track"),
        baseline=_baseline(lead),
    )
    db.add(account)
    return account


def sync_watchlist(db: Session, size: int = 25, min_lead_score: float = 0) -> dict:
    leads = fetch_top_leads(size, min_lead_score)
    added = sum(1 for lead in leads if _add_account(db, lead) is not None)
    db.commit()
    return {"leads_considered": len(leads), "accounts_added": added}


def _save_alert(db: Session, account: WatchedAccount, alert_type: str, severity: str,
                title: str, detail: str, fingerprint: str, url: str | None = None) -> bool:
    if db.query(InsiderAlert).filter(InsiderAlert.fingerprint == fingerprint).first():
        return False
    db.add(InsiderAlert(
        account_id=account.id,
        lead_id=account.lead_id,
        account_name=account.name,
        alert_type=alert_type,
        severity=severity,
        title=title[:300],
        detail=(detail or "")[:1000],
        url=url,
        fingerprint=fingerprint,
    ))
    return True


def _diff_lead(db: Session, account: WatchedAccount, lead: dict) -> int:
    base = account.baseline or {}
    created = 0

    old_score, new_score = float(base.get("score") or 0), float(lead.get("score") or 0)
    delta = new_score - old_score
    if abs(delta) >= SCORE_JUMP:
        direction = "up" if delta > 0 else "down"
        created += _save_alert(
            db, account, "score_jump", "high" if delta >= 2 * SCORE_JUMP else "medium",
            f"{account.name}: lead score {direction} {abs(delta):.0f} pts ({old_score:.0f} → {new_score:.0f})",
            "Lead Intelligence re-scored this account. Check what changed before reaching out.",
            _fingerprint(account.lead_id, "score", f"{round(new_score / 5) * 5}"),
        )

    old_signals = set(filter(None, (base.get("signal_type") or "").split("+")))
    new_signals = set(filter(None, (lead.get("signal_type") or "").split("+")))
    for sig in sorted(new_signals - old_signals):
        created += _save_alert(
            db, account, "new_signal", "high" if sig in ("funding", "tender") else "medium",
            f"{account.name}: new {sig} signal",
            (lead.get("description") or "")[:400],
            _fingerprint(account.lead_id, "signal", sig),
        )

    deadline = lead.get("deadline")
    if deadline:
        try:
            days = (date.fromisoformat(deadline[:10]) - date.today()).days
        except ValueError:
            days = None
        if days is not None and 0 <= days <= DEADLINE_WINDOW_DAYS:
            created += _save_alert(
                db, account, "deadline", "high",
                f"{account.name}: deadline in {days} day(s)",
                f"Submission deadline {deadline[:10]}. Decide go / no-go now.",
                _fingerprint(account.lead_id, "deadline", deadline[:10]),
                lead.get("portal_link"),
            )
    return created


def _classify_news(title: str) -> tuple[str, str] | None:
    t = title.lower()
    for alert_type, severity, words in NEWS_RULES:
        if any(w in t for w in words):
            return alert_type, severity
    return None


def _mentions(name: str, title: str) -> bool:
    core = re.sub(r"\b(inc|ltd|llc|labs|protocol|network|corp|co)\b\.?", "", name, flags=re.I).strip()
    if len(core) < 3:
        return False
    return re.search(rf"\b{re.escape(core)}\b", title, flags=re.I) is not None


def fetch_news(name: str) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(chr(34) + name + chr(34))}+when:{NEWS_LOOKBACK_DAYS}d&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "ToolHub-InsiderAgent/1.0"})
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.text)
    except httpx.HTTPError:
        return []
    return [
        {"title": e.get("title", ""), "link": e.get("link"), "published": e.get("published")}
        for e in feed.entries[:20]
    ]


def _news_alerts(db: Session, account: WatchedAccount) -> int:
    created = 0
    for item in fetch_news(account.name):
        title = item["title"]
        if not _mentions(account.name, title):
            continue
        classified = _classify_news(title)
        if not classified:
            continue
        alert_type, severity = classified
        created += _save_alert(
            db, account, alert_type, severity, f"{account.name}: {title}",
            f"News ({item.get('published') or 'recent'})",
            _fingerprint(account.lead_id, "news", item.get("link") or title),
            item.get("link"),
        )
    return created


def fetch_hiring_count(name: str) -> int | None:
    if not (settings.adzuna_app_id and settings.adzuna_app_key):
        return None
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            resp = client.get(
                "https://api.adzuna.com/v1/api/jobs/gb/search/1",
                params={
                    "app_id": settings.adzuna_app_id,
                    "app_key": settings.adzuna_app_key,
                    "company": name,
                    "max_days_old": 30,
                    "results_per_page": 1,
                },
            )
        if resp.status_code != 200:
            return None
        return int(resp.json().get("count") or 0)
    except (httpx.HTTPError, ValueError):
        return None


def _hiring_alert(db: Session, account: WatchedAccount, base: dict) -> int:
    count = fetch_hiring_count(account.name)
    if count is None:
        return 0
    previous = base.get("open_roles")
    base["open_roles"] = count
    if previous is None or count < 3:
        return 0
    if count - previous >= 3 and count >= previous * 1.5:
        return _save_alert(
            db, account, "hiring", "medium",
            f"{account.name}: hiring spike ({previous} → {count} open roles)",
            "A jump in open roles often means a new initiative or budget.",
            _fingerprint(account.lead_id, "hiring", str(count)),
        )
    return 0


def scan_watchlist(db: Session) -> dict:
    accounts = db.query(WatchedAccount).filter(WatchedAccount.active.is_(True)).all()
    alerts, removed = 0, 0
    for account in accounts:
        try:
            lead = fetch_lead(account.lead_id)
            if lead is None:
                account.active = False
                removed += 1
                db.commit()
                continue
            alerts += _diff_lead(db, account, lead)
            base = {**(account.baseline or {}), **_baseline(lead)}
            if not base.get("is_portal"):
                alerts += _news_alerts(db, account)
                alerts += _hiring_alert(db, account, base)
            account.baseline = base
            account.last_checked_at = datetime.utcnow()
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("Insider scan failed for %s", account.name)
    return {"accounts_scanned": len(accounts), "alerts_created": alerts, "accounts_removed": removed}


def count_watched(db: Session) -> int:
    return db.query(WatchedAccount).filter(WatchedAccount.active.is_(True)).count()


def count_unread(db: Session) -> int:
    return db.query(InsiderAlert).filter(InsiderAlert.read.is_(False)).count()


def recent_alerts_by_lead(db: Session, days: int = 14) -> dict[str, list[InsiderAlert]]:
    since = datetime.utcnow() - timedelta(days=days)
    out: dict[str, list[InsiderAlert]] = {}
    for a in db.query(InsiderAlert).filter(InsiderAlert.created_at >= since).all():
        out.setdefault(a.lead_id, []).append(a)
    return out


@router.get("/watchlist")
def list_watchlist(db: Session = Depends(get_db)):
    accounts = (
        db.query(WatchedAccount)
        .filter(WatchedAccount.active.is_(True))
        .order_by(WatchedAccount.created_at.desc())
        .all()
    )
    unread: dict[str, int] = {}
    for a in db.query(InsiderAlert).filter(InsiderAlert.read.is_(False)).all():
        unread[a.lead_id] = unread.get(a.lead_id, 0) + 1
    return {"accounts": [account_to_dict(a, unread.get(a.lead_id, 0)) for a in accounts]}


@router.post("/watchlist/sync")
def sync_watchlist_endpoint(body: SyncRequest | None = None, db: Session = Depends(get_db)):
    body = body or SyncRequest()
    return sync_watchlist(db, body.size, body.min_lead_score)


@router.post("/watchlist")
def add_to_watchlist(body: AddRequest, db: Session = Depends(get_db)):
    lead = fetch_lead(body.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found in Lead Intelligence")
    _add_account(db, lead)
    db.commit()
    account = db.query(WatchedAccount).filter(WatchedAccount.lead_id == str(lead["id"])).first()
    return account_to_dict(account)


@router.delete("/watchlist/{account_id}")
def remove_from_watchlist(account_id: UUID, db: Session = Depends(get_db)):
    account = db.get(WatchedAccount, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    account.active = False
    db.commit()
    return {"removed": True}


@router.post("/insider/scan")
def scan_endpoint(db: Session = Depends(get_db)):
    job = create_job(db, "insider_scan")
    run_job_in_thread(job.id, lambda s, _r: scan_watchlist(s))
    return {"job_id": str(job.id)}


@router.get("/alerts")
def list_alerts(unread_only: bool = False, lead_id: Optional[str] = None, limit: int = 100,
                db: Session = Depends(get_db)):
    q = db.query(InsiderAlert)
    if unread_only:
        q = q.filter(InsiderAlert.read.is_(False))
    if lead_id:
        q = q.filter(InsiderAlert.lead_id == lead_id)
    alerts = q.order_by(InsiderAlert.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return {"alerts": [alert_to_dict(a) for a in alerts]}


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: UUID, body: AlertPatch, db: Session = Depends(get_db)):
    alert = db.get(InsiderAlert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.read = body.read
    db.commit()
    return alert_to_dict(alert)


@router.post("/alerts/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    updated = db.query(InsiderAlert).filter(InsiderAlert.read.is_(False)).update({"read": True})
    db.commit()
    return {"updated": updated}
