"""Plain-text cleanup for lead descriptions (RSS/HTML sources)."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    if "<" not in text and "&" not in text:
        return re.sub(r"\s+", " ", text).strip()

    soup = BeautifulSoup(text, "html.parser")
    for tag in soup.find_all("a"):
        href = (tag.get("href") or "").strip()
        label = tag.get_text(" ", strip=True)
        if href and label and label != href:
            tag.replace_with(f"{label} ({href})")
        elif href:
            tag.replace_with(href)
        elif label:
            tag.replace_with(label)
        else:
            tag.decompose()

    plain = soup.get_text(" ", strip=True)
    plain = html.unescape(plain)
    return re.sub(r"\s+", " ", plain).strip()


def clean_description(text: str | None, max_len: int = 1000) -> str:
    cleaned = strip_html(text)
    if " | " in cleaned:
        parts: list[str] = []
        for part in cleaned.split(" | "):
            part = part.strip(" |")
            if not part:
                continue
            if part not in parts:
                parts.append(part)
        cleaned = " | ".join(parts)
    if max_len and len(cleaned) > max_len:
        return cleaned[:max_len].rstrip()
    return cleaned
