# Newma-Desk

Newma-Desk 是 **MODS 开发规范**的参考实现，也是一个面向人和 Agent 的可生长工作台。

MODS 是一种革命性的新开发规范，其意义与 MCP、Skills 类似：MCP 统一 Agent 与外部能力的连接方式，Skills 沉淀可复用的工作流，而 MODS 在 Skills 之上进一步把工作流封装为**可复用、可安装、可组合的可视化模组与插件**。它让一项能力不再只是一段由 Agent 执行的流程，还能够拥有长期可用的界面、交互、数据连接和运行状态。

本项目主要用于生成、运行和管理 MODS 所需的统一前端与后端基座，重点提供两类基础能力：

1. **统一接口与规则**：提供统一的数据接口、模型接口、Agent 接口，以及服务发现、调用、鉴权和生命周期管理规则。
2. **统一前端界面接口**：统一管理菜单、一级与二级导航、标签栏、图像生成、图表生成、互动网页动画、Agent 提问，以及 MODS 之间的上下文传递、联动和组合。

Newma-Desk 可以把一次需求固化为长期可用的 `Mod`：每个 Mod 都有独立 HTML 页面、页面地址、数据连接和 AI 入口。Vibe Research 与 Vibe Trading 已作为内置领域运行时并入 Newma-Desk，不再作为独立产品启动；Deepsee 等外部服务通过适配层接入。

> Skill 固化“怎么完成工作”，Mod 固化“怎么看、怎么操作、怎么长期使用”。

> 文档中，`MODS` 表示整套开发规范，`Mod` 表示遵循该规范构建的单个可视化模组或插件。

## 核心概念

| 名称 | 含义 |
| --- | --- |
| Newma-Desk | 整个产品 |
| Desk | 默认前端、侧边栏和 Mod 容器 |
| Mod | 可独立安装、访问、升级的功能单元 |
| View | Mod 内的具体 HTML 页面 |
| Skill | Agent 可重复执行的工作方法 |
| Connector | 数据、Agent 或模型的连接方式 |
| Mod Store | 从 Git 商店发现、安装和更新 Mod |

## 当前 MVP

- 单 Desk、多 Mod；内置 Research / Trading 统一由 Newma-Desk 提供前端运行时和领域 API，外部服务型 Mod 仍可保留独立地址。
- Mod Manifest 控制侧边栏分组、顺序、名称、图标和页面入口。
- Desk UI 提供统一的指标、表格、ECharts、Markdown、筛选器和操作按钮样式。
- ViewSpec 使用 `data-vibe-*` 语义结构，让 Agent 直接读取 HTML 和结构化数据。
- Model Gateway：传统一次性模型调用，支持 OpenAI-compatible、本地兼容模型和 Anthropic/Claude。
- Agent Gateway：可直接调用本机 Codex CLI、Claude Code、Gemini CLI，也可接入 Hermes WebUI；按“用户 + Agent + Mod”保留长期上下文。
- 项目内 `mods/` 是官方商店目录；`mod-projects/` 内置 Vibe Research 和 Vibe Trading。两套业务工程对应的 14 个 Mods 默认启用并注册到侧边栏。
- 侧边栏按 Mod 分类显示固定语义色；用户自定义分类会根据分类名称自动获得稳定颜色。
- Deepsee 作为独立服务运行；Newma-Desk 商店中的 11 个 Deepsee Mods 直接加载其 `/embed/*` 页面，不复制后端、SQLite 或业务源码。

## 架构

```text
Newma-Desk / Sidebar
        |
        +-- Independent HTML Mod
        |       |
        |       +-- Data Connector
        |       +-- Model Gateway -> GPT / Claude / Local Model
        |       +-- Agent Gateway -> Hermes / Future Agent Runtime
        |
        +-- ViewSpec / Mod SDK / Desk UI
```

Model Gateway 和 Agent Gateway 是两条并列链路，执行时不会互相串联：

```text
Mod -> Model Gateway -> Model
Mod -> Agent Gateway -> Agent Runtime -> Memory / Skills / Tools
```

