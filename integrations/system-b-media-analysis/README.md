# instagram-reel-analyzer

System B media backend for turning supported online media URLs into local files and analysis-ready artifacts.

The original PowerShell scripts are still kept as prior art for Instagram reels. The default runtime path is now native Linux/WSL Python so Hermes can call it directly.

## What this does

`media-dl` performs the pre-analysis media preparation stage:

1. identifies the URL source
2. downloads the media with `yt-dlp`
3. saves `yt-dlp` metadata via `*.info.json`
4. extracts mono 16 kHz `audio.wav` with `ffmpeg`
5. samples visual frames with `ffmpeg`
6. writes `manifest.json` for Hermes/System B to consume

Supported source labels:

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

Unknown sources are still attempted through `yt-dlp`; the label is for routing, metrics, and later fallbacks.

## Usage

```bash
python -m media_backend.cli "https://www.instagram.com/reel/REEL_ID/" /tmp/system-b-job
```

Optional flags:

```bash
python -m media_backend.cli URL OUT_DIR --frame-interval 5
python -m media_backend.cli URL OUT_DIR --skip-audio
python -m media_backend.cli URL OUT_DIR --skip-frames
```

On success, stdout is the path to `manifest.json`. Operational status goes to stderr.

## Output shape

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

`manifest.json` includes source label, local artifact paths, frame count, selected platform metadata, and nonfatal extraction errors.

## System B architecture role

Hermes media-analysis intake should create/dedup the Discord workspace first, then call this backend for each URL. This repo should own URL-source download and local artifact preparation. Hermes/System B should own summarization, transcript/vision model calls, thread replies, and Kanban escalation.

The intended flow is:

Discord URL → Hermes intake/dedup → this backend downloads/extracts → System B analyzes local artifacts.

## Current status

Working:

- source detection
- `yt-dlp` download wrapper
- metadata JSON capture
- `ffmpeg` audio extraction
- `ffmpeg` frame sampling
- manifest writer
- mocked unit tests

Still intentionally separate / future work:

- durable transcript backend selection
- VLM/video-model analysis backend selection
- auth-gated/private source handling
- direct integration from Hermes hook into this CLI

## Main files

- `media_backend/` — native Python System B backend
- `tests/` — mocked tests for detector/downloader/extractor/manifest/CLI
- `SKILL.md` — OpenClaw/Hermes operating guide
- `scripts/download_reel.ps1` — legacy PowerShell Instagram download script
- `scripts/extract_media.ps1` — legacy PowerShell extraction script
- `scripts/test_pipeline.ps1` — legacy PowerShell test wrapper
- `references/pipeline.md`
- `references/transcript-status.md`

## Repository role

This repository remains the dedicated project workspace for **System B Media Analysis Pipeline** development and tests. The historical repository name, `instagram-reel-analyzer`, is legacy from the first prototype; the project now covers mixed media source intake and analysis, not Instagram only.

Hermes integration snapshots are also mirrored into the Hermes GitHub fork under `integrations/system-b-media-analysis/` so the pipeline stays attached to the Hermes system while this repo remains the focused project workspace.

