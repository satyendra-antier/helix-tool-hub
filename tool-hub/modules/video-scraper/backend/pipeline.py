from datetime import datetime
from sqlalchemy.orm import Session
from database import VideoScraperJob
from extractor import classify_url, extract
from openai_service import summarize_transcript, transcribe_audio


def run_pipeline(job_id: str, db: Session) -> None:
    job = db.query(VideoScraperJob).filter(VideoScraperJob.id == job_id).first()
    if not job:
        return

    try:
        source_type = classify_url(job.source_url)
        job.source_type = source_type
        job.status = "extracting"
        db.commit()

        data = extract(job.source_url, source_type)
        job.title = data.get("title")
        job.channel_or_author = data.get("channel_or_author")
        job.duration_seconds = data.get("duration_seconds")
        job.thumbnail_url = data.get("thumbnail_url")
        job.transcript = data.get("transcript")
        job.transcript_source = data.get("transcript_source")

        if not job.transcript and data.get("audio_url"):
            job.status = "transcribing"
            db.commit()
            job.transcript = transcribe_audio(data["audio_url"], job.source_url)
            job.transcript_source = "transcribed"

        if not job.transcript:
            raise ValueError("No transcript available and transcription failed")

        job.status = "summarizing"
        db.commit()

        summary = summarize_transcript(job.transcript)
        job.summary_json = summary
        job.status = "done"
        job.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
