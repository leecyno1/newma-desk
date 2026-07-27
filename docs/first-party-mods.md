# 官方 Mod 商店与原生 Mods 接入说明

日期：2026-07-23

## 接入原则

市场行情终端的图表、数据协议、Agent 上下文和与其他 Mods 的边界见
[`market-terminal.md`](./market-terminal.md)。

Vibe Research 与 Vibe Trading 的源码工程已收纳到 `mod-projects/`，作为 Newma-Dock 的内置领域运行时。构建产物、领域 API 和静态页面都由 Newma-Dock 统一挂载，每个侧边栏入口加载对应的内置路由：

```text
Newma-Dock
├── Vibe Investment Mod -> /mod-runtime/research -> /api/research
├── Vibe Trading Mod    -> /mod-runtime/trading  -> /api/trading
├── InStock Analysis    -> 127.0.0.1:9988 -> Newma-Dock 统一行情
├── Orchestra Mods      -> 127.0.0.1:3001 -> Orchestra API 8011
└── Deepsee Mod         -> Deepsee /embed/*      -> Deepsee backend
```

这些内置前端在 iframe 中运行时自动隐藏自身导航，所以用户只看到 Newma-Dock 的统一侧边栏。Mod 内部跳转、表单状态、回测运行记录和领域文件仍由对应领域运行时管理；Agent 会话、模型选择和按 Mod 记忆统一由 Desk 管理。

需要 AI 的页面统一调用 Newma-Dock Agent Gateway。Desk 会把当前 Mod ID、用户 ID 和 Gateway 地址下发给 iframe；Mod 也会主动发送 `vibedesk:ready` 请求配置，避免大型前端包加载较慢时错过一次性的 iframe `load` 消息。

```text
Investment / Trading Mod
        -> Newma-Dock Agent Gateway
        -> 用户在“Agent 设置”中选择的本机 CLI 或 Hermes
```

Model Gateway 仍是另一条独立链路，不会自动串到 Agent 后面。

这里的 `Vibe Investment` 是 Vibe-Research 在 Newma-Dock 中的产品名称，上游仓库名称和同步方式不改变。

统一目录结构：

```text
newma-dock/
├── mods/                         # Mod 商店与路由 Manifest
├── mod-projects/
│   ├── vibe-research/             # 投研 Mods 源码和独立后端
│   └── vibe-trading/              # 量化/交易 Mods 源码和独立后端
└── services/                     # Newma-Dock 中台与通用能力
```

## 商店结构

所有预制 Mod 已从集中式集成清单拆分到项目根目录：

```text
mods/
├── store.json
├── daily-review/mod.json
├── alpha-lab/mod.json
├── backtest-lab/mod.json
└── ...
```

`store.json` 负责商店顺序、内置默认标记和 Git 安装源；每个 `mod.json` 只描述一个 Mod。标准配置会把商店全部 Mods 注册到侧边栏。通过商店安装或更新时，API 会通过标准 Git 拉取优先读取 GitHub，失败后尝试 Gitee；Raw HTTP 仅作为备用，再通过控制面创建并发布 Mod 修订。

多页面项目使用 Manifest `navigation.directory` 接入二级侧边栏。同一套件仍按“一页一 Mod”保留独立权限、生命周期和 Agent Context，只在导航层聚合。用户可以在 Newma-Dock 中覆盖默认目录、拖拽排序、移动页面和冻结位置；本地偏好不会反写上游项目或商店 Manifest。每个二级目录底部由 Desk 自动提供“项目设置”，集中展示套件页面、统一数据路由和 Agent 设置入口。

新 Mod 的 Data Action 可以只声明 Capability、权限和输入输出 Schema，不再写 Provider、API 地址或密钥。省略 `binding.service` 后，Desk 会根据 `directory.id`、当前用户与 Workspace 自动选择数据服务，并允许用户在项目设置中覆盖。固定 `service` 的旧写法继续兼容。

Vibe Research 的 8 个 Mods 和 Vibe Trading 的 6 个 Mods 标记为内置默认 Mod，新环境无需再指定外部工程目录。重复的“投研 AI 设置”和“量化 Agent”已下架，由 Desk 的 Agent 设置与右侧统一 Agent 抽屉替代。

InStock 的 CZSC/轮动页面以及 Orchestra 的八个顶层工作区也作为默认 Mods 安装。它们继续以独立服务运行，但导航、项目设置、Agent Context、数据路由和统一启动由 Desk 管理。

## Mod 清单

### Newma-Dock 图表工作区

以下五个 Level 3 Mods 共享 `@newma-dock/chart-kit`、统一数据能力和同一个市场前端运行时，但在商店、侧边栏、本地状态及 Agent Context 中保持独立：

| Mod | 共享运行时入口 |
| --- | --- |
| 市场扫描器 | `/mods/market-daily/?workspace=scanner` |
| 多周期看盘 | `/mods/market-daily/?workspace=multi-timeframe` |
| 相对强弱地图 | `/mods/market-daily/?workspace=relative-strength` |
| 事件时间轴 | `/mods/market-daily/?workspace=event-timeline` |
| 交易回放室 | `/mods/market-daily/?workspace=trading-replay` |

