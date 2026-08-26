# Publish 平台自动化调研

蚁小二的账号资产、批量任务、表单校验、发布记录和数据复盘机制已整理为独立基准文档：`docs/technical/yixiaoer-publish-benchmark.md`。后续第 7 环节设计应参考其产品机制，但不直接复用其 Cookie、云代理或 SaaS 登录体系。

更新时间：2026-08-02

## 目标

Transwrite 生成平台内容包后，Publish 能一键或半自动发布到：

- 微信公众号
- 小红书
- 抖音
- B站
- 微博
- X / Twitter
- 可选：知乎、视频号、快手、百家号、TikTok、YouTube

## 总体判断

当前正式路线不是从零写平台自动化，而是组合五层：

1. `social-auto-upload` 作为小红书、抖音、B站和视频号的统一受控上传主执行器。
2. 千帆云递作为本地可视化账号、素材、封面和发布队列控制台。
3. API-first CLI / Skill / MCP 与 PostBot 浏览器扩展作为平台后备路线。
4. OpenCLI 负责抖音实时活动发现和 UI 命令适配。
5. 本地 OpenClaw / Baoyu skills 继续负责公众号、微博、X 等非统一视频渠道；Postiz 只保留为海外排程候选。

Publish 仍必须保留任务/Campaign 级发布授权和 Publish Guard，但不再对授权范围内的每个弹窗和最终点击重复请求确认。原创声明、AI 内容声明、协议和封面确认按已验收的发布元数据自动处理；用户自有账号且已同步到当前电脑的一次性验证码，只在能明确匹配平台、账号和时间时自动填写一次，且不写入任何日志或回执。图形验证码、滑块、账号/设备风险审核和授权范围变更仍为硬停项，因此不承诺在任何平台状态下都能完全无人值守。

## 优先接入矩阵

| 平台 | 主执行器 | 备选/参考 | 建议等级 |
| --- | --- | --- | --- |
| 微信公众号 | `baoyu-post-to-wechat`、`wechat-multi-publisher`、`wechat-public-cli` | `wechat-article-publisher-skill`、`wechat-publisher`、`wechat-pub-rs` | 直接集成 |
| 小红书 | `social-auto-upload-bridge` | `All-IN-ONE`、`XhsSkills`、`Spider_XHS`、`xiaohongshu-mcp`、持久化浏览器 | 统一 CLI + API-first fallback |
| 抖音 | `social-auto-upload-bridge` | `douyin-upload-skill`、OpenCLI、持久化浏览器 | 统一 CLI + 活动实时发现 |
| B站 | `social-auto-upload-bridge` | `bilibili-upload-bridge`、人工包；`biliup-rs` 仅历史参考 | 统一 CLI |
| 微博 | `weibo-manager`、`baoyu-post-to-weibo` | `weibo-create-new-post`、`WeiboPilot`、Selenium/Puppeteer 项目 | 强审批集成 |
| X | `baoyu-post-to-x` | `xurl`、`x-cli`、`TweetCLI`、X API v2 media upload | 直接集成 |
| 知乎 | `zhihu-post` | 浏览器自动化 | 按需集成 |
| 视频号 | `social-auto-upload-bridge` | 千帆云递、持久化浏览器、人工包 | 已进入正式四平台主链 |
| 快手/百家号/TikTok/YouTube | `social-auto-upload` 可覆盖 | 千帆云递、Postiz（海外） | 按需扩展 |

## 关键外部项目

### social-auto-upload

地址：https://github.com/dreammis/social-auto-upload

价值：

- 覆盖抖音、Bilibili、小红书、快手、视频号、百家号、TikTok 等视频上传和定时发布。
- 已作为国内四平台视频分发统一外部依赖，并由受控桥执行。

风险：

- 浏览器/UI 自动化可能受平台改版影响。
- 需要账号登录态、Cookie、反风控策略。
- 不直接解决公众号、微博长文、X Article。

建议：

- 以独立、可更新的上游克隆放在 `vendor/publish/social-auto-upload`，主仓库忽略其源码、虚拟环境和 Cookie。
- 由 `social-auto-upload-bridge` 读取冻结的 `channel_pack.json`，先校验命名账号，再 Dry Run，最后等待当前会话确认。
- 小红书、抖音、B站、视频号均使用它作为统一主路由。

### B站上传工具

候选：

- `biliup/biliup-rs`：命令行投稿、登录、上传、追加、查看稿件。
- `bilibiliupload`：Python CLI/库式上传。
- `biliup-watcher`：监听目录并自动上传到 B站。

