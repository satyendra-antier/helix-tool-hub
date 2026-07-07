"""On-device transcription — no OpenAI Audio API (whisper-1) required."""

from __future__ import annotations

import os

from config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            settings.local_whisper_model,
            device=settings.local_whisper_device,
            compute_type=settings.local_whisper_compute_type,
        )
    return _model


def _run_transcribe(audio_path: str, *, vad_filter: bool) -> str:
    model = _get_model()
    segments, _info = model.transcribe(
        audio_path,
        beam_size=5,
        vad_filter=vad_filter,
        language=None,
    )
    parts = [seg.text.strip() for seg in segments if seg.text.strip()]
    return " ".join(parts).strip()


def transcribe_audio_file(audio_path: str) -> str:
    if not os.path.isfile(audio_path):
        raise ValueError(f"Audio file not found: {audio_path}")
    size = os.path.getsize(audio_path)
    if size < 1024:
        raise ValueError(
            f"Extracted audio is too small ({size} bytes) — source likely has no speech track"
        )

    # VAD can drop quiet intros; retry without it before failing.
    for vad_filter in (True, False):
        text = _run_transcribe(audio_path, vad_filter=vad_filter)
        if text:
            return text

    raise ValueError("Local transcription returned empty text")
