# 第一批原生 Mods 接入说明

日期：2026-07-21

## 接入原则

VibeDesk 不复制 Vibe Investment 或 Vibe Trading 的业务页面，也不合并它们的后端。每个侧边栏入口直接加载上游原生路由：

```text
VibeDesk
├── Vibe Investment Mod -> Vibe-Research frontend -> Vibe-Research backend
└── Vibe Trading Mod    -> Vibe-Trading frontend  -> Vibe-Trading backend
```

两个上游前端在 iframe 中运行时自动隐藏自身侧边栏，所以用户只看到 VibeDesk 的统一导航。Mod 内部跳转、表单状态、Agent Session、回测运行记录和文件存储仍由对应上游管理。

这里的 `Vibe Investment` 是 Vibe-Research 在 VibeDesk 中的产品名称，上游仓库名称和同步方式不改变。

## Mod 清单

### Vibe Investment

| Mod | 原生路由 |
| --- | --- |
| 每日复盘 | `/daily-review` |
| 资讯雷达 | `/intel` |
| 自选股 | `/watchlist` |
| 我的持仓 | `/portfolio` |
| 个股研究 | `/stock-data` |
| 产业链研究 | `/sectors` |
| 我的研报 | `/my-reports` |
| 研究记录 | `/notes` |
| 投研 AI 设置 | `/settings` |

### Vibe Trading

| Mod | 原生路由 |
| --- | --- |
| 量化总览 | `/` |
| 量化 Agent | `/agent` |
| 因子实验室 | `/alpha-zoo` |
| 回测实验室 | `/reports` |
| 相关性分析 | `/correlation` |
| 交易台 | `/runtime` |
| 量化系统设置 | `/settings` |

Run Detail、因子详情、因子比较等二级页面继续由 Vibe Trading 内部链接进入，不重复占用 VibeDesk 一级侧边栏。

## 本地启动

以下命令分别在独立终端执行。

### 1. Vibe Investment

```bash
cd ../Vibe-Research/backend
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8900
```

```bash
cd ../Vibe-Research/frontend
VITE_API_URL=http://127.0.0.1:8900 \
npm run dev -- --host 127.0.0.1 --port 5899
```

### 2. Vibe Trading

```bash
cd "/Volumes/PSSD/Projects/港大trading os/Vibe-Trading"
.venv/bin/python -m cli serve --port 8899
```

```bash
cd "/Volumes/PSSD/Projects/港大trading os/Vibe-Trading/frontend"
VITE_API_URL=http://127.0.0.1:8899 \
npm run dev -- --host 127.0.0.1 --port 5901
```

### 3. VibeDesk

```bash
services/api/.venv/bin/python -m uvicorn vibe_visualization_api.main:app \
  --app-dir services/api --host 127.0.0.1 --port 8901
```

注册或更新第一批 Mod：

```bash
npm run mods:register
```

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8901 \
VITE_MOD_ORIGIN=http://127.0.0.1:5891 \
npm run dev:shell -- --host 127.0.0.1 --port 5888
```

打开 `http://127.0.0.1:5888`。

## 地址覆盖

生产环境或不同端口部署时，在注册前设置：

```bash
VIBEDESK_INVESTMENT_WEB_URL=https://investment.example.com \
VIBEDESK_TRADING_WEB_URL=https://trading.example.com \
VIBEDESK_CONTROL_PLANE_URL=https://desk-api.example.com \
npm run mods:register
```

三个地址都必须是 HTTP(S) origin，不能包含账号、密码、查询参数或路径。云端可以使用三个子域名，也可以由反向代理将它们映射到独立服务。

## 上游同步

- VibeDesk 只保存路由与导航 Manifest，不导入上游源码。
- 上游新增一级页面时，在对应 `integration.json` 中增加一条 Mod 配置。
- 上游页面内部实现更新时，VibeDesk 无需同步页面代码。
- 上游路由变化时，修改 `route` 后重新运行 `npm run mods:register`。
- 任一上游服务停止，不会影响另一套上游后端和 VibeDesk 控制面。
