# 会话摘要（微信聊天记录分析项目）

## 基本情况
- 负责人：用户，协同开发：Codex 助手
- 项目：微信聊天记录分析系统（FastAPI + SQLite + 前端 HTML）
- 会话时间：2025-09-18 ～ 2025-09-20

## 关键事件与修复
1. **后端同步/图片访问**
   - 修复 `/api/sync/chatlog/full` 使用 `chatlog_client` 解析 plain text JSON 混合返回
   - 图片预览 URL 转换问题：构造 `/image/<id>`，保留 `/data/...` 目录结构

2. **AI 分析模块**
   - 引入全量消息合并：分析前将 `messagesDataJson` 与当前表格数据合并、归一化
   - 增加倒计时提示、缺失 API Key 的兜底文案
   - `performAIAnalysis` 优先调用 `/api/ai/summary`，失败回退 `/api/ai/summary-local`

3. **前端数据展示**
   - 市场观点：按六大类（宏观政策/行业板块/公司基本面/投资策略/市场情绪/其他观点）聚合，输出关键词云、情绪分布、2000 字以内摘要，过滤通用词
   - 会议路演：表格显示开始时间、平台、会议号、发送人（可跳转消息）、主题（≤10字）
   - 反驳观点：检测正负情绪构成的对立主题，展示双方摘要与建议追问
   - 高评分联系人：Top10 联系人中选 20 条高价值摘要（排除垃圾消息）

4. **发送管理 / n8n 接入**
   - AI 回复生成改为调用 `/api/ai/suggest-replies`（失败时本地兜底）
   - 发送改为 `/api/send`，校验 `chat_id`

5. **拉取功能**
   - 当后端只返回少量数据时自动回退 chatlog 服务拉取，确保按钮拉取大量消息

---

## 2025-09-20 增量更新（AI 总结重构 + 小模型落地）

- 流程重构（只看外部消息）
  - 前后端统一过滤 `direction='out'` 我方消息；`/api/messages` 新增 `direction` 参数并兼容 `external`。
  - 垃圾阈值提升：≤15 个汉字或 ≤30 字符的短消息被剔除（前后端一致）。

- 提示词与模块化
  - 将“市场观点/会议路演/反驳观点/高评分联系人”四模块的系统/用户提示词拆分，可在功能设置独立配置；取消词频/人数等硬约束，改为大模型通读后自主归纳，输出语义化 HTML。

- 小模型（Qwen3‑8B）接入与分工
  - 新增 `tool_model` 配置项；小模型负责单条消息关键词、9–12位会议号（含平台类型）、30字摘要与语气抽取；大模型（30B）负责四大板块写作。
  - 数据库新增 `messages.derived JSON` 持久化抽取结果：`keywords/meeting_number/summary/tone/key_info`。
  - `/api/messages` 在返回前对近7天消息做增量抽取并写入 `derived`；超过7天自动清空该字段，避免历史累积和 token 浪费。

- 前端体验
  - “关键信息”列优先展示 `derived.key_info`（会议平台+会议号/关键词/摘要），缺失时回退本地 `extractKeyInfo()`。
  - `messagesDataJson` 写入即完成“外部+去垃圾”的过滤，AI 分析只消费有效消息。
  - 功能设置页新增“小模型”输入框，支持读写 `/api/ai/config` 的 `tool_model`。

- 可靠性
  - `/api/ai/summary-local` 增强异常保护，失败时返回 HTML 提示而非 500；`siliconflow_chat()` 对 HTTP 错误附带响应片段，便于排查。

## 使用提示
- 在“功能设置”填入 SiliconFlow API Key，确认主/小模型；
- 打开“消息列表”后会自动加载近7天数据并生成关键信息，再点击“开始AI分析”；
- 若面板仍为空，查看卡片错误文案（通常为 LLM 请求异常或 Key 缺失）。

## 当前状态
- 前端在 `wechat_ui_0811.html` 中集成上述逻辑；AI 分析、会议表、反驳、联系人摘要均可用
- `docs/session-summary.md` 保存本会话压缩记录，供后续参考

## 待注意事项
- 仍需在生产环境配置 `SILICONFLOW_API_KEY` 才能运行本地模型
- 若希望自动持久化 chatlog 数据，可考虑增加同步任务或定期调用 `/api/sync/chatlog/full`

---

## 2025-09-24 更新（消息列表统一口径 + 小模型派生增强 + 设置项）

- 列表统一口径
  - 新增 `GET /api/messages/effective`：后端统一执行“只看外部/去系统提示/去短消息”过滤，前端不再自行过滤，避免不一致；支持 `period=1day|3days|1week|1month`。
  - `/api/messages/export` 保持与列表相同的取数逻辑，便于核对。

