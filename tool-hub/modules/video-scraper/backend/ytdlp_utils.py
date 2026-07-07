"""Robust yt-dlp wrappers — format fallbacks and YouTube player client rotation."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import yt_dlp

YOUTUBE_PLAYER_CLIENTS = ["android", "ios", "web", "mweb", "tv_embedded"]

# Most permissive first; strict preferences tried before last-resort worst
DOWNLOAD_FORMAT_CHAIN = [
    "ba/b",
    "bestaudio/best",
    "bestaudio[ext=m4a]/bestaudio",
    "best[height<=720]/best",
    "bv*+ba/b",
    "worst",
]


def normalize_video_url(url: str) -> str:
    """Canonicalize youtu.be and shorts URLs."""
    lower = url.lower()
    if "youtu.be/" in lower:
        vid = urlparse(url).path.lstrip("/").split("/")[0]
        return f"https://www.youtube.com/watch?v={vid}"
    if "youtube.com/shorts/" in lower:
        vid = urlparse(url).path.split("/shorts/")[-1].split("/")[0].split("?")[0]
        return f"https://www.youtube.com/watch?v={vid}"
    return url


def _base_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 60,
        "retries": 3,
        "noprogress": True,
    }


def metadata_opts() -> dict:
    return {
        **_base_opts(),
        "skip_download": True,
        "ignore_no_formats_error": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB", "en.*"],
        "extractor_args": {"youtube": {"player_client": YOUTUBE_PLAYER_CLIENTS}},
    }


def download_opts(outtmpl: str, fmt: str) -> dict:
    return {
        **_base_opts(),
        "outtmpl": outtmpl,
        "format": fmt,
        "ignore_no_formats_error": True,
        "merge_output_format": "mp4",
        "extractor_args": {"youtube": {"player_client": YOUTUBE_PLAYER_CLIENTS}},
    }


def extract_info(url: str, download: bool = False, outtmpl: str | None = None) -> dict:
    """Extract with player-client and format fallbacks."""
    url = normalize_video_url(url)
    last_error: Exception | None = None

    if not download:
        attempts = [metadata_opts()]
    else:
        attempts = [download_opts(outtmpl or "media.%(ext)s", fmt) for fmt in DOWNLOAD_FORMAT_CHAIN]

    for opts in attempts:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=download)
            if info is not None:
                return info
        except Exception as exc:
            last_error = exc
            msg = str(exc).lower()
            if "format" not in msg and "no formats" not in msg:
                raise
            continue

    if last_error:
        raise last_error
    raise ValueError("Could not extract video metadata")


def resolve_playlist_first_video(info: dict, download: bool, outtmpl: str | None = None) -> dict:
    """If URL is a playlist/channel, drill into first entry."""
    if not (info.get("_type") in ("playlist", "multi_video") or info.get("entries")):
        return info

    entries = [e for e in (info.get("entries") or []) if e]
    if not entries:
        raise ValueError("Playlist/channel has no videos")

    entry = entries[0]
    entry_url = entry.get("webpage_url") or entry.get("url")
    if not entry_url or not str(entry_url).startswith("http"):
        vid = entry.get("id")
        if not vid:
            raise ValueError("Could not resolve playlist entry URL")
        entry_url = f"https://www.youtube.com/watch?v={vid}"

    return extract_info(entry_url, download=download, outtmpl=outtmpl)
