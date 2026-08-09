# 官方 Mod 商店与原生 Mods 接入说明

日期：2026-07-29

## 接入原则

市场行情终端的图表、数据协议、Agent 上下文和与其他 Mods 的边界见
[`market-terminal.md`](./market-terminal.md)。

Vibe Research 与 Vibe Trading 的源码工程已收纳到 `mod-projects/`，作为 Newma-Desk 的内置领域运行时。构建产物、领域 API 和静态页面都由 Newma-Desk 统一挂载，每个侧边栏入口加载对应的内置路由：

```text
Newma-Desk
├── Vibe Research Mod   -> /mod-runtime/research -> /api/research
├── Vibe Trading Mod    -> /mod-runtime/trading  -> /api/trading
├── InStock Analysis    -> 127.0.0.1:9988 -> Newma-Desk 统一行情
├── Orchestra Mods      -> 127.0.0.1:3001 -> Orchestra API 8011
└── Deepsee Mod         -> Deepsee /embed/*      -> Deepsee backend
```

这些内置前端在 iframe 中运行时自动隐藏自身导航，所以用户只看到 Newma-Desk 的统一侧边栏。Mod 内部跳转、表单状态、回测运行记录和领域文件仍由对应领域运行时管理；Agent 会话、模型选择和按 Mod 记忆统一由 Desk 管理。

需要 AI 的页面统一调用 Newma-Desk Agent Gateway。Desk 会把当前 Mod ID、用户 ID 和 Gateway 地址下发给 iframe；Mod 也会主动发送 `vibedesk:ready` 请求配置，避免大型前端包加载较慢时错过一次性的 iframe `load` 消息。

```text
Research / Trading Mod
        -> Newma-Desk Agent Gateway
        -> 用户在“Agent 设置”中选择的本机 CLI 或 Hermes
```

Model Gateway 仍是另一条独立链路，不会自动串到 Agent 后面。

Vibe Research 与 Vibe Trading 保留为完整源码和运行来源，并分别作为不可拆分的项目组进入一个投资栏目。一级导航固定为十四个核心栏目与“其他”，稳定栏目 ID 不随来源仓库、页面路由或服务地址改变；完整规则见 [`investment-domain-mod-standard.md`](./investment-domain-mod-standard.md)。

统一目录结构：

```text
newma-desk/
├── mods/                         # Mod 商店与路由 Manifest
├── mod-projects/
│   ├── vibe-research/             # 投研 Mods 源码和独立后端
│   └── vibe-trading/              # 量化/交易 Mods 源码和独立后端
└── services/                     # Newma-Desk 中台与通用能力
```

## 商店结构

所有预制 Mod 已从集中式集成清单拆分到项目根目录：

```text
mods/
├── store.json
├── research-suite/suite.json
├── trading-suite/suite.json
├── portfolio-suite/suite.json
├── deepsee-suite/suite.json
├── orchestra-suite/suite.json
└── ...
```

`store.json` 负责商店顺序、内置默认标记和 Git 安装源；单页 Mod 继续使用 `mod.json`，多页面项目收敛到 `suite.json`。标准配置会把商店全部 Mods 注册到侧边栏。通过商店安装或更新时，API 会通过标准 Git 拉取优先读取 GitHub，失败后尝试 Gitee；Raw HTTP 仅作为备用，再通过控制面创建并发布 Mod 修订。

多页面项目使用 Manifest `navigation.project` 声明唯一所属栏目，用与 Suite ID 相同的 `navigation.directory.id` 声明完整项目组。页面仍按“一页一 Mod”保留独立权限、生命周期和 Agent Context，但不能跨栏目或跨项目组拆分；一级栏固定显示十四个核心栏目与“其他”，二级面板按完整项目列出原有页面和项目设置。

新 Mod 的 Data Action 可以只声明 Capability、权限和输入输出 Schema，不再写 Provider、API 地址或密钥。省略 `binding.service` 后，Desk 会根据完整项目的 `directory.id`、当前用户与 Workspace 自动选择数据服务，并允许用户在项目设置中覆盖；单页 Mod 使用自身 ID。栏目 `project.id` 只负责导航归属，不承担项目数据作用域。

Vibe Research 与 Vibe Trading 的页面现已分别收敛到 `research-suite` 与 `trading-suite`，展开后的 Mod ID、原生路由、权限和导航保持兼容；重复的“投研 AI 设置”和“量化 Agent”已下架，由 Desk 的 Agent 设置与右侧统一 Agent 抽屉替代。

