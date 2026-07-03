import os
import subprocess
import tempfile

from config import settings
from llm_client import chat, parse_json


def transcribe_audio(audio_url: str, source_url: str) -> str:
    provider = settings.transcription_provider.lower()
    if provider != "openai":
        raise ValueError(f"Unsupported transcription provider: {provider}. Use openai (Whisper).")

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY required for transcription")

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", audio_url,
                "-vn", "-acodec", "libmp3lame", "-t", "600",
                audio_path,
            ],
            capture_output=True,
            timeout=300,
            check=True,
        )

        from llm_client import get_client

        with open(audio_path, "rb") as f:
            response = get_client().audio.transcriptions.create(
                model="whisper-1",
                file=f,
            )
        return response.text.strip()


def summarize_transcript(transcript: str) -> dict:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY required for summarization")

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