## 默认 Mod 命名

```text
今日
├── Today                 今日总览
└── Daily Review          每日复盘

市场
├── Market Pulse          市场行情
├── Watchlist             自选股
├── News Radar            资讯雷达
└── Portfolio Brief       持仓研报

研究
├── Stock Research        个股研究
├── Industry Map          产业链研究
└── Research Library      研究资料库

量化
├── Alpha Lab             因子实验室 / Alpha Zoo
└── Backtest Lab          回测实验室 / 回测报告

交易
└── Trade Desk            交易台
```

## 官方 Mod 商店

项目根目录的 `mods/` 是 Newma-Desk 官方商店，每个 Mod 都有独立的 `mods/<mod-id>/mod.json`。商店页面读取这个目录，并显示当前安装状态。

- 商店索引：`mods/store.json`
- GitHub 安装源：`leecyno1/newma-dock` 的 `main/mods` 目录
- Gitee 备用源：`leecyno1/newma-dock` 的 `main/mods` 目录
- 上游页面仍来自 Vibe Research 和 Vibe Trading，不复制进 Newma-Desk。

新环境会把商店全部 Mods 注册到侧边栏：

```bash
npm run mods:check
npm run mods:compat
npm run mods:certify -- --mod market-daily,multi-timeframe
npm run mods:register
```

`mods:compat` 只验证 Manifest 声明与静态合同，不授予运行认证；`mods:certify` 会连接当前运行中的 Desk，实际检查页面健康、iframe 嵌入、Bridge 握手、320px 布局，并为 Level 3 验证 Agent Context 的接收与持久化。认证报告默认写入系统临时目录。

已有环境需要同步完整商店清单时，也可以运行：

```bash
npm run mods:standardize
```

侧边栏会显示全部已注册 Mods；“Mod 商店”继续负责浏览来源、查看安装状态和从 Git 更新。第三方 Mod 不会被标准化脚本移除。

默认地址：

```text
NEWMA_DESK_INVESTMENT_WEB_URL=http://127.0.0.1:8911
NEWMA_DESK_TRADING_WEB_URL=http://127.0.0.1:8911
NEWMA_DESK_DEEPSEE_WEB_URL=http://127.0.0.1:8001
NEWMA_DESK_CONTROL_PLANE_URL=http://127.0.0.1:8911
```

完整启动方式见 [官方 Mod 商店与原生 Mods 接入说明](docs/first-party-mods.md)。

## 本地启动

要求：Node.js 22+、npm 10+、Python 3.12+。

```bash
npm install

cd services/api
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
cd ../..
```

复制环境变量模板。只使用本机 CLI 时无需填写模型 API Key：

```bash
cp .env.example .env
```

推荐用统一开发启动器启动 Newma-Desk、Market Pulse，以及内置的 Research / Trading 领域运行时：

```bash
npm run dev:stack
```

Research 与 Trading 不再分别启动 `5899 / 5901 / 8900 / 8899`。它们的领域 API 被挂载到 Newma-Desk API 的 `/api/research`、`/api/trading`，前端构建产物由 `/mod-runtime/research`、`/mod-runtime/trading` 统一托管。标准运行端口为 `5888 / 5891 / 8911`，七周期和 Deepsee 仍按各自服务边界运行。

查看整套服务状态：

```bash
npm run dev:status
```

统一启动器把 Newma-Desk API、Market Pulse、Desk 和内置 Research / Trading 视为核心运行时；InStock、Orchestra、Seven Cycle 与 Deepsee 属于可选或外部 Mod。可选 Mod 不可用时会显示 `WARN/MISS`，但不会关闭已经就绪的 Desk。需要把所有可选 Mod 也纳入严格检查时使用：

```bash
npm run dev:status -- --strict
```

