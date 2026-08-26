---
name: dasheng-daily-draft
description: Use when running Stage 3 Draft from approved Brief topics and producing Reasoning Sheets, standard drafts, and draft quality gates.
version: 1.0.0
stage: draft
runner: python
---

# dasheng-daily-draft

## 定位

这是 Newma 工作流第三环节 Draft 的正式单阶段 skill。

职责：
- 读取 Brief Gate 通过的 `selected_topics.json`
- 读取完整 `topic_cards.json`
- 为每个选题生成 `Reasoning Sheet`
- 生成可审核的事实与分析底稿
- 同步生成可编辑、自包含、离线可用的 HTML 草稿
- 输出文字洁癖 / 质量门禁，供编辑审核

不负责：
- 微信排版
- 公众号渠道稿、公众号封面和渠道标题包装
- Transwrite 的口播视频、播客或多平台变体
- 账号登录、草稿上传、平台发布和链接回收
- 发布

## canonical 输入

- `selected_topics.json`：状态必须为 `approved`，且 `selected_topics` 非空
- `topic_cards.json`：必须包含对应 `topic_id` 的完整题卡

## canonical 输出

- `03_ReasoningSheet_<topic>.md`
- `03_ReasoningSheet_<topic>.json`
- `03_标准初稿_<topic>.md`
- `03_HTML草稿_<topic>.html`
- `03_质量门禁_<topic>.json`
- `03_初稿_报告.md`
- `selected_topics_for_draft.json`
- `final_structure_snapshot.json`
- `final_structure_snapshot.template.json`
- `draft_quality_gate.json`
- `draft_manifest.json`
- `03_IllustrationIntents_<topic>.json`

## 执行方式

```bash
python3 scripts/run_mainline_stage.py draft --run-id <run_id>
```

或直接执行：

```bash
python3 scripts/build_stage3_draft.py \
  ~/Desktop/自媒体创作/<run_id>/02_选题/selected_topics.json \
  ~/Desktop/自媒体创作/<run_id>/02_选题/topic_cards.json \
  --run-id <run_id>
```

## Qoder 执行边界

- Qoder 只负责当前选题目录内的研究、取数、图表、正文配图、Reasoning Sheet、标准初稿、离线 HTML、事实核查和质量门禁。
- 多选题可以从同一写作引擎上下文分叉独立 Qoder 会话，但每个会话只能写自己的 `topic_id` 目录；阶段总 manifest 由主控统一生成。
- Qoder 的 `draft_result.json` 必须写明 `stage=draft`、`next_stage=transwrite`、`next_stage_authorized=false`。
- Qoder 不得调用公众号、社交媒体或账号管理工具，不得生成微信排版稿、封面和发布文案，也不得进入 Transwrite 或 Publish。
- 所有运行产物必须写入 `${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/<run_id>/03_初稿/`；不得写入项目仓库、skill 目录或临时工作目录。

## 质量门禁

`draft_quality_gate.json` 会记录：

- 中文字数
- 一级标题数量
- 是否存在引用与待补源小节
- AI 味高频句式命中

硬性篇幅：每个选题中文正文不少于 **10000 个汉字**，可以更多，不能更少。

当前重点检查并提示少用：

- `不是……而是……`
- `这意味着`
- `本质上`
- `不可否认`
- `综上所述`

门禁状态为 `warning` 不阻塞编辑审核，但会写入 `draft_manifest.json.quality_gate`。

## HTML 草稿规则

- HTML 与 Markdown 同步生成；HTML 负责编辑预览和微信公众号导入前检查，Markdown 负责事实源稿。
- HTML 必须自包含：CSS/JS 内联，离线可打开，不允许 CDN 或本地引用。
- Chart.js 图表必须内联 v4.4.4 UMD；自写图表初始化必须 `DOMContentLoaded`、`typeof Chart` 降级、`responsive:false`、显式 canvas 宽高、`deepMerge` 合并配置，log 坐标写 `type:'logarithmic'`。
- 表格标签类放 `<td>` 内 `<span>`，根内容区 `contenteditable="true"`，必须支持编辑/预览切换、全选、保存下载。
- 图表、配图、数据来源必须绑定 `claim_id`；未核验数据只能留下待补槽，不能生成假走势或假来源。
- 配图可由运行 Agent 调用 image 工具生成，压缩后 base64 嵌入；发布前 canvas 图表建议截图替换成静态图。
- 对正文执行比喻/举例语义扫描：明确例子、类比、拟人和抽象机制优先进入 `dasheng-lemon-illustrations`。生成的柠檬漫画必须紧跟对应段落，并记录 intent id、原文句子、核心意思和角色动作。
- 关键词命中不等于必须生成。只有漫画能提高理解、形成认知锚点时才保留；真实证据场景仍使用图表、网页、表格和文档。

## 硬规则

- Draft 只写分析底稿，不做 DNA 改写、文风修饰或平台化包装
- 每题必须充分展开事实、数据、概念口径、机制、正反论证、反驳、情景推演和结论
- 每题中文正文少于 10000 个汉字时不得通过质量门禁
- 必须继承 Brief 的来源内容、争议点、观点和内容单元
- 不得把多个选题混成一篇
- 不得编造不存在的来源、数据和机构表态
- `final_structure_snapshot.json` 确认后进入 transwrite
- 数据、图表、配图和 HTML 嵌入必须由 Draft 内完成
- 必需的柠檬漫画未生成并嵌入时，Draft 资产门禁不得标记 complete
- 多版本改写只作为按需工具，不再是主链阶段
