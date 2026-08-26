---
name: dasheng-daily-intake
description: Use when running the canonical Newma intake stage for the current day and producing real-title, real-link source radar outputs for Brief handoff.
---

# dasheng-daily-intake

## 定位

这是 **Newma 工作流的 Intake 单环节 Skill**，但执行口径以本地 canonical Stage 1 为准。

它吸收并替代历史上 `dasheng-caiji` 的采集职责，不再并行维护两套采集定义。

职责：
- 执行当天 canonical intake 采集
- 生成真实标题、真实链接的报告 / 底稿
- 输出交给 Brief 的标准 JSON 接口
- 如当前链路要求，再交给飞书同步层做共享文档与群通知

不负责：
- 聚类
- Brief
- 大纲
- 初稿
- 强化版

---

## 数据源

默认执行模式为 `DASHENG_INTAKE_MODE=simple`，数据源采用 **本地 0913 / 8001 优先 + 公开免登录热点捕捉**。旧的 5173 / reports / 8000 远程链路只作为显式 legacy 回滚口，不再作为日常默认采集方式。

### 1）本地 0913 / 8001 内容中心

用途：通过 `${DASHENG_0913_ROOT:-../0913}` 提供的本地聚合 API，优先读取微信聊天记录、公众号文章、自媒体文章和本地新闻流。

固定要求：
- 健康检查：`GET /api/health`
- 聊天会话：`GET /api/chats`
- 微信聊天记录：`GET /api/messages?direction=in&fast=true&include_meta=true&include_mp_messages=false`
- 公众号文章：`GET /api/mp/articles?filter_spam=true`
- 自媒体文章：`GET /api/media/items?filter_noise=true`
- 新闻流：`GET /api/newsfeed/items`
- 以上三类核心内容源必须每次都发起采集；某路不可用时可降级继续，但必须在 `channel_tasks.json` 和 `intake_manifest.json` 记录错误，不得静默跳过
- 本机 `127.0.0.1` 请求必须绕过系统 HTTP/HTTPS 代理，避免误走 `7890` 导致超时
- 本地消息必须生成可追溯锚点：`dasheng-local://messages/<id>`
- 公众号文章无原始 URL 时必须生成：`dasheng-local://mp/<id>`
- 自媒体内容无原始 URL 时必须生成：`dasheng-local://media/<id>`
- 本地新闻没有原始 URL 时，必须生成：`dasheng-local://news/<id>`
- 每条进入标准化池的样本都要保留标题、来源、摘要、时间和原始 payload

原始落盘：
- `raw/local_messages.json`
- `raw/local_mp_articles.json`
- `raw/local_media_items.json`
- `raw/local_newsfeed.json`

可调参数：
- `DASHENG_LOCAL_CHAT_INTAKE_BASE`：默认 `http://127.0.0.1:8001`
- `DASHENG_LOCAL_CHAT_LIMIT`：默认 `120`
- `DASHENG_LOCAL_MP_LIMIT`：默认 `200`
- `DASHENG_LOCAL_MEDIA_LIMIT`：默认 `300`

### 2）公开热点捕捉模块

用途：作为独立 `hotspot_radar` 模块捕捉公开新闻与热榜动态。本模块不硬过滤新闻内容，只做来源健康、热度、宏观/时政/市场倾向评分，供 intake 和其它 Agent 复用。

独立执行：
- `python3 scripts/run_hotspot_radar.py`
- 项目 skill：`skills/dasheng-hotspot-radar`

输出：
- `hotspot_radar.json`
- `hotspot_radar_manifest.json`
- `raw/hotspot_radar.json`

### 3）公开新闻池

固定要求：
- 数据源至少包括：`同花顺`、`华尔街见闻`、`彭博市场`
- 每条必须保留 `heat_score`、`tone`、`category`、`heat_cluster`
- 输出渠道为 `public_news`，并写入 `raw/public_news_fallback_items.json`
- `AI热点` 可从该新闻池派生，但不能替代原始 `public_news` 全量记录

### 4）合并新闻源

用途：把 0913 的本地新闻流与公开财经新闻池合并成单一 `news` 渠道，避免同一条快讯在 Intake 中重复入库。

