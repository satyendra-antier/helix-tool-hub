import json
import re
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import yt_dlp
from config import settings

PLATFORM_DOMAINS = {
    "youtube.com", "youtu.be", "vimeo.com", "twitter.com", "x.com",
    "tiktok.com", "reddit.com", "facebook.com", "soundcloud.com",
    "instagram.com", "twitch.tv",
}

DIRECT_FILE_RE = re.compile(r"\.(mp4|webm|mov|m4v|mkv)(\?.*)?$", re.I)


def classify_url(url: str) -> str:
    parsed = urlparse(url)
    domain = (parsed.netloc or "").lower().replace("www.", "")
    if DIRECT_FILE_RE.search(parsed.path):
        return "direct-file"
    if any(d in domain for d in PLATFORM_DOMAINS):
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
    if settings.ignore_robots_txt:
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


def extract_with_ytdlp(url: str) -> dict:
    rate_limit_domain(url)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "ignoreerrors": False,
        "format": "bestaudio/best/worst",
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise ValueError("Could not extract video metadata")

    if info.get("drm") or "drm" in str(info.get("formats", [])).lower():
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
                sub_url = subs_dict[lang][0].get("url")
                if sub_url:
                    transcript = _fetch_subtitle_text(sub_url)
                    transcript_source = "native-captions"
                    break
        if transcript:
            break

    return {
        "title": info.get("title"),
        "channel_or_author": info.get("uploader") or info.get("channel"),
        "duration_seconds": int(duration) if duration else None,
        "thumbnail_url": info.get("thumbnail"),
        "transcript": transcript,
        "transcript_source": transcript_source,
        "audio_url": info.get("url"),
        "webpage_url": info.get("webpage_url") or url,
    }


def _fetch_subtitle_text(sub_url: str) -> str:
    with httpx.Client(timeout=30) as client:
        resp = client.get(sub_url)
        resp.raise_for_status()
        text = resp.text
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_generic_page(url: str) -> dict:
    # yt-dlp handles 1800+ sites and does not use our Playwright/robots path
    try:
        return extract_with_ytdlp(url)
    except Exception as ytdlp_err:
        ytdlp_msg = _ytdlp_error_message(ytdlp_err)

    if not check_robots_txt(url):
        raise ValueError(
            "robots.txt disallows scraping this URL. "
            "Use a direct platform link (YouTube, Vimeo, etc.), a direct .mp4 URL, "
            "or set IGNORE_ROBOTS_TXT=true in .env if you have permission to access this page."
        )

    rate_limit_domain(url)
    from playwright.sync_api import sync_playwright

    video_urls: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def handle_response(response):
                u = response.url
                if ".m3u8" in u or ".mpd" in u or DIRECT_FILE_RE.search(u):
                    video_urls.append(u)

            page.on("response", handle_response)
            page.goto(url, wait_until="networkidle", timeout=60000)

            for el in page.query_selector_all("video source, video"):
                src = el.get_attribute("src")
                if src:
                    video_urls.append(src)

            browser.close()
    except Exception as playwright_err:
        raise ValueError(
            f"Could not extract video. yt-dlp: {ytdlp_msg}. Page scrape: {playwright_err}"
        ) from playwright_err

    if not video_urls:
        raise ValueError(
            f"No video stream found on page. yt-dlp also failed: {ytdlp_msg}"
        )

    stream_url = video_urls[0]
    if not stream_url.startswith("http"):
        parsed = urlparse(url)
        stream_url = f"{parsed.scheme}://{parsed.netloc}{stream_url}"

    return extract_with_ytdlp(stream_url)


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
    }


def extract(url: str, source_type: str) -> dict:
    if source_type == "platform":
        return extract_with_ytdlp(url)
    if source_type == "generic-page":
        return extract_generic_page(url)
    if source_type == "direct-file":
        return extract_direct_file(url)
    raise ValueError(f"Unknown source type: {source_type}")
