# Newma Canonical Stage Contract

## Stage Order

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

## Required Deliverables

- Intake: `intake_manifest.json`
- Brief: `brief_manifest.json` + `selected_topics.json`
- Draft: `draft_manifest.json` + `final_structure_snapshot.json`
- Transwrite: `transwrite_manifest.json` + `transwrite_decision.json`
- Publish: `publish_manifest.json` + `publish_decision.json` + `publish_guard_report.json/md`
- Postmortem: `postmortem_manifest.json` + `publish_guard` 摘要

Optional rewrite tools may emit `rewrite_manifest.json`, but it is not a required gate in the canonical mainline.

Optional asset generators may emit `paradigm_manifest.json` or `training_manifest.json`, but neither is a required gate in the canonical mainline.

## Brief Contract

- Generation mode: `ai_only`
- Output shape: 8-10 flat independent topic cards
- Canonical outputs:
  - `02_编辑Brief库.md`
  - `02_研究Brief库.md`
  - `02_编辑Brief_报告.md`
  - `topic_cards.json`
  - `selected_topics.json`
  - `brief_manifest.json`

## Draft Contract

- Formal upstream input: `selected_topics.json` + `topic_cards.json`，且 Brief Gate 已批准。
- Formal output root: `${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/<run_id>/03_初稿/`。
- Draft 只生成研究、可复核数据、图表、正文配图、Reasoning Sheet、标准初稿、自包含离线 HTML、事实核查和质量门禁。
- Draft 不生成公众号渠道终稿或封面，不执行 Transwrite，不登录账号、不上传草稿、不调用平台发布工具。
- Per-topic `draft_result.json` must include `stage=draft`, `next_stage=transwrite`, and `next_stage_authorized=false`.
- Canonical stage outputs are `draft_manifest.json` + `final_structure_snapshot.json`; completion only makes Transwrite eligible for later approval and never authorizes it automatically.

## Transwrite Contract

- Formal upstream input: `draft_manifest.json`
- Required gates: `final_structure_snapshot.json` + `transwrite_decision.json`
- Optional upstream assets: `paradigm_profile.yaml`, `video-style-training/style_profile.json`
- Lanes:
  - `wechat_article`
  - `explainer_html_video`
  - `vox_explainer_video`
  - `talking_head_video`
  - `digital_human_video`
  - `commercial_promo_video`
  - `cinematic_short_drama_video`（默认 deferred）
  - `podcast`
- Outputs:
  - `04_转写计划.md`
  - `transwrite_manifest.json`
  - per-topic lane manifests

## Publish Contract

- Formal upstream input: `transwrite_manifest.json`
- Required gate: `publish_decision.json`
- Publish only handles acceptance, package creation, draft/manual execution, link recovery, and guard verification.
- Publish outputs:
  - `07_发布计划.md`
  - `07_发布包.md`
  - `channel_execution_manifest.json`
  - `publish_verification_report.json`
  - `publish_guard_report.json`
  - `publish_guard_report.md`
  - `publish_manifest.json`

## Publish Guard Contract

- `publish_guard.py` 只校验发布批次结果，不上传、不发布、不打开浏览器、不读取 cookies。
- 默认输入：`publish_manifest.json` + 同目录 `publish_verification_report.json`；缺少验真报告时不得通过。
- `publish_manifest.publish_results` 与 `publish_verification_report.records` 必须一致；两份文件的 `publish_summary` 也必须一致并匹配重算结果。
- 每条回填结果都必须能追到磁盘上的 `publish_result.json`，且核心发布字段必须与 manifest/verification 记录一致。
- 默认模式即使未通过也返回 0，方便人工查看报告；CI/正式门禁必须使用 `--fail-on-error`，未通过时返回非 0。
- 默认输出：
  - `publish_guard_report.json`
  - `publish_guard_report.md`
  - `publish_manifest.publish_guard`
- `publish_manifest.publish_guard` 至少包含：
  - `status`
  - `passed`
  - `checked_at`
  - `report_json`
  - `report_markdown`
  - `will_not_publish`
- `published_links` 只允许 `status=published`、`verification_status=verified` 且带正式 `platform_url` 的结果。
- `draft_records` 只允许 `status=draft|scheduled`、`verification_status=verified` 且带 `draft_id` 的结果。
- `record_publish_result.py` 不得因为存在正式 URL 或草稿 ID 自动推断 `verified`；执行器或人工回填必须显式传入验真状态。
- `draft_url` 与 `platform_url` 必须分离，草稿链接不得冒充正式发布链接。
- `build_stage5_publish.py` 初始生成时也必须写入 `publish_summary`；未回填任何渠道时 `status=pending_execution`、`recorded_count=0`、`pending_count=total_channels`。

## Postmortem Contract

- Formal upstream input: `publish_manifest.json`
- Default mode may continue when `publish_manifest.publish_guard` is missing, but the report must show `publish_guard.status=missing`.
- Formal gated mode must pass `--require-publish-guard`; if Publish Guard is missing, not passed, or its `report_json` / `report_markdown` files are missing, Postmortem must fail before writing outputs.
- `postmortem_manifest.json` must include `publish_guard` summary:
  - `present`
  - `status`
  - `passed`
  - `report_json`
  - `report_markdown`
  - `checked_at`