结论：

- `biliup-rs` 上游已归档，不再进入主路由。
- B站主路由改为 `social-auto-upload`，`bilibili-upload-bridge` 保留为平台包装和人工 fallback。

### 小红书自动化

候选：

- `cv-cat/All-IN-ONE`：小红书、微博、抖音统一 CLI & Agent Skill，覆盖搜索、详情、评论、上传、发布、蒲公英和千帆等命令，适合做 API-first 执行入口。
- `cv-cat/XhsSkills`：小红书接口 skill 包装，偏薄桥接，适合被 Newma skill 调度。
- `cv-cat/Spider_XHS`：底层 API 和签名源头，适合做接口变更时的 source-of-truth。
- `xpzouying/xiaohongshu-mcp`：Go/Rod MCP，支持搜索、详情、发布图文和视频，适合 MCP 化接入。
- `TimeCyber/mcp-xiaohongshu` / `rednote-mcp`：Node/Playwright MCP，支持搜索、详情、评论、图文发布，适合浏览器/MCP fallback。
- `JoeanAmier/XHS-Downloader`：强采集/下载工具，适合竞品素材采集，不适合发布主链。
- 本地 `xiaohongshu-auto`：发布笔记、管理内容，依赖登录 Cookie / 浏览器。
- 本地 `xiaohongshu-ops`：选题、发布前演练、发布后复盘和运营。
- `xiaohongshu-automation`：Playwright CDP 连接 OpenClaw 浏览器，支持发布、搜索、评论、用户资料。
- `xhs_ai_publisher`：PyQt/FastAPI/Playwright，复用登录态和预览发布。
- `Autoxhs`：生成图片、标题、内容、标签并发布。

建议：

- Publish 四平台 Campaign 主执行器统一为 `social-auto-upload-bridge`。
- 小红书后备优先级：`All-IN-ONE` → `XhsSkills/Spider_XHS` → `xiaohongshu-mcp/rednote-mcp` → 持久化浏览器。
- `XHS-Downloader` 只进入 intake / 竞品监控 / 素材抓取，不进入发布主链。
- 发布前运营校验和发布后维护可继续利用 `xiaohongshu-ops`。

### 微信公众号

候选：

- 本地 `baoyu-post-to-wechat`：HTML/Markdown/图文，API 或 Chrome CDP。
- 本地 `wechat-multi-publisher`：多篇 Markdown 推草稿箱。
- 本地 `wechat-public-cli`：CLI 发布/草稿。
- `wechat-article-publisher-skill`：Markdown/HTML 发布到公众号草稿。
- `wechat-publisher`：OpenClaw skill，Markdown + 图片上传 + 转 WeChat HTML + 草稿箱。
- `wechat-pub-rs`：Rust SDK，上传文章和管理草稿。

建议：

- 主路径：`baoyu-post-to-wechat`。
- 批量主副文：`wechat-multi-publisher`。
- CLI fallback：`wechat-public-cli`。
- API 权限不足时走浏览器/CDP，默认推草稿不直接群发。

### 微博

候选：

- 本地 `weibo-manager`：Puppeteer + Feishu 审批，强制 Request -> Approve -> Execute。
- 本地 `baoyu-post-to-weibo`：微博图文/头条文章半自动。
- `weibo-create-new-post`：Selenium 自动发微博。
- `WeiboPilot`：微博账号管理、批量发帖、定时发布、自动评论的 Electron 工具。

建议：

- 短微博必须用 `weibo-manager` 的审批流。
- 长文/头条文章走 `baoyu-post-to-weibo`。
- 不接入自动评论/自动私信，避免风控和运营风险。

### X / Twitter

候选：

- 本地 `baoyu-post-to-x`：文本、图片、视频、X Articles，支持 Chrome 插件/Computer Use/CDP。
- `xdevplatform/xurl`：X 官方 CLI，可走 API v2，支持媒体上传流程。
- `Infatoshi/x-cli`：X/Twitter API v2 CLI。
- `TweetCLI`：简单 CLI，文本与媒体附件。
- `Postiz`：开源社媒排程工具，支持 X 等海外平台。

建议：

- 主路径：`baoyu-post-to-x`，因为它已经适配本地 Chrome 和 X Article。
- API fallback：`xurl` / `x-cli`。
- 如果未来需要海外社媒统一日历和排程，再接 `Postiz`。

### Postiz

地址：https://github.com/gitroomhq/postiz-app

