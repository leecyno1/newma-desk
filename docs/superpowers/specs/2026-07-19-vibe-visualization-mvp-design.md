# vibe-visualization MVP 设计规格

日期：2026-07-19

## 1. 产品定义

`vibe-visualization` 是一个面向人类与 Agent 的持久化网页模组基座。

它解决的问题不是一次性生成图表，而是把用户反复使用的分析工作流固化为可持续更新、可独立访问、可嵌入统一侧边栏、可继续迭代的 HTML 应用。

产品中的两类资产互相配合：

- Skill 保存“如何取数、分析和完成工作流”。
- Module 保存“如何持续展示结果并与用户交互”。

Agent 调用 Skill 产生结构化结果，Module 使用稳定的数据契约展示结果。模块发布后可定时复用相同工作流刷新数据。

## 2. MVP 目标

MVP 必须完成：

1. 建立独立的 `vibe-visualization` 仓库。
2. 提供动态侧边栏与模组注册中心。
3. 每个模组以独立 HTML 应用存在，既可嵌入基座，也可通过稳定 URL 直接访问。
4. 提供统一 Agent/大模型 Gateway，不绑定 Hermes、Codex 或单一模型提供商。
5. 提供统一数据服务登记与访问方式。
6. 支持结构化页面模组、受控静态网页模组和外部 URL 模组三种来源。
7. 先以适配器接入 Vibe-Research、Vibe-Trading，再逐步拆解为独立 HTML 入口。
8. 完成一个由 Agent 生成配置、用户确认后固化的“每日股票行情”示范模组。
9. 支持草稿、预览、发布、禁用和回滚。
10. 支持模组导入、导出和私下分享；MVP 不建设公共市场。

## 3. 非目标

MVP 不包含：

- 在线代码 IDE。
- 任意不受信任代码在主应用上下文中运行。
- 公共模组市场及其审核、计费和排名体系。
- 多人实时协作。
- 将两个上游后端合并成一个业务后端。
- 一次性重写 Vibe-Research 或 Vibe-Trading。
- 让大模型承担普通 UI 状态同步。
- 自动执行未经用户授权的交易操作。

## 4. 当前项目基础判断

当前代码已经证明了方向可行，但仍是原型门户，不是可扩展基座。

已有基础：

- Vibe-Research 与 Vibe-Trading 都使用 React、Vite、TypeScript 和 ECharts，页面拆分技术路线相近。
- 两个后端均提供 HTTP API，Vibe-Trading 还具备 Agent 会话、skills、产物、调度和运行记录。
- 当前统一门户已经验证了单侧边栏、iframe 嵌入和双后端隔离。
- 两个上游布局已支持嵌入时隐藏自身侧边栏。
- 服务可独立启动和故障隔离。

缺失能力：

- 当前侧边栏和模块 URL 硬编码在 `portal/app.js` 与 `portal/index.html`。
- 没有 Module Manifest、动态安装、版本、权限和回滚。
- 没有统一 Agent Gateway 与 Agent 能力发现协议。
- 没有网页间事件协议和模组 SDK。
- 没有结构化页面 Renderer。
- 没有模组发布审批、数据刷新记录和运行审计。
- 没有对任意 HTML、跨域网页和交易操作的完整安全边界。

因此，当前项目大约具备 MVP 所需基础的三分之一。适合演进，不适合直接把现有静态门户改名后发布。

## 5. 总体架构

系统分为五层：

```text
人类用户 / Hermes / Codex / 其他 Agent
                    |
                    v
        Agent & Model Gateway
                    |
                    v
  Control Plane: Registry / Lifecycle / Permissions / Scheduler / Audit
                    |
                    v
  Runtime Plane: Structured / Static HTML / External URL
                    |
                    v
 Data Services: Research / Trading / Market Data / Custom Services
```

MVP 在逻辑上保留上述分层，在物理部署上只增加一个基座后端，避免过早拆成多个微服务：

- 前端：React 19、TypeScript、Vite、ECharts，使用 npm workspaces 管理。
- 基座后端：FastAPI、Pydantic、SQLite；Control Plane、Agent Gateway 和 Data Service Registry 作为同一进程中的独立包。
- 测试：Vitest、Pytest、Playwright。
- 外部业务服务：Vibe-Research、Vibe-Trading 及其他数据服务继续独立部署。

### 5.1 Web Shell

Web Shell 负责：

- 动态侧边栏。
- 模组加载与直接访问链接。
- 登录状态和用户工作区。
- 模组状态、错误和权限提示。
- iframe 容器及 Module Bridge。

Web Shell 不包含行情、回测、产业链或交易业务逻辑。

### 5.2 Control Plane

Control Plane 负责：

- Module Manifest 校验与注册。
- 草稿、预览、发布、禁用和回滚。
- 模组版本与发布历史。
- 权限、数据服务依赖和 Agent 能力声明。
- 定时刷新配置。
- 操作记录、错误记录和健康状态。

MVP 使用 SQLite 保存注册状态、版本、计划任务和审计记录；模组静态资源与数据快照保存在工作区文件目录。

### 5.3 Runtime Plane

