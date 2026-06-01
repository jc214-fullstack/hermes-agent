"""Media artifact extraction for System B."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class ExtractionError(Exception):
    """Raised when ffmpeg extraction fails."""


class TranscriptionError(Exception):
    """Raised when local speech-to-text transcription fails."""


def extract_audio(video_path: str | Path, out_dir: str | Path) -> Path:
    """Extract mono 16 kHz WAV from ``video_path`` into ``out_dir/audio.wav``."""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / "audio.wav"

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise ExtractionError(
            f"ffmpeg audio extraction failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    return audio_path


def extract_frames(video_path: str | Path, out_dir: str | Path, interval: int = 8) -> list[Path]:
    """Sample one frame every ``interval`` seconds at 960 px wide."""

    if interval <= 0:
        raise ValueError("interval must be a positive integer")

    out_dir = Path(out_dir)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_pattern = str(frames_dir / "frame-%03d.jpg")

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps=1/{interval},scale=960:-2,format=yuvj420p",
            "-q:v",
            "2",
            frame_pattern,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise ExtractionError(
            f"ffmpeg frame extraction failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    return sorted(frames_dir.glob("frame-*.jpg"))


def transcribe_audio(audio_path: str | Path, out_dir: str | Path) -> Path:
    """Transcribe ``audio_path`` with local faster-whisper into markdown.

    The model defaults to ``base`` because this hook runs inline during gateway
    intake. Override with ``SYSTEM_B_WHISPER_MODEL`` when a larger local model is
    acceptable.
    """

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - depends on optional install
        raise TranscriptionError(f"faster-whisper unavailable: {exc}") from exc

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = out_dir / "02b-stt-transcript.md"
    model_name = os.environ.get("SYSTEM_B_WHISPER_MODEL", "base")

    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), beam_size=5, vad_filter=True)
        lines = [
            f"# STT transcript via faster-whisper {model_name}",
            "",
            f"- language: `{getattr(info, 'language', 'unknown')}`",
            f"- language_probability: `{getattr(info, 'language_probability', 'unknown')}`",
            f"- source_audio: `{audio_path}`",
            "",
        ]
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            lines.append(f"[{segment.start:06.2f} --> {segment.end:06.2f}] {text}")
        transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return transcript_path
    except Exception as exc:
        raise TranscriptionError(f"faster-whisper transcription failed: {exc}") from exc
