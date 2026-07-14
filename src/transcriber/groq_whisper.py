"""Transcribe audio using Groq's free Whisper API."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB free tier limit


async def transcribe_audio(audio_url: str, language: str = "en") -> str | None:
    """Download audio and transcribe via Groq Whisper API.

    Returns formatted transcript with timestamps, or None on failure.
    """
    if not settings.groq_api_key:
        logger.warning("Groq API key not configured, skipping transcription")
        return None

    try:
        audio_path = await _download_audio(audio_url)
        if not audio_path:
            return None

        file_size = audio_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            logger.info(f"Audio file too large ({file_size / 1024 / 1024:.1f}MB), chunking")
            transcript = await _transcribe_chunked(audio_path, language)
        else:
            transcript = await _transcribe_file(audio_path, language)

        if audio_path.exists():
            audio_path.unlink()

        return transcript

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return None


async def _download_audio(url: str) -> Path | None:
    """Download audio file to temp directory."""
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            suffix = ".mp3"
            content_type = resp.headers.get("content-type", "")
            if "ogg" in content_type:
                suffix = ".ogg"
            elif "wav" in content_type:
                suffix = ".wav"
            elif "m4a" in content_type or "mp4" in content_type:
                suffix = ".m4a"

            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(resp.content)
            tmp.close()

            path = Path(tmp.name)
            logger.info(f"Downloaded audio: {path.stat().st_size / 1024 / 1024:.1f}MB")
            return path

    except Exception as e:
        logger.error(f"Failed to download audio from {url}: {e}")
        return None


async def _transcribe_file(audio_path: Path, language: str) -> str | None:
    """Transcribe a single audio file via Groq API."""
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    with open(audio_path, "rb") as f:
        files = {"file": (audio_path.name, f, "audio/mpeg")}
        data = {
            "model": settings.groq_whisper_model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
            "language": language,
        }

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers=headers,
                files=files,
                data=data,
            )

            if resp.status_code != 200:
                logger.error(f"Groq API error {resp.status_code}: {resp.text[:200]}")
                return None

            result = resp.json()

    return _format_segments(result.get("segments", []))


async def _transcribe_chunked(audio_path: Path, language: str) -> str | None:
    """Split large audio files and transcribe each chunk."""
    try:
        import subprocess
        chunk_dir = Path(tempfile.mkdtemp())

        subprocess.run(
            [
                "ffmpeg", "-i", str(audio_path),
                "-f", "segment", "-segment_time", "600",  # 10 min chunks
                "-c:a", "libmp3lame", "-ar", "16000", "-ac", "1",
                "-q:a", "5",
                str(chunk_dir / "chunk_%03d.mp3"),
            ],
            capture_output=True,
            check=True,
        )

        chunks = sorted(chunk_dir.glob("chunk_*.mp3"))
        logger.info(f"Split into {len(chunks)} chunks")

        all_segments = []
        offset = 0.0

        for chunk_path in chunks:
            transcript = await _transcribe_file(chunk_path, language)
            if transcript:
                for line in transcript.split("\n"):
                    if line.startswith("["):
                        ts_end = line.index("]")
                        ts_str = line[1:ts_end]
                        mins, secs = ts_str.split(":")
                        original_secs = int(mins) * 60 + int(secs)
                        adjusted_secs = original_secs + int(offset)
                        adj_mins = adjusted_secs // 60
                        adj_secs = adjusted_secs % 60
                        all_segments.append(f"[{adj_mins:02d}:{adj_secs:02d}]{line[ts_end + 1:]}")
                    else:
                        all_segments.append(line)

            chunk_duration_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(chunk_path)],
                capture_output=True, text=True,
            )
            if chunk_duration_result.returncode == 0:
                offset += float(chunk_duration_result.stdout.strip())

            chunk_path.unlink()

        chunk_dir.rmdir()
        return "\n".join(all_segments) if all_segments else None

    except FileNotFoundError:
        logger.warning("ffmpeg not found, cannot chunk large audio files")
        return None
    except Exception as e:
        logger.error(f"Chunked transcription failed: {e}")
        return None


def _format_segments(segments: list[dict]) -> str:
    """Format Groq API segments into timestamped transcript."""
    lines = []
    for seg in segments:
        start = seg.get("start", 0)
        text = seg.get("text", "").strip()
        if text:
            mins = int(start) // 60
            secs = int(start) % 60
            lines.append(f"[{mins:02d}:{secs:02d}] {text}")
    return "\n".join(lines)
