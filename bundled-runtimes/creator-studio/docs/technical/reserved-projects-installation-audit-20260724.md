# 储备项目与视觉 Skill 安装审计（2026-07-24）

## 结论

本轮将可保留的上游统一收口到项目内的 `vendor/reserved/`，并保留既有的 `vendor/publish/social-auto-upload`。共登记 39 个项目，其中 38 个为本轮新克隆，1 个为既有上游。Codex 新安装并注册 33 个视频、动画、图画与设计 Skill。

`vendor/reserved/` 已加入 `.gitignore`。第三方源码、虚拟环境、`node_modules`、模型、媒体、缓存和登录状态均不进入主仓库版本控制，也不得作为运行产物目录。

权威机器注册表：`configs/external/reserved_projects.json`。

## 筛选标准

保留项目至少满足一项独特能力，并同时满足稳定上游、可审查源码、许可证/维护状态可接受、能够在本机形成调用链等条件。用户明确点名的后备项目允许降级保留，但必须标为 `reference_only` 或 `experimental`，不能进入默认生产路由。

优先级如下：

1. `production_candidate`：HTML Video、HyperFrames、Remotion、Video Wrapper、Claude Real Video、Lottie、成熟设计 Skill。
2. `preferred_local_experiment`：FreeCut 等本地低成本剪辑路线。
3. `backup` / `experimental`：Video Use、Claude Shorts、Seedance、Vox Director、Palmier、Chengfeng。
4. `reference_only`：Talking Head Editor，仅用于流程与镜头语言参考。

## 克隆结果

- 视频与剪辑：15 个。
- HTML/渲染：2 个。
- 图画、设计与 Skill 集合：10 个。
- 发布与下载：11 个（含既有 `social-auto-upload`）。
- Boutique 目录源：1 个。

所有新项目均为独立 Git 仓库，远端、路径和当前 HEAD 已写入注册表。调用配置已从旧的 `${EXTERNAL_VOLUME}/...` 分散路径迁移到本项目的 `vendor/reserved/...`。

## 已安装并注册的 Skill

共 33 个：

- 视频/剪辑/动画：`video-use`、`freecut`、`video-wrapper`、`vox-director`、`claude-shorts`、`seedance2-skill`、`remotion-video-skill`、`remotion-video-toolkit`、`cut-talking-head`、`finish-talking-head`、`gif-sticker-maker`、`ian-xiaohei-illustrations`、`video-frames`、`reusable-footage-material`、`remotion-best-practices`、`animated-financial-display`。
- 设计/图画：`canvas-design`、`algorithmic-art`、`brand-guidelines`、`animation-vocabulary`、`apple-design`、`emil-design-eng`、`find-animation-opportunities`、`improve-animations`、`review-animations`、`pick-ui-library`、`brandkit`、`high-end-visual-design`、`image-to-code`、`minimalist-ui`、`design-taste-frontend`、`web-animation-design`、`guizang-social-card-skill`。

第三方 Skill 中 6 个使用了 Codex 不支持的前置元字段，已在 `~/.codex/skills` 的安装副本中做兼容修正；未改变工作流正文。Skill 从下一轮对话开始进入稳定发现范围。

## 本地依赖状态

已建立独立 Python 3.11 `.venv`：

- `video-use`
- `freecut`（含 `whisper-mlx`）
- `claude-real-video`（含 `fast`）
- `video-wrapper`（含 Playwright Python 运行时）
- `claude-shorts`
- `claude-code-video-toolkit`
- `talking-head-editor`
- `vox-director`

已安装 Node/Bun 依赖：

