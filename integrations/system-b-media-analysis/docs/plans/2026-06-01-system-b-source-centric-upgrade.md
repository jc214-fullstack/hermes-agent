# System B Source-Centric Upgrade Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Upgrade System B from a thread-first media extractor into a source-centric Hermes media-analysis pipeline with deterministic adapter routing, a usable index browser, and passive Discord diagnostics for real-link testing.

**Architecture:** Keep `jc214-fullstack/instagram-reel-analyzer` as the focused project repo and mirror the integration bundle into Hermes under `integrations/system-b-media-analysis/`. The runtime stays Hermes-owned: live hooks under `/home/imagi/.hermes/hooks`, live helper library under `/home/imagi/media-analysis/lib`, workspaces under `/home/imagi/media-analysis/threads`, and durable source data under `/home/imagi/media-analysis/index` plus new source-centric storage under `/home/imagi/media-analysis/sources`.

**Tech Stack:** Python 3.11, Hermes gateway hooks, Discord threads, JSON/JSONL now with SQLite-ready boundaries later, `yt-dlp`, `gallery-dl`, direct HTTP/file acquisition, `ffmpeg`, faster-whisper/local STT when available, pytest.

---

## Product decision

Mike wants this project to remain the dedicated System B project repo even though the repository name is historically `instagram-reel-analyzer`. The Hermes repo should keep System B as a subfolder/mirror, not replace the project repo.

Canonical project identity: **System B Media Analysis Pipeline** / **Hermes Media Analysis Pipeline**.

Dedicated project repo: `jc214-fullstack/instagram-reel-analyzer`.

Hermes mirror path: `jc214-fullstack/hermes-agent:integrations/system-b-media-analysis/`.

## Upgrade scope selected by Mike

This plan covers the selected functional upgrades:

1. **Source-centric storage** — sources become durable first-class objects; Discord threads become views/runs over sources.
2. **Adapter router** — deterministic acquisition and extraction routing by source kind/platform/file type.
3. **Index browser / diagnostics surface** — a simple way to inspect processed sources, failures, retries, and related threads.
4. **Passive real-link Discord test pipeline** — Mike can drop a real test link in Discord and receive diagnostics plus the normal summary without needing a separate manual test harness.

This plan does **not** restart the Hermes gateway. Any live-hook behavior changes require Mike approval before restart.

---

## Current design baseline

The current pipeline is:

1. Discord message arrives in the media-analysis channel/thread.
2. Hermes intake hook creates or finds `/home/imagi/media-analysis/threads/<thread_id>/`.
3. Intake writes `00-request.md` and `state.json`.
4. Backend hook calls `media_backend.cli` from the project repo.
5. Backend downloads/extracts local artifacts into the thread workspace under `assets/source-N/`.
6. Backend writes `manifest.json` with media paths, metadata, transcript status, frames, and errors.
7. Backend enriches `01-source.md`, updates `/home/imagi/media-analysis/index/sources.jsonl`, and optionally renames the Discord thread.
8. Hermes analysis produces human-facing thread summaries and markdown artifacts.

Known weakness: the thread folder still acts like the main durable identity. The upgrade should make the source itself durable and let threads point to sources.

---

# Phase 1 — Source-centric storage

## Target behavior

Every acquired source gets a stable source directory under:

`/home/imagi/media-analysis/sources/`

Suggested layout:

```text
/home/imagi/media-analysis/sources/
  platform/
    youtube/<source_key>/
    meta/instagram/<source_key>/
    meta/facebook/<source_key>/
    meta/threads/<source_key>/
    x/<source_key>/
    tiktok/<source_key>/
    reddit/<source_key>/
  raw-files/
    video/<source_key>/
    audio/<source_key>/
    image/<source_key>/
    document/<source_key>/
  web/
    article/<source_key>/
    generic/<source_key>/
```

The thread workspace should keep run-specific state and lightweight pointers, while source assets and source manifests live in source storage.

## Data contract

Add these fields to backend `manifest.json` and thread `state.json` job records:

```json
{
  "source_storage": {
    "source_key": "stable-slug-or-hash",
    "source_dir": "/home/imagi/media-analysis/sources/platform/youtube/...",
    "storage_class": "platform|raw-file|web",
    "platform": "youtube|instagram|...",
    "company": "meta|null",
    "raw_kind": "video|audio|image|document|null"
  },
  "thread_run": {
    "thread_id": "discord-thread-id",
    "workspace_path": "/home/imagi/media-analysis/threads/<thread_id>",
    "job_index": 0
  }
}
```

Also extend `sources.jsonl` with:

```json
{
  "source_key": "...",
  "source_dir": "...",
  "run_count": 1,
  "thread_ids": ["..."],
  "latest_thread_id": "...",
  "latest_workspace_path": "..."
}
```