这些 Mods 统一收发 `security.selected`，并把当前标的、筛选条件、图表状态、事件与回放进度发布给 Desk 右侧 Agent。Desk Agent 还可以通过反向 UI Action 桥安全切换周期、设置指标、创建价格预警和保存布局；事件保留真实来源与证据 ID，交易回放可沉淀为 Newma-Dock Replay Artifact。

市场终端及上述五个工作区默认聚合到“市场 → 行情工具”二级目录。Deepsee 的 11 个页面默认聚合到“Deepsee → Deepsee 功能”二级目录，避免母侧边栏被同一上游项目的页面占满。用户可随时在“界面设置”中改为一级显示或创建自己的二级目录。

市场终端已作为首个统一数据接口示例：嵌入 Desk 时通过宿主 Action 请求 `market.quote`、`market.ohlcv`、`market.overview` 等能力，不感知具体 Provider；独立调试时仍保留固定 `market-data` 客户端作为兼容回退。

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

### Vibe Trading

| Mod | 原生路由 |
| --- | --- |
| 量化总览 | `/` |
| 因子实验室 | `/alpha-zoo` |
| 回测实验室 | `/reports` |
| 相关性分析 | `/correlation` |
| 交易台 | `/runtime` |
| 量化系统设置 | `/settings` |

Run Detail、因子详情、因子比较等二级页面继续由 Vibe Trading 内部链接进入，不重复占用 Newma-Dock 一级侧边栏。

### Deepsee

Deepsee 在 `http://127.0.0.1:8001` 独立运行。Newma-Dock 只安装页面入口，SQLite、WeChat API、邮件、新闻、同步任务和消息发送仍由 Deepsee 管理。

| Mod | 嵌入路由 |
| --- | --- |
| Deepsee 数据看板 | `/embed/dashboard` |
| Deepsee AI 分析 | `/embed/ai-summary` |
| Deepsee 新闻 | `/embed/news-agg` |
| Deepsee 微信 | `/embed/message-list` |
| Deepsee 邮件 | `/embed/email-messages` |
| Deepsee 会议 | `/embed/minutes-agg` |
| Deepsee 自媒体 | `/embed/folo-agg` |
| Deepsee 公众号 | `/embed/mp-agg` |
| Deepsee 消息群发 | `/embed/send-management` |
| Deepsee 联系人评分 | `/embed/contact-management` |
| Deepsee 设置 | `/embed/function-settings` |

这些页面由 [`deepsee-suite/suite.json`](../mods/deepsee-suite/suite.json) 一次声明，Suite Discovery 自动展开为 11 个可独立安装、独立打开和独立授权的 Mods。设置页通过 `navigation.role = settings` 自动进入二级侧边栏设置区，不再由 Desk 根据 Deepsee 名称硬编码。

### InStock 分析

InStock 保持独立 Tornado 服务，默认端口为 `9988`。页面不依赖 MySQL，行情通过 Newma-Dock 的统一市场数据接口取得；分析结果又以 `instock-analysis` Provider 暴露给其他 Mod 和 Agent。

| Mod | 嵌入路由 | 统一能力 |
| --- | --- | --- |
| CZSC 缠论结构 | `/mods/czsc` | `analysis.czsc` |
| 行业与 ETF 轮动 | `/mods/rotation` | `analysis.rotation` |

两个页面聚合到“量化 → InStock 分析”二级目录，并由 Desk 自动补充项目设置页。
Desk 右侧 Agent 的问答与修改模式会把这两个 Mod 定位到 InStock 源码目录，而不是 Newma-Dock 根目录。

### Orchestra 投委会

Orchestra 保持前后端独立服务：前端 `3001`，API `8011`。Newma-Dock 不接管其投委会执行、用户、组合、密钥或持久化，只负责按工作区嵌入、二级导航、主题环境和 Agent Context。

| Mod | 工作区参数 |
| --- | --- |
| 投委会 | `workspace=committee` |
| 历史讨论 | `workspace=history` |
| 研究成果 | `workspace=reports` |
| 19 席位 | `workspace=agents` |
| Skills | `workspace=skills` |
| 数据工具 | `workspace=data` |
| 账户与组合 | `workspace=workspace` |
| 运行设置 | `workspace=settings` |

八个页面聚合到“投决 → Orchestra 投委会”二级目录。项目内部主导航在嵌入模式下隐藏，避免与 Newma-Dock 的母侧边栏重复。
Desk 右侧 Agent 会使用 Orchestra 前后端的共同项目目录，因此同一次 Mod 修改任务可以同时理解界面和服务端契约。

## 本地启动

推荐从 Newma-Dock 根目录统一启动。该命令会构建 `mod-projects/` 中的 Research / Trading 前端，并把两套领域 API 与静态运行时挂载到 Newma-Dock；Deepsee 仍保持独立运行：

```bash
npm run dev:stack
```

Research / Trading 不再占用独立端口，也不再作为独立产品入口运行。统一地址为：

