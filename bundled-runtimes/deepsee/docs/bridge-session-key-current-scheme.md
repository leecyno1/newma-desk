# Hermes bridge session key — current scheme

Current rule for 0913 WeChat auto-reply:

- Hermes session key is bridge-scoped, not per-contact and not the old shared-session wording
- prefer `agent:bridge:wechat_gateway:subsession:<subsession_id>`
- if no subsession exists, fall back to `agent:bridge:wechat_gateway:chat:<chat_or_sender>`
- contact / group-member isolation remains in 0913 persistence (`wechat_subsessions`, memberships, turns), not in Hermes session fan-out

Why:

- avoid cross-channel pollution
- avoid session explosion from one Hermes session per contact
- keep Hermes responsible only for bridge-level reasoning continuity
- keep 0913 responsible for contact, group, membership, and turn persistence

Examples:

- fixed subsession path:
  - `agent:bridge:wechat_gateway:subsession:wechat_gateway_default`
- fallback path without resolved subsession:
  - `agent:bridge:wechat_gateway:chat:wxid_friend_a`

What to update after future migrations:

1. `app/services/hermes_bridge.py`
2. tests asserting `X-Hermes-Session-Id` and execution metadata
3. `DEPLOY_FULL.md` and repo docs under `docs/`
4. Hermes skill docs under `~/.hermes/skills/software-development/0913-wechat-smart-reply/`

Verification grep used during this cleanup:

- no repo markdown hits for:
  - `per-chat session`
  - `_per_chat_session_id`
  - `one key per contact`
  - `X-Hermes-Session-Id: wechat_gateway_default`
  - `X-Hermes-Session-Key: wechat_gateway_default`

This file is the concise source for the current session-key scheme. Historical incident notes should be read as diagnosis history unless they explicitly say they describe current behavior.
