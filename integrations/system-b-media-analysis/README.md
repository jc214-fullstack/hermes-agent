# System B Media Analysis Pipeline

This is the Hermes-owned media analysis pipeline for Discord source intake, extraction, durable source indexing, and thread naming.

It is not an Instagram-only project. The old `instagram-reel-analyzer` repository name came from the original prototype and is now treated as a legacy staging name, not the canonical system identity.

Canonical identity: **System B Media Analysis Pipeline** / **Hermes Media Analysis Pipeline**.

Runtime surfaces:
- Live hooks: `/home/imagi/.hermes/hooks/media-analysis-intake` and `/home/imagi/.hermes/hooks/media-analysis-z-backend`
- Live helper library: `/home/imagi/media-analysis/lib`
- Durable source index: `/home/imagi/media-analysis/index/sources.jsonl`
- Per-thread workspaces: `/home/imagi/media-analysis/threads/<thread_id>/`

This repo package preserves the Hermes-specific hook bundle and reapply surface so the system can survive Hermes upgrades and repo cleanup without depending on the old Instagram-named project.
