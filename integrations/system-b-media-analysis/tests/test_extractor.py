from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from media_backend.extractor import (
    ExtractionError,
    extract_audio,
    extract_frames,
    transcribe_audio,
)


def test_extract_audio_success(tmp_path):
    fake_video = tmp_path / "video.mp4"

    with patch("media_backend.extractor.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = extract_audio(fake_video, tmp_path)

    assert result == tmp_path / "audio.wav"
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "1"
    assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == "16000"


def test_extract_audio_failure(tmp_path):
    with patch("media_backend.extractor.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="invalid data")
        with pytest.raises(ExtractionError, match="audio extraction failed"):
            extract_audio(tmp_path / "video.mp4", tmp_path)


def test_extract_frames_success(tmp_path):
    def fake_run(cmd, **kwargs):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        for i in range(1, 4):
            (frames_dir / f"frame-{i:03d}.jpg").write_bytes(b"fake jpg")
        return MagicMock(returncode=0, stderr="")

    with patch("media_backend.extractor.subprocess.run", side_effect=fake_run):
        frames = extract_frames(tmp_path / "video.mp4", tmp_path, interval=8)

    assert len(frames) == 3
    assert all(f.suffix == ".jpg" for f in frames)


def test_extract_frames_failure(tmp_path):
    with patch("media_backend.extractor.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="ffmpeg error")
        with pytest.raises(ExtractionError, match="frame extraction failed"):
            extract_frames(tmp_path / "video.mp4", tmp_path)


def test_extract_frames_custom_interval(tmp_path):
    with patch("media_backend.extractor.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        extract_frames(tmp_path / "video.mp4", tmp_path, interval=4)

    cmd = mock_run.call_args[0][0]
    assert "fps=1/4" in " ".join(cmd)
    assert "format=yuvj420p" in " ".join(cmd)
    assert "-q:v" in cmd


def test_extract_frames_rejects_bad_interval(tmp_path):
    with pytest.raises(ValueError, match="positive"):
        extract_frames(tmp_path / "video.mp4", tmp_path, interval=0)


def test_transcribe_audio_success(tmp_path, monkeypatch):
    class FakeModel:
        def __init__(self, model_name, device, compute_type):
            self.model_name = model_name
            self.device = device
            self.compute_type = compute_type

        def transcribe(self, audio_path, beam_size, vad_filter):
            segments = [
                SimpleNamespace(start=0.0, end=1.25, text=" hello world "),
                SimpleNamespace(start=1.25, end=2.0, text=""),
            ]
            info = SimpleNamespace(language="en", language_probability=0.99)
            return segments, info

    fake_module = SimpleNamespace(WhisperModel=FakeModel)
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", fake_module)

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake wav")
    result = transcribe_audio(audio, tmp_path)

    assert result == tmp_path / "02b-stt-transcript.md"
    text = result.read_text()
    assert "faster-whisper base" in text
    assert "[000.00 --> 001.25] hello world" in text
    assert "language: `en`" in text
