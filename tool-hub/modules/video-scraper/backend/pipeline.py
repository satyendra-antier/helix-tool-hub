from datetime import datetime

from sqlalchemy.orm import Session

from config import settings
from database import VideoScraperItem, VideoScraperJob
from extractor import classify_url, extract_with_ytdlp, extract_direct_file
from media_store import delete_job_media, download_direct_stream, download_video_to_disk
from openai_service import summarize_transcript, transcribe_local_file
from page_discovery import discover_all_page_videos
from video_candidates import canonicalize_video_url
from ytdlp_utils import normalize_video_url


def _download_and_transcribe(job_id: str, video_url: str) -> str:
    """Download one video URL and return transcript text."""
    playable = canonicalize_video_url(normalize_video_url(video_url)) or canonicalize_video_url(video_url)
    if not playable:
        raise ValueError(f"Not a playable video URL: {video_url[:120]}")

    local_path: str | None = None
    try:
        if classify_url(playable) == "direct-file" or ".m3u8" in playable:
            local_path, _ = download_direct_stream(playable, job_id)
        else:
            local_path, _ = download_video_to_disk(playable, job_id)
        transcript = transcribe_local_file(local_path)
        if not transcript.strip():
            raise ValueError("Local transcription returned empty text")
        return transcript
    finally:
        delete_job_media(job_id, [])


def _extract_video_meta(video_url: str) -> dict:
    playable = canonicalize_video_url(normalize_video_url(video_url)) or canonicalize_video_url(video_url)
    if not playable:
        raise ValueError(f"Invalid video URL: {video_url[:120]}")
    if classify_url(playable) == "direct-file":
        return extract_direct_file(playable)
    return extract_with_ytdlp(playable)


def _resolve_transcript(job_id: str, meta: dict, video_url: str) -> tuple[str, str]:
    transcript = meta.get("transcript")
    source = meta.get("transcript_source")
    if transcript and transcript.strip():
        return transcript, source or "native-captions"
    text = _download_and_transcribe(job_id, video_url)
    return text, "transcribed-staged"


def _update_batch_progress(job: VideoScraperJob, items: list[VideoScraperItem], current: VideoScraperItem | None) -> None:
    total = len(items)
    done = sum(1 for i in items if i.status == "done")
    failed = sum(1 for i in items if i.status == "failed")
    finished = done + failed
    job.progress_json = {
        "videos_total": total,
        "videos_done": done,
        "videos_failed": failed,
        "videos_processing": max(0, total - finished),
        "percent": int(finished / total * 100) if total else 0,
        "current_index": current.sort_order + 1 if current else None,
        "current_video_url": current.video_url if current else None,
        "current_video_title": current.title if current else None,
        "current_status": current.status if current else None,
    }


def _process_item(item: VideoScraperItem, job_id: str, db: Session) -> None:
    item.status = "extracting"
    db.commit()

    meta = _extract_video_meta(item.video_url)
    item.title = meta.get("title")
    item.channel_or_author = meta.get("channel_or_author")
    item.duration_seconds = meta.get("duration_seconds")
    item.thumbnail_url = meta.get("thumbnail_url")

    item.status = "transcribing"
    db.commit()

    transcript, source = _resolve_transcript(job_id, meta, item.video_url)
    item.transcript = transcript
    item.transcript_source = source

    item.status = "summarizing"
    db.commit()

    summary = summarize_transcript(transcript)
    summary["video_url"] = item.video_url
    summary["extraction_method"] = meta.get("extraction_method", "yt-dlp")
    item.summary_json = summary
    item.status = "done"
    item.completed_at = datetime.utcnow()
    db.commit()


