# Transcript Status

## Current state
The local download and extraction path is proven.
The visual-analysis path is proven.
The speech-to-text path is the remaining unstable piece and may require a different backend than the current ffmpeg whisper attempt.

## Rules
- Do not claim a transcript exists unless a transcript file is actually produced.
- If transcription fails, still return a useful visual summary and note that transcript generation is pending/failed.
- Prefer honest partial success over fake completeness.

## Current fallback posture
1. Download reel
2. Extract audio + frames
3. Analyze frames
4. Report transcript status clearly
