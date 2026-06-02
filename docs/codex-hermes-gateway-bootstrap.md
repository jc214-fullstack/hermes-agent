# Codex Mobile -> Windows Codex Host -> Hermes Gateway Bootstrap

This is the first working iteration for remote recovery from phone.

Flow: Phone -> ChatGPT/Codex Mobile -> connected Windows Codex App host -> `hermes-gateway-bootstrap` skill -> CMD scripts -> Hermes Gateway.

For this to work, the Windows machine must stay powered on, awake, online, signed into Codex, and running the Codex desktop app host.

## Mobile commands

Use this to check/start/bootstrap:

`Use $hermes-gateway-bootstrap to make sure Hermes is up and initialized.`

Use this to restart:

`Use $hermes-gateway-bootstrap to restart Hermes Gateway.`

## Local scripts

- `scripts\hermes-gateway-up.cmd`
- `scripts\hermes-gateway-restart.cmd`

## Defaults

- Health URL: `http://127.0.0.1:8787/health`
- Init URL: `http://127.0.0.1:8787/system/initialize`
- Port: `8787`
- Timeout: `60` seconds
- Log dir: `.hermes\logs`
- Runtime dir: `.hermes\run`

## Supported environment variables

- `HERMES_HEALTH_URL`
- `HERMES_INIT_URL`
- `HERMES_PROJECT_ROOT`
- `HERMES_START_CMD`
- `HERMES_STOP_CMD`
- `HERMES_GATEWAY_SERVICE`
- `HERMES_TIMEOUT_SECONDS`
- `HERMES_SKIP_INIT`
- `HERMES_PORT`
- `HERMES_ALLOW_PORT_KILL`

## Start-command inference used in this iteration

From Hermes docs/repo command references, this iteration defaults `HERMES_START_CMD` to:

`hermes gateway start`

If your local install requires a different command, set `HERMES_START_CMD` explicitly.

## Manual fallback

Run from project root on Windows:

- `scripts\hermes-gateway-up.cmd`
- `scripts\hermes-gateway-restart.cmd`

## Future hardening

- Install Hermes Gateway as a Windows service.
- Configure service auto-restart.
- Add a scheduled watchdog task.
- Add Tailscale/SSH/RDP fallback access.
