# 官方 Mod 商店与原生 Mods 接入说明

更新日期：2026-08-26

## 接入原则

市场行情终端的图表、数据协议、Agent 上下文和与其他 Mods 的边界见
[`market-terminal.md`](./market-terminal.md)。

Vibe Research、Vibe Trading 和其他可见 Mod 的运行源码已收纳到 `bundled-runtimes/`。构建产物、领域 API 和静态页面由 Newma-Desk 统一挂载，每个侧边栏入口加载对应运行时：

```text
Newma-Desk
├── Vibe Research Mod   -> /mod-runtime/research -> /api/research
├── Vibe Trading Mod    -> /mod-runtime/trading  -> /api/trading
├── World Intelligence  -> 127.0.0.1:8501 -> /api/global-intel
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

Vibe Research 与 Vibe Trading 保留为完整源码和运行来源。导航描述可按业务职责拆成多个 Suite，但不会复制或拆分运行时；同一页面仍只有一个主归属。一级导航固定为 16 个投资模块，稳定栏目 ID 不随来源仓库、页面路由或服务地址改变；完整规则见 [`investment-domain-mod-standard.md`](./investment-domain-mod-standard.md)。

统一目录结构：

```text
newma-desk/
├── mods/                         # Mod 商店与路由 Manifest
├── bundled-runtimes/
│   ├── vibe-research/             # 投研 Mods 源码和独立后端
│   ├── vibe-trading/              # 量化/交易 Mods 源码和独立后端
│   ├── world-intel-mcp/            # 全球态势与事件数据平面
│   └── ...                         # Deepsee、InStock、基金、投决、创作等运行时
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

`store.json` 负责商店顺序、内置默认标记和 Git 安装源；单页 Mod 继续使用 `mod.json`，多页面项目收敛到 `suite.json`。新状态默认注册全球专题、政策、资金和基金研究等 20 个基础 Mod；其余项目由用户从商店安装。已有状态不会被默认注册重置。通过商店安装或更新时，API 会通过标准 Git 拉取优先读取 GitHub，失败后尝试 Gitee；Raw HTTP 仅作为备用，再通过控制面创建并发布 Mod 修订。

多页面项目使用 Manifest `navigation.project` 声明唯一所属栏目，用与 Suite ID 相同的 `navigation.directory.id` 保存数据与 Agent 作用域。页面仍按“一页一 Mod”保留独立权限、生命周期和 Agent Context。一级栏固定显示 16 个模块；二级面板直接显示页面，不再渲染来源项目文件夹，“栏目数据与能力”固定在面板底部。

新 Mod 的 Data Action 可以只声明 Capability、权限和输入输出 Schema，不再写 Provider、API 地址或密钥。省略 `binding.service` 后，Desk 会根据完整项目的 `directory.id`、当前用户与 Workspace 自动选择数据服务，并允许用户在项目设置中覆盖；单页 Mod 使用自身 ID。栏目 `project.id` 只负责导航归属，不承担项目数据作用域。

Vibe Trading 按量化研究和交易台拆成两个导航 Suite；Vibe Research 按公司、策略、行业和基金拆成多个导航 Suite。它们继续复用原运行时。新闻与舆情、催化剂日历复用 Research 运行时，但作为独立 Mod 进入“全球”。重复的“投研 AI 设置”和“量化 Agent”已下架，由 Desk 的 Agent 设置与右侧统一 Agent 抽屉替代。

InStock 的 CZSC/轮动页面以及 Orchestra 的八个顶层工作区保留在 Mod 商店中，用户安装后继续以独立服务运行；导航、项目设置、Agent Context、数据路由和统一启动由 Desk 管理。

## Mod 清单

### Newma-Desk 图表工作区

全球情报使用独立的 MapLibre GL + deck.gl 前端运行时，并由 `world-intel-mcp` 数据适配器提供全球态势、事件与静态地理数据。市场图表工具继续共享 `market-daily` 交易市场运行时：

| Mod | 共享运行时入口 |
| --- | --- |
| 全球情报 | `/mods/global-intelligence/` |
| 市场扫描器 | `/mods/market-daily/?workspace=scanner` |
| 多周期看盘 | `/mods/market-daily/?workspace=multi-timeframe` |
| 相对强弱地图 | `/mods/market-daily/?workspace=relative-strength` |
| 日线时间轴 | `/mods/market-daily/?workspace=event-timeline` |
| 交易回放室 | `/mods/market-daily/?workspace=trading-replay` |

