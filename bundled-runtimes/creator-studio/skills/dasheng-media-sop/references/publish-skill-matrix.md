# Publish 技能矩阵

更新时间：`2026-08-02`

## 当前原则

Publish 不改写核心正文、图表、主视频或播客。它读取 `transwrite_manifest.json` 中已完成或可打包的 lane，生成平台衍生标题、文案、标签、封面、账号路由、执行器请求、人工包和发后验真记录。

## 平台矩阵

| 平台 | 主执行器 | 备选/辅助 | 自动化等级 | 当前决策 |
| --- | --- | --- | --- | --- |
| 微信公众号 | `baoyu-post-to-wechat` | `wechat-multi-publisher`、`wechat-public-cli`、`md2wechat` | 半自动/草稿优先 | 直接集成 |
| 小红书 | `social-auto-upload-bridge` | `dasheng-xhs-publish-bridge`、`all-in-one`、`xiaohongshu-mcp`、持久化浏览器 | 本地 CLI 确认执行 + fallback | 已接通受控执行 |
| 抖音 | `social-auto-upload-bridge` | `douyin-upload-skill`、持久化浏览器 | 本地 CLI 确认执行 + fallback | 已接通受控执行 |
| B站 | `social-auto-upload-bridge` | `bilibili-upload-bridge`、人工包；`biliup-rs` 仅历史参考 | 本地 CLI 确认执行 | 已接通受控执行 |
| 视频号 | `social-auto-upload-bridge` | 持久化浏览器、人工包 | 本地 CLI 确认执行 + fallback | 已升级为正式渠道 |
| 微博 | `weibo-manager` | `baoyu-post-to-weibo` | 强审批/半自动 | 短帖强审批，长文半自动 |
| X | `baoyu-post-to-x` | `xurl`、`x-cli`、`Postiz` | 半自动/API fallback | 直接集成 |
| 知乎 | `zhihu-post` | 浏览器自动化 | 半自动 | 按需启用 |
| 快手/百家号/TikTok | 暂无 Newma 主执行器 | `social-auto-upload` | 待验证 | 后续按需扩展 |

## 本地已具备 Skills

| Skill | 来源 | 角色 |
| --- | --- | --- |
| `baoyu-post-to-wechat` | `boutique-openclaw-skills` / 本机已安装 | 公众号单篇文章、图文、HTML/Markdown 发布 |
| `wechat-multi-publisher` | `boutique-openclaw-skills` | 多篇文章推草稿箱 |
| `wechat-public-cli` | `boutique-openclaw-skills` / 本机已安装 | 公众号 CLI fallback |
| `baoyu-post-to-weibo` | `boutique-openclaw-skills` | 微博长文/图文半自动 |
| `weibo-manager` | `boutique-openclaw-skills` | 微博短帖强审批流 |
| `baoyu-post-to-x` | `boutique-openclaw-skills` | X 文本、图片、视频、X Article |
| `dasheng-xhs-publish-bridge` | 本仓库 | 小红书 API-first / browser fallback 发布桥 |
| `xiaohongshu-auto` | `boutique-openclaw-skills` | 小红书发布执行器 |
| `xiaohongshu-ops` | `boutique-openclaw-skills` | 小红书发布前演练、发布后运营维护 |
| `all-in-one` | `cv-cat/All-IN-ONE` | 小红书/微博/抖音统一 CLI + skill 参考 |
| `xhs-skills` | `cv-cat/XhsSkills` | Spider_XHS 的薄 skill 包装 |
| `spider-xhs` | `cv-cat/Spider_XHS` | 小红书 API/source-of-truth |
| `xiaohongshu-mcp` | `xpzouying/xiaohongshu-mcp` | MCP publish/search/access 参考 |
| `rednote-mcp` | `TimeCyber/mcp-xiaohongshu` | 浏览器/MCP 参考 |
| `xhs-downloader` | `JoeanAmier/XHS-Downloader` | 素材与竞品采集，不作发布主链 |
| `douyin-upload-skill` | `boutique-openclaw-skills` | 抖音官方上传与 fallback outbox |
| `zhihu-post` | `boutique-openclaw-skills` | 知乎专栏/想法发布 |
| `publish-guard` | `boutique-openclaw-skills` | 发后验真、凭据和审计参考 |
| `social-auto-upload-bridge` | 本仓库 | 外部 `social-auto-upload` 多视频平台桥 |
| `bilibili-upload-bridge` | 本仓库 | B站投稿桥，优先 `biliup-rs`，fallback `social-auto-upload` |
| `dasheng-publish-operations-bridge` | 本仓库 + external `agent-skills-launch-pack` | 公众号/小红书/抖音/X 起号、矩阵角色、发布包装和复盘指标审查；不执行发布 |
| `qianfan-sync` | `DevilJie/social-auto-upload-web-ui` | 本地可视化账号中心、素材中心、封面编辑和多账号队列 |
| `postbot` | `gitcoffee-os/postbot` 稳定公开分支 | 复用浏览器已登录会话的扩展后备路线 |
| `opencli` | `jackwener/OpenCLI` | 抖音实时活动发现和浏览器 UI 适配 |

## 外部候选