## Task 1: Add source key and source directory planner tests

**Objective:** Define deterministic source storage paths before changing downloader behavior.

**Files:**
- Modify: `media_backend/storage.py`
- Test: `tests/test_storage.py`

**Test cases to add:**

- YouTube URL routes to `platform/youtube/<key>`.
- Instagram `/reel/` and `/p/` route to `platform/meta/instagram/<key>`.
- Facebook routes to `platform/meta/facebook/<key>`.
- Threads routes to `platform/meta/threads/<key>` after detector support is added.
- Direct `.mp4` routes to `raw-files/video/<key>`.
- Direct `.pdf` routes to `raw-files/document/<key>`.
- Generic article URL routes to `web/generic/<key>` initially.

**Run:**

```bash
cd /home/imagi/projects/instagram-reel-analyzer
pytest tests/test_storage.py -q
```

**Expected:** New tests fail until storage planner is implemented.

## Task 2: Implement source storage planner

**Objective:** Return source-centric storage metadata without moving files yet.

**Files:**
- Modify: `media_backend/storage.py`

**Implementation notes:**

- Use normalized URL or URL path ID when available.
- Fall back to a short SHA256 hash for stable uniqueness.
- Do not dedupe-block reprocessing; source keys identify storage, not whether a run is allowed.
- Preserve current `storage_plan.relative_dir` for backward compatibility, but point it at source-centric layout.

**Run:**

```bash
pytest tests/test_storage.py -q
```

**Expected:** Storage planner tests pass.

## Task 3: Write acquired files into source storage and link from thread workspace

**Objective:** Make source storage the primary artifact location while keeping thread workspace compatibility.

**Files:**
- Modify: `media_backend/cli.py`
- Modify: `media_backend/downloader.py` if output directory handling needs adjustment
- Test: `tests/test_cli.py`
- Test: `tests/test_manifest.py`

**Implementation notes:**

- Add optional CLI flag: `--source-root /home/imagi/media-analysis/sources`.
- Default source root to `/home/imagi/media-analysis/sources` unless overridden.
- Download into `source_dir/raw/` or `source_dir/assets/`.
- Keep thread output `manifest.json` in the thread job output directory.
- Thread manifest points to source asset paths.
- Avoid symlinks unless tests prove WSL/Discord tooling handles them reliably. Prefer plain JSON pointers first.

**Run:**

```bash
pytest tests/test_cli.py tests/test_manifest.py -q
```

**Expected:** CLI writes a manifest containing `source_storage.source_dir`, and existing manifest consumers still pass.

## Task 4: Update hook state and durable index for source-centric fields

**Objective:** Persist source identity across thread runs.

**Files:**
- Modify: `integrations/hermes-hooks/media-analysis-z-backend/handler.py`
- Modify: `integrations/hermes-hooks/lib/state.py`
- Test: `tests/test_backend_hook.py`

**Implementation notes:**

- Copy `manifest["source_storage"]` into job state.
- Extend `upsert_source_record()` to preserve `source_key`, `source_dir`, `thread_ids`, `run_count`, and latest run fields.
- Existing thread title rename behavior remains unchanged.

**Run:**

```bash
pytest tests/test_backend_hook.py -q
```

**Expected:** Backend hook tests verify source-centric fields in state and `sources.jsonl`.

---

# Phase 2 — Adapter router

## Target behavior

System B should route acquisition based on source shape, not just try one downloader and hope:

```text
raw/local/direct file      -> direct adapter
YouTube/Vimeo/Loom         -> yt-dlp adapter, transcript metadata first where possible
Instagram carousel/post    -> gallery-dl first, preserve all images/video assets
Instagram reel/video       -> gallery-dl or yt-dlp based on observed reliability, fallback to the other
X/Twitter/Reddit/Facebook  -> gallery-dl first, fallback yt-dlp
TikTok                     -> yt-dlp first or gallery-dl based on test evidence, fallback other
PDF/document URL           -> document adapter, not video downloader path
generic article/web URL    -> web/document extraction adapter later; for now diagnostics mark unsupported if no media
```

## Task 5: Introduce adapter decision object

**Objective:** Make routing explicit and testable.

**Files:**
- Create: `media_backend/adapters.py`
- Test: `tests/test_adapters.py`

**Data shape:**

```python
@dataclass(frozen=True)
class AdapterDecision:
    primary: str
    fallbacks: tuple[str, ...]
    reason: str
    expected_media_kind: str | None = None
```

**Adapters:**

- `direct`
- `yt-dlp`
- `gallery-dl`
- `document`
- `web-page`
- `unsupported`

**Run:**

```bash
pytest tests/test_adapters.py -q
```

**Expected:** Tests define routing for each selected platform/source type.

## Task 6: Refactor downloader to use adapter decisions

**Objective:** Make downloader behavior match adapter router instead of hidden conditionals.

