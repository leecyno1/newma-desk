# Publish 阶段正式架构

更新时间：`2026-08-02`

## 目标

`publish` 是轻量执行层，负责验收、平台衍生包装、账号路由、推草稿/受控发布包、链接回收和发后验真。

正式阶段顺序：

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

`transwrite` 已负责公众号转写、口播主视频、播客生产包；`publish` 不改写核心内容，但可以为每个平台生成标题、主题文案、标签、完整构图封面、短标题、分类和活动候选。

## 正式输入

- `transwrite_manifest.json`
- `publish_decision.json`

若缺少任一文件，`publish` 必须拒绝执行。

## 执行闭环

### 1. Publish Gate

校验 `publish_decision.json`：

- 发布平台矩阵
- 每题每平台路由
- 标题、发布时间、可见性
- 是否允许立即发布，还是仅创建草稿 / 打开浏览器待授权

### 2. Package

从 `transwrite_manifest.json` 读取各 lane：

- `wechat_article`：公众号、微博、X 等文字渠道
- `talking_head_video`：小红书、抖音、B站等视频渠道
- `podcast`：播客渠道

只有 `completed` / `packageable` 的 lane 可进入发布执行包。兼容旧文字包时，`ready_base_package` 可被视为可打包。

若 lane 状态仍是 `planned`、`planned_for_render`、`ready_for_agent_execution`、`ready_for_skill_execution`、`blocked_missing_*`、`waiting_for_human_media` 或 `failed_qc`，只能标记为等待，不得误报完成。

### 3. Draft Push / Manual Pack

按渠道生成执行器调用计划：

- 公众号：`baoyu-post-to-wechat` / `wechat-multi-publisher` / `md2wechat`
- 微博：`baoyu-post-to-weibo`
- X：`baoyu-post-to-x`
- 小红书：`social-auto-upload-bridge` / API-first / MCP / 持久化浏览器 fallback
- 抖音：`social-auto-upload-bridge` / `douyin-upload-skill` / 持久化浏览器 fallback
- B站：`social-auto-upload-bridge` / `bilibili-upload-bridge` / `biliup-rs` / 人工投稿包
- 视频号：`social-auto-upload-bridge` / 持久化浏览器 / 人工投稿包
- 播客：人工上传或音频平台 API

浏览器型、MCP、普通外部 CLI 或人工包路线在未取得当前任务/当前 Campaign 的发布授权时，默认只生成流程计划。用户已明确要求发布，或执行 `execute_publish_request.py --confirm-execute` 后，该授权覆盖当次任务内的最终发布点击与流程弹窗，不得再逐项暂停请求确认。`--confirm-execute` 仍只允许受控的 `skill_draft_push` 与带登录检查、表单预检和结果回填的 `social-auto-upload` 路线。

双账号、多版本、多平台任务先由 `build_publish_campaign.py` 生成 Campaign。逻辑账号只映射到非敏感账号槽；Cookie/Profile 以命名目录保存，禁止读取或导出。Campaign 的 Dry Run 状态与账号登录状态必须分开统计。只有主执行器账号状态全部为 `valid`，才可进入当前任务/Campaign 的发布授权与执行。

授权后的交互策略：

- 有头发布浏览器禁止全屏或最大化，默认以 `1180×780` 小窗在附属屏幕右上角后台启动，不抢占当前工作焦点。若未连接附属屏幕，则降级为主屏右上角的非全屏小窗。
- 原创声明、AI 内容声明、平台协议、封面确认等普通流程弹窗，按已验收的 `publish_metadata` 和当前发布任务自动选择、点击并继续；禁止猜测与事实不符的原创或 AI 声明。
- 用户自有账号的短信/邮件一次性验证码，若已同步到当前电脑，则只读取与当前平台、账号和时间匹配的最新验证码，自动填写一次并继续发布。
- 一次性验证码只存在于当次交互内存中；禁止写入日志、截图标注、回执、manifest、仓库或长期记忆，禁止在对话中复述。
- 图形验证码、滑块、设备/账号风险审核、验证码来源或所属账号不明等无法可靠自动完成的挑战，必须停止当次交互并报告，禁止循环点击或反复试错。
- 弹窗或验证流程如果要求更换发布账号、平台、内容、可见性或付费项目，属于超出原授权范围，不得自动接受。

