# Hermes media-analysis hook backup

This directory mirrors the live Hermes media-analysis hooks and helper libs from:

- `/home/imagi/.hermes/hooks/media-analysis-intake/`
- `/home/imagi/.hermes/hooks/media-analysis-z-backend/`
- `/home/imagi/media-analysis/lib/`

## Current source database behavior

The durable source index is JSONL for now, not SQLite:

- live path: `/home/imagi/media-analysis/index/sources.jsonl`
- one JSON object per normalized source URL
- records include URL, thread ID, workspace path, source type, platform, creator, title, confidence, canonical source/database name, Discord thread title, timestamps, and compact metadata

The backend hook calls `upsert_source_record()` after a successful extraction, so future completed runs update this index automatically.

## Current thread-title behavior

The hook flow now stores canonical naming fields in `state.json` and attempts a Discord thread rename after backend metadata extraction:

- `canonical_source_name`: durable source/database name, usually `<platform>: <title> — <creator>`
- `thread_title_base`: Discord-safe base title derived from the canonical name
- `thread_title_suggestion`: final title, with numeric suffix if duplicate/similar context requires one
- `thread_title_source`: currently `backend_metadata` for automatic hook output
- `thread_rename`: result of the Discord API rename attempt

Examples:

- `youtube: Responding To Your Mad Men Hot Takes 🔥 — Pure Kino`
- `instagram: Post by bestapps.ai — bestapps.ai`

Set `SYSTEM_B_RENAME_THREADS=0` to disable automatic Discord renames without disabling indexing.

No gateway restart is performed by this backup step. Live hook changes require an approved Hermes gateway restart before future runs use the new automatic behavior.
