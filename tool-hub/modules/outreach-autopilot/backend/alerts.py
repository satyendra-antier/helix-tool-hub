"""Hot-lead alerts to Slack and/or Telegram. Silently skipped when not configured."""

from __future__ import annotations

import httpx

from config import settings


def channels() -> dict[str, bool]:
    return {
        "slack": bool(settings.slack_webhook_url),
        "telegram": bool(settings.telegram_bot_token and settings.telegram_chat_id),
    }


def send_alert(title: str, lines: list[str], link: str | None = None) -> dict[str, bool]:
    text = f"*{title}*\n" + "\n".join(f"• {l}" for l in lines if l)
    if link:
        text += f"\n{link}"
    sent = {"slack": False, "telegram": False}
    with httpx.Client(timeout=10) as client:
        if settings.slack_webhook_url:
            try:
                sent["slack"] = client.post(settings.slack_webhook_url, json={"text": text}).status_code < 300
            except httpx.HTTPError:
                pass
        if settings.telegram_bot_token and settings.telegram_chat_id:
            try:
                resp = client.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                    json={"chat_id": settings.telegram_chat_id, "text": text.replace("*", "")},
                )
                sent["telegram"] = resp.status_code < 300
            except httpx.HTTPError:
                pass
    return sent
