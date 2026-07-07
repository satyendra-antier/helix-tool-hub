import json
import re
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from config import settings
from video_candidates import (
    discover_videos_in_html,
    fetch_page_html,
    canonicalize_video_url,
    is_playable_video_candidate,
)
from ytdlp_utils import extract_info, normalize_video_url, resolve_playlist_first_video

PLATFORM_DOMAINS = {
    "youtube.com", "youtu.be", "vimeo.com", "twitter.com", "x.com",
    "tiktok.com", "reddit.com", "facebook.com", "soundcloud.com",
    "instagram.com", "twitch.tv", "dailymotion.com", "wistia.com",
    "brightcove.com", "jwplatform.com",
}

DIRECT_FILE_RE = re.compile(r"\.(mp4|webm|mov|m4v|mkv|m3u8|mpd)(\?.*)?$", re.I)


def classify_url(url: str) -> str:
    parsed = urlparse(url)
    domain = (parsed.netloc or "").lower().replace("www.", "")
    lower = url.lower()
    if DIRECT_FILE_RE.search(parsed.path):
        return "direct-file"
    if any(d in domain for d in PLATFORM_DOMAINS):
        return "platform"
    if "youtube.com/@" in lower or "youtube.com/channel/" in lower:
        return "platform"
    return "generic-page"


_domain_last_request: dict[str, float] = {}


def rate_limit_domain(url: str) -> None:
    domain = urlparse(url).netloc
    now = time.time()
    last = _domain_last_request.get(domain, 0)
    wait = settings.rate_limit_per_domain_seconds - (now - last)
    if wait > 0:
        time.sleep(wait)
    _domain_last_request[domain] = time.time()


def check_robots_txt(url: str) -> bool:
    if settings.ignore_robots_txt or settings.video_discovery_ignore_robots:
        return True
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch("*", url)
    except Exception:
        return True


def _ytdlp_error_message(exc: Exception) -> str:
    msg = str(exc)
    if "DRM" in msg.upper():
        return "DRM-protected source, cannot extract"
    return msg


def extract_with_ytdlp(url: str, download: bool = False) -> dict:
    url = normalize_video_url(url)
    rate_limit_domain(url)

    info = extract_info(url, download=download)
    info = resolve_playlist_first_video(info, download=download)

    if info is None:
        raise ValueError("Could not extract video metadata")

    if info.get("drm") is True:
        raise ValueError("DRM-protected source, cannot extract")

    duration = info.get("duration") or 0
    if duration > settings.max_video_duration_seconds:
        raise ValueError(
            f"Video exceeds max duration ({settings.max_video_duration_seconds}s)"
        )

    transcript = None
    transcript_source = None
    subtitles = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}

    for subs_dict in [subtitles, auto_subs]:
        for lang in ["en", "en-US", "en-GB"]:
            if lang in subs_dict:
                transcript = _fetch_best_subtitle_text(subs_dict[lang])
                if transcript:
                    transcript_source = "native-captions"
                    break
        if transcript:
            break
        # Fuzzy match en* subtitle tracks
        if not transcript:
            for lang_key, tracks in subs_dict.items():
                if lang_key.startswith("en") and tracks:
                    transcript = _fetch_best_subtitle_text(tracks)
                    if transcript:
                        transcript_source = "native-captions"
                        break
        if transcript:
            break

    webpage = info.get("webpage_url") or url
    audio_url = info.get("url") or webpage

    return {
        "title": info.get("title"),
        "channel_or_author": info.get("uploader") or info.get("channel"),
        "duration_seconds": int(duration) if duration else None,
        "thumbnail_url": info.get("thumbnail"),
        "transcript": transcript,
        "transcript_source": transcript_source,
        "audio_url": audio_url,
        "webpage_url": webpage,
        "extraction_method": "yt-dlp",
        "candidate_url": url,
    }


