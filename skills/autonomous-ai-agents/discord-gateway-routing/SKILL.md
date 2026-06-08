---
name: discord-gateway-routing
description: "Configure Hermes Discord routing: mention gates, free-response channels, auto-threading, handoff routes, and per-channel model bindings."
version: 1.0.0
author: Nous Research
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Discord, Gateway, Routing, Threads, Handoff, Deep Work, Model Binding]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [hermes-agent]
---

# Discord Gateway Routing

Use this skill when the user wants Hermes to behave differently in Discord channels or threads — especially around **whether `@mentions` are required**, **whether replies stay inline or move into threads**, **whether a channel should be free-response**, or **whether one Discord channel should hand work off into another channel with a different model binding**.

## When to use

Load this skill for requests like:

- "Can Hermes reply without me pinging it every time?"
- "Stop creating threads in this bot channel."
- "Keep stricter mention-gating everywhere except one room."
- "Route anything matching this phrase into a Deep Work channel."
- "Make this destination channel always use a different model/provider."
- "Why did Hermes create a new thread in another channel?"
- "How do I wire quick work → deep work in Discord?"

## Core Discord routing knobs

These settings live under the top-level `discord:` block in `~/.hermes/config.yaml`.

### 1. `require_mention`

```yaml
discord:
  require_mention: true
```

- `true`: Hermes only responds in server channels when mentioned, except where another exemption applies.
- `false`: Hermes may respond to ordinary channel messages anywhere it is otherwise allowed.

Recommended default: keep this `true`, then carve out specific always-on rooms with `free_response_channels`.

### 2. `thread_require_mention`

```yaml
discord:
  thread_require_mention: false
```

- `false` (default): once Hermes has participated in a thread, it usually keeps responding there without another `@mention`.
- `true`: thread follow-ups are gated the same way as normal channels.

Turn this on for multi-bot servers where several bots share the same thread surface.

### 3. `free_response_channels`

```yaml
discord:
  free_response_channels:
    - CHANNEL_ID
```

These channels become mention-free. Hermes responds inline there, which makes them good bot-help or command-center channels.

### 4. `no_thread_channels`

```yaml
discord:
  no_thread_channels:
    - CHANNEL_ID
```

These channels stay in the main channel instead of auto-creating a thread per mention.

### 5. `auto_thread`

```yaml
discord:
  auto_thread: true
```

- `true`: normal mentioned messages in text channels can spin off into their own conversation thread.
- `false`: disables automatic thread creation globally.

Prefer `no_thread_channels` over disabling `auto_thread` globally when the user only wants one or two channels to stay inline.

### 6. `channel_model_bindings`

```yaml
discord:
  channel_model_bindings:
    - id: "1510042356487950376"
      model: gpt-5.5
      provider: openai-codex
      base_url: https://chatgpt.com/backend-api/codex
```

This binds a specific Discord parent channel or thread to a specific model/provider pair.

Important behavior:

- Exact thread/channel ID matches win.
- If the incoming message is in a thread and the thread itself has no explicit binding, Hermes falls back to the parent channel ID.
- New handoff threads inherit the binding from their configured target parent channel.

Use this whenever one room should always run a different model than the rest of the gateway.

### 7. `handoff_routes`

```yaml
discord:
  handoff_routes:
    - label: Deep Work
      target_channel_id: "1510042356487950376"
      trigger_phrases:
        - push this to deep work
        - push this to the deep work channel
      auto_run_marker: "[AUTO_RUN_DEEP_WORK]"
      thread_name_prefix: Deep Work
```

A handoff route watches for a start-anchored trigger phrase, creates a new thread under the target parent channel, rewrites the task into a handoff-prefixed message, and lets that destination thread run with its own model binding.

Field meanings:

- `label`: operator-facing label for logs and injected handoff text.
- `target_channel_id`: parent Discord channel where the routed thread should be created.
- `trigger_phrases`: phrases that activate the route. These should be imperative, start-of-message phrases.
- `auto_run_marker`: internal marker used for the bot-authored follow-up that actually kicks off work in the new thread.
- `thread_name_prefix`: friendly prefix for the created thread title.

