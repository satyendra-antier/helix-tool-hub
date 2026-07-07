"""Discover concrete video URLs from page HTML and filter non-playable links."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx

YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:embed/|shorts/|live/|watch\?v=)|youtu\.be/)([A-Za-z0-9_-]{6,})",
    re.I,
)
DAILYMOTION_ID_RE = re.compile(
    r"dailymotion\.com/(?:embed/)?video/([a-zA-Z0-9]+)",
    re.I,
)
VIMEO_ID_RE = re.compile(r"vimeo\.com/(?:video/)?(\d+)", re.I)
DATA_VIDEO_URL_RE = re.compile(r"""data-video-url=["']([^"']+)["']""", re.I)
DATA_VIDEO_ID_RE = re.compile(r"""data-video-id=["']([A-Za-z0-9_-]{6,})["']""", re.I)
IFRAME_SRC_RE = re.compile(r"""<iframe[^>]+src=["']([^"']+)["']""", re.I)
OG_VIDEO_RE = re.compile(
    r"""<meta[^>]+property=["']og:video(?::secure_url|:url)?["'][^>]+content=["']([^"']+)["']""",
    re.I,
)
STREAM_IN_HTML_RE = re.compile(
    r"""https?://[^\s"'<>]+\.(?:mp4|webm|m4v|mov|m3u8|mpd)(?:\?[^\s"'<>]*)?""",
    re.I,
)
DIRECT_FILE_RE = re.compile(r"\.(mp4|webm|mov|m4v|mkv|m3u8|mpd)(\?.*)?$", re.I)

CHANNEL_PATH_MARKERS = (
    "youtube.com/@",
    "youtube.com/channel/",
    "youtube.com/user/",
    "youtube.com/c/",
    "youtube.com/playlist",
)

TRACKING_HOST_MARKERS = (
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
    "facebook.com/tr",
    "hotjar.com",
    "clarity.ms",
    "hubspot.com",
    "hs-scripts.com",
    "hsforms.net",
    "hsforms.com",
    "licdn.com",
    "snap.licdn.com",
)

EMPTY_EMBED_RE = re.compile(
    r"(?:youtube(?:-nocookie)?\.com/embed/?(?:\?|$)"
    r"|dailymotion\.com/embed/video/?(?:\?|$)"
    r"|player\.vimeo\.com/video/?(?:\?|$)"
    r"|vimeo\.com/video/?(?:\?|$))",
    re.I,
)

PLATFORM_HOST_MARKERS = (
    "youtube.com", "youtu.be", "youtube-nocookie.com",
    "dailymotion.com", "vimeo.com", "player.vimeo.com",
    "wistia.com", "twitch.tv", "tiktok.com",
)


def is_bad_video_candidate(url: str) -> bool:
    """Channel pages, oEmbed endpoints, blobs, and empty shells."""
    return canonicalize_video_url(url) is None and _is_obviously_junk(url)


def _is_obviously_junk(url: str) -> bool:
    if not url or url.startswith("blob:"):
        return True
    lower = url.lower()
    if any(marker in lower for marker in CHANNEL_PATH_MARKERS):
        return True
    if "wp-json/oembed" in lower:
        return True
    if lower.endswith("/videos") or lower.endswith("/video"):
        return True
    if EMPTY_EMBED_RE.search(lower):
        return True
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if any(marker in host for marker in TRACKING_HOST_MARKERS):
        return True
    if "ns.html" in (parsed.path or "").lower() and "googletagmanager" in host:
        return True
    return False


def is_playable_video_candidate(url: str) -> bool:
    """True only when URL resolves to a concrete media target."""
    return canonicalize_video_url(url) is not None


def youtube_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def normalize_candidate_url(raw: str, base_url: str = "") -> str | None:
    if not raw or raw.startswith(("javascript:", "data:")):
        return None
    raw = raw.strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    elif raw.startswith("/") and base_url:
        from urllib.parse import urljoin
        raw = urljoin(base_url, raw)
    if "${" in raw or "{{" in raw:
        return None
    return raw


def extract_youtube_id(url: str) -> str | None:
    match = YOUTUBE_ID_RE.search(url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    if "youtube.com" in (parsed.netloc or "").lower():
        qs = parse_qs(parsed.query)
        if qs.get("v"):
            vid = qs["v"][0]
            if len(vid) >= 6:
                return vid
    return None


def extract_dailymotion_id(url: str) -> str | None:
    match = DAILYMOTION_ID_RE.search(url)
    return match.group(1) if match else None


def extract_vimeo_id(url: str) -> str | None:
    match = VIMEO_ID_RE.search(url)
    return match.group(1) if match else None


def canonicalize_video_url(url: str) -> str | None:
    """
    Normalize to a concrete playable URL, or None if this is a junk shell /
    tracking iframe / marketing page / empty embed.
    """
    if not url or _is_obviously_junk(url):
        return None

    url = url.strip()
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = parsed.path or ""

    yt_id = extract_youtube_id(url)
    if yt_id:
        return youtube_watch_url(yt_id)

    dm_id = extract_dailymotion_id(url)
    if dm_id:
        return f"https://www.dailymotion.com/video/{dm_id}"

    vim_id = extract_vimeo_id(url)
    if vim_id:
        return f"https://vimeo.com/{vim_id}"

    if DIRECT_FILE_RE.search(path) or ".m3u8" in url.lower() or ".mpd" in url.lower():
        return url

    # Host is a known video platform but no resolvable ID → empty embed shell
    if any(marker in host for marker in PLATFORM_HOST_MARKERS):
        return None

    # Generic website page (live-demo, landing pages, etc.) — not downloadable media
    if parsed.scheme in ("http", "https"):
        return None

    return None


def discover_videos_in_html(html: str, page_url: str = "") -> list[str]:
    """Parse static HTML for embedded video URLs (marketing sites, WordPress)."""
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        url = normalize_candidate_url(raw, page_url)
        if not url:
            return
        canonical = canonicalize_video_url(url)
        if not canonical or canonical in seen:
            return
        seen.add(canonical)
        found.append(canonical)

    for match in DATA_VIDEO_URL_RE.finditer(html):
        add(match.group(1))

    for match in DATA_VIDEO_ID_RE.finditer(html):
        add(youtube_watch_url(match.group(1)))

    for match in IFRAME_SRC_RE.finditer(html):
        add(match.group(1))

    for match in OG_VIDEO_RE.finditer(html):
        add(match.group(1))

    for match in YOUTUBE_ID_RE.finditer(html):
        add(youtube_watch_url(match.group(1)))

    for match in DAILYMOTION_ID_RE.finditer(html):
        add(f"https://www.dailymotion.com/video/{match.group(1)}")

    for match in VIMEO_ID_RE.finditer(html):
        add(f"https://vimeo.com/{match.group(1)}")

    for match in STREAM_IN_HTML_RE.finditer(html):
        add(match.group(0))

    return found


def fetch_page_html(url: str, timeout: float = 45.0) -> tuple[str, str]:
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text, str(resp.url)


def discover_video_urls_from_page(url: str) -> list[str]:
    html, final_url = fetch_page_html(url)
    return discover_videos_in_html(html, final_url)