- `html-video`：`pnpm install`、GSAP、Lottie Web、全量 build；smoke 与 typecheck 通过。
- `html-anything`：`pnpm install`。
- `hyperframes`：`bun install`，Skill lint 通过。
- `text-to-lottie`：依赖与 Unicode text-slot 测试通过；上游 `@kobalte/core` 类型声明与当前 TypeScript 不兼容，已在本地储备副本启用 `skipLibCheck` 兼容层，应用源码仍保持严格检查，全量 build 通过后才登记为可用。
- `claude-shorts/remotion`：`npm install` 完成；上游审计报告 11 个漏洞（7 moderate、4 high），未执行可能破坏兼容性的强制修复。Python 导入通过，但 PyAV 与 OpenCV 各自捆绑的 FFmpeg 动态库出现重复类告警，因此保留为后备路线，正式视频前必须单独回归。
- `guizang-social-card-skill`：Node 依赖已安装。Playwright 专用 Chromium 下载速度异常，已改为优先使用本机 Google Chrome，并保留 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` 覆盖入口，避免未来调用被浏览器包下载阻塞。
- `baoyu-skills`：Node 依赖已安装。上游漏声明 `socks`，在本地储备副本补齐后 249/249 测试通过；审计报告 5 个漏洞（1 low、4 high），未强制升级。

系统工具：FFmpeg、ffprobe、whisper-cli、yt-dlp、pnpm、bun、uv 均已发现。Homebrew 公式会连带升级 12 个系统媒体依赖且下载失败，因此没有采用；`auto-editor` 改用隔离的 `uv tool` 安装，CLI 版本 `29.3.1` 已验证，未改动现有 FFmpeg/whisper-cpp。

## 需要外部状态的项目

- `vox-director`：需要 `ATLASCLOUD_API_KEY`。
- `seedance2-skill`、MiniMax/Inference 类 Skill：需要对应模型权限或 API Key。
- 发布、下载和云草稿工具：需要用户主动登录；本轮未读取 Cookie、未配置账号、未上传或发布。
- `palmier-pro`：源码已保留，仍需桌面 App/MCP 服务才能进入实验路由。
- `talking-head-editor`：缺少清晰许可证且没有原生 Codex Skill，只读参考。

## 剔除项目

- `video-editing-pipeline`、`ffmpeg-usage`：没有稳定独立上游，且能力已被内部流程覆盖。
- `caption-clip`：低采用、无清晰许可证、能力重复。
- `product-launch-video-skill`：过于小众，质量和复用性不及保留的 Remotion 工具链。
- `rednote-mcp`、`x-cli`：分别被 `xiaohongshu-mcp` 与 `xurl`/现有发布链覆盖。
- Boutique 的旧 `remotion-video`、`demo-video`：硬编码失效路径或旧 Clawdbot 依赖。
- Boutique 的 `video-subtitles`：主要面向希伯来语/英语，不适合中文主链。
- Boutique 的 `video-agent`：只有 HeyGen API 说明，没有可安装上游。
- 重复动画 Skill：由 HyperFrames、Remotion、Lottie 与 Emil 动画审查套件覆盖。

## 调用原则

正式制作默认使用“导演规划 + HTML Video/Remotion/HyperFrames + 动态图表 + FFmpeg QC”的组合。FreeCut/Video Use/Auto Editor 只进入可回滚实验；Talking Head Editor 只提供流程参考；生成式 B-roll 不得冒充事实证据。所有外部产物必须通过现有证据台账、渲染合约与人工审片关口。

## 导演统一路由注册（补充）

`configs/video/tool_registry.json` 已升级为 v2：除内部工具外，登记项目内导演 Skill 和本轮安装的全部 33 个视频/设计 Skill。`configs/external/reserved_projects.json` 为全部 39 个保留项目增加了能力、制作阶段和执行模式索引。

`scripts/video_director_tool_router.py` 会合并工具、Skill 与项目三类登记，按线路、能力、级别、运行状态和依赖生成：

- 制作阶段主路由与后备路由；
- 每个分镜的 `required_capabilities`；
- `primary_stack` 与 `fallback_stack`；
- API Key、模型权限、登录、桌面 App 和 `reference_only` 受阻原因；
- 独立的 `tool_routing_plan.json`。

`scripts/dasheng_video_director.py` 已默认执行该路由器并将结果写入 `scene_plan.json`。`docs/technical/video-technical-stack-registry.html` 是面向人工复核的自包含技术注册站，可按名称、能力、状态和路径搜索全部登记项。