InStock 的 CZSC/轮动页面以及 Orchestra 的八个顶层工作区也作为默认 Mods 安装。它们继续以独立服务运行，但导航、项目设置、Agent Context、数据路由和统一启动由 Desk 管理。

## Mod 清单

### Newma-Desk 图表工作区

以下五个 Level 3 Mods 共享 `@newma-desk/chart-kit`、统一数据能力和同一个市场前端运行时，但在商店、侧边栏、本地状态及 Agent Context 中保持独立：

| Mod | 共享运行时入口 |
| --- | --- |
| 市场扫描器 | `/mods/market-daily/?workspace=scanner` |
| 多周期看盘 | `/mods/market-daily/?workspace=multi-timeframe` |
| 相对强弱地图 | `/mods/market-daily/?workspace=relative-strength` |
| 事件时间轴 | `/mods/market-daily/?workspace=event-timeline` |
| 交易回放室 | `/mods/market-daily/?workspace=trading-replay` |

这些 Mods 统一收发 `security.selected`，并把当前标的、筛选条件、图表状态、事件与回放进度发布给 Desk 右侧 Agent。Desk Agent 还可以通过反向 UI Action 桥安全切换周期、设置指标、创建价格预警和保存布局；事件保留真实来源与证据 ID，交易回放可沉淀为 Newma-Desk Replay Artifact。

Deepsee 的 11 个页面作为一个完整项目进入“其他 → DeepSee”。行情终端的六个页面作为一个完整项目进入“市场面 → 行情工具”，不再按页面用途拆到个股研究或战术择时。

市场终端已作为首个统一数据接口示例：嵌入 Desk 时通过宿主 Action 请求 `market.quote`、`market.ohlcv`、`market.overview` 等能力，不感知具体 Provider；独立调试时仍保留固定 `market-data` 客户端作为兼容回退。

### Vibe Research

这些页面由 [`research-suite/suite.json`](../mods/research-suite/suite.json) 一次声明，再由 Suite Discovery 展开为独立安装项。Vibe Research 作为完整项目整体进入“宏观面”，项目内保留全部页面、共同运行来源、版本和 Agent Workspace。

| Mod | 原生路由 |
| --- | --- |
| 每日复盘 | `/daily-review` |
| 宏观观察 | `/macro-monitor` |
| 资讯雷达 | `/intel` |
| 自选股 | `/watchlist` |
| 研究机会池 | `/idea-funnel` |
| 个股研究 | `/stock-data` |
| 产业链研究 | `/sectors` |
| 基金与 ETF 研究 | `/etf-research` |
| 催化剂日历 | `/catalyst-calendar` |
| 财报研究 | `/earnings-workbench` |
| 同业比较 | `/peer-comparison` |
| 预测与估值 | `/valuation-workbench` |
| 研究备忘录 | `/research-memo` |
| 投资逻辑 | `/thesis-tracker` |
| 研究档案 | `/my-reports` |
| 研究记录 | `/notes` |

催化剂日历与市场侧“事件时间轴”共享 `newma-desk.catalyst-calendar.v1` 合同。日历负责未来事件、周期观察窗、确认/失效条件和结果归档；事件时间轴负责已发生事件与历史行情叠加。详细标准见 [`catalyst-calendar-standard.md`](./catalyst-calendar-standard.md)。

宏观观察使用 `newma-desk.macro-monitor.v1` 合同，把增长、价格、流动性、经济事件、来源状态和缺口统一进入 Desk Agent Context。它与七周期研究互补：宏观观察呈现可核验事实与发布日历，七周期只提供通过门槛的概率观察窗。
详细标准见 [`macro-monitor-standard.md`](./macro-monitor-standard.md)。

研究机会池使用 `newma-desk.idea-funnel.v1` 合同，把市场扫描、主题、资讯、催化剂、产业链和自选线索整理为双向假设、筛选方法、优先级评分、证伪条件与研究任务，再交给投资逻辑、财报、同业、估值或研究备忘录。其“流程总览”实时汇总既有研究缓存中的复核到期、逾期任务、陈旧来源与档案缺口，不复制底层数据或新增存储。筛选结果与流程完整度始终不是投资结论。详细标准见 [`idea-funnel-standard.md`](./idea-funnel-standard.md)。

投资逻辑使用 `newma-desk.investment-thesis.v1` 合同，把个股核心论点、3–5 个支柱、3–5 个证伪风险、催化剂、证据、确信度和阶段复盘存入 Desk-managed Storage。它只记录研究状态，不包含仓位或交易动作；右侧统一 Agent 可以基于当前证券继续补充长周期行情、财务、公告、新闻、宏观和产业链证据。详细标准见 [`investment-thesis-standard.md`](./investment-thesis-standard.md)。