- 小模型派生链路
  - 修复链接/卡片类消息（type=49）正文为空导致无法派生的问题：同步时写入 `Message.meta.contents`；派生时若 `content_text` 为空，从 `meta.contents.title/desc/url` 组装文本供小模型摘要。
  - 新增派生进度：`POST /api/messages/derive?progress_key=...` + `GET /api/messages/derive/progress?key=...`；前端显示进度并在完成后自动刷新列表。
  - UI 侧“关键信息”列：去除 `ai:` 前缀后以黑色显示；`fallback:` 以灰色斜体显示；优先使用 `derived.key_info`（平台简称+会议号 | 摘要）。

- AI 总结格式对齐
  - 会议路演：只显示“时间(月-日 时:分)”与“形式(简称)”，删除“信心”；主题直接使用 `key_info/summary`，不省略，自动换行。
  - 反驳观点：仅“主观点 | 冲突观点”两列表格，禁止臆造；文末新增“怀疑与结论”。
  - 工具栏：将“运行分析/导出/高级选项”与时间标签同一行顶端对齐。

- 设置项持久化（`data/ai_config.json`）
  - `message_filters`：external_only / exclude_short / exclude_system。
  - `derive_defaults`：batch_size / concurrency / temperature / force。
  - 前端“功能设置”面板可读写以上配置，保存后作为后端默认值生效。

- 运维与修复
  - 修复数个因缩进/时间解析导致的 500/启动失败问题；为 SQLite 同步写入增加重试，缓解 `database is locked`；
  - 拉取流程改为“先渲染原文→后台派生→完成后刷新”，避免首屏空白。

### 验收建议
1) 功能设置：保存派生默认与过滤默认；
2) 拉取近7天(后端) → 消息列表“拉取1周”，观察进度条与“关键信息”黑色补齐；
3) 测试主模型 → AI 总结“运行分析”，确认会议/反驳表格按规范输出。

---

## 2025-09-24（晚）增补（列表进度条 + 行内刷新 + 链接内容派生）

- 体验与可见性
  - 消息列表新增派生进度条，位置在“拉取”按钮与“时间范围”同一行；派生时显示，完成后自动隐藏。
  - 派生完成后“就地刷新”行（仅更新关键信息/分类/情绪/会议号），不再整表重建，减少闪动。
  - 关键信息列去除 `ai:` 前缀后以黑色展示；`fallback:` 以灰色斜体展示（便于一眼区分来源）。

- 链接/卡片内容派生修复
  - chatlog 中 `type=49` 等消息正文为空但在 `contents.title/desc/url` 携带真实文本；
  - 同步：把 `contents` 持久化到 `Message.meta.contents`；派生：当 `content_text` 为空时从 `meta.contents` 组装文本参与小模型摘要。

- 进度与接口
  - 触发派生：`POST /api/messages/derive?progress_key=<k>`；
  - 轮询进度：`GET /api/messages/derive/progress?key=<k>` → `{status, done, total}`；前端同时在“AI 总结页”和“消息列表”显示进度条。
  - 行内刷新：`GET /api/messages/effective` 拉取一页后按 `id` 映射，仅更新变更行的关键信息/分类/情绪。

- 设置项（延伸）
  - `derive_defaults` 与 `message_filters` 均可在“功能设置”面板读写（派生批大小/并发/温度/强制；只看外部/去短/去系统）。
  - 保存后写入 `data/ai_config.json`，并作为后端默认值应用于 `/api/messages/derive` 与 `/api/messages/effective`。

- AI 总结（确认要求）
  - 会议路演：时间=会议开始时间（`09-24 19:30`），形式=简称（腾/进/飞/ZM/TM/钉/电），删除“信心”；主题=`key_info/summary`，不省略、自动换行。
  - 反驳观点：仅“主观点 | 冲突观点”两列表格，末尾“怀疑与结论”；严格事实导向，禁止臆造。
  - 注意：需“主模型”连通（功能设置 → 测试主模型）后点击“运行分析”方可生成四模块内容。

### 现状与验证
- 通过 `/api/messages/effective` 可见 `derived.summary`/`derived.key_info` 已为 `tool` 产出（示例：含会议号与平台简称；摘要前缀为 `ai:`，前端已去前缀渲染）。
- 若仍见大量 `fallback:`，建议把“派生批大小=10/并发=6”以提高稳定性；或在网络较闲时再执行“拉取近N天(后端)”后重跑派生。

### 后续可选
- 将“仅显示小模型产出（隐藏 fallback）”做成列表级开关；
- 派生进度显示百分比与时长估计；
- 将 AI 总结的模块/并发/温度/强制快照等高级选项也持久化到配置文件（多人环境统一）。


## 2025-09-21 ～ 2025-09-23 对话与关键变更（第二阶段）

本阶段聚焦四件事：消息列表可用性、AI 总结可读性、小模型派生落地（用“ai:”前缀验真）、以及可测试的 API 配置/联通模块。

