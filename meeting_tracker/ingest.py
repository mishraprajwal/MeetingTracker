"""Transcript ingestion: text/VTT/SRT directly, audio/video via Whisper transcription."""
from __future__ import annotations

import re
from pathlib import Path

AUDIO_EXT = {".mp3", ".mp4", ".m4a", ".wav", ".webm", ".mpeg", ".mpga", ".ogg", ".flac"}


def clean_caption_text(raw: str) -> str:
    """Strip WebVTT/SRT headers, cue numbers and timestamps, keeping speaker lines."""
    out = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s == "WEBVTT" or s.isdigit() or "-->" in s or s.startswith(("NOTE", "Kind:", "Language:")):
            continue
        s = re.sub(r"</?v[^>]*>|</?c[^>]*>", "", s)  # VTT voice/class tags
        out.append(s)
    return "\n".join(out)


def transcribe_audio(path: Path) -> str:
    from openai import OpenAI

    client = OpenAI()
    with path.open("rb") as f:
        return client.audio.transcriptions.create(model="whisper-1", file=f).text


def load_transcript(source: str) -> str:
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Transcript/recording not found: {source}")
    ext = path.suffix.lower()
    if ext in AUDIO_EXT:
        return transcribe_audio(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    return clean_caption_text(raw) if ext in {".vtt", ".srt"} else raw
