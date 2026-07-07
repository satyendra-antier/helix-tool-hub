"""
Temporary media staging — local disk + MinIO. Always deleted after processing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

from config import settings


def _local_job_dir(job_id: str) -> Path:
    path = Path(settings.media_dir) / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _minio_client():
    if not settings.minio_enabled:
        return None
    from minio import Minio

    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket() -> None:
    client = _minio_client()
    if not client:
        return
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def upload_file(job_id: str, local_path: str, object_name: str | None = None) -> str | None:
    client = _minio_client()
    if not client:
        return None
    ensure_bucket()
    key = object_name or f"{job_id}/{Path(local_path).name}"
    client.fput_object(settings.minio_bucket, key, local_path)
    return key


def download_to_local(job_id: str, object_key: str, dest_name: str) -> str:
    client = _minio_client()
    dest = _local_job_dir(job_id) / dest_name
    if client:
        client.fget_object(settings.minio_bucket, object_key, str(dest))
    return str(dest)


def delete_job_media(job_id: str, minio_keys: list[str] | None = None) -> None:
    """Remove local temp dir and MinIO objects for this job."""
    local_dir = Path(settings.media_dir) / job_id
    if local_dir.exists():
        shutil.rmtree(local_dir, ignore_errors=True)

    client = _minio_client()
    if not client or not minio_keys:
        return
    for key in minio_keys:
        try:
            client.remove_object(settings.minio_bucket, key)
        except Exception:
            pass


def _probe_media(path: str) -> dict:
    import json
    import subprocess

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError(f"Invalid media file: {result.stderr[:200]}")
    data = json.loads(result.stdout)
    duration = float(data.get("format", {}).get("duration") or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    has_video = any(s.get("codec_type") == "video" for s in data.get("streams", []))
    if duration <= 0 and not has_audio:
        raise ValueError("Downloaded file has no audio stream")
    return {"duration": duration, "has_audio": has_audio, "has_video": has_video}


def download_video_to_disk(url: str, job_id: str) -> tuple[str, str | None]:
    """
    Download video/audio to local staging, optionally mirror to MinIO.
    Returns (local_path, minio_object_key).
    """
    from ytdlp_utils import extract_info, normalize_video_url

    url = normalize_video_url(url)
    job_dir = _local_job_dir(job_id)
    output_template = str(job_dir / "media.%(ext)s")

    info = extract_info(url, download=True, outtmpl=output_template)
    if info is None:
        raise ValueError("Download failed — no media returned")

    # Find downloaded file
    files = sorted(job_dir.glob("media.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise ValueError("Download completed but no output file found")

    local_path = str(files[0])
    _probe_media(local_path)

    # HLS/DASH fallback via ffmpeg if yt-dlp left a fragment
    if local_path.endswith((".m3u8", ".mpd")):
        mp4_path = str(job_dir / "media.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", local_path, "-c", "copy", mp4_path],
            capture_output=True,
            timeout=600,
            check=True,
        )
        local_path = mp4_path

    minio_key = upload_file(job_id, local_path)
    return local_path, minio_key


def download_direct_stream(url: str, job_id: str) -> tuple[str, str | None]:
    """ffmpeg download for direct mp4/m3u8 URLs."""
    job_dir = _local_job_dir(job_id)
    ext = "mp4" if ".m3u8" not in url else "mp4"
    dest = str(job_dir / f"stream.{ext}")

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", url,
            "-t", str(settings.max_video_duration_seconds),
            "-c", "copy", dest,
        ],
        capture_output=True,
        timeout=600,
        check=True,
    )
    _probe_media(dest)
    minio_key = upload_file(job_id, dest)
    return dest, minio_key
