# 阶段地图

## 0.6 Video Style Training（可选）

- 目标：从用户提供的大量样板视频中学习可复用的视频风格 DNA。
- 常见输入：博主/栏目样板视频目录、`style_id`、博主名、平台名。
- 交付：`training_manifest.json`、`per_video/*/analysis.json`、`style_profile.json`、`style_profile.md`。
- 默认输出：`~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/`。
- 备注：这是独立可选资产，不改变主链顺序；后续 `talking_head_video`、`explainer_html_video`、`vox_explainer_video`、`digital_human_video`、`commercial_promo_video` 和电影短剧规划只引用 `style_profile.json`。
- 禁止：把样板视频、压缩上传副本、训练报告或渲染预览写入项目根目录或 `skills/`。

## 0.7 Video Self Learning（可选、定时）

- 目标：每天增量发现目标博主的新视频，按视频 ID 去重后学习导演、设计、分镜、转场、制作、图表和审美规律。
- 入口：`python3 scripts/run_mainline_stage.py video-self-learn`。
- 默认时间：每天 `22:00 Asia/Shanghai`。
- 交付：逐视频 `analysis.json / analysis.md`、博主滚动候选画像、导演候选手册、审美手册、技术栈复现映射和进化日志。
- 默认输出：`~/Desktop/自媒体创作/00_范式学习/视频训练/每日博主自学习/`。
- 技术栈：`yt-dlp -> claude-real-video -> Codex Agent -> knowledge base`。
- 约束：技术栈判断只能写为复现建议；自动规则必须保持候选状态，不能覆盖已批准 DNA。

## 1. Intake

- 目标：采集原始来源，保留链接，形成当天底稿与报告。
- 常见输入：端口数据、网页、公众号文章、外部热点。
- 交付：`01_内容采集_底稿.md`、`01_内容采集_报告.md`、`intake_manifest.json`
- 默认采集规模：X、微博各 `100` 条，其它平台各 `50` 条。
- 报告默认只做话题频次 `Top10` 统计，不做主观初筛。

## 2. Brief

- 目标：基于 canonical intake 证据池生成 8-10 个 AI-only 独立题卡。
- 常见输入：`brief_input.json`、`channel_top10.json`、`event_clusters.json`、`raw/intake_records.json`
- 交付：`02_编辑Brief库.md`、`02_研究Brief库.md`、`02_编辑Brief_报告.md`、`topic_cards.json`、`brief_manifest.json`
- 结构要求：每题包含标题、判断、核心命题、证据缺口、推荐数据角度、推荐视觉角度、关键来源。
- 人工指定选题必须强制入池；同一逻辑链超过半数则阶段失败。

## 3. Draft

- 目标：形成标准初稿，默认是 `4000-8000` 字长文底稿，并供编辑直接改造成终稿。
- 常见输入：确认题目、核心判断、骨架、来源包。
- 默认输出：`${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/<run_id>/03_初稿/`。
- 交付：`03_标准初稿_<topic>.md`、`03_初稿_报告.md`、`draft_manifest.json`
- 结构规则：优先 `开篇 + 三段论 + 结尾` 或 `开篇 + 4 章 + 结尾`，一级标题不得超过 `4` 个。
- 内容规则：只写标准事实稿，不注入账号 DNA 和平台腔；主动补数据、表格和权威来源。
- 漫画规则：扫描原文比喻、举例、类比、拟人和抽象机制，输出 `03_IllustrationIntents_<topic>.json`，调用 `dasheng-lemon-illustrations` 生成柠檬人漫画并嵌入对应段落。
- 边界：只完成内容、数据和正文视觉资产；不生成公众号渠道终稿/封面，不执行 Transwrite，不登录账号、不上传或发布。完成时只标记下一候选阶段为 Transwrite，且默认未授权。

## 4. Transwrite

- 目标：把确认后的 Draft 转成公众号文章、普通无头、VOX 调查解释、真人口播和播客生产包。
- 常见输入：`draft_manifest.json`、`final_structure_snapshot.json`、`transwrite_decision.json`。
- 三类通路：
  - 公众号：Style DNA / humanize / 封面 / 微信 HTML 转写
  - 视频：普通无头、VOX 调查解释、真人口播使用独立 Lane；共享 Remotion 主时间轴、证据门禁和最终 QC
  - 播客：Coze / MiniMax API 请求包
- 交付：`04_转写计划.md`、`transwrite_manifest.json`、每题 lane manifest。
- 备注：不补事实、不重做图表；外部 API/素材缺失必须显式标记。
- 漫画继承：公众号和视频共用 Draft illustration intents；公众号保留段后漫画，视频导演改造成全屏或透明叠加的 setup-action-result 分镜。

## 5. Publish

- 目标：验收转写包，生成发布包，执行或半执行平台分发，并回收链接。
- 常见输入：`transwrite_manifest.json`、`publish_decision.json`。
- 平台执行矩阵：
  - 公众号：`baoyu-post-to-wechat` / `wechat-multi-publisher` / `md2wechat`
  - 微博：`baoyu-post-to-weibo`
  - X：`baoyu-post-to-x`
  - 小红书：`social-auto-upload-bridge` / API-first / MCP / 持久化浏览器 fallback
  - 抖音：`social-auto-upload-bridge` / `douyin-upload-skill` / 持久化浏览器 fallback
  - B站：`social-auto-upload-bridge` / `bilibili-upload-bridge` / `biliup-rs` / 人工投稿包
  - 视频号：`social-auto-upload-bridge` / 持久化浏览器 / 人工投稿包
  - 播客：人工上传或音频平台 API
  - 验真：`record_publish_result.py` 回填 + `publish_verification_report.json` + `publish_guard.py`
- 交付：`07_发布包.md`、`07_发布计划.md`、`channel_execution_manifest.json`、`publish_verification_report.json`、`publish_guard_report.json/md`、`publish_manifest.json`
- 备注：平台分发动作并入 `publish`，但内容生产不在 Publish 内完成。

## 6. Postmortem

- 目标：复盘效果，输出继续/停止/测试建议，并回写知识库。
- 常见输入：`publish_manifest.json`、Publish Guard 状态、发布链接、平台数据、人工反馈。
- 口径：按 `topic_id` 聚合，不按渠道包计数；只有 `published` + `verification_status=verified` + 正式 URL 才算已发布。
- 交付：`08_复盘报告.md`、`08_L1回写建议.md`、`postmortem_manifest.json`

## 按需工具：Rewrite

- 独立素材环节已删除；图表、封面、图片、数据和 HTML 嵌入都在 Draft 内完成。
- `rewrite-variants`：只在需要额外多版本稿时调用；常规渠道表达交给 Transwrite 处理。