研究备忘录使用 `newma-desk.research-memo.v1` 合同，通过来源 Mod 与档案 ID 引用投资逻辑、财报、同业、估值和催化剂，不复制底层档案。它负责收敛结论、差异认知、三情景、反方风险、监控面板和版本变化，并可继续交给 Desk Agent 或 Orchestra 讨论。详细标准见 [`research-memo-standard.md`](./research-memo-standard.md)。

研究记录使用 `newma-desk.research-records.v1` 合同，把每日复盘、资讯要点和 Agent 问答写入 Desk-managed Storage，并自动迁移旧 `vr-notes` 本地记录。正文由轻量安全的 ResearchText Module 渲染，不执行 HTML 或脚本；右侧 Agent 可以总结当前记录、查找关联档案并生成后续研究清单。详细标准见 [`research-record-standard.md`](./research-record-standard.md)。

### 组合资产中心

组合总览使用 `newma-desk.portfolio-research-coverage.v1` 合同，把当前持仓与 Research Archive Index 按市场和证券代码即时匹配，显示核心研究、支持分析、复核到期与来源回跳。该视图只读取引用，不复制研究正文、不持久化派生结果，也不生成持仓评分或交易信号；研究索引不可用时，组合账本和行情继续独立工作。旧 Vibe Research 持仓只允许用户在“组合设置”中明确迁移，不会在读取组合或创建工作区时自动导入。详细标准见 [`portfolio-research-coverage-standard.md`](./portfolio-research-coverage-standard.md)。

### Vibe Trading

这些页面由 [`trading-suite/suite.json`](../mods/trading-suite/suite.json) 一次声明，再由 Suite Discovery 展开为独立安装项。Vibe Trading 作为完整项目整体进入“量化研究”，交易台与设置仍保留在项目内部。

| Mod | 原生路由 |
| --- | --- |
| 量化总览 | `/` |
| 因子实验室 | `/alpha-zoo` |
| 回测实验室 | `/reports` |
| 相关性分析 | `/correlation` |
| 交易台 | `/runtime` |
| 量化系统设置 | `/settings` |

Run Detail、因子详情、因子比较等详情页继续由 Vibe Trading 页面内部链接进入，不额外占用 Project Rail 或 Project Panel 页面列表。

### Deepsee

Deepsee 在 `http://127.0.0.1:8001` 独立运行。Newma-Desk 只安装页面入口，SQLite、WeChat API、邮件、新闻、同步任务和消息发送仍由 Deepsee 管理。

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

这些页面由 [`deepsee-suite/suite.json`](../mods/deepsee-suite/suite.json) 一次声明，Suite Discovery 自动展开为 11 个可独立安装、独立打开和独立授权的 Mods。全部页面进入其他，并由共享 `deepsee-suite` directory 聚合为一个 `DeepSee` 二级目录。

### InStock 分析

InStock 保持独立 Tornado 服务，默认端口为 `9988`。页面不依赖 MySQL，行情通过 Newma-Desk 的统一市场数据接口取得；分析结果又以 `instock-analysis` Provider 暴露给其他 Mod 和 Agent。

| Mod | 嵌入路由 | 统一能力 |
| --- | --- | --- |
| CZSC 缠论结构 | `/mods/czsc` | `analysis.czsc` |
| 行业与 ETF 轮动 | `/mods/rotation` | `analysis.rotation` |

CZSC 缠论结构进入资金面，行业与 ETF 轮动进入战术择时；旧 `instock-suite` directory 只保留为来源内部分组兼容信息。
Desk 右侧 Agent 的问答与修改模式会把这两个 Mod 定位到 InStock 源码目录，而不是 Newma-Desk 根目录。

### Orchestra 投委会

Orchestra 保持前后端独立服务：前端 `3001`，API `8011`。Newma-Desk 不接管其投委会执行、用户、组合、密钥或持久化，只负责按工作区嵌入、项目导航、主题环境和 Agent Context。

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

投委讨论、历史、报告、席位、Skills 和数据工具进入投决会；账户与组合进入交易、风控与组合管理；运行设置进入其他。项目内部主导航在嵌入模式下隐藏，避免与 Newma-Desk 领域导航重复。
Desk 右侧 Agent 会使用 Orchestra 前后端的共同项目目录，因此同一次 Mod 修改任务可以同时理解界面和服务端契约。