核心启动等待时间可通过 `NEWMA_DESK_STARTUP_TIMEOUT_MS` 调整；可选 Mod 使用独立的 `NEWMA_DESK_OPTIONAL_STARTUP_TIMEOUT_MS`，默认 30 秒。Seven Cycle 的健康响应会读取 Catalog 状态，单次探测默认允许 5 秒，可通过 `NEWMA_DESK_SEVEN_CYCLE_HEALTH_TIMEOUT_MS` 调整，避免慢盘场景被误判为掉线。
统一启动器默认使用 `runtime/newma-desk-stack.pid` 做单实例保护；重复执行 `npm run dev:stack` 会直接提示现有进程，不会重复占用 Mods 端口。确需改变锁文件位置时，可设置 `NEWMA_DESK_STACK_PID_FILE`。
Newma-Desk 启动 Seven Cycle 时会显式启用严格的 Catalog 设备漂移自修复；它只接受 manifest、产品 checksum、旧 Catalog 审计和两份 deployment 全部通过验证的重挂载场景。可用 `NEWMA_DESK_SEVEN_CYCLE_REPAIR_CATALOG_ON_START=0` 关闭。

### 外部 Mod Runtime Descriptor

Deepsee、Seven Cycle、InStock 与 Orchestra 统一由
[`config/external-mod-runtimes.json`](config/external-mod-runtimes.json) 声明工作区候选、HTTP 入口和健康路径。这个 Runtime Descriptor 是启动生命周期的公共 Interface；Node 启动器和 Python Agent Gateway 各自通过 Adapter 读取它，因此端口、路径发现和允许的来源只需要维护一处。

默认会依次从 Newma-Desk 同级项目目录、`~/Desktop/Projects` 和仓库内候选目录发现外部工作区。新机器通常不需要填写个人绝对路径；如果目录布局不同，可以先覆盖发现根目录：

```text
NEWMA_DESK_PROJECTS_ROOT=/path/to/projects
NEWMA_DESK_DESKTOP_PROJECTS_ROOT=/path/to/desktop-projects
```

也可以只覆盖单个工作区或入口，例如：

```text
NEWMA_DESK_INSTOCK_WORKSPACE=/path/to/instock-analysis
NEWMA_DESK_INSTOCK_WEB_URL=https://instock.example.com
```

本地入口且发现了工作区时，统一启动器负责启动和停止对应进程；远程入口只做健康检查；缺少的可选工作区会保留为明确的降级状态，不影响核心 Desk。空环境变量等同于未覆盖，继续使用 Descriptor 发现。

也可以分别启动 API、Desk 和示例 Mod：

```bash
services/api/.venv/bin/python -m uvicorn vibe_visualization_api.main:app \
  --app-dir services/api --host 127.0.0.1 --port 8911

VITE_API_PROXY_TARGET=http://127.0.0.1:8911 \
VITE_MOD_ORIGIN=http://127.0.0.1:5891 \
npm run dev:shell -- --host 127.0.0.1 --port 5888

VITE_GATEWAY_BASE_URL=http://127.0.0.1:8911 \
VITE_PARENT_ORIGIN=http://127.0.0.1:5888 \
npm run dev -w @newma-desk/market-pulse -- \
  --host 127.0.0.1 --port 5891
```

打开 `http://127.0.0.1:5888`。

## AI 配置

打开 Newma-Desk 后，点击侧边栏底部的“Agent 设置”：

- 自动发现本机已安装的 Codex CLI、Claude Code 和 Gemini CLI。
- 选择一个全局默认 Agent，或给某个 Mod 单独指定 Agent。
- 点击“测试”会走完整的 Desk → Agent Gateway → 本机 CLI 链路。
- 本机 CLI 使用各自已有的登录态，不在网页里保存订阅账号或 API Key。

本机 CLI 的工作目录按 Mod 隔离：Investment Mods 使用 `NEWMA_DESK_INVESTMENT_WORKSPACE`，Trading Mods 使用 `NEWMA_DESK_TRADING_WORKSPACE`，其他 Mod 使用 `NEWMA_DESK_WORKSPACE_ROOT`。

常用环境变量：

