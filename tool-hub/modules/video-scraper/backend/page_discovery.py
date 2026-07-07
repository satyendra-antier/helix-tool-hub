"""Discover all playable video URLs on a marketing / portfolio page."""

from __future__ import annotations

from urllib.parse import urlparse

from extractor import classify_url, rate_limit_domain
from video_candidates import canonicalize_video_url, discover_videos_in_html, fetch_page_html
from ytdlp_utils import normalize_video_url


def discover_all_page_videos(url: str, max_videos: int = 25) -> list[str]:
    """
    Return deduplicated playable video URLs for a page.
    Single platform URLs return a one-element list.
    """
    source_type = classify_url(url)
    if source_type == "platform":
        canon = canonicalize_video_url(normalize_video_url(url))
        return [canon] if canon else []

    if source_type == "direct-file":
        canon = canonicalize_video_url(url)
        return [canon] if canon else []

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    pages_to_scan = [url.rstrip("/")]
    for suffix in ("/video-testimonials", "/live-demo", "/videos", "/portfolio", "/work"):
        alt = base + suffix
        if alt not in pages_to_scan:
            pages_to_scan.append(alt)

    found: list[str] = []
    seen: set[str] = set()

    for page_url in pages_to_scan:
        try:
            rate_limit_domain(page_url)
            html, final_url = fetch_page_html(page_url)
            for raw in discover_videos_in_html(html, final_url):
                if raw not in seen:
                    seen.add(raw)
                    found.append(raw)
        except Exception:
            continue

    if not found:
        try:
            from browser_discovery import discover_videos_in_browser

            rate_limit_domain(url)
            discovery = discover_videos_in_browser(url)
            for candidate in discovery.candidates:
                canon = canonicalize_video_url(candidate.url)
                if canon and canon not in seen:
                    seen.add(canon)
                    found.append(canon)
        except Exception:
            pass

    return found[:max_videos]