**Files:**
- Modify: `media_backend/downloader.py`
- Modify: `media_backend/cli.py`
- Test: `tests/test_downloader.py`
- Test: `tests/test_cli.py`

**Implementation notes:**

- Keep existing behavior passing during refactor.
- Include `adapter_decision` in metadata and manifest.
- Preserve fallback warnings in `metadata["_adapter_warnings"]`.
- For unsupported `web-page` or `document` cases, return a clear diagnostic status instead of pretending video extraction failed.

**Run:**

```bash
pytest tests/test_downloader.py tests/test_cli.py -q
```

**Expected:** Existing downloader tests pass and new adapter-decision tests prove which adapter was selected.

## Task 7: Add document/raw file no-video path

**Objective:** Stop sending PDFs/documents/images through video assumptions.

**Files:**
- Modify: `media_backend/cli.py`
- Modify: `media_backend/manifest.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_manifest.py`

**Implementation notes:**

- Documents produce `media_kind: document` and `transcript_status: document_only`.
- Images/carousels produce `media_kind: image|carousel` and `transcript_status: visual_only`.
- Audio produces STT attempt without frame extraction.
- Video produces audio + STT + frames.

**Run:**

```bash
pytest tests/test_cli.py tests/test_manifest.py -q
```

**Expected:** Each media kind gets correct artifact expectations and diagnostics.

---

# Phase 3 — Index browser and diagnostics surface

## Target behavior

Mike should be able to ask “what has System B processed?” and get a useful answer without reading JSONL manually.

Minimum first version: a CLI command that reads the source index and prints compact diagnostics.

Suggested command:

```bash
python -m media_backend.index_cli list --limit 20
python -m media_backend.index_cli show <source_key-or-normalized-url>
python -m media_backend.index_cli failures --limit 20
python -m media_backend.index_cli thread <thread_id>
```

Optional later: Discord command or hook-triggered diagnostics summary.

## Task 8: Add index reader module

**Objective:** Provide clean Python functions for reading/searching the current index.

**Files:**
- Create: `media_backend/index_store.py`
- Test: `tests/test_index_store.py`

**Functions:**

```python
def load_sources(path: Path = DEFAULT_SOURCES_INDEX) -> list[dict]: ...
def list_recent(limit: int = 20) -> list[dict]: ...
def find_source(query: str) -> dict | None: ...
def find_by_thread(thread_id: str) -> list[dict]: ...
def list_failures(limit: int = 20) -> list[dict]: ...
```

**Run:**

```bash
pytest tests/test_index_store.py -q
```

**Expected:** Functions handle missing files, malformed lines, duplicates, and enriched records.

## Task 9: Add index CLI

**Objective:** Give operators a local diagnostic browser.

**Files:**
- Create: `media_backend/index_cli.py`
- Test: `tests/test_index_cli.py`
- Modify: `README.md`

**Commands:**

- `list`
- `show`
- `thread`
- `failures`

**Output style:** Plain text first; JSON flag optional:

```bash
python -m media_backend.index_cli list --limit 5
python -m media_backend.index_cli show youtube:abc123
python -m media_backend.index_cli failures --json
```

**Run:**

```bash
pytest tests/test_index_store.py tests/test_index_cli.py -q
```

**Expected:** CLI produces readable output and machine-readable `--json` output.

## Task 10: Add generated diagnostics markdown

**Objective:** Produce a diagnostics artifact that can be pasted or posted in Discord.

**Files:**
- Modify: `media_backend/index_cli.py`
- Test: `tests/test_index_cli.py`

**Command:**

```bash
python -m media_backend.index_cli diagnostics --thread-id <thread_id>
```

**Diagnostics should include:**

- source URL
- adapter selected
- fallback warnings
- source storage path
- manifest path
- media kind
- transcript status
- frame count
- source index status
- errors/warnings
- next recommended repair action if something failed

**Expected:** Passive diagnostics become usable in Discord test runs.

---

# Phase 4 — Passive real-link Discord test pipeline

## Target behavior

Mike can drop a real test link in Discord and mark it as a test run. System B still runs normally, but also posts or writes diagnostics that show what happened.

Suggested trigger conventions:

- Message contains `#systemb-test`
- or starts with `test system b:`
- or is posted in a dedicated test thread/channel if Mike creates one later

The test pipeline should not require a separate bot command at first. It should be passive and low-friction.

## Task 11: Add test-run detection in intake hook

**Objective:** Mark Discord runs as diagnostics/test runs based on message text.

**Files:**
- Modify: `integrations/hermes-hooks/media-analysis-intake/handler.py`
- Test: `tests/test_backend_hook.py` or create focused `tests/test_intake_hook.py` if needed

**State field:**