### 1) 消息列表（Message List）
- 去掉“会议”单独列，改为在“摘要”里提示（后续确认需求，不再需要会议按钮，已移除按钮，仅保留文本）。
- 恢复与固定“原文”列内容，点击可展开全文；压缩“类型/分类/情绪”列宽，把更多空间让给“摘要”。
- 在“拉取一周”右侧显示本次拉取的真实时间范围（min~max）。
- 过滤系统提示类消息（邀请入群/撤回/朋友验证/红包等）。
- 派生链路调整为“先 /api/messages/derive → 再拉取”，保证摘要/关键词先生成再渲染列表。
- 摘要来源标识：
  - 小模型产出强制以 `ai: ` 前缀（后端强制）；
  - 兜底摘要写为 `fallback: ...`，前端以灰色斜体显示，便于肉眼识别。

### 2) AI 总结（四大模块）
- 页头新增抬头条：显示报告实际时间范围、样本数与生成时间；把“近N天”标签、运行按钮与读秒状态合并到抬头同一行。
- 分模块渲染改进：
  - 市场观点：同时生成 HTML 与 Markdown，前端优先渲染 HTML，分节清晰；
  - 会议路演信息：表格列（时间/平台/会议号/主讲人/要点/信心）修复；
  - 反驳观点：新增“议题卡片”可展开/收起，解决摘要不完整问题；
  - 高评分联系人：阈值从 ≥85 降至 ≥70 且近3天活跃，避免空白。
- 可靠性：renderMarkdown 兼容 HTML/Markdown，均能安全渲染；失败时返回兜底文本而非空白。

### 3) 小模型派生（工具模型）
- 新增与强化：
  - `ensure_message_features()` 强制把小模型 `summary` 加前缀 `ai: `，并在 `derived.summary_origin=tool/fallback` 标记来源；
  - 若工具模型调用失败/缺失，使用本地兜底关键词/摘要/会议号提取，摘要写为 `fallback: ...`；
  - `/api/messages/derive` 支持按 period（1day/3days/1week/1month）批量派生。
- 前端：
  - 摘要列直接显示 derived.summary；当来源为 fallback/不以 `ai:` 开头时以灰斜体显示；
  - 彻底移除“关键词徽标”相关功能（统计/样式/交互全部删除）。

### 4) API 配置与联通测试（功能设置）
- 后端路由：
  - `GET /api/ai/test-main`：测试主模型，返回 {status, output|error, config}；
  - `GET /api/ai/test-tool`：测试小模型，返回 {status, output|error, config}；
  - `POST /api/ai/test-tool-summary`：输入一段文本，直接返回小模型输出（raw 与 parsed），即使 JSON 解析失败也返回 200，便于肉眼核对；
  - 修复了先前未导入 `siliconflow_tool_chat` 导致 NameError 的问题。
- 前端面板：
  - 新增主/小模型“状态指示条”（待测/成功/失败），显示 api_url / model(tool_model) / has_key 与错误详情；
  - “小模型摘要测试”可输入任意文本，查看小模型原始 JSON 输出是否含 `ai:` 前缀。
- 配置持久化：读写 `data/ai_config.json`；刷新后 key 以掩码显示“*** 已配置 ***”。

### 5) Token 控制与模块预过滤（大模型摘要）
- 在 `/api/ai/summary` 内对各模块做“相关子集预筛选”与“摘要压缩”，避免 token 暴涨；超大文本时切分分块汇总再合并。
- 采用 HTML/Markdown 双通路：若模型返回 HTML，直接渲染；否则渲染 Markdown；始终保留本地兜底。

### 6) 运维与可用性
- 修复一次因 try 块未闭合导致的语法错误（重启后 8001 无法访问）；
- 修复 datetime aware/naive 比较报错；
- scripts/manage.sh 增强：
  - 增加 `NO_INSTALL=1` 跳过依赖安装（网络受限/离线调试更稳）；
  - 新增 `dev`（`uvicorn --reload`）命令，开发时热重载更快。
- 约定：今后每次修改后默认执行重启（或 dev 热重载），避免你看不到调试结果。

### 7) 已知结论
- 当列表摘要以 `ai:` 开头时，确认来自小模型；`fallback:` 为兜底。
- 若“测试小模型/主模型”状态失败，请依据返回的 `error` 与 `config` 定位：常见为 401（鉴权）、404（模型名）、429（频控）与 5xx（服务端）。

> 注：第二阶段大量涉及 UI 与后端逻辑耦合的细节，具体实现位于 `wechat_ui_0811.html` 与 `app/routers/ai.py`、`app/services/ai_tools.py`、`app/services/llm_client.py`。

---

## 2025-10-20 调整（去除 key_info + 两段式摘要覆盖）

