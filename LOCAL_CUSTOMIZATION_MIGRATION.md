# Local customization migration policy

This file is the operator policy for Mike's personal Hermes customizations during upstream upgrades.

## Goal

Keep Hermes upgrades low-fragility.

The preferred flow is:

1. Back up Hermes state and profiles.
2. Upgrade Hermes itself.
3. Reapply only the customizations we still need.
4. Run the post-update verifier.
5. Keep the dedicated fix repo and backup repo aligned with the new reality.

## Canonical sources

Hermes core customization lives in these canonical places:

- Live branch in this repo: `feat/channel-routed-gateway-state`
- Dedicated fix repo: `https://github.com/jc214-fullstack/hermes-channel-routed-gateway-state-fix`
- Local dedicated fix repo: `/home/imagi/projects/hermes-channel-routed-gateway-state-fix`
- Patch artifact: `artifacts/hermes-agent-channel-routed-gateway-state.patch`
- Upgrade control repo: `/home/imagi/projects/hermes-upgrade-backup`
- Verifier: `/home/imagi/projects/hermes-upgrade-backup/scripts/verify_post_update.sh`

## Keep / Remove / Update policy

### KEEP

Keep these unless upstream Hermes fully replaces them with equivalent behavior:

1. The minimal gateway/session-state customization for channel-routed model state persistence across resets.
2. The dedicated fix repo and its patch artifact as the canonical pull/reapply source.
3. The post-update verifier in `hermes-upgrade-backup`.
4. The repo-managed loadout system in `hermes-coding-terminal-load-out-system`.
5. This migration policy file.

### REMOVE

Remove or retire these when they are superseded:

1. Duplicate alias branches that point at the same customization commit.
2. Ad-hoc working-tree patch captures once the normalized patch and dedicated fix repo are current.
3. Hermes-core custom code that upstream has replaced cleanly.
4. Upgrade safety stashes after a stable cycle, once the branch, patch repo, and verifier have all been validated again.

### UPDATE

Update these whenever upstream Hermes changes the surrounding integration surface:

1. `LOCAL_CUSTOMIZATION_MIGRATION.md` if the list of custom files or policy changes.
2. The dedicated fix repo README, manifest, and patch artifact.
3. The post-update verifier if Hermes health checks, runtime manifests, or loadout validation rules change.
4. The heartbeat/update-readiness collector if upgrade decisions need new evidence.
5. The loadout repo verification expectations if runtimes or adapters change.

## Upgrade decision rules

### Seamless upgrade is allowed when

- Hermes can be updated without losing access to the dedicated fix repo.
- The patch artifact is present and readable.
- The verifier script is present and readable.
- The loadout repo is still available for validation/materialization checks.

### Pause and inspect before upgrading when

- The dedicated fix repo is missing or dirty in a suspicious way.
- The verifier script is missing.
- The live customization branch is not the expected branch.
- There is evidence that upstream now overlaps the local patch and the patch may need re-splitting.

## Reapply sequence

1. Update Hermes.
2. Check whether the customization survived cleanly.
3. If not, reapply from the dedicated fix repo patch or cherry-pick from the canonical branch.
4. Run:

```bash
EXPECTED_HERMES_VERSION='<new-version>' /home/imagi/projects/hermes-upgrade-backup/scripts/verify_post_update.sh
```

5. Confirm Hermes health, loadout validation, loadout tests, and temp-home materialization.
6. Refresh the dedicated fix repo artifacts if the customization itself changed.

## Files currently expected to matter

The local Hermes-core customization currently centers on:

- `gateway/run.py`
- `hermes_state.py`
- `plugins/platforms/discord/adapter.py`
- `tests/gateway/test_session_boundary_hooks.py`
- `tests/gateway/test_model_command_channel_binding.py`

If that file set changes, update this policy and the dedicated fix repo manifest together.

## Operator note

The design target is always to keep the Hermes-core delta small and keep the real product repo-managed elsewhere. If upstream absorbs a local behavior cleanly, prefer removing local core code rather than carrying dead patch surface forever.