价值：

- 开源、自托管、社媒排程。
- 支持 X、Bluesky、Mastodon、Discord、TikTok、YouTube、Instagram、LinkedIn 等。

限制：

- 不覆盖公众号、小红书、B站、微博这类中文核心平台。
- 更适合海外平台排程和团队日历，不适合直接替代 Newma Publish。

建议：

- 作为海外平台排程候选，不作为当前主链核心。

### 千帆云递（QianFan Sync）

地址：https://github.com/DevilJie/social-auto-upload-web-ui

定位：本地账号管理、账号标签、素材中心、封面编辑、定时任务和发布队列控制台。后端、前端和 MCP 依赖已安装，前端已构建。

安全要求：通过 `SAU_DATA_DIR=~/Library/Application Support/NewmaPublishSessions/qianfan-sync` 外置数据库、Cookie、日志和上传缓存。使用 `python3 scripts/start_publish_console.py --confirm-start` 启动，访问 `http://127.0.0.1:5173`。

### PostBot

地址：https://github.com/gitcoffee-os/postbot

定位：复用浏览器已登录会话的扩展式多平台后备路线。默认分支依赖未公开的 `@gitcoffee/*` 包，无法复现构建；本地选择公开依赖的 `1.1.20` 稳定分支并完成构建。它不替代受控统一上传器。

### OpenCLI

地址：https://github.com/jackwener/OpenCLI

定位：浏览器 UI 命令适配和抖音活动实时查询。活动名只能来自发布当日查询结果；没有直接相关候选时应明确“不参加”，不得为流量硬选无关活动。

## Publish 集成方案

### 1. 平台适配包

每个 channel pack 固定输出：

- `channel_pack.json`
- `README.md`
- `assets/`
- `execution_request.json`
- `verification_request.json`

### 1.1 持久化浏览器登录态

所有浏览器型发布必须走发布专用持久化 Profile：

- 配置：`configs/publish/browser_profiles.json`
- 打开：`python3 scripts/open_publish_browser.py <channel>`
- 默认目录：`~/Library/Application Support/NewmaPublishProfiles/<platform>`

禁止使用 Chrome DevTools MCP 临时 profile、一次性自动化 profile、项目目录或 `skills/` 目录保存平台 cookies。Agent 只允许复用 profile 目录，不允许读取、导出、复制或提交 cookies。

统一账号中心由 `configs/publish/account_registry.json` 管理非敏感槽位映射。CLI 登录态独立保存在 `~/Library/Application Support/NewmaPublishSessions/social-auto-upload/cookies/`，第三方仓库中的 `cookies/` 仅作为该目录的本地符号链接。使用 `python3 scripts/publish_accounts.py --init` 初始化，使用 `python3 scripts/publish_accounts.py --check-auth` 在发布前验证各槽位；检查不会发布内容或输出 Cookie 内容。

当前映射：

| 逻辑账号 | 小红书 | 抖音 | B站 | 视频号 |
| --- | --- | --- | --- | --- |
| `publisher-a` | `xiaohongshu_video` / `slot-1` | `douyin_video` / `slot-1` | `bilibili_video` / `slot-1` | `wechat_channels_video` / `slot-1` |
| `publisher-b` | `xiaohongshu_video_2` / `slot-2` | `douyin_video_2` / `slot-2` | `bilibili_video_2` / `slot-2` | `wechat_channels_video_2` / `slot-2` |

逻辑账号仅作路由，真实平台昵称保留在各自登录态中。首次扫码后复用命名 Profile/CLI 会话，不要求每次重新输入手机号。

### 2. 执行模式

- `guarded_unified_cli`：四平台统一上传，命名账号校验 + Dry Run + 当前会话确认。
- `api_official`：官方 API，如 X、公众号部分 API。
- `browser_confirm`：浏览器填充，用户确认发布。
- `approval_required`：微博这类必须 Request -> Approve -> Execute。
- `manual_package`：B站/视频号在没有稳定执行器前导出人工包。
- `fallback_export`：官方 API 或浏览器失败时导出 outbox。

### 2.1 Dry-run 预演入口

不依赖具体内容包的发布通路体检：

```bash
python3 scripts/run_mainline_stage.py doctor --publish
python3 scripts/run_mainline_stage.py doctor --publish --channel wechat_article --channel xiaohongshu_video
```

`doctor --publish` 只检查本地 skill、外部依赖根目录、CLI 二进制和持久化浏览器 Profile 配置，不打开浏览器、不读取 cookies、不触发真实发布。

