# Pipeline

## Goal

Turn a supported online media URL into a locally analyzable artifact set for System B.

## Stages

1. Detect URL source.
2. Download media with `yt-dlp`.
3. Capture platform metadata with `yt-dlp --write-info-json`.
4. Extract mono 16k WAV audio with `ffmpeg`.
5. Sample frames every N seconds with `ffmpeg`.
6. Write `manifest.json` with artifact paths, source label, metadata, and nonfatal errors.
7. Hand local artifacts to transcript, OCR, vision, and final-analysis stages.

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

## Minimum success bar

- source detected
- MP4 or other media file downloaded
- metadata JSON captured when the platform exposes it
- manifest written

## Full preparation success bar

- media file downloaded
- `audio.wav` created
- frame samples created
- manifest contains video, audio, frames, metadata, and no extraction errors

## Analysis success bar

- transcript generated when possible
- frame/OCR/visual findings produced
- transcript and visual findings merged into a reliable review
- confidence and extraction caveats are explicit

## System B boundary

This repo owns download and artifact preparation. Hermes media-analysis owns Discord intake/dedup/thread workflow and final user-facing analysis.