固定要求：
- 原始 `raw/local_newsfeed.json` 和 `raw/public_news_fallback_items.json` 仍分别保留，用于源健康追溯
- 标准化入库前必须按 `source_id + item_id`、去参数 URL、规范化标题和近似标题合并
- 合并后优先保留原始 HTTP 链接、更高热度和更完整摘要的代表条目
- 每个合并条目必须保留 `merged_sources`、`merged_count` 和各上游链接
- 合并产物写入 `raw/merged_news_items.json`
- `channel_top10.json` 只输出一个“合并新闻源” Top10，不再分别输出本地新闻和公开新闻重复榜单

### 5）公开热榜池

用途：当本地 8001 不足或不可用时，补充不依赖 API key、不依赖登录态的公开热点池。

固定要求：
- RSS 源至少包括：`Reddit RSS`、`Hacker News RSS`、`新浪财经 RSS`、`WSJ RSS`
- 热榜源至少包括：`微博热搜`、`知乎热榜`、`抖音热榜`、`虎扑热榜`、`头条热榜`
- 所有公开源必须写入 `raw/public_fallback_items.json`
- 每条都要带原链接

### 6）AI 热点汇总

用途：从微信聊天、公众号、自媒体、本地新闻、公开新闻与公开热榜中派生 AI / Agent / Skill / Workflow 方向的高时效证据池。

固定要求：
- 固定输出最多 `10` 条 `AI热点` 汇总
- 这些样本进入 intake 分析池与 brief handoff 时使用更高权重
- 但不替代全量原始采集底稿

### 7）Legacy 远程链路

用途：仅在需要回滚或对比旧采集结果时显式启用。

固定要求：
- 启用方式：`DASHENG_INTAKE_MODE=legacy python3 scripts/run_stage1_intake.py`
- legacy 保留 5173 / reports / 8000 public wechat / B站 AI 聚合逻辑
- legacy 异常不能影响 simple 默认路径

---

## Intake 必须交付的内容

1. `notes/01_内容采集_报告.md`
2. `notes/01_内容采集_底稿.md`
3. `raw/intake_records.json`
4. `raw/local_messages.json`
5. `raw/local_mp_articles.json`
6. `raw/local_media_items.json`
7. `ai_hot_topics.json`
8. `raw/merged_news_items.json`
9. `channel_top10.json`
10. `event_clusters.json`
11. `source_quality_report.json`
12. `channel_tasks.json`
13. `brief_input.json`
14. `intake_manifest.json`

---

## 执行顺序

1. 检查本地 0913 / 8001 健康状态
2. 分别采集微信聊天 `/api/messages`、公众号 `/api/mp/articles`、自媒体 `/api/media/items`和新闻流 `/api/newsfeed/items`
3. 无论本地是否成功，都执行 `hotspot_radar` 公开热点捕捉
4. 把 `local_news` 与 `public_news` 合并去重为单一 `news` 渠道
5. 合并 `local_chat`、`wechat`、`content_research`、`news`、`public_hot`
6. 从全部本地内容源、合并新闻源和公开热榜中派生 `AI热点` Top10
7. 对各渠道样本做真实标题清洗、去重、渠道内热度评级
8. 生成渠道 Top10、底稿全量清单、重复/噪音池与 Brief handoff
9. 落盘 canonical manifest 与 handoff 文件
10. 如启用飞书同步，再把 canonical 产物映射到飞书

---

## 硬规则

- **截图全部取消**，不作为 intake 正式交付物
- **报告与底稿必须只出现真实抓取标题**
- **以上内容都必须带原始链接**
- **默认模式不得主动依赖 5173 / reports / 8000 远程接口**
- **默认模式必须尝试采集微信聊天记录、公众号文章和自媒体文章**
- **0913 三类内容源不得用空任务占位；必须真实请求并记录状态**
- **本地新闻与公开财经新闻必须合并去重后才进入正式 Intake 池**
- **legacy 远程接口只能通过 `DASHENG_INTAKE_MODE=legacy` 显式启用**
- **每个渠道都要单独产出 Top10；不足 10 条如实展示**
- **`AI热点` 必须单列产出 Top10，并进入 `brief_input.json.ai_hot_candidates`**
- **正式执行脚本是**：`../../scripts/run_stage1_intake.py`

---

一句话版：

**daily intake = 跑本地 canonical Stage 1，生成真实标题 / 真实链接的 intake 雷达，并把标准交接文件交给 Brief。**