def _parse_subtitle_payload(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None

    if text.startswith("{") and "wireMagic" in text:
        try:
            data = json.loads(text)
            parts: list[str] = []
            for event in data.get("events", []):
                for seg in event.get("segs", []) or []:
                    chunk = (seg.get("utf8") or "").strip()
                    if chunk and chunk != "\n":
                        parts.append(chunk)
            joined = re.sub(r"\s+", " ", " ".join(parts)).strip()
            return joined or None
        except json.JSONDecodeError:
            pass

    # WebVTT
    if "WEBVTT" in text or re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->", text):
        cues: list[str] = []
        buffer: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line == "WEBVTT":
                continue
            if "-->" in line:
                if buffer:
                    cues.append(" ".join(buffer))
                    buffer = []
                continue
            if line.isdigit() or line.startswith(("Kind:", "Language:", "NOTE")):
                continue
            line = re.sub(r"align:[^\s]+", "", line).strip()
            line = re.sub(r"<[^>]+>", "", line).strip()
            if line:
                buffer.append(line)
        if buffer:
            cues.append(" ".join(buffer))
        unique: list[str] = []
        for cue in cues:
            if not unique or cue != unique[-1]:
                unique.append(cue)
        cleaned = re.sub(r"\s+", " ", " ".join(unique)).strip()
        return cleaned or None

    cleaned = re.sub(r"WEBVTT|Kind:\s*captions|Language:\s*\w+", " ", text)
    cleaned = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}", " ", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _fetch_best_subtitle_text(tracks: list[dict]) -> str | None:
    """Prefer human-readable VTT/SRT over YouTube json3 caption payloads."""
    preferred_ext = ("json3", "vtt", "srt", "srv3", "ttml")
    ordered = sorted(
        tracks,
        key=lambda t: preferred_ext.index(t.get("ext", "json3"))
        if t.get("ext") in preferred_ext
        else 99,
    )
    for track in ordered:
        sub_url = track.get("url")
        if sub_url:
            text = _fetch_subtitle_text(sub_url)
            if text:
                return text
    return None


def _fetch_subtitle_text(sub_url: str) -> str | None:
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(sub_url)
            resp.raise_for_status()
            text = resp.text
    except Exception:
        return None
    return _parse_subtitle_payload(text)


def _try_candidates_with_ytdlp(
    candidates: list[str],
    extraction_method: str,
    discovery_meta: dict | None = None,
) -> dict:
    errors: list[str] = []
    candidate_urls: list[str] = []
    for raw in candidates:
        if not raw:
            continue
        url = canonicalize_video_url(normalize_video_url(raw)) or canonicalize_video_url(raw)
        if not url or url in candidate_urls:
            continue
        candidate_urls.append(url)
        try:
            if classify_url(url) == "direct-file":
                meta = extract_direct_file(url)
            else:
                meta = extract_with_ytdlp(url)
            if (
                meta.get("title", "").lower() in ("embed", "player", "")
                and not meta.get("transcript")
                and not meta.get("duration_seconds")
            ):
                errors.append(f"{url[:80]}: empty embed shell")
                continue
            meta["extraction_method"] = extraction_method
            meta["all_candidates"] = candidate_urls
            if discovery_meta:
                meta["discovery"] = discovery_meta
            return meta
        except Exception as exc:
            errors.append(f"{url[:80]}: {_ytdlp_error_message(exc)}")
            continue

    raise ValueError(
        f"Found {len(candidate_urls)} video candidate(s) but none could be extracted. "
        + " | ".join(errors[:4])
    )


def discover_from_html_page(url: str) -> dict:
    """Fast path: scrape static HTML for data-video-url / YouTube embeds."""
    rate_limit_domain(url)
    html, final_url = fetch_page_html(url)
    candidates = discover_videos_in_html(html, final_url)
    if not candidates:
        raise ValueError("No embedded video URLs in page HTML")

    return _try_candidates_with_ytdlp(
        candidates,
        extraction_method="html-embed",
        discovery_meta={"page_url": final_url, "candidate_count": len(candidates)},
    )