MVP 支持三类模组，但最终均以 HTML 页面呈现：

1. `structured`：通过结构化 View Schema 渲染指标、表格、ECharts、Markdown、筛选器和表单。
2. `static`：由任意前端技术构建出的独立静态 HTML 应用。
3. `external`：已经部署在其他服务上的独立网页地址。

三类模组都必须提供 Manifest，并拥有稳定 URL。

### 5.4 Agent & Model Gateway

Gateway 是 Agent 中立的统一入口，负责：

- 注册 Hermes、Codex、OpenAI-compatible 模型或其他 Agent Adapter。
- 列出 Agent 与模组提供的能力。
- 接收自然语言任务和结构化任务。
- 将任务路由到 Skill、模组 Action 或数据服务。
- 通过 SSE 返回进度、结果和产物。
- 在需要修改模组代码、Manifest、权限或数据源时创建待审批变更。

MVP 的核心接口：

```text
GET  /api/capabilities
POST /api/agent/tasks
GET  /api/agent/tasks/{task_id}
GET  /api/agent/tasks/{task_id}/events
POST /api/modules/{module_id}/actions/{action_id}
```

### 5.5 Data Services

后端业务能力继续保持独立。每个数据服务通过统一描述登记：

- 服务 ID、基础地址和健康检查。
- REST、MCP、SSE 或 WebSocket 类型。
- 能力列表和输入输出 Schema。
- 访问权限、超时和重试规则。
- Secret 引用；Secret 永远只保存在服务端。

## 6. Module Contract

每个模组至少包含：

```text
module-package/
├── module.json
└── dist/
    ├── index.html
    └── assets/
```

外部模组只需要 `module.json`，其 `entry.url` 指向远程地址。

Manifest 必须声明：

```json
{
  "schemaVersion": "1.0",
  "id": "market-daily",
  "name": "每日股票行情",
  "version": "0.1.0",
  "category": "market",
  "entry": {
    "type": "structured",
    "url": "/modules/market-daily/"
  },
  "permissions": ["market.read"],
  "dataServices": ["market-data"],
  "agentCapabilities": ["market.explain", "market.refresh"],
  "events": {
    "emits": ["security.selected"],
    "accepts": ["date.changed", "security.selected"]
  },
  "refresh": {
    "mode": "schedule",
    "cron": "0 18 * * 1-5"
  }
}
```

Manifest 的代码、权限、数据源和 Agent 能力发生变化时，必须生成新版本并重新审批。单纯的数据快照刷新不触发重新发布。

## 7. 网页与 Agent 交互

系统采用双通道，避免把所有网页消息都交给大模型处理。

### 7.1 确定性事件通道

用于股票代码、日期、筛选条件、跳转和刷新状态等确定性信息：

- iframe 与 Shell：`window.postMessage`。
- 同源独立页面：`BroadcastChannel`。
- 跨域或跨设备页面：Gateway WebSocket/SSE 中继。

事件统一使用版本化 Envelope：

```json
{
  "version": "1.0",
  "event": "security.selected",
  "source": "market-daily",
  "target": "stock-analysis",
  "traceId": "event-id",
  "payload": {"symbol": "600519", "market": "CN"}
}
```

### 7.2 Agent 语义通道

用于需要推理、工具调用或工作流编排的任务，例如：

- 解释行情异动。
- 根据当前股票调用产业链分析。
- 把选定因子交给回测模组。
- 比较不同页面的结果并生成摘要。

网页通过 Module SDK 向 Gateway 提交任务，并订阅进度与产物。

## 8. 模组生命周期

```text
需求
  -> Agent 生成页面配置或代码
  -> Draft
  -> Preview
  -> 用户批准
  -> Published
  -> 自动刷新数据
  -> 结构/代码变更时重新进入 Preview
```

规则：

- 首次发布必须由用户确认。
- 数据刷新可以按授权计划自动运行。
- 布局、代码、权限、Agent 能力或数据源变化必须重新确认。
- 每个已发布版本都可以回滚。
- 模组默认私有，可以导出为带 Manifest 的压缩包。

## 9. 仓库结构

```text
vibe-visualization/
├── apps/
│   ├── shell/                 # Web Shell
│   └── module-host/           # 静态 HTML 与结构化页面托管
├── services/
│   └── api/                   # 单 FastAPI 进程
│       ├── control_plane/     # Registry、Lifecycle、Scheduler、Audit
│       ├── agent_gateway/     # Agent/模型适配与任务路由
│       └── data_services/     # 外部数据与业务服务登记
├── packages/
│   ├── contracts/             # Manifest、Event、View Schema
│   ├── module-sdk/            # 页面调用 Gateway、数据与事件
│   └── structured-renderer/   # 表格、图表、指标、Markdown、表单
├── modules/
│   └── market-daily/          # MVP 示范模组
├── integrations/
│   ├── vibe-research/         # 上游路由和数据能力适配
│   └── vibe-trading/          # 上游路由和数据能力适配
├── deploy/
├── docs/
└── tests/
```

## 10. 两个上游项目的拆解策略

拆解分两步，避免破坏上游同步能力。

### 第一步：URL 适配

