# Loadout Runtime Launch Integration

## Goal

Make Claude Code and Codex launches a first-class Hermes runtime path instead of leaving `hermes loadout ...` as operator-only plumbing.

## Design

Keep two layers separate:

1. the external loadout repo owns route resolution, loadout definitions, validation, manifests, and runtime-surface materialization
2. Hermes owns only a thin launch/control shim that calls the external repo before runtime launch

That separation keeps the loadout system upgrade-safe. Hermes updates only need to preserve a tiny integration layer instead of an embedded loadout brain.

## Hermes-side surfaces

### 1. `hermes loadout`

Operator control plane for:

- `status`
- `resolve`
- `apply`
- `launch`

It should reuse the external repo scripts directly, not reimplement resolution or materialization logic.

### 2. `terminal_agent` built-in tool

Canonical one-shot launcher for Claude Code and Codex. It should:

1. infer the runtime from task text when omitted
2. resolve/apply the matching loadout via the external repo
3. write the loadout into the live runtime home
4. launch the runtime with a stable one-shot command shape
5. return structured execution data so Hermes can review the run

## Runtime command shapes

### Claude

`claude -p <task> --output-format json --max-turns <n>`

### Codex

`codex exec --full-auto <task>`

For Codex, the launcher also sets `CODEX_HOME` to the applied runtime home.

## Guardrails

- Hermes should not duplicate loadout YAML or merge logic.
- Hermes should consume the external repo's JSON apply output.
- Claude custom-home launch overrides are intentionally rejected until a reliable Claude-side override path is known.
- The live manifest remains the inspectable proof of what was applied.

## Verification standard

1. targeted Hermes tests for CLI and tool behavior pass
2. the CLI can resolve and dry-run launch against the external repo
3. the tool can dry-run and return runtime/loadout/manifest metadata
4. live manifests exist after a real apply

## Why this is upgrade-safe

The external loadout repo remains the primary product. Hermes only knows how to call it. That means future loadout refinement, session-policy changes, and runtime-surface edits continue to happen in the dedicated repo with minimal Hermes churn.