正式执行前先跑：

```bash
python3 scripts/run_mainline_stage.py publish \
  --transwrite-manifest ~/Desktop/自媒体创作/<run_id>/04_转写/transwrite_manifest.json \
  --publish-decision ~/Desktop/自媒体创作/<run_id>/05_发布/publish_decision.json \
  --dry-run
```

该命令只做三件事：

- 生成平台 `channel_pack.json`、`execution_request.json`、`verification_request.json` 和 `platform_form_validation.json`。
- 调用 `prepare_publish_execution.py` 为每个渠道选择可用执行路线。
- 写出机器可读的 `publish_dry_run_report.json` 和授权前复核用的 `publish_preflight_report.md`，取得当前任务/Campaign 的整体发布授权后进入真实执行。

### 3. 统一验真

平台执行器统一输入：

```bash
python3 scripts/build_publish_payload.py \
  --channel-pack ~/Desktop/自媒体创作/<run_id>/05_发布/channel_packs/<topic_id>/<channel>/channel_pack.json
```

生成 `publish_payload.json` 前会按 `configs/publish/platform_form_rules.json` 执行平台字段预检。`publish_payload.json` 只负责把通过校验的 `channel_pack.json` 转成平台 skill/CLI 可消费的标准输入，不会触发发布；存在阻断错误时执行入口返回 `blocked_platform_form_validation`。

安全执行入口：

```bash
python3 scripts/execute_publish_request.py \
  --execution-request ~/Desktop/自媒体创作/<run_id>/05_发布/channel_packs/<topic_id>/<channel>/execution_request.json
```

默认只做 dry-run；只有当前会话明确确认后才允许追加 `--confirm-execute`。确认执行允许公众号 `skill_draft_push` 和经过表单预检、账号登录检查、结果回填约束的 `social-auto-upload` 四平台路线。Campaign 的 `account_auth_status` 未全部达到 `valid` 时必须整体阻断。

发布后必须回填：

- `platform_url`
- `platform_post_id` / `draft_id`
- `account`
- `published_at`
- `screenshot`
- `verification_status`
- `error`

标准回填入口：

```bash
python3 scripts/record_publish_result.py \
  --channel-pack ~/Desktop/自媒体创作/<run_id>/05_发布/channel_packs/<topic_id>/<channel>/channel_pack.json \
  --success true \
  --status draft \
  --draft-id <draft_id> \
  --verification-status verified \
  --account <account_name>
```

该入口会同步更新：

- `channel_packs/<topic_id>/<channel>/publish_result.json`
- `channel_packs/<topic_id>/<channel>/publish_result.md`
- `channel_pack.json`
- `channel_execution_manifest.json`
- `publish_verification_report.json`
- `publish_manifest.json`

没有验真不得写 `published`。

批次验收入口：

```bash
python3 scripts/publish_guard.py \
  --publish-manifest ~/Desktop/自媒体创作/<run_id>/05_发布/publish_manifest.json
```

该入口默认在同目录写出 `publish_guard_report.json` / `publish_guard_report.md`，并把报告路径、状态和验收时间回写到 `publish_manifest.publish_guard`。它只校验批次结果，不上传、不发布、不打开浏览器、不读取 cookies。

## 下一步落地

已完成：

- 更新 `publish-skill-matrix.md`。
- 新增 `social-auto-upload-bridge` skill。
- 新增 `bilibili-upload-bridge` skill。
- 新增上游仓库登记表：`configs/publish/upstream_repos.json`。
- 新增上游检查脚本：`scripts/check_publish_upstreams.py`。
- 新增发布结果回填脚本：`scripts/record_publish_result.py`。

当前落地：

1. `build_publish_campaign.py` 已支持“两个视频版本 × 两个逻辑账号 × 四个平台”的 8 条独立任务。
2. 每条任务独立生成标题、文案、标签、完整构图封面、账号槽位、活动状态、表单预检和上传 Dry Run。
3. `publish_accounts.py` 已支持安全目录初始化与 8 个命名账号的只读登录检查。
4. `execute_publish_campaign.py` 在账号主执行器状态未全部为 `valid` 时拒绝确认执行。
5. 千帆云递控制台可一键启动；PostBot 稳定公开分支和 OpenCLI 均已构建。
6. 后续只需完成每个命名账号的一次性扫码登录，并在任务/Campaign 授权前复核活动、可见性和排期；授权后的流程弹窗与可明确匹配的同步一次性验证码由执行器自动处理。
