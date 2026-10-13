"""Sort replies into 7 types (AI when available, keyword rules otherwise)."""

from __future__ import annotations

import json
import re

from llm_client import chat_json, llm_available

CATEGORIES = (
    "interested", "question", "not_now", "not_interested", "unsubscribe", "out_of_office", "referral",
)

LABELS = {
    "interested": "Interested",
    "question": "Has a question",
    "not_now": "Not now",
    "not_interested": "Not interested",
    "unsubscribe": "Unsubscribe",
    "out_of_office": "Out of office",
    "referral": "Wrong person / referral",
}

RULES: list[tuple[str, tuple[str, ...]]] = [
    ("unsubscribe", ("unsubscribe", "remove me", "stop emailing", "stop contacting", "do not contact",
                     "don't contact", "take me off", "opt out", "opt-out")),
    ("out_of_office", ("out of office", "out of the office", "ooo", "on leave", "on vacation", "away until",
                       "automatic reply", "auto-reply", "autoreply", "limited access to email", "back on")),
    ("referral", ("not the right person", "wrong person", "right person is", "reach out to", "contact my colleague",
                  "better person", "i've cc", "i have cc", "looping in", "please contact", "handles this")),
    ("not_interested", ("not interested", "no thanks", "no thank you", "we're good", "we are good", "not a fit",
                        "we'll pass", "we will pass", "already have a vendor", "not looking")),
    ("not_now", ("not right now", "not now", "next quarter", "next year", "maybe later", "circle back",
                 "few months", "not a priority", "reach out later", "check back")),
    ("interested", ("interested", "let's talk", "lets talk", "sounds good", "happy to chat", "book a",
                    "schedule", "set up a call", "jump on a call", "send me", "tell me more", "keen", "love to")),
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def rule_classify(subject: str, body: str) -> dict:
    text = f"{subject}\n{body}".lower()
    words = re.sub(r"[^a-z ]", " ", (body or "").lower()).split()
    if words and words[0] == "stop" and len(words) <= 3:
        return {"category": "unsubscribe", "confidence": 0.95, "reasoning": "Reply says stop."}
    for category, phrases in RULES:
        hit = next((p for p in phrases if p in text), None)
        if hit:
            return {"category": category, "confidence": 0.7, "reasoning": f"Matched phrase: '{hit}'."}
    if "?" in body:
        return {"category": "question", "confidence": 0.6, "reasoning": "Reply asks a question."}
    return {"category": "question", "confidence": 0.3, "reasoning": "Unclear reply, a person should read it."}


PROMPT = """Classify this reply to a B2B cold email into exactly one category:
interested | question | not_now | not_interested | unsubscribe | out_of_office | referral
- referral = they say someone else is the right person (extract that person if given)
- out_of_office = auto-reply; extract the return date if given (YYYY-MM-DD)
Return JSON: {"category": str, "confidence": 0..1, "reasoning": "one sentence",
"referral_name": str|null, "referral_email": str|null, "return_date": str|null}"""


def classify(subject: str, body: str) -> dict:
    result = rule_classify(subject, body)
    if llm_available():
        try:
            out = chat_json(PROMPT + "\n\nReply:\n" + json.dumps({"subject": subject, "body": body[:3000]}))
            if out.get("category") in CATEGORIES:
                result = {
                    "category": out["category"],
                    "confidence": float(out.get("confidence") or 0.8),
                    "reasoning": out.get("reasoning") or "",
                    "referral_name": out.get("referral_name"),
                    "referral_email": out.get("referral_email"),
                    "return_date": out.get("return_date"),
                }
        except Exception:  # noqa: BLE001
            pass
    if result["category"] == "referral" and not result.get("referral_email"):
        emails = EMAIL_RE.findall(body or "")
        result["referral_email"] = emails[0].lower() if emails else None
    return result