- Research API：`/api/research`
- Trading API：`/api/trading`
- Research Mod 运行时：`/mod-runtime/research`
- Trading Mod 运行时：`/mod-runtime/trading`
- InStock：`http://127.0.0.1:9988`
- Orchestra 前端：`http://127.0.0.1:3001`
- Orchestra API：`http://127.0.0.1:8011`

可用 `npm run dev:status` 查看完整状态。该命令默认只以核心运行时是否就绪决定退出状态；InStock、Orchestra、Seven Cycle 或 Deepsee 不可用时会明确显示降级，但不会阻断 Desk。发布前需要检查全部可选 Mod 时使用 `npm run dev:status -- --strict`。

统一启动器会先完成核心运行时，再并行启动可选 Mod。Seven Cycle 的健康端点返回 `409` 且声明数据 freshness 不可用时，表示进程存活但数据降级，不再被误判为整套 Newma-Dock 启动失败。

### 外部 Mod 运行时发现

外部 Mod 的路径、入口和健康检查统一声明在
[`config/external-mod-runtimes.json`](../config/external-mod-runtimes.json)。该 Runtime Descriptor 不保存账号、密钥或个人绝对路径；Node 启动器与 Python Agent Gateway 使用不同 Adapter 读取同一个 Interface，避免同一 Mod 的工作区和端口散落在多份配置里。

默认发现根目录：

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `NEWMA_DOCK_PROJECTS_ROOT` | Newma-Dock 仓库的父目录 | 常规项目工作区 |
| `NEWMA_DOCK_DESKTOP_PROJECTS_ROOT` | `~/Desktop/Projects` | 桌面项目工作区 |

每个外部 Mod 仍可用 `NEWMA_DOCK_*_WORKSPACE` 精确覆盖工作区，用 `NEWMA_DOCK_*_WEB_URL` / `NEWMA_DOCK_*_API_URL` 覆盖入口。空值会继续使用自动发现。入口指向本机且工作区存在时，统一启动器管理其进程；入口指向远程地址时只做健康检查；工作区缺失时显示降级但不阻断核心运行时。

新增 External Mod Runtime 时，应在 Descriptor 中加入稳定 ID、工作区候选、入口 origin 和 health path，并为 Node/Python Adapter 的公共 Interface 补测试，不要把机器路径写入启动脚本或 `.env.example`。

独立启动 Research / Trading 只用于上游源码调试，不再属于 Newma-Dock 的标准运行和交付方式。

### Deepsee

```bash
cd /path/to/Deepsee
bash scripts/manage.sh start
```

确认 `http://127.0.0.1:8001/api/health` 可以访问。Deepsee Mods 不负责安装或启动该服务。

### Newma-Dock

默认工作目录已指向项目内的两个 Mod 工程。只有在主动使用外部副本时才需要覆盖：

```bash
export NEWMA_DOCK_INVESTMENT_WORKSPACE=/absolute/path/to/vibe-research
export NEWMA_DOCK_TRADING_WORKSPACE=/absolute/path/to/vibe-trading
```

```bash
services/api/.venv/bin/python -m uvicorn vibe_visualization_api.main:app \
  --app-dir services/api --host 127.0.0.1 --port 8911
```

注册商店全部 Mods：

```bash
npm run mods:register
```

同步已有环境的标准配置时也可以执行：

```bash
npm run mods:standardize
```

完成后全部商店 Mods 会出现在 Newma-Dock 左侧导航中；商店继续提供 Git 来源、安装状态和更新入口。

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8911 \
VITE_MOD_ORIGIN=http://127.0.0.1:5891 \
npm run dev:shell -- --host 127.0.0.1 --port 5888
```

打开 `http://127.0.0.1:5888`。

## 地址覆盖

生产环境或不同端口部署时，在注册前设置：

```bash
NEWMA_DOCK_INVESTMENT_WEB_URL=https://investment.example.com \
NEWMA_DOCK_TRADING_WEB_URL=https://trading.example.com \
NEWMA_DOCK_DEEPSEE_WEB_URL=https://deepsee.example.com \
NEWMA_DOCK_CONTROL_PLANE_URL=https://desk-api.example.com \
npm run mods:register
```

四个地址都必须是 HTTP(S) origin，不能包含账号、密码、查询参数或路径。云端建议给 Newma-Dock、Investment、Trading 和 Deepsee 使用独立子域名，再由反向代理映射到各自服务。

## 商店与上游同步

- Newma-Dock 根仓库保存路由与导航 Manifest；两个内置 Mod 工程位于 `mod-projects/` 并保留各自独立 Git 历史。
- 上游新增一级页面时，在 `mods/<mod-id>/mod.json` 新增一个独立商店条目，并加入 `mods/store.json`。
- 上游页面内部实现更新时，Newma-Dock 无需同步页面代码。
- 上游路由变化时，修改对应 Mod 的 `runtime.route`。已安装用户可在商店点击“从 Git 更新”。
- 商店内容推送到 GitHub/Gitee 后，用户安装时会直接读取 Git 中的版本。
- 任一上游服务停止，不会影响另一套上游后端和 Newma-Dock 控制面。