全球情报发布 `newma-desk.global-intelligence.v1` Agent Context，包含地图图层、筛选、选中事件、来源健康和实时事件摘要。市场 Mods 统一收发 `security.selected`，并把当前标的、筛选条件、图表状态与回放进度发布给 Desk 右侧 Agent；Desk Agent 可通过反向 UI Action 桥安全切换周期、设置指标、创建价格预警和保存布局。

Deepsee 的 11 个页面进入一级模块“深瞳”。交易行情、日线时间轴与图表工具进入“市场”；全球情报、新闻与舆情和催化剂日历进入“全球”。

市场终端已作为首个统一数据接口示例：嵌入 Desk 时通过宿主 Action 请求 `market.quote`、`market.ohlcv`、`market.overview` 等能力，不感知具体 Provider；独立调试时仍保留固定 `market-data` 客户端作为兼容回退。

### Vibe Research

Vibe Research 按主职责拆成公司、策略、行业和基金四个导航 Suite，再由 Suite Discovery 展开。新闻与舆情、催化剂日历和宏观观察继续复用同一运行时，但拥有独立的模块归属。

| 一级模块 | Mod | 原生路由 |
| --- | --- | --- |
| 全球 | 新闻与舆情 / 催化剂日历 | `/intel` / `/catalyst-calendar` |
| 宏观 | 宏观观察 | `/macro-monitor` |
| 策略 | 研究机会池 | `/idea-funnel` |
| 行业 | 产业图谱 | `/sectors` |
| 基金 | ETF 研究 | `/etf-research` |
| 公司 | 财报、投资逻辑、同业、估值、备忘录、档案、记录 | `/earnings-workbench` 等 |

催化剂日历与市场侧“日线时间轴”共享 `newma-desk.catalyst-calendar.v1` 合同。日历负责未来事件、周期观察窗、确认/失效条件和结果归档；日线时间轴负责已发生事件与历史行情叠加。详细标准见 [`catalyst-calendar-standard.md`](./catalyst-calendar-standard.md)。

宏观观察使用 `newma-desk.macro-monitor.v1` 合同，把增长、价格、流动性、经济事件、来源状态和缺口统一进入 Desk Agent Context。它与周期叠加互补：宏观观察呈现可核验事实与发布日历，周期叠加只提供通过门槛的概率观察窗。
详细标准见 [`macro-monitor-standard.md`](./macro-monitor-standard.md)。

研究机会池使用 `newma-desk.idea-funnel.v1` 合同，把市场扫描、主题、资讯、催化剂、产业链和自选线索整理为双向假设、筛选方法、优先级评分、证伪条件与研究任务，再交给投资逻辑、财报、同业、估值或研究备忘录。其“流程总览”实时汇总既有研究缓存中的复核到期、逾期任务、陈旧来源与档案缺口，不复制底层数据或新增存储。筛选结果与流程完整度始终不是投资结论。详细标准见 [`idea-funnel-standard.md`](./idea-funnel-standard.md)。

投资逻辑使用 `newma-desk.investment-thesis.v1` 合同，把个股核心论点、3–5 个支柱、3–5 个证伪风险、催化剂、证据、确信度和阶段复盘存入 Desk-managed Storage。它只记录研究状态，不包含仓位或交易动作；右侧统一 Agent 可以基于当前证券继续补充长周期行情、财务、公告、新闻、宏观和产业链证据。详细标准见 [`investment-thesis-standard.md`](./investment-thesis-standard.md)。

研究备忘录使用 `newma-desk.research-memo.v1` 合同，通过来源 Mod 与档案 ID 引用投资逻辑、财报、同业、估值和催化剂，不复制底层档案。它负责收敛结论、差异认知、三情景、反方风险、监控面板和版本变化，并可继续交给 Desk Agent 或 Orchestra 讨论。详细标准见 [`research-memo-standard.md`](./research-memo-standard.md)。

研究记录使用 `newma-desk.research-records.v1` 合同，把每日复盘、资讯要点和 Agent 问答写入 Desk-managed Storage，并自动迁移旧 `vr-notes` 本地记录。正文由轻量安全的 ResearchText Module 渲染，不执行 HTML 或脚本；右侧 Agent 可以总结当前记录、查找关联档案并生成后续研究清单。详细标准见 [`research-record-standard.md`](./research-record-standard.md)。

