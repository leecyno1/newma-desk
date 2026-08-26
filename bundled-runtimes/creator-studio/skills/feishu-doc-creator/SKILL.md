---
name: feishu-doc-creator
description: Use when creating or updating Feishu docs from markdown in this repo and you need the known-safe block conversion flow instead of writing docx blocks naively.
---

# Feishu Doc Creator

## 目标

用本仓库已经验证过的方式，把 markdown 文档可靠写入飞书 docx 文档。

## 本地实现

- 脚本：`${DASHENG_PROJECT_ROOT:-.}/scripts/send_feishu_report.py`

## 核心规则

- 先走 markdown convert API
- 过滤不支持创建的 block 类型：
  - `31` Table
  - `32` TableCell
- 按 `first_level_block_ids` 排序后再写入
- 表格型内容若无法通过 API 直写，必须优雅降级而不是卡死

## 何时使用

- 阶段报告要同步飞书
- Intake / Brief / Draft / Publish 文档要批量推送飞书
- 需要避免空白文档、invalid param、block 顺序错乱
