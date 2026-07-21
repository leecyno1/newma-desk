# VibeDesk

VibeDesk 是一个面向人和 Agent 的可生长工作台。

它把一次需求固化为长期可用的 `Mod`：每个 Mod 都有独立 HTML 页面、独立地址、数据连接和 AI 入口，既可以嵌入 VibeDesk，也可以单独访问。Vibe Research、Vibe Trading 和其他上游项目继续保持后端隔离，通过适配层接入同一个 Desk。

> Skill 固化“怎么完成工作”，Mod 固化“怎么看、怎么操作、怎么长期使用”。

## 核心概念

| 名称 | 含义 |
| --- | --- |
| VibeDesk | 整个产品 |
| Desk | 默认前端、侧边栏和 Mod 容器 |
| Mod | 可独立安装、访问、升级的功能单元 |
| View | Mod 内的具体 HTML 页面 |
| Skill | Agent 可重复执行的工作方法 |
| Connector | 数据、Agent 或模型的连接方式 |
| Mod Library | 管理、安装、启停和更新 Mod |

## 当前 MVP

- 单 Desk、多独立 Mod；每个 Mod 可嵌入，也可通过 URL 单独访问。
- Mod Manifest 控制侧边栏分组、顺序、名称、图标和页面入口。
- Desk UI 提供统一的指标、表格、ECharts、Markdown、筛选器和操作按钮样式。
- ViewSpec 使用 `data-vibe-*` 语义结构，让 Agent 直接读取 HTML 和结构化数据。
- Model Gateway：传统一次性模型调用，支持 OpenAI-compatible、本地兼容模型和 Anthropic/Claude。
- Agent Gateway：接入 Hermes WebUI，按“用户 + Agent + Mod”复用长期 Session。
- 示例 Mod：市场行情，支持刷新、模型解释和 Agent 长期上下文解释。

## 架构

```text
VibeDesk / Sidebar
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

## 第一批原生 Mods

VibeDesk 已提供两组原生 URL Adapter：

- `Vibe Investment`：对应 `simonlin1212/Vibe-Research`，包含每日复盘、资讯雷达、自选股、持仓、个股研究、产业链研究、研报、研究记录和投研 AI 设置。
- `Vibe Trading`：对应 `HKUDS/Vibe-Trading`，包含量化总览、量化 Agent、因子实验室、回测实验室、相关性分析、交易台和量化系统设置。

两个原生前端被嵌入时会自动隐藏自身侧边栏，因此 VibeDesk 中只保留一套左侧导航。注册命令是幂等的，可在上游地址变化或清空 VibeDesk 数据库后重复执行：

```bash
npm run mods:check
npm run mods:register
```

默认地址：

```text
VIBEDESK_INVESTMENT_WEB_URL=http://127.0.0.1:5899
VIBEDESK_TRADING_WEB_URL=http://127.0.0.1:5901
VIBEDESK_CONTROL_PLANE_URL=http://127.0.0.1:8901
```

完整启动方式见 [第一批原生 Mods 接入说明](docs/first-party-mods.md)。

## 本地启动

要求：Node.js 22+、npm 10+、Python 3.12+。

```bash
npm install

cd services/api
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
cd ../..
```

复制环境变量模板并按需填写模型或 Hermes 配置：

```bash
cp .env.example .env
```

分别启动 API、Desk 和示例 Mod：

```bash
services/api/.venv/bin/uvicorn vibe_visualization_api.main:app \
  --app-dir services/api --host 127.0.0.1 --port 8901

VITE_API_PROXY_TARGET=http://127.0.0.1:8901 \
VITE_MOD_ORIGIN=http://127.0.0.1:5891 \
npm run dev:shell -- --host 127.0.0.1 --port 5888

VITE_GATEWAY_BASE_URL=http://127.0.0.1:8901 \
VITE_PARENT_ORIGIN=http://127.0.0.1:5888 \
npm run dev -w @vibedesk/market-pulse -- \
  --host 127.0.0.1 --port 5891
```

打开 `http://127.0.0.1:5888`。

## AI 配置

常用环境变量：

```text
VIBEDESK_MODEL_DEFAULT_ADAPTER=openai-compatible
VIBEDESK_OPENAI_BASE_URL=https://api.openai.com/v1
VIBEDESK_OPENAI_API_KEY=
VIBEDESK_OPENAI_MODEL=gpt-5.6

VIBEDESK_ANTHROPIC_API_KEY=
VIBEDESK_ANTHROPIC_MODEL=claude-sonnet-4-5

VIBEDESK_AGENT_DEFAULT_ADAPTER=hermes-webui
VIBEDESK_HERMES_WEBUI_BASE_URL=http://127.0.0.1:8787
```

API Key 只保存在服务端，不会下发给 Mod 前端。

## 兼容策略

为了让 Vibe Research、Vibe Trading 和已经发布的页面可以平滑迁移，MVP 暂时保留以下旧入口：

- `/api/modules/*` 继续可用；新代码使用 `/api/mods/*`。
- `?module=` 继续可读取；VibeDesk 写入的新地址使用 `?mod=`。
- `VIBE_VIS_*` 环境变量继续可读取；新配置使用 `VIBEDESK_*`。
- `ModuleManifest`、`ModuleBridge` 等类型保留为兼容别名；新代码使用 `ModManifest`、`ModBridge`。
- 现有源码目录和 Python 包路径暂不强制重命名，避免阻断上游同步。

## 验证

```bash
npm test
npm run typecheck
npm run build
services/api/.venv/bin/python -m pytest -q
npm run test:e2e
```

## 文档

- [产品词汇与模块命名](docs/product-language.md)
- [第一批原生 Mods 接入说明](docs/first-party-mods.md)
- [ViewSpec 页面规范](docs/view-spec.md)
- [Gateway 分离设计](docs/superpowers/specs/2026-07-20-gateway-separation-design.md)