```json
{
  "test_run": true,
  "diagnostics_requested": true,
  "diagnostics_trigger": "#systemb-test"
}
```

**Run:**

```bash
pytest tests/test_backend_hook.py -q
```

**Expected:** Test-trigger messages set diagnostics fields; normal messages do not.

## Task 12: Backend writes diagnostics artifact for test runs

**Objective:** Create a machine and human readable diagnostic file after extraction.

**Files:**
- Modify: `integrations/hermes-hooks/media-analysis-z-backend/handler.py`
- Test: `tests/test_backend_hook.py`

**Artifact:**

`/home/imagi/media-analysis/threads/<thread_id>/04-diagnostics.md`

**Contents:**

- adapter selected
- commands attempted, sanitized
- source storage fields
- downloaded files count
- manifest path
- audio/transcript/frame status
- source index upsert status
- Discord rename status
- errors/warnings

**Run:**

```bash
pytest tests/test_backend_hook.py -q
```

**Expected:** Test runs write `04-diagnostics.md`; normal runs can optionally skip it or write compact diagnostics only on failure.

## Task 13: Include diagnostics pointer in Discord/Hermes final summary

**Objective:** Make test-run results easy to inspect in the thread.

**Files:**
- Modify: `integrations/hermes-hooks/media-analysis-z-backend/handler.py` if hook-created prompt context needs to instruct Hermes
- Modify: `SKILL.md` or `integrations/hermes-hooks/README.md` if this is prompt-level behavior
- Test: `tests/test_backend_hook.py`

**Behavior:**

When `diagnostics_requested` is true, final thread summary should include:

```text
Diagnostics: 04-diagnostics.md
Adapter: yt-dlp -> success
Transcript: stt_complete
Frames: 8
Source index: upserted
Source storage: /home/imagi/media-analysis/sources/...
```

**Expected:** Mike sees diagnostics plus normal content summary.

## Task 14: Add passive real-link test checklist doc

**Objective:** Give Mike a simple repeatable test script for Discord.

**Files:**
- Create: `docs/system-b-discord-test-pipeline.md`

**Checklist:**

1. Drop a YouTube link with `#systemb-test`.
2. Confirm thread title renames to `youtube: <title> — <creator>`.
3. Confirm `01-source.md`, `02-extract.md`, `03-analysis.md`, and `04-diagnostics.md` exist.
4. Confirm diagnostics show adapter, transcript, frames, source index, and source storage.
5. Drop an Instagram reel with `#systemb-test`.
6. Drop an Instagram carousel with `#systemb-test`.
7. Drop a direct image/PDF/video with `#systemb-test`.
8. Report failures back into project as adapter-specific fixes.

---

# Verification strategy

## Unit/focused tests

Run after every task:

```bash
cd /home/imagi/projects/instagram-reel-analyzer
pytest -q
```

Focused commands by area:

```bash
pytest tests/test_storage.py -q
pytest tests/test_adapters.py -q
pytest tests/test_downloader.py -q
pytest tests/test_cli.py -q
pytest tests/test_manifest.py -q
pytest tests/test_backend_hook.py -q
pytest tests/test_index_store.py tests/test_index_cli.py -q
```

## Live/passive tests

Do not restart Hermes gateway without Mike approval.

After gateway restart is approved and performed, test with:

```text
#systemb-test <YouTube URL>
#systemb-test <Instagram reel URL>
#systemb-test <Instagram carousel URL>
#systemb-test <direct image/PDF/video URL>
```

Acceptance criteria for each live run:

- Thread workspace exists.
- Source storage directory exists.
- `state.json` has `source_storage` fields.
- `sources.jsonl` has enriched source record.
- `01-source.md` includes metadata and canonical name.
- `04-diagnostics.md` exists for test runs.
- Discord thread summary includes diagnostics pointer and normal summary.
- Failures are explicit, adapter-specific, and repairable.

---

# Commit and mirror policy

For every implementation phase:

1. Commit to `jc214-fullstack/instagram-reel-analyzer` first.
2. Mirror `integrations/hermes-hooks/` and relevant docs into Hermes fork path `integrations/system-b-media-analysis/`.
3. Commit and push the Hermes mirror branch.
4. Do not restart gateway unless Mike explicitly approves.
5. If live hook files are changed under `/home/imagi/.hermes/hooks`, create a tarball backup under `/home/imagi/media-analysis/backups/`.

---

# Recommended implementation order

1. Source storage planner and manifest fields.
2. Hook/index support for source storage fields.
3. Adapter decision object.
4. Downloader refactor to use adapter router.
5. Index reader and CLI browser.
6. Diagnostics artifact generation.
7. Passive Discord `#systemb-test` detection.
8. Real-link smoke tests after approved gateway restart.

This keeps the risk low: storage and metadata become durable first, then acquisition routing improves, then the operator-facing diagnostics layer lands.