- 字段与语义
  - 移除 `derived.key_info` 字段，统一以 `derived.summary` 展示摘要；来源标识为 `derived.summary_origin in {"fallback","tool"}`。
  - 小模型产出强制以 `ai: ` 前缀；兜底摘要以 `fallback: ` 前缀，便于排查来源；UI 展示时建议去前缀，但使用配色区分。

- 两段式流水线
  1) 兜底快刷：`populate_fallback_derived()` 立即为有效消息写入短摘要（灰色），不依赖外部接口；
  2) AI 覆盖：`ensure_message_features()` 在小模型成功返回后覆盖写入（橘色），`summary_origin` 置为 `tool`。不再做“填空式合并”。

- 前端显示建议
  - “摘要/关键信息”列绑定 `derived.summary`；根据 `derived.summary_origin` 应用样式：`tool → .summary-text.ai`（橘色），`fallback → .summary-text.fallback`（灰色斜体）。
  - 展示时去掉 `ai:` 与 `fallback:` 前缀，仅保留配色差异；鼠标悬停可显示完整文本与原文片段。

- 提示词与模块
  - 工具模型提示已去除 key_info 字段要求；会议模块“主题列”直接取 `summary`（去前缀，≤10字）。

- 兼容与迁移
  - 旧数据中若存在 `derived.key_info`，前端应忽略该字段；无需 DB 迁移。
  - 测试数据/样例应改为使用 `derived.summary` 与 `summary_origin`。

---

## 2025-09-25 更新（列表可读性 + 拉取机制 + 黑名单 + 发送集成）

- 路由统一
  - `/` 与 `/static/index.html` 指向同一静态页；`/ui/legacy` 永久 404（避免旧版入口混淆）。

- 原文列与列表列序
  - “原文”移到“关键信息”左侧，清理中间空白列；类型/分类/情绪固定 40px，发送人 80px。
  - 原文列修复：保留图片/视频/链接徽标的同时渲染文本片段；`dataset.fullContent` 优先文本，缺失时回退 URL；绑定 `showFullContent()`。
  - 链接纯 URL 场景：片段为空时显示 hostname；appmsg(xml) 解析 url/title 并补齐全文数据。
  - 短链接不过度过滤：`isShortMessageText()` 对 http/https 直接视为有效。

- 筛选栏与可用性
  - 筛选条 `position: sticky` 冻结在顶部；“关键信息”列 2 行截断，点击展开/收起；支持键盘上下选择与 Enter/Space 弹出气泡详情。

- 拉取机制（改为手动直连 chatlog）
  - 关闭自动拉取/自动派生/自动二次刷新；仅保留三个手动按钮（今日/3天/1周）。
  - 按 talker + `limit=500/offset` 逐日抓取 chatlog 最新消息并渲染到表格；完成后在后台触发 `/api/sync/chatlog/full?days=N` 持久化（不阻塞 UI）。
  - 状态提示与按钮状态：拉取中“从chatlog拉取近N天…”，完成“已更新”，按钮始终在 finally 中恢复。
  - 列表接口时间对齐：后端把前端 ISO 时间统一转为“本地 naive 时间”，避免最近小时缺失。

- 顶部进度与统计
  - 顶部细进度条用于 `/api/messages/derive` 进度轮询（保留给手动派生使用）。
  - 右上角统计改为动态：总消息、联系人数、最后同步时间、市场观点数、高重要度数。

- 黑/白名单（前后端一致）
  - API：`GET /api/filters`、`POST /api/filters/blacklist`、`POST /api/filters/whitelist`（使用 SyncState JSON 持久化）。
  - 同步层强过滤：白名单优先、其后黑名单；被黑名单命中的消息不再写入 DB。
  - 联系人管理：操作列新增“拉黑/删除”，并与后端同步；评分加减、重置维持。

- 发送管理与 WeChatPadPro 集成
  - 配置：`.env` 新增 `WECHATPAD_HTTP_BASE`（例：`http://60.205.58.39:1238`）与可选 `WECHATPAD_TEXT_PATH`（默认 `/api/v1/message/sendText`）。
  - 后端：`POST /api/send/wechatpad` 批量发送文本；客户端 `app/services/wechatpad_client.py`。
  - 前端：发送管理新增单条“WX”按钮与“群发到WeChatPad”。

- 代码定位（主要变更）
  - 前端：`static/index.html`（列顺序/原文渲染/冻结筛选/手动拉取按钮/进度条/黑名单与发送 UI）。
  - 后端：
    - 时间解析本地化：`app/routers/messages.py` `_parse_dt`（列表与有效列表）。
    - 黑白名单：`app/routers/configs.py`（filters API）、`app/services/sync_service.py`（同步过滤）。
    - WeChatPadPro：`app/routers/send.py`、`app/services/wechatpad_client.py`。