| 项目 | 地址 | 适合用途 | 决策 |
| --- | --- | --- | --- |
| `social-auto-upload` | `https://github.com/dreammis/social-auto-upload` | 抖音、B站、小红书、快手、视频号、百家号、TikTok 等视频上传 | 作为外部依赖桥，不 vendoring |
| `All-IN-ONE` | `https://github.com/cv-cat/All-IN-ONE` | 小红书/微博/抖音统一 CLI & skill 参考 | 作为 API-first 发布参考 |
| `XhsSkills` | `https://github.com/cv-cat/XhsSkills` | 小红书接口 skill 包装 | 作为 API-first 主候选 |
| `Spider_XHS` | `https://github.com/cv-cat/Spider_XHS` | 小红书 API/creator 能力底座 | 作为 API-first 主候选 |
| `xiaohongshu-mcp` | `https://github.com/xpzouying/xiaohongshu-mcp` | 小红书 MCP 发布/访问 | 作为 MCP 候选 |
| `rednote-mcp` | `https://github.com/TimeCyber/mcp-xiaohongshu` | 小红书 MCP 发布/访问 | 作为 MCP 候选 |
| `XHS-Downloader` | `https://github.com/JoeanAmier/XHS-Downloader` | 下载/采集/竞品素材 | 不作为发布主链 |
| `biliup-rs` | `https://github.com/biliup/biliup-rs` | B站命令行投稿历史参考 | 上游已归档，不进入主路由 |
| `qianfan-sync` | `https://github.com/DevilJie/social-auto-upload-web-ui` | 本地多账号、素材、封面与发布队列控制台 | 已安装，账号数据外置 |
| `postbot` | `https://github.com/gitcoffee-os/postbot` | 浏览器扩展式多平台发布后备 | 稳定公开分支已构建 |
| `opencli` | `https://github.com/jackwener/OpenCLI` | 抖音活动实时发现和 UI 命令适配 | 已安装并构建 |
| `bilibiliupload` | GitHub/PyPI 同名项目 | Python B站上传库/CLI | B站 fallback |
| `Postiz` | `https://github.com/gitroomhq/postiz-app` | 海外社媒排程，X/TikTok/YouTube/LinkedIn 等 | 海外平台排程候选 |
| `xurl` | `https://github.com/xdevplatform/xurl` | X 官方 API CLI、媒体上传 | X API fallback |
| `x-cli` | `https://github.com/Infatoshi/x-cli` | X/Twitter API v2 CLI | X API fallback |
| `agent-skills-launch-pack` | `https://github.com/chenjin-cmd/agent-skills-launch-pack_` | 公众号、小红书、抖音、视频号和 X 的起号/运营策略 | 外部 advisory 上游，不当作发布执行器，不 vendoring |

## 执行模式

| 模式 | 含义 | 适用平台 |
| --- | --- | --- |
| `api_official` | 官方 API 上传/发布 | 抖音、X、公众号部分路径 |
| `browser_confirm` | 浏览器填充，人工确认发布 | 公众号、X、微博头条、知乎 |
| `approval_required` | Request -> Approve -> Execute | 微博短帖 |
| `manual_package` | 只导出人工发布包 | B站/视频号未配置执行器时 |
| `fallback_export` | 自动失败后导出 outbox | 抖音、B站、小红书 |
| `account_operations_advisory` | Agent/Skill 生成定位、钩子、关键词、合集、节奏和复盘建议 | 公众号、小红书、抖音、X |

## 强约束

1. 所有平台必须先生成 `channel_pack.json`，再调用执行器。
2. 浏览器型、审批型平台不得自动点击最终发布按钮。
3. 微博短帖必须走 `weibo-manager` 审批流。
4. 小红书优先走 API-first / MCP / CLI，只有失败时才切浏览器 fallback。
5. 小红书、抖音、B站和视频号即使 `sau` 返回 0，也必须保持 `needs_manual_verification`，直至回收平台 URL、稿件 ID 或可核验回执。
6. `social-auto-upload` 作为外部依赖调用，不把运行产物写入 skill 目录。
7. 没有 `Publish Guard` 或平台回执验真，不得回报“已发布”。
8. `agent-skills-launch-pack` 不具备登录、上传、定时或发布能力，不得出现在执行器路由中。
9. 冷启动、低流量、沉寂、风险审查和矩阵实验账号的受控执行，需要有效的 `account_operations_advice.json`。
10. Dry Run 命令可生成不等于账号已登录；Campaign 必须分别记录 `dry_run_ready_count` 和 `account_auth_status`。
11. 活动必须实时发现并人工确认，禁止虚构或自动选择不相关活动。

## 后续开发

1. `build_stage5_publish.py` 为每个 channel pack 输出 `execution_request.json` 和 `verification_request.json`。
2. `run_mainline_stage.py publish --dry-run` 输出 `publish_preflight_report.md`，汇总每个平台的选中路线、缺失依赖、浏览器 Profile 和人工确认要求。
3. `run_mainline_stage.py doctor --publish` 提供不依赖内容包的发布通路体检，只检查 skill、外部依赖、CLI 和持久化 Profile 配置。
4. 为四个平台补登录引导页、账号槽位状态和平台回执抓取。
5. 为视频号补双封面、短标题和草稿 ID 的自动验真。
6. 为每个平台补发布频率、每日限额与失败退避策略；不得读取或导出 cookies。