```text
NEWMA_DESK_MODEL_DEFAULT_ADAPTER=openai-compatible
NEWMA_DESK_OPENAI_BASE_URL=https://api.openai.com/v1
NEWMA_DESK_OPENAI_API_KEY=
NEWMA_DESK_OPENAI_MODEL=gpt-5.6

NEWMA_DESK_ANTHROPIC_API_KEY=
NEWMA_DESK_ANTHROPIC_MODEL=claude-sonnet-4-5

NEWMA_DESK_AGENT_DEFAULT_ADAPTER=codex-cli
NEWMA_DESK_AGENT_TIMEOUT_SECONDS=300
NEWMA_DESK_WORKSPACE_ROOT=.
NEWMA_DESK_INVESTMENT_WORKSPACE=mod-projects/vibe-research
NEWMA_DESK_TRADING_WORKSPACE=mod-projects/vibe-trading
NEWMA_DESK_MOD_SESSION_SECRET=请在生产环境设置固定随机值
NEWMA_DESK_MOD_SESSION_TTL_SECONDS=900

# Hermes WebUI 是可选的外部 Agent Adapter
NEWMA_DESK_HERMES_WEBUI_BASE_URL=http://127.0.0.1:8787
```

API Key 只保存在服务端，不会下发给 Mod 前端。

## 兼容策略

为了让 Vibe Research、Vibe Trading 和已经发布的页面可以平滑迁移，MVP 暂时保留以下旧入口：

- `/api/modules/*` 继续可用；新代码使用 `/api/mods/*`。
- `?module=` 继续可读取；Newma-Desk 写入的新地址使用 `?mod=`。
- `NEWMA_DOCK_*`、`VIBEDESK_*` 和 `VIBE_VIS_*` 环境变量继续可读取；新配置使用 `NEWMA_DESK_*`。
- `ModuleManifest`、`ModuleBridge` 等类型保留为兼容别名；新代码使用 `ModManifest`、`ModBridge`。
- Manifest 1.0 继续作为旧 Mod 兼容模式；新 Mod 使用 Manifest 1.1 和显式 Action Binding。
- 现有源码目录和 Python 包路径暂不强制重命名，避免阻断上游同步。

## 验证

```bash
npm test
npm run typecheck
npm run build
npm run test:api
npm run test:e2e
```

Manifest 的兼容等级只是声明。运行中的 Mod 还需要通过 `npm run mods:certify` 检查 health、embed、Bridge、窄屏布局和相应等级的 Agent Context，才算获得 Runtime Certification。

完整发布验收可以一次执行：

```bash
npm run test:release
```

它先执行静态测试、类型检查、构建和 Python 测试，再复用当前 Newma-Desk 核心栈；若核心未运行则临时启动。随后执行核心状态检查、Manifest 合同、7 个 Level 3 默认 Mod 的 Runtime Certification，以及侧边栏、市场工作区和内置 Research / Trading 的 Live E2E。临时启动的进程会在验收结束后统一停止。

默认发布验收允许外部可选 Mod 降级；需要把 Deepsee、Seven Cycle、InStock 和 Orchestra 全部作为发布条件时使用：

```bash
NEWMA_DESK_REQUIRE_EXTERNAL_MODS=1 npm run test:release:live
```

本地 Playwright 默认复用已安装的 Google Chrome，CI 默认使用安装的 Playwright Chromium；可通过 `NEWMA_DESK_PLAYWRIGHT_CHANNEL` 显式覆盖。CI 中的集成 Mod 和外部 Runtime job 使用仓库变量开关，未配置时会在工作流中明确显示为 skipped，而不是静默省略。

## 文档

- [产品词汇与模块命名](docs/product-language.md)
- [Newma-Desk Mod 三级兼容标准](docs/mod-compatibility-standard.md)
- [官方 Mod 商店与原生 Mods 接入说明](docs/first-party-mods.md)
- [ViewSpec 页面规范](docs/view-spec.md)
- [Gateway 分离设计](docs/superpowers/specs/2026-07-20-gateway-separation-design.md)