把现有路由注册为独立模组入口：

| 来源 | 首批模组 |
|---|---|
| Vibe-Research | 每日复盘、股票行情、个股分析、产业链研究 |
| Vibe-Trading | Alpha Zoo、回测报告、交易控制台 |

这一阶段不复制业务组件，只通过 Manifest、URL、数据服务和 Agent 能力接入。

### 第二步：独立构建入口

逐个将目标页面改造成可独立构建的 HTML 入口。拆解遵循：

- 页面不直接引用原项目的全局 Layout。
- 页面通过数据服务接口获取业务数据。
- 页面通过 Module SDK 发送事件和 Agent 任务。
- 页面可以在没有 Web Shell 时直接打开。
- 上游适配补丁保持小而独立，便于重新应用到新版上游。

MVP 只完整拆出“每日股票行情”示范模组；其他页面先使用 URL Adapter。

## 11. MVP 数据流

以每日股票行情为例：

1. 用户要求 Agent 创建每日行情页面。
2. Agent 发现 `market-data` 服务和结构化 Renderer 能力。
3. Agent 生成 View Schema、数据查询配置和 Module Manifest。
4. Control Plane 保存为 Draft 并提供预览 URL。
5. 用户批准后，Registry 将模组加入侧边栏。
6. Scheduler 在交易日收盘后调用 `market.refresh`。
7. 结果保存为版本化数据快照。
8. 模组加载快照并显示指标、表格和动态图表。
9. 用户选择股票时，模组发出 `security.selected`。
10. 用户要求解释时，页面通过 Gateway 调用 `market.explain`。

## 12. 安全边界

- HTML 模组默认在 sandbox iframe 中运行。
- 未经信任的模组不能访问 Shell DOM、浏览器存储或 Secret。
- iframe 来源必须在 Manifest 和服务端允许列表中。
- Module Bridge 校验 origin、module ID、事件类型和 payload Schema。
- Secret 只由 Gateway 或数据服务读取，不传给页面。
- 模组权限最小化授权。
- 交易相关 Action 必须单独声明 `trade.execute` 权限，并在每次真实下单前要求用户确认。
- Agent 不得绕过 Lifecycle 直接修改已发布页面。
- 模组包导入时校验 Manifest、文件大小、路径穿越和内容安全策略。

## 13. 故障处理

- 单个模组崩溃不影响 Shell 和其他模组。
- 数据服务不可用时显示最后成功快照及更新时间。
- Agent Gateway 不可用时，纯展示与确定性页面交互仍可使用。
- Agent 任务使用超时、取消、有限重试和可追踪 task ID。
- 外部模组健康检查失败时，侧边栏显示离线状态并提供独立地址。
- Scheduler 失败保留上次成功数据并记录审计事件。
- Manifest 不合法时拒绝发布，不影响现有版本。

## 14. 测试策略

MVP 必须具备：

- Manifest、Event Envelope 和 View Schema 的契约测试。
- Registry 生命周期和版本回滚测试。
- Agent Adapter 与数据服务 Adapter 的模拟测试。
- iframe origin、权限和消息校验测试。
- 结构化 Renderer 的组件测试。
- 每日行情模组的数据快照与空数据测试。
- 页面独立访问与 Shell 嵌入两种模式的端到端测试。
- Vibe-Research、Vibe-Trading URL Adapter 的健康与路由冒烟测试。
- 任一上游服务停止后其他模组仍可用的隔离测试。

## 15. MVP 交付顺序

1. 初始化独立仓库、基础工具链和 CI。
2. 实现 contracts、Manifest 校验和 Module SDK。
3. 实现单一 FastAPI 基座后端、Control Plane 与 SQLite Registry。
4. 实现动态 Web Shell 和 sandbox Module Host。
5. 实现 Agent Gateway 的 Adapter 接口及一个 OpenAI-compatible Adapter。
6. 实现 Data Service Registry。
7. 实现 Structured Renderer。
8. 完成每日股票行情示范模组。
9. 注册 Vibe-Research、Vibe-Trading 的首批 URL Adapter。
10. 完成生命周期、权限、故障隔离和端到端验证。
11. 创建同名 GitHub、Gitee 仓库并推送经过验证的 MVP。

## 16. 验收标准

- 侧边栏完全由 Registry 动态生成，不再硬编码模块。
- 一个合法 Module Manifest 可以安装、预览、发布、禁用和回滚。
- 每个模组都有可直接访问的稳定 URL，并能嵌入 Web Shell。
- 每日股票行情模组可以由结构化配置生成，显示真实数据表格和 ECharts 图表。
- 行情数据可以按计划刷新，失败时保留上次成功快照。
- 页面能通过 Module SDK 发送结构化事件和 Agent 任务。
- 至少一个外部 Agent/模型 Adapter 可通过 Gateway 使用。
- Vibe-Research 与 Vibe-Trading 的首批页面可作为隔离模组访问。
- 停止任一上游服务不会导致 Web Shell 或其他模组失效。
- 代码、权限和数据源变化必须经过预览与批准。
- GitHub 与 Gitee 均存在名为 `vibe-visualization` 的同步仓库。
