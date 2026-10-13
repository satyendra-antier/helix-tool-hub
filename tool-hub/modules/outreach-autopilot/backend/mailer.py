"""Send from our own mailboxes (SMTP) and read replies (IMAP).

`sandbox` mailboxes never touch the network: sends are recorded only and replies
are injected through the API. Use them to test the whole loop safely.
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from zoneinfo import ZoneInfo

from config import settings
from crypto import decrypt, sign
from database import Mailbox

BOUNCE_SENDERS = ("mailer-daemon", "postmaster", "mail delivery")
BOUNCE_SUBJECTS = ("undeliverable", "delivery status notification", "returned mail", "delivery failure",
                   "undelivered mail", "failure notice", "mail delivery failed")


def local_now(tz: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.now(ZoneInfo("UTC"))


def within_send_window(cfg: dict) -> bool:
    now = local_now(cfg.get("timezone") or "UTC")
    if not cfg.get("send_weekends") and now.weekday() >= 5:
        return False
    return int(cfg.get("send_start_hour", 9)) <= now.hour < int(cfg.get("send_end_hour", 18))


def daily_cap(mb: Mailbox) -> int:
    days = max(0, (datetime.utcnow() - (mb.created_at or datetime.utcnow())).days)
    return int(min(mb.daily_cap_max or 50, (mb.daily_cap_start or 20) + (mb.ramp_per_day or 0) * days))


def _reset_counter(mb: Mailbox, tz: str) -> None:
    today = local_now(tz).date().isoformat()
    if mb.sent_today_date != today:
        mb.sent_today = 0
        mb.sent_today_date = today


def bounce_rate(mb: Mailbox) -> float:
    return (mb.bounced_total or 0) / mb.sent_total if mb.sent_total else 0.0


def can_send(mb: Mailbox, cfg: dict) -> tuple[bool, str]:
    _reset_counter(mb, cfg.get("timezone") or "UTC")
    if not mb.active:
        return False, mb.paused_reason or "mailbox paused"
    if (mb.sent_total or 0) >= 20 and bounce_rate(mb) > float(cfg.get("max_bounce_rate", 0.05)):
        mb.active = False
        mb.paused_reason = f"Bounce rate {bounce_rate(mb):.0%} is above the safe limit. Clean the list, then resume."
        return False, mb.paused_reason
    if (mb.sent_today or 0) >= daily_cap(mb):
        return False, "daily cap reached"
    return True, ""


def unsubscribe_url(enrollment_id: str) -> str:
    token = sign(str(enrollment_id))
    return f"{settings.outreach_public_url.rstrip('/')}/unsubscribe?e={enrollment_id}&t={token}"


def build_message(
    mb: Mailbox,
    *,
    to_email: str,
    to_name: str | None,
    subject: str,
    body: str,
    enrollment_id: str,
    in_reply_to: str | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    domain = (mb.email.split("@")[-1] or "leadgen.local").strip()
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["From"] = formataddr((mb.from_name or "", mb.email))
    msg["To"] = formataddr((to_name or "", to_email))
    msg["Subject"] = subject
    unsub = unsubscribe_url(enrollment_id)
    msg["List-Unsubscribe"] = f"<{unsub}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    footer = f"\n\n--\nNot the right time? Reply \"stop\" or unsubscribe here: {unsub}"
    msg.set_content(body.rstrip() + footer)
    return msg


def _smtp(mb: Mailbox) -> smtplib.SMTP:
    password = decrypt(mb.secret_enc)
    if (mb.smtp_security or "starttls") == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(mb.smtp_host, mb.smtp_port or 465, timeout=30,
                                                context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(mb.smtp_host, mb.smtp_port or 587, timeout=30)
        if mb.smtp_security != "none":
            server.starttls(context=ssl.create_default_context())
    server.login(mb.username or mb.email, password)
    return server


def send(mb: Mailbox, msg: EmailMessage) -> None:
    if mb.kind == "sandbox":
        return
    with _smtp(mb) as server:
        server.send_message(msg)


def record_sent(mb: Mailbox) -> None:
    mb.sent_today = (mb.sent_today or 0) + 1
    mb.sent_total = (mb.sent_total or 0) + 1


def test_connection(mb: Mailbox) -> dict:
    if mb.kind == "sandbox":
        return {"smtp": True, "imap": True, "note": "Sandbox mailbox: nothing is really sent."}
    out = {"smtp": False, "imap": False, "error": None}
    try:
        with _smtp(mb):
            out["smtp"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = f"SMTP: {e}"
    try:
        with _imap(mb):
            out["imap"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = (out["error"] + " | " if out["error"] else "") + f"IMAP: {e}"
    return out


def _imap(mb: Mailbox) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port or 993, timeout=30)
    conn.login(mb.username or mb.email, decrypt(mb.secret_enc))
    return conn


def _text_body(msg: email.message.Message) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                body = part.get_content() if hasattr(part, "get_content") else part.get_payload(decode=True).decode(errors="ignore")
                break
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html = part.get_content()
                    body = re.sub(r"<[^>]+>", " ", html)
                    break
    else:
        body = msg.get_content() if hasattr(msg, "get_content") else str(msg.get_payload())
    return strip_quoted(body)


def strip_quoted(body: str) -> str:
    """Keep only the new part of a reply."""
    lines: list[str] = []
    for line in (body or "").splitlines():
        if line.startswith(">"):
            break
        if re.match(r"^On .+wrote:\s*$", line.strip()) or line.strip().startswith("-----Original Message"):
            break
        lines.append(line)
    return "\n".join(lines).strip()[:5000]


def fetch_new_messages(mb: Mailbox) -> list[dict]:
    """New inbox messages since the last seen UID."""
    if mb.kind == "sandbox":
        return []
    out: list[dict] = []
    with _imap(mb) as conn:
        conn.select("INBOX")
        since = (mb.last_seen_uid or 0) + 1
        typ, data = conn.uid("search", None, f"UID {since}:*")
        if typ != "OK":
            return out
        uids = [int(u) for u in (data[0] or b"").split() if int(u) >= since][:100]
        for uid in uids:
            typ, msg_data = conn.uid("fetch", str(uid), "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            msg = email.message_from_bytes(msg_data[0][1], policy=email.policy.default)
            name, addr = parseaddr(str(msg.get("From", "")))
            out.append({
                "uid": uid,
                "message_id": str(msg.get("Message-ID", "")).strip() or f"uid-{mb.id}-{uid}",
                "in_reply_to": str(msg.get("In-Reply-To", "")).strip(),
                "references": str(msg.get("References", "")).strip(),
                "from_email": addr.lower(),
                "from_name": name,
                "subject": str(msg.get("Subject", "")),
                "body": _text_body(msg),
            })
            mb.last_seen_uid = max(mb.last_seen_uid or 0, uid)
    return out


def is_bounce(item: dict) -> bool:
    sender = (item.get("from_email") or "").lower()
    subject = (item.get("subject") or "").lower()
    return any(s in sender for s in BOUNCE_SENDERS) or any(s in subject for s in BOUNCE_SUBJECTS)


def bounced_address(item: dict) -> str | None:
    found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", item.get("body") or "")
    for addr in found:
        if not any(s in addr.lower() for s in BOUNCE_SENDERS):
            return addr.lower()
    return None
