---
name: dasheng-daily-postmortem
description: Use when the workflow enters Postmortem after Publish and published content needs to be evaluated with performance data, Publish Guard status, accuracy checks, and knowledge-base writeback suggestions.
---

# dasheng-daily-postmortem

## 状态

`internal module / Postmortem 执行层`

## 当前定位

这是当前主链应保留的内部执行模块。

它负责在发布后接收平台表现数据，形成复盘判断，但不负责总控调度。

## 当前标准入口

- 总控入口：`${DASHENG_PROJECT_ROOT:-.}/skills/dasheng-media-sop/SKILL.md`
- 脚本入口：`python3 scripts/postmortem_writeback.py --publish-manifest ~/Desktop/自媒体创作/<run_id>/05_发布/publish_manifest.json`
- 正式门控入口：`python3 scripts/postmortem_writeback.py --publish-manifest ~/Desktop/自媒体创作/<run_id>/05_发布/publish_manifest.json --require-publish-guard`

## 标准职责

- 汇总浏览、互动、传播等数据
- 读取 `publish_manifest.publish_guard`，把发布批次验收状态写入复盘
- 解释预测偏差与结构性误判
- 输出继续 / 停止 / 测试建议
- 形成可回写的知识条目建议

## 复盘口径

- 复盘 `topics` 必须按 `topic_id` 聚合；一个选题分发多个渠道仍只算一个 topic。
- 只有 `published`、`verification_status=verified` 且带正式平台 URL 的结果，才能算作已发布。
- `draft` / `scheduled` 必须带 `draft_id` 且 `verification_status=verified`，只能算草稿，不计入已发布。
- `needs_manual_verification` 说明验真未闭环，不能写入成功案例。
- 若 `publish_manifest.publish_guard` 缺失，复盘报告必须提示先运行 `scripts/publish_guard.py --publish-manifest <publish_manifest.json>`。
- 默认模式允许复盘继续并提示 Guard 缺失；正式门控模式必须加 `--require-publish-guard`，若 Guard 缺失或未通过，应直接失败，不生成复盘产物。

## 标准交付

- `08_复盘报告.md`
- `08_L1回写建议.md`
- `postmortem_manifest.json`

`postmortem_manifest.json` 必须包含 `publish_guard` 摘要，至少包含 `present`、`status`、`passed`、`report_json`、`report_markdown`、`checked_at`。

## 现阶段限制

- 当前可用作原型或半自动复盘层
- 真实平台数据闭环仍需继续增强