def discover_with_browser(url: str) -> dict:
    """Playwright: inspect page + iframes + network for video candidates."""
    from browser_discovery import discover_videos_in_browser

    if not check_robots_txt(url) and not settings.video_discovery_ignore_robots:
        raise ValueError(
            "robots.txt disallows this URL. Set VIDEO_DISCOVERY_IGNORE_ROBOTS=true "
            "or IGNORE_ROBOTS_TXT=true if you have permission."
        )

    rate_limit_domain(url)
    discovery = discover_videos_in_browser(url)

    usable = [c for c in discovery.candidates if not c.url.startswith("blob:")]
    if not usable:
        raise ValueError(
            f"No video found in page or iframes ({discovery.iframe_count} iframes scanned). "
            f"Notes: {'; '.join(discovery.notes) or 'none'}"
        )

    candidate_urls = [c.url for c in usable[:12]]
    meta = _try_candidates_with_ytdlp(
        candidate_urls,
        extraction_method=f"browser-{usable[0].source}",
        discovery_meta={
            "iframe_count": discovery.iframe_count,
            "candidate_url": usable[0].url,
            "frame_url": usable[0].frame_url,
            "score": usable[0].score,
            "notes": discovery.notes,
        },
    )
    if discovery.page_title and not meta.get("title"):
        meta["title"] = discovery.page_title
    return meta


def extract_generic_page(url: str) -> dict:
    errors: list[str] = []
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # 1) Static HTML — data-video-url / YouTube IDs (fast, works for WordPress marketing sites)
    pages_to_scan = [url.rstrip("/")]
    for suffix in ("/video-testimonials", "/live-demo", "/videos", "/portfolio", "/work"):
        alt = base + suffix
        if alt not in pages_to_scan:
            pages_to_scan.append(alt)

    for page_url in pages_to_scan:
        try:
            meta = discover_from_html_page(page_url)
            if page_url != url.rstrip("/"):
                meta["extraction_method"] = f"html-embed-subpath"
            return meta
        except Exception as html_err:
            errors.append(f"html@{page_url}: {html_err}")

    # 2) yt-dlp on submitted URL (direct platform links)
    try:
        return extract_with_ytdlp(url)
    except Exception as ytdlp_err:
        errors.append(f"yt-dlp@{url}: {_ytdlp_error_message(ytdlp_err)}")

    # 3) Browser: page + iframes + network (lazy-loaded players)
    for page_url in pages_to_scan:
        try:
            meta = discover_with_browser(page_url)
            if page_url != url.rstrip("/"):
                meta["extraction_method"] = f"browser-subpath"
            return meta
        except Exception as browser_err:
            errors.append(f"browser@{page_url}: {browser_err}")

    raise ValueError("Could not extract video. " + " | ".join(errors[:5]))


def extract_direct_file(url: str) -> dict:
    import subprocess

    rate_limit_domain(url)
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise ValueError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0))

    if duration > settings.max_video_duration_seconds:
        raise ValueError(
            f"Video exceeds max duration ({settings.max_video_duration_seconds}s)"
        )

    return {
        "title": url.split("/")[-1].split("?")[0],
        "channel_or_author": None,
        "duration_seconds": int(duration) if duration else None,
        "thumbnail_url": None,
        "transcript": None,
        "transcript_source": None,
        "audio_url": url,
        "webpage_url": url,
        "extraction_method": "direct-file",
        "candidate_url": url,
    }


def extract(url: str, source_type: str) -> dict:
    if source_type == "platform":
        return extract_with_ytdlp(url)
    if source_type == "generic-page":
        return extract_generic_page(url)
    if source_type == "direct-file":
        return extract_direct_file(url)
    raise ValueError(f"Unknown source type: {source_type}")