### 8. `deep_work_trigger_phrases`

```yaml
discord:
  deep_work_trigger_phrases:
    - push this to deep work
```

This is the legacy shortcut that is folded into the normalized handoff route list. Prefer `handoff_routes` for new setups because it is explicit and extensible.

## Recommended patterns

### Pattern A: one no-ping inline bot channel

When the user wants:

- no repeated pings in one room
- no auto-created threads in that room
- stricter mention-gating everywhere else

use:

```yaml
discord:
  require_mention: true
  free_response_channels:
    - COMMAND_CENTER_CHANNEL_ID
  no_thread_channels:
    - COMMAND_CENTER_CHANNEL_ID
  auto_thread: true
```

### Pattern B: quick-work → deep-work routing

When the user wants a lightweight intake channel that can kick harder work into a dedicated Deep Work channel, use:

```yaml
discord:
  require_mention: true
  free_response_channels:
    - QUICK_WORK_CHANNEL_ID
  no_thread_channels:
    - QUICK_WORK_CHANNEL_ID
  channel_model_bindings:
    - id: "DEEP_WORK_PARENT_CHANNEL_ID"
      model: gpt-5.5
      provider: openai-codex
      base_url: https://chatgpt.com/backend-api/codex
  handoff_routes:
    - label: Deep Work
      target_channel_id: "DEEP_WORK_PARENT_CHANNEL_ID"
      trigger_phrases:
        - push this to deep work
      auto_run_marker: "[AUTO_RUN_DEEP_WORK]"
      thread_name_prefix: Deep Work
```

Expected runtime behavior:

1. User sends a start-anchored trigger in the intake channel.
2. Hermes creates a thread under the Deep Work parent channel.
3. Hermes posts the rewritten handoff task into that new thread.
4. The new thread runs under the Deep Work channel's model binding.
5. Recursive triggers inside the destination channel/thread are ignored.

## How to answer the user

1. Figure out whether they want inline chat, mention-free chat, thread isolation, or cross-channel handoff.
2. Keep `require_mention: true` unless they explicitly want Hermes broadly always-on.
3. For one always-on room, prefer `free_response_channels` + `no_thread_channels`.
4. For a separate execution lane, add both `channel_model_bindings` and `handoff_routes` together.
5. If they want Deep Work behavior, make the trigger phrase imperative and start-anchored.
6. Tell them config changes need a gateway restart before behavior changes are live.

## Pitfalls

- Do **not** imply that `/sethome` changes mention gating or thread behavior. Home routing and channel behavior are separate concerns.
- Do **not** configure a handoff route without a matching `channel_model_bindings` entry for the destination channel.
- Do **not** rely on vague trigger phrases buried mid-sentence; the intended route match is start-anchored.
- Do **not** treat the destination thread as a brand-new independent config surface. Inheritance comes from the parent channel binding unless you explicitly bind the thread ID itself.
- Do **not** forget the restart. Editing `config.yaml` alone does not update an already-running gateway process.
- When using CLI config helpers for structured lists/maps, verify the resulting YAML shape on disk. Arrays and mappings must remain real YAML structures, not quoted blobs.

## Verification / rollout

After changing routing config:

1. Run `hermes config check`.
2. Restart the gateway.
3. Test one normal non-mentioned message in a configured free-response channel.
4. Test that a no-thread channel stays inline.
5. Test a handoff phrase like `push this to deep work: ...` from the intake surface.
6. Confirm a new thread appears under the target parent channel.
7. Confirm the receiving thread reports the expected model/provider from the destination channel binding.
8. Confirm repeating the trigger phrase inside the destination thread does **not** recurse into another handoff.

## Operator notes

If the user is asking for broad Discord behavior changes, prefer editing the structured `discord:` block in `config.yaml` over scattered env vars, then keep env vars only for secrets or temporary overrides.
