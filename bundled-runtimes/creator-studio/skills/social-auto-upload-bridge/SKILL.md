---
name: social-auto-upload-bridge
description: Use when Newma Publish needs a bridge to the external social-auto-upload project for video upload packages across Bilibili, Xiaohongshu, Douyin, Kuaishou, WeChat Channels, Baijiahao, TikTok, or YouTube.
---

# Social Auto Upload Bridge

## Role

Use `social-auto-upload` as the guarded local video uploader for 小红书、抖音、B站和视频号. It is a project-local upstream dependency kept under `vendor/publish/`, excluded from the main repository, and independently updateable.

Default root:

```bash
${SOCIAL_AUTO_UPLOAD_ROOT:-${DASHENG_PROJECT_ROOT:-.}/vendor/publish/social-auto-upload}
```

## When To Use

- Publish has a completed video `channel_pack.json`.
- The target channel is `xiaohongshu_video`, `douyin_video`, `bilibili_video`, or `wechat_channels_video`.
- A completed `channel_pack.json` contains the final MP4 and platform metadata.
- The account is represented by an explicit `account_name` or stable `account_slot`; default is `slot-1`.

## Inputs

- `channel_pack.json`
- Final MP4 path
- Title, description, tags, cover if available
- Platform account/session already configured in the external project

## Workflow

1. Check upstream registry:
   ```bash
   python3 scripts/check_publish_upstreams.py --name social-auto-upload
   ```
2. Check local external repo exists and is healthy.
3. Convert `channel_pack.json` into the external project's expected upload config.
   ```bash
   python3 scripts/build_video_upload_package.py --channel-pack <channel_pack.json>
   ```
4. Build the exact login-check and upload command without publishing:
   ```bash
   python3 scripts/execute_social_auto_upload.py --channel-pack <channel_pack.json>
   ```
5. Show the platform, account slot, title, video, cover, schedule and generated command for review.
6. Only after explicit current-session confirmation run:
   ```bash
   python3 scripts/execute_social_auto_upload.py \
     --channel-pack <channel_pack.json> \
     --confirm-execute
   ```
7. The executor must run `sau <platform> check --account <account>` before upload. Invalid login blocks execution and returns the headed login command.
8. Write results back under `~/Desktop/自媒体创作/<run_id>/05_发布/channel_packs/...` and keep verification as `needs_manual_verification` until a platform URL or draft ID is recovered.

For two-version, multi-account distribution, build a Campaign first. The campaign owns platform-specific titles, descriptions, tags, covers, activity state and logical-account routing; this bridge only executes each frozen task package:

```bash
python3 scripts/build_publish_campaign.py --spec <campaign_spec.json> --output-dir <run_dir>
python3 scripts/publish_accounts.py --check-auth --output <run_dir>/account_auth_report.json
python3 scripts/build_publish_campaign.py --spec <campaign_spec.json> --output-dir <run_dir>
python3 scripts/execute_publish_campaign.py --campaign <run_dir>/publish_campaign.json
```

## Platform Mapping

| Newma channel | `sau` platform | Notes |
| --- | --- | --- |
| `xiaohongshu_video` | `xiaohongshu` | Video, cover, tags and schedule |
| `douyin_video` | `douyin` | Video, cover, tags and schedule |
| `bilibili_video` | `bilibili` | Requires `platform_notes.tid` or `category_id` |
| `wechat_channels_video` | `tencent` | Supports short title, category, draft and dual cover hints |

Douyin activities are discovered live through OpenCLI when available. Pass `platform_notes.activity_selected` only after editorial confirmation. Pass `platform_notes.declaration` only when the exact Douyin option text was explicitly approved; never infer it.

## Account Slots

- `platform_notes.account_name` has highest priority.
- `platform_notes.account_slot: 1` maps to `slot-1`; slot 2 maps to `slot-2`.
- Login state belongs under `~/Library/Application Support/NewmaPublishSessions/social-auto-upload/cookies/`. The ignored upstream `cookies/` path is only a symlink to this secure state directory.
- Login must be performed interactively with the relevant `sau <platform> login --account <slot> --headed` command.
- Account aliases, slots and auth methods are registered in `configs/publish/account_registry.json`; the registry contains no secrets or cookies.
- Initialize or audit account storage with `python3 scripts/publish_accounts.py --init` and validate sessions with `python3 scripts/publish_accounts.py --check-auth`.

## Hard Rules

1. Never copy generated videos or credentials into `skills/`.
2. Never commit the nested upstream repository, its `.venv`, cookies, logs, or browser state into the main repository.
3. Never execute final publish without explicit current-session confirmation. `auto_confirm` is not accepted by the guarded executor.
4. If login, CAPTCHA, cookie, or upload permission fails, export a manual package and mark the execution `fallback_export`.
5. Always run Publish Guard or platform-specific verification before reporting success.
6. A zero CLI exit code means only “upload command completed”; it is not proof of publication.
7. Use headed mode by default for browser-based platforms to reduce login and anti-bot failures.
8. Campaign execution requires every primary `social_auto_upload` account status to be `valid`; browser state alone is not proof that the CLI session is usable.
9. Never invent or auto-select a platform activity. Unselected activities remain `live_discovery_required`.

## Upstream

Tracked in:

```bash
configs/publish/upstream_repos.json
```