def _run_single_video(job: VideoScraperJob, job_id: str, video_url: str, db: Session) -> None:
    job.status = "extracting"
    db.commit()

    meta = _extract_video_meta(video_url)
    job.title = meta.get("title")
    job.channel_or_author = meta.get("channel_or_author")
    job.duration_seconds = meta.get("duration_seconds")
    job.thumbnail_url = meta.get("thumbnail_url")
    job.progress_json = {
        "videos_total": 1,
        "videos_done": 0,
        "videos_failed": 0,
        "videos_processing": 1,
        "percent": 0,
        "current_index": 1,
        "current_video_url": video_url,
        "current_video_title": job.title,
        "current_status": "extracting",
    }
    db.commit()

    job.status = "transcribing"
    job.progress_json["current_status"] = "transcribing"
    db.commit()

    transcript, source = _resolve_transcript(job_id, meta, video_url)
    job.transcript = transcript
    job.transcript_source = source

    job.status = "summarizing"
    job.progress_json["current_status"] = "summarizing"
    db.commit()

    summary = summarize_transcript(transcript)
    summary["extraction"] = {
        "method": meta.get("extraction_method"),
        "candidate_url": video_url,
    }
    job.summary_json = summary
    job.progress_json = {
        "videos_total": 1,
        "videos_done": 1,
        "videos_failed": 0,
        "videos_processing": 0,
        "percent": 100,
        "current_status": "done",
    }
    job.status = "done"
    job.completed_at = datetime.utcnow()
    db.commit()


def _run_batch(job: VideoScraperJob, job_id: str, video_urls: list[str], db: Session) -> None:
    job.is_batch = True
    job.status = "discovering"
    job.title = job.title or f"Batch scrape ({len(video_urls)} videos)"
    job.progress_json = {
        "videos_total": len(video_urls),
        "videos_done": 0,
        "videos_failed": 0,
        "videos_processing": len(video_urls),
        "percent": 0,
    }
    db.commit()

    items: list[VideoScraperItem] = []
    for idx, video_url in enumerate(video_urls):
        item = VideoScraperItem(
            job_id=job.id,
            video_url=video_url,
            sort_order=idx,
            status="queued",
        )
        db.add(item)
        items.append(item)
    db.commit()

    job.status = "processing"
    db.commit()

    for item in items:
        db.refresh(item)
        _update_batch_progress(job, items, item)
        db.commit()
        try:
            _process_item(item, job_id, db)
        except Exception as exc:
            item.status = "failed"
            item.error = str(exc)
            item.completed_at = datetime.utcnow()
            db.commit()

    db.refresh(job)
    for item in items:
        db.refresh(item)

    done = sum(1 for i in items if i.status == "done")
    failed = sum(1 for i in items if i.status == "failed")
    _update_batch_progress(job, items, None)
    job.progress_json["current_status"] = None

    if done == 0:
        job.status = "failed"
        job.error = f"All {failed} video(s) failed to process"
    elif failed > 0:
        job.status = "partial"
        job.error = f"{failed} of {len(items)} video(s) failed"
    else:
        job.status = "done"
        job.error = None

    # Mirror first successful item on job row for backwards compatibility
    first_ok = next((i for i in items if i.status == "done"), None)
    if first_ok:
        job.title = job.title or first_ok.title
        job.thumbnail_url = first_ok.thumbnail_url

    job.completed_at = datetime.utcnow()
    db.commit()


def run_pipeline(job_id: str, db: Session) -> None:
    job = db.query(VideoScraperJob).filter(VideoScraperJob.id == job_id).first()
    if not job:
        return

    try:
        source_type = classify_url(job.source_url)
        job.source_type = source_type
        job.status = "discovering"
        db.commit()

        video_urls = discover_all_page_videos(
            job.source_url,
            max_videos=settings.max_videos_per_page,
        )

        if not video_urls:
            raise ValueError("No playable videos found on this page")

        if len(video_urls) == 1:
            job.is_batch = False
            _run_single_video(job, job_id, video_urls[0], db)
        else:
            _run_batch(job, job_id, video_urls, db)

    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        if job.progress_json is None:
            job.progress_json = {"percent": 0, "videos_total": 0, "videos_done": 0, "videos_failed": 0}
        db.commit()
    finally:
        delete_job_media(job_id, [])
