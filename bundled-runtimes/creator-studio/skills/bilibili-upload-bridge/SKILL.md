---
name: bilibili-upload-bridge
description: Use when Newma Publish needs to prepare, upload, or package Bilibili video submissions from completed transwrite video channel packs.
---

# Bilibili Upload Bridge

## Role

Bridge Newma Publish channel packs to B站 upload tools. Prefer `biliup-rs`; use the project-local, ignored `social-auto-upload` upstream as fallback. Both remain independently updateable and are not version-locked by the main repository.

Default roots:

```bash
${BILIUP_RS_ROOT:-${BILIUP_RS_ROOT:-vendor/reserved/publish/biliup-rs}}
${SOCIAL_AUTO_UPLOAD_ROOT:-${DASHENG_PROJECT_ROOT:-.}/vendor/publish/social-auto-upload}
```

## Inputs

- `channel_pack.json` for `bilibili_video`
- Final MP4
- Optional SRT/subtitle
- Title, description, tags, cover

## Workflow

1. Check upstream registry:
   ```bash
   python3 scripts/check_publish_upstreams.py --name biliup-rs
   ```
2. Validate final video exists.
3. Build B站 submission package:
   - title
   - description
   - tags
   - cover
   - video path
   - subtitle path when present
   ```bash
   python3 scripts/build_video_upload_package.py --channel-pack <channel_pack.json>
   ```
4. Prefer a dry-run or draft/upload preview when the external tool supports it.
5. Ask for explicit confirmation before real submission.
6. Write platform response, draft ID, URL, screenshot, or fallback reason back to the publish package.

## Fallback

If `biliup-rs` is missing, broken, or cannot authenticate:

1. Try `social-auto-upload-bridge` for Bilibili.
2. If that fails, export an人工投稿包 and mark status `manual_package`.

## Hard Rules

1. B站 uploads are not considered published until a URL,稿件 ID, or platform response is recovered and verified.
2. Do not store B站 cookies or account secrets inside this repo or `skills/`.
3. Do not mark `ready_for_execution` if the MP4 is missing.
4. If the account requires CAPTCHA/SMS/manual login, stop and request user action.

## Upstream

Tracked in:

```bash
configs/publish/upstream_repos.json
```
