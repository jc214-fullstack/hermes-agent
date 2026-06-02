---
name: hermes-gateway-bootstrap
description: Mobile-safe Hermes Gateway check/start/bootstrap/restart dispatcher for Codex-hosted Windows machines.
version: 1.0.0
---

# Hermes Gateway Bootstrap

When the user asks to check, wake, start, bootstrap, recover, or initialize Hermes Gateway, run:

`scripts\hermes-gateway-up.cmd`

When the user asks to restart Hermes Gateway, run:

`scripts\hermes-gateway-restart.cmd`

## Natural-language triggers

Run `scripts\hermes-gateway-up.cmd` for intents containing:
- check gateway
- is hermes up
- wake hermes
- start hermes
- bootstrap hermes
- recover hermes
- initialize hermes

Run `scripts\hermes-gateway-restart.cmd` for intents containing:
- restart hermes gateway
- reboot hermes gateway
- bounce gateway

## Required response format (mobile-friendly)

Return:
- command run
- gateway healthy: yes/no
- started: yes/no/unknown
- restarted: yes/no/unknown
- initialized: yes/no/skipped/failed
- errors (if any)
- next action (if needed)

## Notes

- This workflow assumes Codex mobile sends command -> Windows Codex host executes local scripts.
- It does not require a visible terminal window to remain open.
- Safety: do not kill arbitrary processes unless `HERMES_ALLOW_PORT_KILL=1`.
