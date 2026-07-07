"""
Deep browser-based video discovery — main page, iframes, embeds, and network streams.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from video_candidates import (
    canonicalize_video_url,
    discover_videos_in_html,
    is_playable_video_candidate,
    normalize_candidate_url,
)

STREAM_RE = re.compile(r"\.(m3u8|mpd|mp4|webm|mov|m4v|mkv)(\?|$)", re.I)
DIRECT_FILE_RE = re.compile(r"\.(mp4|webm|mov|m4v|mkv|m3u8|mpd)(\?.*)?$", re.I)
PLATFORM_DOMAINS = {
    "youtube.com", "youtu.be", "vimeo.com", "twitter.com", "x.com",
    "tiktok.com", "reddit.com", "facebook.com", "soundcloud.com",
    "instagram.com", "twitch.tv", "dailymotion.com", "wistia.com",
}
EMBED_ATTRS = ("src", "data-src", "data-video", "data-url", "href", "poster")


@dataclass
class VideoCandidate:
    url: str
    source: str
    frame_url: str = ""
    score: int = 0


@dataclass
class DiscoveryResult:
    page_title: str = ""
    candidates: list[VideoCandidate] = field(default_factory=list)
    iframe_count: int = 0
    notes: list[str] = field(default_factory=list)


def _score_candidate(url: str, source: str) -> int:
    score = 10
    lower = url.lower()
    if not is_playable_video_candidate(url):
        score -= 100
    if DIRECT_FILE_RE.search(urlparse(url).path):
        score += 40
    if any(d in lower for d in PLATFORM_DOMAINS):
        score += 35
    if "youtu.be/" in lower or "watch?v=" in lower:
        score += 30
    if "data-video" in source:
        score += 45
    if ".m3u8" in lower:
        score += 25
    if ".mpd" in lower:
        score += 20
    if "video" in source:
        score += 15
    if "iframe" in source:
        score += 10
    if "network" in source:
        score += 12
    if lower.startswith("blob:"):
        score -= 50
    return score


def _normalize_url(base: str, raw: str) -> str | None:
    if not raw or raw.startswith("javascript:") or raw.startswith("data:"):
        return None
    if "+" in raw and ("dailymotion" in raw or "youtube" in raw or "{" in raw):
        return None
    if "${" in raw or "{{" in raw or "[%" in raw:
        return None
    if "google.com/recaptcha" in raw or "gstatic.com" in raw:
        return None
    if "googletagmanager.com" in raw or "google-analytics.com" in raw:
        return None
    if raw.startswith("blob:"):
        return raw
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("http"):
        return raw
    return urljoin(base, raw)


def discover_videos_in_browser(url: str, timeout_ms: int = 90000) -> DiscoveryResult:
    from playwright.sync_api import sync_playwright

    result = DiscoveryResult()
    seen: set[str] = set()

    def add(url_raw: str, source: str, frame_url: str = "") -> None:
        normalized = _normalize_url(url, url_raw)
        if not normalized or normalized in seen:
            return
        canonical = canonicalize_video_url(normalized)
        if not canonical or canonical in seen:
            return
        seen.add(canonical)
        result.candidates.append(VideoCandidate(
            url=canonical,
            source=source,
            frame_url=frame_url or url,
            score=_score_candidate(canonical, source),
        ))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()

        def on_response(response):
            u = response.url
            ct = (response.headers.get("content-type") or "").lower()
            if STREAM_RE.search(u) or "mpegurl" in ct or "dash+xml" in ct or "video/" in ct:
                add(u, "network-response", page.url)

        page.on("response", on_response)

        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(2500)

        # Scroll to trigger lazy-loaded video sections
        for _ in range(6):
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            page.wait_for_timeout(1000)

        # Try clicking common "load more" / video tab triggers
        for selector in [
            'text=Video Testimonials',
            'text=Load More Videos',
            'a[href*="video"]',
            'button:has-text("Video")',
        ]:
            try:
                el = page.query_selector(selector)
                if el:
                    el.click(timeout=3000)
                    page.wait_for_timeout(2000)
            except Exception:
                pass

        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            result.notes.append("networkidle timeout — using partial DOM capture")

        result.page_title = page.title() or ""
        page_html = page.content()

        for video_url in discover_videos_in_html(page_html, page.url):
            add(video_url, "html-data-video", page.url)

        # Meta tags (og:video only — skip oEmbed API links)
        for sel, attr in [
            ('meta[property="og:video"]', "content"),
            ('meta[property="og:video:url"]', "content"),
            ('meta[property="og:video:secure_url"]', "content"),
        ]:
            for el in page.query_selector_all(sel):
                val = el.get_attribute(attr)
                if val:
                    add(val, f"meta:{sel}", page.url)

        frames = page.frames
        result.iframe_count = max(0, len(frames) - 1)

        for frame in frames:
            frame_url = frame.url or url
            try:
                # video / source elements
                for el in frame.query_selector_all("video, video source, audio source"):
                    for attr in ("src", "data-src"):
                        src = el.get_attribute(attr)
                        if src:
                            add(src, "video-element", frame_url)

                # iframes and embeds (nested players)
                for el in frame.query_selector_all("iframe, embed, object"):
                    for attr in EMBED_ATTRS:
                        src = el.get_attribute(attr)
                        if src:
                            add(src, "iframe-embed", frame_url)

                # Common lazy-load data attributes
                for el in frame.query_selector_all("[data-video-src], [data-video-url], [data-video-id], [data-src], [data-href]"):
                    for attr in ("data-video-src", "data-video-url", "data-video-id", "data-src", "data-href"):
                        val = el.get_attribute(attr)
                        if not val:
                            continue
                        if attr == "data-video-id":
                            val = f"https://www.youtube.com/watch?v={val}"
                        if is_playable_video_candidate(val):
                            add(val, "data-attribute", frame_url)

                # anchor links to media files
                for el in frame.query_selector_all("a[href]"):
                    href = el.get_attribute("href") or ""
                    if STREAM_RE.search(href) or any(d in href for d in ("youtube", "vimeo", "youtu.be")):
                        add(href, "anchor-link", frame_url)
            except Exception as exc:
                result.notes.append(f"frame scan skipped ({frame_url[:60]}): {exc}")

        browser.close()

    result.candidates.sort(key=lambda c: c.score, reverse=True)
    return result