需要人工查看账号、素材、封面和发布队列时，运行 `scripts/start_publish_console.py --confirm-start` 启动千帆云递本地控制台。它使用外置 `NewmaPublishSessions/qianfan-sync` 数据目录，不得把账号状态写回仓库。

活动必须在发布当天实时发现：抖音优先使用 OpenCLI，其他平台通过对应持久化 Profile 复核。禁止虚构活动名或为了流量加入不相关活动。

### 3A. Account Operations Advisory

公众号、小红书、抖音和 X 渠道包同时生成 `account_operations_request.json`：

- 公众号 → `wechat-account-launch-expert`
- 小红书 → `xiaohongshu-account-launch-expert`
- 抖音 → `douyin-account-launch-expert`
- X → `x-twitter-cold-start-expert`

统一由 `dasheng-publish-operations-bridge` 读取外部
`agent-skills-launch-pack`，并生成 `account_operations_advice.json/.md`。

该层只调整定位一致性、标题/钩子、关键词/标签、合集、发布节奏、互动和复盘指标；不登录、不上传、不发布，也不重写已验收的核心内容。

`new/cold_start/low_performance/dormant/risk_review/matrix_experiment`
默认为受控执行前必审。建议 JSON 通过契约验证并重建发布包后，才恢复可确认执行状态。

### 4. Link Recovery

发布后必须回填：

- 平台 URL
- 平台 post ID / 草稿 ID
- 发布时间
- 发布账号
- 截图或错误状态

### 5. Publish Guard

所有平台执行后都要通过 `record_publish_result.py` 回填并生成 `publish_verification_report.json`，禁止“只执行命令就宣称已发布”。

- 批量发布先展开为独立 `task_id`，同平台不同账号不得共用结果身份。
- 任务级渠道包位于 `channel_packs/<topic_id>/<channel>/<task_id>/`；旧决策继续兼容两级目录。
- 每次失败和重试追加到 `publish_result_history.json` 与 `publish_results/attempt-XXXX.json`，不得覆盖历史尝试。
- 失败必须归类并生成 `publish_retry_request.json`；退避只产生计划，不自动执行发布。
- 已同步到当前电脑、且能明确匹配平台与账号的一次性验证码按上述策略自动填写；平台风控、图形/滑块挑战和内容拒绝必须停止并报告，禁止循环重试。

- `published_links`：仅允许 `status=published`、`verification_status=verified` 且带正式 `platform_url` 的结果进入。
- `draft_records`：仅允许 `status=draft|scheduled`、`verification_status=verified` 且带 `draft_id` 的结果进入。
- `draft_url` 必须与 `platform_url` 分离，草稿链接不得冒充正式发布链接。
- 同一 `topic_id` 多渠道分发时，公众号草稿 + 小红书/抖音/B站正式发布属于 `completed_with_mixed_status`，Postmortem 仍按一个 topic 聚合。
- Postmortem 只从已验真的 `publish_results` 计算 `published/drafted`，不得读取旧 `channel_pack.wechat_article_url` 作为成功发布证据。

## 标准输出

- `07_发布计划.md`
- `07_发布包.md`
- `channel_execution_manifest.json`
- `publish_verification_report.json`
- `publish_manifest.json`
- `channel_packs/<topic_id>/<channel>/account_operations_request.json`
- `channel_packs/<topic_id>/<channel>/account_operations_advice.json`
- `channel_packs/<topic_id>/<channel>/<task_id>/channel_pack.json`（批量矩阵任务）

## 旧能力去向

- `publish_video_supplement.py`：保留为兼容工具或 Transwrite 视频 lane 参考，不再是正式 Publish 主入口。
- `channel_adaptation_manifest.json`：旧适配层产物，不再是当前主链必需文件。
