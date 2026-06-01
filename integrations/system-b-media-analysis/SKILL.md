---
name: instagram-reel-analyzer
description: Download and prepare online media URLs for System B analysis. Use when a user sends an Instagram/TikTok/YouTube/X/Facebook/Reddit/Vimeo/Loom/direct video URL and wants local media artifacts, audio, sampled frames, metadata, or a merged review.
---

# Instagram Reel Analyzer / System B Media Backend

Run the media preparation pipeline end to end. This repo is no longer only Instagram-specific; it is the first System B backend for source identification, media download, and local artifact extraction.

## Core workflow

1. Identify the URL source with `media_backend.detector.detect()`.
2. Download the media and metadata with `yt-dlp` through `media_backend.downloader.download()`.
3. Extract mono 16 kHz WAV audio with `ffmpeg`.
4. Sample frames with `ffmpeg` for visual review.
5. Write `manifest.json` for Hermes/System B.
6. Hand the local artifacts to the analysis stage for transcript/vision/model synthesis.

## Native Linux/WSL command

```bash
python -m media_backend.cli "https://www.instagram.com/reel/REEL_ID/" /tmp/system-b-job
```

Optional:

```bash
python -m media_backend.cli URL OUT_DIR --frame-interval 5
python -m media_backend.cli URL OUT_DIR --skip-audio
python -m media_backend.cli URL OUT_DIR --skip-frames
```

The command prints the manifest path to stdout. Status and warnings go to stderr. A download failure exits nonzero. Audio/frame failures are recorded in the manifest as nonfatal errors so partial visual/audio analysis can still proceed.

## Supported source labels

- `instagram`
- `tiktok`
- `youtube`
- `twitter`
- `facebook`
- `reddit`
- `vimeo`
- `loom`
- `direct`
- `unknown`

Unknown URLs are still attempted through `yt-dlp`; the label lets System B pick fallback behavior later.

## Output shape

Minimum expected output:

```text
OUT_DIR/
  <downloaded-video-file>
  <downloaded-video-file>.info.json
  manifest.json
  <video-stem>-analysis/
    audio.wav
    frames/
      frame-001.jpg
      frame-002.jpg
```

`manifest.json` is the handoff contract for Hermes/System B. It includes:

- original URL
- source label
- local video path
- audio path if extracted
- sampled frame paths
- selected platform metadata from `yt-dlp`
- extraction errors if any

## Legacy PowerShell commands

These remain as prior art and Windows/OpenClaw compatibility scripts:

```powershell
powershell -ExecutionPolicy Bypass -File {baseDir}\scripts\download_reel.ps1 -Url "https://www.instagram.com/reel/REEL_ID/"
powershell -ExecutionPolicy Bypass -File {baseDir}\scripts\extract_media.ps1 -InputVideo "{baseDir}\output\REEL_ID.mp4"
powershell -ExecutionPolicy Bypass -File {baseDir}\scripts\test_pipeline.ps1 -InputVideo "{baseDir}\output\REEL_ID.mp4"
```

Prefer the Python CLI from Hermes/WSL.

## Rules

- Prefer public URLs.
- If download fails because the platform blocks access or requires auth, ask for the video file directly.
- Do not pretend a transcript exists unless speech-to-text has actually produced one.
- Use frame analysis even when transcript is partial or unavailable.
- Keep the final user-facing summary concise unless asked for a deeper breakdown.
- Do not make raw video-model upload the default first step. Download, extract metadata/audio/frames, then analyze.

## Tests

```bash
python -m pytest tests -q
```
