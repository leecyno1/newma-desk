---
name: dasheng-xhs-publish-bridge
description: Use when Newma Publish needs to route Xiaohongshu publishing or content access through API-first CLI, MCP, or browser fallback bridges.
---

# Newma XHS Publish Bridge

## Overview

This is the thin Xiaohongshu publish bridge for Newma. Keep it API-first. Use the smallest viable external surface for the current channel pack and fall back only when the primary path fails.

## When to Use

- The channel pack targets Xiaohongshu publish, draft, or post-publish verification.
- You need to choose between CLI, API wrapper, MCP, or browser fallback.
- You need a stable handoff from Newma publish packs to an external XHS tool.

## Priority Order

1. `all-in-one` for unified CLI/agent routing.
2. `xhs-skills` / `spider-xhs` for API-first creator and content access.
3. `xiaohongshu-mcp` / `rednote-mcp` when MCP transport is easier.
4. `xiaohongshu-auto` or browser fallback when API transport is blocked.

## Inputs

- `channel_pack.json`
- `execution_request.json`
- `verification_request.json`
- Final video or image assets referenced by `artifact_hint`

## Execution Contract

1. Read `execution_request.json`.
2. Run the local preparation script:
   ```bash
   python3 scripts/prepare_publish_execution.py --execution-request <execution_request.json>
   ```
   `scripts/prepare_xhs_publish_execution.py` remains as a Xiaohongshu-specific compatibility entry.
3. Stop for login, CAPTCHA, risk-control, or final publish confirmation.
4. Write platform result beside the channel pack.
5. Run or prepare `publish-guard` verification from `verification_request.json`.

## Rules

- Do not vendor upstream repositories into Newma.
- Do not store cookies, media, or publish outputs inside `skills/`.
- Use persistent browser profiles for any browser fallback.
- Always return a verification artifact or a clear fallback reason.