## 本地启动

推荐从 Newma-Desk 根目录统一启动。该命令会构建 `mod-projects/` 中的 Research / Trading 前端，并把两套领域 API 与静态运行时挂载到 Newma-Desk；Deepsee 仍保持独立运行：

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

统一启动器会先完成核心运行时，再并行启动可选 Mod。Seven Cycle 的健康端点返回 `409` 且声明数据 freshness 不可用时，表示进程存活但数据降级，不再被误判为整套 Newma-Desk 启动失败。

### 外部 Mod 运行时发现

外部 Mod 的路径、入口和健康检查统一声明在
[`config/external-mod-runtimes.json`](../config/external-mod-runtimes.json)。该 Runtime Descriptor 不保存账号、密钥或个人绝对路径；Node 启动器与 Python Agent Gateway 使用不同 Adapter 读取同一个 Interface，避免同一 Mod 的工作区和端口散落在多份配置里。

默认发现根目录：

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `NEWMA_DESK_PROJECTS_ROOT` | Newma-Desk 仓库的父目录 | 常规项目工作区 |
| `NEWMA_DESK_DESKTOP_PROJECTS_ROOT` | `~/Desktop/Projects` | 桌面项目工作区 |

每个外部 Mod 仍可用 `NEWMA_DESK_*_WORKSPACE` 精确覆盖工作区，用 `NEWMA_DESK_*_WEB_URL` / `NEWMA_DESK_*_API_URL` 覆盖入口。空值会继续使用自动发现。入口指向本机且工作区存在时，统一启动器管理其进程；入口指向远程地址时只做健康检查；工作区缺失时显示降级但不阻断核心运行时。

新增 External Mod Runtime 时，应在 Descriptor 中加入稳定 ID、工作区候选、入口 origin 和 health path，并为 Node/Python Adapter 的公共 Interface 补测试，不要把机器路径写入启动脚本或 `.env.example`。

独立启动 Research / Trading 只用于上游源码调试，不再属于 Newma-Desk 的标准运行和交付方式。

### Deepsee

```bash
cd /path/to/Deepsee
bash scripts/manage.sh start
```

确认 `http://127.0.0.1:8001/api/health` 可以访问。Deepsee Mods 不负责安装或启动该服务。

### Newma-Desk

默认工作目录已指向项目内的两个 Mod 工程。只有在主动使用外部副本时才需要覆盖：

```bash
export NEWMA_DESK_INVESTMENT_WORKSPACE=/absolute/path/to/vibe-research
export NEWMA_DESK_TRADING_WORKSPACE=/absolute/path/to/vibe-trading
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

完成后全部商店 Mods 会出现在 Newma-Desk 左侧导航中；商店继续提供 Git 来源、安装状态和更新入口。

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8911 \
VITE_MOD_ORIGIN=http://127.0.0.1:5891 \
npm run dev:shell -- --host 127.0.0.1 --port 5888
```

打开 `http://127.0.0.1:5888`。

## 地址覆盖

生产环境或不同端口部署时，在注册前设置：

```bash
NEWMA_DESK_INVESTMENT_WEB_URL=https://investment.example.com \
NEWMA_DESK_TRADING_WEB_URL=https://trading.example.com \
NEWMA_DESK_DEEPSEE_WEB_URL=https://deepsee.example.com \
NEWMA_DESK_CONTROL_PLANE_URL=https://desk-api.example.com \
npm run mods:register
```

四个地址都必须是 HTTP(S) origin，不能包含账号、密码、查询参数或路径。云端建议给 Newma-Desk、Investment、Trading 和 Deepsee 使用独立子域名，再由反向代理映射到各自服务。

## 商店与上游同步

- Newma-Desk 根仓库保存路由与导航 Manifest；两个内置 Mod 工程位于 `mod-projects/` 并保留各自独立 Git 历史。
- 上游新增可独立运行页面时，在现有 Suite 的 `pages[]` 中追加页面；单页项目才使用 `mods/<mod-id>/mod.json`。新增页面继承同一栏目和完整项目身份，不新增一级栏目，也不另建 Suite。
- 上游页面内部实现更新时，Newma-Desk 无需同步页面代码。
- 上游路由变化时，修改对应 Mod 的 `runtime.route`。已安装用户可在商店点击“从 Git 更新”。
- 商店内容推送到 GitHub/Gitee 后，用户安装时会直接读取 Git 中的版本。
- 任一上游服务停止，不会影响另一套上游后端和 Newma-Desk 控制面。