### 组合资产中心

组合总览使用 `newma-desk.portfolio-research-coverage.v1` 合同，把当前持仓与 Research Archive Index 按市场和证券代码即时匹配，显示核心研究、支持分析、复核到期与来源回跳。该视图只读取引用，不复制研究正文、不持久化派生结果，也不生成持仓评分或交易信号；研究索引不可用时，组合账本和行情继续独立工作。旧 Vibe Research 持仓只允许用户在“组合设置”中明确迁移，不会在读取组合或创建工作区时自动导入。详细标准见 [`portfolio-research-coverage-standard.md`](./portfolio-research-coverage-standard.md)。

### Vibe Trading

这些页面复用同一 Vibe Trading 运行时。量化页面由 [`trading-suite/suite.json`](../mods/trading-suite/suite.json) 声明，交易台由 `trading-execution-suite` 声明。

| 一级模块 | Mod | 原生路由 |
| --- | --- | --- |
| 量化 | 量化总览 | `/` |
| 量化 | 因子实验室 | `/alpha-zoo` |
| 量化 | 回测实验室 | `/reports` |
| 量化 | 相关性分析 | `/correlation` |
| 量化 | 量化系统设置 | `/settings` |
| 交易 | 交易台 | `/runtime` |

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

这些页面由 [`deepsee-suite/suite.json`](../mods/deepsee-suite/suite.json) 一次声明，Suite Discovery 自动展开为 11 个可独立安装、独立打开和独立授权的 Mod，统一进入“深瞳”。

### InStock 分析

InStock 保持独立 Tornado 服务，默认端口为 `9988`。页面不依赖 MySQL，行情通过 Newma-Desk 的统一市场数据接口取得；分析结果又以 `instock-analysis` Provider 暴露给其他 Mod 和 Agent。

| Mod | 嵌入路由 | 统一能力 |
| --- | --- | --- |
| CZSC 缠论结构 | `/mods/czsc` | `analysis.czsc` |
| 行业与 ETF 轮动 | `/mods/rotation` | `analysis.rotation` |

CZSC 缠论结构进入“市场”，行业与 ETF 轮动进入“行业”；来源运行时与导航归属彼此独立。
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

Orchestra 的八个工作区统一进入“投决”，作为同一投决协作系统呈现。项目内部主导航在嵌入模式下隐藏，避免与 Newma-Desk 导航重复。
Desk 右侧 Agent 会使用 Orchestra 前后端的共同项目目录，因此同一次 Mod 修改任务可以同时理解界面和服务端契约。

## 本地启动

首次克隆先安装全部仓内运行时依赖，再统一启动：

```bash
npm run runtime:bootstrap
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

### Mod 运行时发现

仓内及可覆盖 Mod 的路径、入口和健康检查统一声明在
[`config/external-mod-runtimes.json`](../config/external-mod-runtimes.json)。该 Runtime Descriptor 不保存账号、密钥或个人绝对路径；Node 启动器与 Python Agent Gateway 使用不同 Adapter 读取同一个 Interface，避免同一 Mod 的工作区和端口散落在多份配置里。

默认优先使用 `bundled-runtimes/`。以下根目录只作为开发覆盖候选：

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

注册默认基础 Mod：

```bash
npm run mods:register
```

同步已有环境的标准配置时也可以执行：

```bash
npm run mods:standardize
```

完成后会注册商店中标记为 `defaultInstall` 的 20 个基础 Mod；已有环境中已安装的项目保持不变。`mods:standardize` 用于管理员显式补齐全部官方商店，商店继续提供 Git 来源、安装状态和更新入口。

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

- Newma-Desk 根仓库同时保存路由 Manifest、运行源码快照和依赖锁文件；`mod-projects/` 仅用于本地覆盖测试。
- 上游新增可独立运行页面时，在现有 Suite 的 `pages[]` 中追加页面；单页项目才使用 `mods/<mod-id>/mod.json`。新增页面继承同一栏目和完整项目身份，不新增一级栏目，也不另建 Suite。
- 上游页面内部实现更新时，Newma-Desk 无需同步页面代码。
- 上游路由变化时，修改对应 Mod 的 `runtime.route`。已安装用户可在商店点击“从 Git 更新”。
- 商店内容推送到 GitHub/Gitee 后，用户安装时会直接读取 Git 中的版本。
- 任一上游服务停止，不会影响另一套上游后端和 Newma-Desk 控制面。
