"""AI email writer for each sequence step, with safe templates when no API key is set.

Strategy (from the best public outreach workflows):
  1 opener      genuine question about their signal, no pitch, no link
  2 follow_up   short, natural nudge
  3 insight     one concrete idea tied to their signal and our strength
  4 soft_close  the only email with the booking link
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

from llm_client import chat_json, llm_available

STEP_GUIDE = {
    "opener": "Open a conversation. Ask ONE genuine question about the specific signal. No pitch, no link, no meeting ask. Max 80 words.",
    "follow_up": "Short, friendly follow-up to your first email in the same thread. Add one new angle. No link. Max 60 words.",
    "insight": "Share ONE concrete, useful idea tied to their signal and our strength (a pattern, risk, or quick win). Offer to share more. No link. Max 100 words.",
    "soft_close": "Polite last note. Offer a short call using the booking link if provided; otherwise ask if a call next week works. Make it easy to say no. Max 70 words.",
    "answer": "Answer their question directly and honestly using only the facts given. If unsure, say we'll confirm. Suggest a next step. Max 120 words.",
}

SYSTEM = (
    "You write short, human B2B emails. Plain text, no emojis, no hype words "
    "(revolutionary, cutting-edge, synergy), no fake familiarity, never invent facts "
    "about the recipient. Always sign with the sender name given. Output JSON."
)


ROLE_WORDS = {
    "institutional", "lending", "sales", "team", "info", "partnerships", "partnership", "support", "business",
    "development", "contact", "hello", "admin", "marketing", "media", "press", "office", "general", "inquiry",
    "inquiries", "bd", "hr", "careers", "investor", "relations", "operations", "finance", "legal",
}


def _first_name(name: str | None) -> str:
    words = (name or "").strip().split()
    if not words or any(w.lower().strip(".,") in ROLE_WORDS for w in words):
        return ""
    return words[0]


def _signal_line(lead: dict) -> str:
    return (lead.get("fit_reason") or "").strip() or (lead.get("description") or "")[:160]


def _public_signal(lead: dict) -> str:
    """The fit reason minus our internal wording ('fits our X market'), safe to show the recipient."""
    text = (lead.get("fit_reason") or "").strip()
    for cut in (" and fits our", ", which fits our", ". Fits our", " fits our"):
        if cut in text:
            text = text.split(cut)[0]
    return text.rstrip(" .")


def _signature(cfg: dict) -> str:
    if cfg.get("signature"):
        return cfg["signature"]
    parts = [cfg.get("sender_name") or "", cfg.get("company_name") or ""]
    return "\n".join(dict.fromkeys(p for p in parts if p))


def _money(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}" if v >= 1000 else ""


def _date(value) -> str:
    try:
        return datetime.fromisoformat(str(value)[:10]).strftime("%-d %b" if os.name != "nt" else "%#d %b")
    except ValueError:
        return ""


def _short(text: str, limit: int = 70) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def lead_facts(lead: dict) -> dict:
    """Concrete, recipient-safe facts per signal type, pulled from the lead record."""
    desc = (lead.get("description") or "").strip()
    sig = (lead.get("signal_type") or "").lower()
    facts = {
        "signal": sig,
        "company": _short(lead.get("name") or "your team", 60),
        "market": (lead.get("domain_context") or {}).get("domain_name") or "",
        "deadline": _date(lead.get("deadline")),
    }
    if sig == "hiring" and "—" in desc:
        facts["role"] = _short(desc.split("—", 1)[1].split(",")[0], 60)
    elif sig == "protocol":
        category = desc.split(" protocol on", 1)[0].strip() if " protocol on" in desc else ""
        facts["category"] = category if category.isupper() else category.lower()
        facts["tvl"] = _money(lead.get("signal_value"))
    elif sig == "launch":
        facts["tagline"] = _short(desc.split(" Discussion (", 1)[0].rstrip(". "), 90)
    elif sig == "funding":
        facts["amount"] = _money(lead.get("signal_value"))
    elif sig in ("grant", "tender"):
        facts["agency"] = _short(desc.split("—", 1)[0], 60) if "—" in desc else ""
    return {k: v for k, v in facts.items() if v}


def _opener(f: dict, lead: dict) -> tuple[str, str, str]:
    """(subject, observation, question) for the first email."""
    c, sig, market = f["company"], f.get("signal"), f.get("market")
    if sig == "hiring" and f.get("role"):
        role = f["role"]
        return (f"Your {role} hire",
                f"I saw {c} is hiring {_article(role)} {role}.",
                "Is that hire about adding capacity for something already planned, or a new direction for the team?")
    if sig == "protocol":
        what = f"{f['category']} " if f.get("category") else ""
        seen = (f"I was looking at {c} on DefiLlama: {f['tvl']} locked in {what}is serious scale." if f.get("tvl")
                else f"I was looking at {c} on DefiLlama. That's serious scale for {_article(what or 'a')} {what}protocol.")
        return (f"{c}'s next upgrade",
                seen,
                "As it keeps growing, what's the bigger headache right now: shipping new features, or audits and upgrade safety?")
    if sig == "launch":
        what = f": \"{f['tagline']}\"" if f.get("tagline") else ""
        return (f"Congrats on the {c} launch",
                f"Congrats on launching {c}{what}.",
                "Now that it's out, what's next on the build list: scaling, integrations, or new features?")
    if sig == "funding":
        amount = f" {f['amount']}" if f.get("amount") else ""
        headline = len(c.split()) > 5
        return ("Congrats on the raise",
                f"I saw the recent news: \"{c}\"." if headline else f"Congrats on the recent{amount} news at {c}.",
                "Where does the new money go first on the tech side: a new product, scaling what you have, or compliance?")
    if sig in ("grant", "tender"):
        due = f" (closing {f['deadline']})" if f.get("deadline") else ""
        kind = "tender" if sig == "tender" else "programme"
        return (f"Question about the {kind}",
                f"I saw the {c} {kind}{due}.",
                "Is there a contact for technical questions before submissions, and are you open to industry partners on the build side?")
    signal = _public_signal(lead)
    return (f"Question about {c}",
            f"I noticed {signal}." if signal else f"I've been following {c}'s recent growth.",
            f"Curious how you're thinking about {market or 'your roadmap'} over the next couple of quarters?")


def _nudge(f: dict) -> str:
    sig = f.get("signal")
    if sig == "hiring" and f.get("role"):
        return f"If the {f['role']} search takes a while, we can carry that work in the meantime and hand it over cleanly. Worth a quick chat?"
    if sig == "protocol":
        return "Even a quick yes or no on whether upgrades or audits are on the roadmap this quarter would help."
    if sig == "launch":
        return "Happy to share what usually breaks first in the weeks after a launch, if that's useful."
    if sig == "funding":
        return "Curious whether the tech plan is moving faster than hiring right now."
    if sig in ("grant", "tender"):
        due = f" before {f['deadline']}" if f.get("deadline") else ""
        return f"Is there still room for a technical partner{due}?"
    return f"Is {f.get('market') or 'this'} on your plate this quarter?"


def _insight(f: dict) -> str:
    sig, c = f.get("signal"), f["company"]
    if sig == "hiring":
        return ("While a senior seat is open, teams often lose two or three months of roadmap. "
                "A small senior squad can keep things moving and hand over to the new hire.")
    if sig == "protocol":
        size = f"With {f['tvl']} locked, " if f.get("tvl") else ""
        return (f"{size}most incidents we see come from upgrade paths, oracle edge cases and admin keys "
                "rather than the core contracts. A short review of those three usually pays for itself.")
    if sig == "launch":
        return ("Right after a launch the gaps tend to show up in three places: load, third-party integrations, "
                "and security reviews that were pushed to later.")
    if sig == "funding":
        return ("After a raise the plan usually moves faster than hiring. Teams that ship on time often add "
                "a small senior team for the first release and hire in parallel.")
    if sig in ("grant", "tender"):
        return ("Winning bids usually show a working prototype or reference build, a clear architecture "
                "and a named delivery team up front.")
    market = f.get("market") or "the first"
    return f"One pattern we keep seeing with teams like {c}: the {market} release slips when security and scale are left to the end."


def _topic(f: dict) -> str:
    sig = f.get("signal")
    if sig == "hiring" and f.get("role"):
        return f"covering the {f['role']} work"
    return {
        "protocol": "an upgrade or audit review",
        "launch": "the post-launch build",
        "funding": "the first release after the raise",
        "grant": "the technical side of the bid",
        "tender": "the technical side of the bid",
    }.get(sig or "", f.get("market") or "this")


def template_email(kind: str, lead: dict, contact: dict, cfg: dict, previous_subject: str | None) -> dict:
    first = _first_name(contact.get("name"))
    hi = f"Hi {first}," if first else "Hi there,"
    f = lead_facts(lead)
    sig = _signature(cfg)
    first_subject, observation, question = _opener(f, lead)
    reply_subject = f"Re: {previous_subject or first_subject}"
    if kind == "opener":
        subject = first_subject
        if lead.get("referred_by"):
            observation = f"{lead['referred_by']} suggested I reach out to you. {observation}"
        body = f"{hi}\n\n{observation}\n\n{question}\n\n{sig}"
    elif kind == "follow_up":
        subject = reply_subject
        body = f"{hi}\n\nJust bringing this back up in case it got buried. {_nudge(f)}\n\n{sig}"
    elif kind == "insight":
        subject = reply_subject
        value = f" {cfg['value_prop'].strip()}" if cfg.get("value_prop") else ""
        body = f"{hi}\n\n{_insight(f)}{value}\n\nHappy to share a short checklist if useful.\n\n{sig}"
    else:
        link = cfg.get("booking_link")
        subject = reply_subject
        ask = f"grab 20 minutes here: {link}" if link else "just reply and we'll find 20 minutes."
        body = (f"{hi}\n\nI'll stop here so I don't crowd your inbox. If {_topic(f)} becomes a priority "
                f"at {f['company'] if len(f['company'].split()) <= 5 else 'your end'}, {ask}\n\n"
                f"If not, no worries at all.\n\n{sig}")
    return {"subject": subject, "body": body, "method": "template"}


def write_email(
    kind: str,
    lead: dict,
    contact: dict,
    cfg: dict,
    *,
    previous_subject: str | None = None,
    thread: list[dict] | None = None,
    learnings: list[str] | None = None,
) -> dict:
    if not llm_available():
        return template_email(kind, lead, contact, cfg, previous_subject)
    payload = {
        "step_goal": STEP_GUIDE.get(kind, STEP_GUIDE["follow_up"]),
        "lead": {
            "company": lead.get("name"),
            "why_now": _public_signal(lead) or _signal_line(lead),
            "internal_note_do_not_quote": lead.get("fit_reason"),
            "signal_type": lead.get("signal_type"),
            "market": (lead.get("domain_context") or {}).get("domain_name"),
            "description": (lead.get("description") or "")[:600],
            "facts": lead_facts(lead),
        },
        "recipient": {"name": _first_name(contact.get("name")) and contact.get("name"), "title": contact.get("title")},
        "referred_by": lead.get("referred_by"),
        "sender": {
            "name": cfg.get("sender_name"),
            "company": cfg.get("company_name"),
            "company_url": cfg.get("company_url"),
            "value_prop": cfg.get("value_prop"),
            "signature": cfg.get("signature"),
            "booking_link": cfg.get("booking_link") if kind in ("soft_close", "answer") else None,
        },
        "previous_subject": previous_subject,
        "thread_so_far": (thread or [])[-4:],
        "what_worked_before": (learnings or [])[:5],
    }
    prompt = (
        "Write the next email. Return JSON {\"subject\": str, \"body\": str}. "
        "For follow-ups in the same thread use 'Re: <previous_subject>' as subject.\n\n"
        + json.dumps(payload, default=str)
    )
    try:
        out = chat_json(prompt, system=SYSTEM)
        if out.get("body"):
            return {"subject": out.get("subject") or f"Re: {previous_subject}", "body": out["body"], "method": "ai"}
    except Exception:  # noqa: BLE001
        pass
    return template_email(kind, lead, contact, cfg, previous_subject)


MEETING = re.compile(r"\b(call|chat|talk|meet|meeting|demo|times?|slots?|schedule|calendar|available|availability)\b", re.I)
WHEN = re.compile(
    r"\b(?:(?:next|this) (?:week|month)|tomorrow|today|(?:next |this |on )?(?:monday|tuesday|wednesday|thursday|friday)"
    r"(?: (?:morning|afternoon|evening))?)\b",
    re.I,
)


def _wants_meeting(text: str) -> bool:
    """True when every question in the reply is about booking a time, so no human answer is needed."""
    if not MEETING.search(text):
        return False
    questions = [q for q in re.split(r"(?<=[.!?])\s+", text) if q.strip().endswith("?")]
    return all(MEETING.search(q) for q in questions)


def meeting_reply(question: str, contact: dict, cfg: dict, subject: str | None) -> dict:
    link = cfg.get("booking_link")
    when = WHEN.search(question)
    day = when.group(0).strip() if when else ""
    timing = f" {day[0].upper()}{day[1:]} works for us." if day else ""
    ask = (f"Here's my calendar, pick any slot that suits you: {link}\n\n"
           "If nothing fits, send two or three times and I'll make one work."
           if link else "Send two or three times that suit you and I'll confirm one.")
    return {
        "subject": f"Re: {subject or ''}".strip(),
        "body": (f"Hi {_first_name(contact.get('name')) or 'there'},\n\nThanks, glad to hear it.{timing} {ask}\n\n"
                 f"{_signature(cfg)}"),
        "method": "template",
    }


def write_answer(question: str, lead: dict, contact: dict, cfg: dict, subject: str | None) -> dict:
    if not llm_available():
        if _wants_meeting(question):
            return meeting_reply(question, contact, cfg, subject)
        sender = _signature(cfg)
        link = cfg.get("booking_link")
        return {
            "subject": f"Re: {subject or ''}".strip(),
            "body": (f"Hi {_first_name(contact.get('name')) or 'there'},\n\nThanks for the question. "
                     f"[Write your answer here.]\n\n"
                     + (f"Happy to go through it on a quick call: {link}\n\n" if link else "")
                     + f"{sender}"),
            "method": "template",
        }
    return write_email(
        "answer", lead, contact, cfg,
        previous_subject=subject,
        thread=[{"from": "lead", "text": question}],
    )
