# Vibe Visualization

Vibe Visualization 是一个同时面向人和 Agent 的开放式网页可视化基座。

它提供统一侧边栏、独立 HTML Module、数据服务入口、Vibe HTML 展示规范，以及彼此独立的 Model Gateway 和 Agent Gateway。现有 Vibe Research、Vibe Trading 或其他项目可以在保持后端隔离的情况下接入同一个前端基座。

## 当前 MVP

- 单前端、多独立 Module，每个 Module 可以嵌入基座或通过 URL 单独访问。
- Module Manifest 控制侧边栏分组、顺序、名称和图标。
- 统一的指标、表格、ECharts、Markdown、筛选器和操作按钮样式。
- Vibe HTML 使用 `data-vibe-*` 语义结构，方便 Agent 高效读取页面。
- Model Gateway：传统一次性模型调用，支持 OpenAI-compatible、本地兼容模型和 Anthropic/Claude。
- Agent Gateway：接入 Hermes WebUI，按“用户 + Agent + Module”复用长期 Session。
- 示例 Module：每日股票行情，支持刷新、模型解释和 Agent 长期上下文解释。

## 架构

```text
Web Base / Sidebar
        |
        +-- Independent HTML Module
        |       |
        |       +-- Data Service
        |       +-- Model Gateway -> GPT / Claude / Local Model
        |       +-- Agent Gateway -> Hermes / Future Agent Runtime
        |
        +-- Vibe HTML / Module SDK / Shared UI Foundation
```

Model Gateway 和 Agent Gateway 是两条并列链路。Agent 自己管理模型、Memory、Skills 和工具，基座不会把 Agent 请求强制转入 Model Gateway。

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

分别启动 API、Shell 和示例 Module：

```bash
services/api/.venv/bin/uvicorn vibe_visualization_api.main:app \
  --app-dir services/api --host 127.0.0.1 --port 8901

VITE_API_PROXY_TARGET=http://127.0.0.1:8901 \
VITE_MODULE_ORIGIN=http://127.0.0.1:5891 \
npm run dev:shell -- --host 127.0.0.1 --port 5888

VITE_GATEWAY_BASE_URL=http://127.0.0.1:8901 \
VITE_PARENT_ORIGIN=http://127.0.0.1:5888 \
npm run dev -w @vibe-visualization/market-daily -- \
  --host 127.0.0.1 --port 5891
```

打开 `http://127.0.0.1:5888`。

## AI 配置

常用环境变量：

```text
VIBE_VIS_MODEL_DEFAULT_ADAPTER=openai-compatible
VIBE_VIS_OPENAI_BASE_URL=https://api.openai.com/v1
VIBE_VIS_OPENAI_API_KEY=
VIBE_VIS_OPENAI_MODEL=gpt-5.6

VIBE_VIS_ANTHROPIC_API_KEY=
VIBE_VIS_ANTHROPIC_MODEL=claude-sonnet-4-5

VIBE_VIS_AGENT_DEFAULT_ADAPTER=hermes-webui
VIBE_VIS_HERMES_WEBUI_BASE_URL=http://127.0.0.1:8787
```

API Key 只保存在服务端，不会下发给 Module 前端。

## 验证

```bash
npm test
npm run typecheck
npm run build
services/api/.venv/bin/pytest -q
npm run test:e2e
```

## 文档

- [简化版基座设计](docs/superpowers/specs/2026-07-20-vibe-base-simplified-design.md)
- [Gateway 分离设计](docs/superpowers/specs/2026-07-20-gateway-separation-design.md)
- [Vibe HTML 规范](docs/vibe-html.md)
