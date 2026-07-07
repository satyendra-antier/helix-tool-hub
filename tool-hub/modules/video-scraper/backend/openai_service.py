import os
import subprocess
import tempfile

from config import settings
from llm_client import chat, parse_json


def _extract_audio_to_mp3(source: str, output_path: str, max_seconds: int = 600) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", source,
            "-vn", "-acodec", "libmp3lame",
            "-ar", "16000", "-ac", "1",
            "-t", str(max_seconds),
            output_path,
        ],
        capture_output=True,
        timeout=300,
        text=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "")[-500:]
        raise ValueError(f"ffmpeg audio extraction failed: {stderr}")
    if not os.path.isfile(output_path) or os.path.getsize(output_path) < 1024:
        raise ValueError("ffmpeg produced no usable audio — video may be silent or music-only")


def _transcription_error_hint(exc: Exception) -> str:
    msg = str(exc)
    if "model_not_found" in msg or "does not have access to model" in msg:
        return (
            f"{msg} — gpt-5-mini cannot transcribe audio. "
            "Set TRANSCRIPTION_PROVIDER=local (default) to transcribe on-device, "
            "or use TRANSCRIPTION_PROVIDER=openai with an Audio API-enabled key."
        )
    return msg


def _transcribe_openai_audio(audio_path: str) -> str:
    from llm_client import get_client

    with open(audio_path, "rb") as f:
        response = get_client().audio.transcriptions.create(
            model=settings.transcription_model,
            file=f,
        )
    return response.text.strip()


def _transcribe_audio_file(audio_path: str) -> str:
    provider = settings.transcription_provider.lower()

    if provider == "local":
        from local_transcription import transcribe_audio_file
        return transcribe_audio_file(audio_path)

    if provider == "openai":
        if not settings.resolve_api_key():
            raise ValueError(
                "VIDEO_SCRAPER_OPENAI_API_KEY or OPENAI_API_KEY required for openai transcription"
            )
        return _transcribe_openai_audio(audio_path)

    raise ValueError(
        f"Unsupported TRANSCRIPTION_PROVIDER={provider!r}. Use 'local' or 'openai'."
    )


def transcribe_local_file(local_path: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        _extract_audio_to_mp3(local_path, audio_path)
        try:
            return _transcribe_audio_file(audio_path)
        except Exception as exc:
            raise ValueError(_transcription_error_hint(exc)) from exc


def transcribe_audio(audio_url: str, source_url: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        _extract_audio_to_mp3(audio_url, audio_path)
        return _transcribe_audio_file(audio_path)


def summarize_transcript(transcript: str) -> dict:
    if not settings.resolve_api_key():
        raise ValueError(
            "VIDEO_SCRAPER_OPENAI_API_KEY or OPENAI_API_KEY required for summarization (gpt-5-mini)"
        )

    prompt = f"""You are summarizing a video transcript. Return ONLY valid JSON, no markdown fences, no preamble.

Schema:
{{
  "one_line_summary": string,
  "key_points": string[],
  "chapters": [{{ "timestamp_hint": string, "title": string }}],
  "notable_quotes": string[],
  "topics": string[]
}}

Transcript:
{transcript[:50000]}"""

    return parse_json(chat(prompt, json_mode=True))
