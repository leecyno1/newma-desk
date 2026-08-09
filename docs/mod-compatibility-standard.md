# Newma-Desk Mod Compatibility Standard 1.0（工作草案）

涉及持久化的 Mod 还必须遵循 [MOD Storage Standard](./mod-storage-standard.md)，不得直接连接 Desk 主数据库或依赖其物理表结构。

状态：Draft 0.4
Manifest：1.1  
Bridge Protocol：1.0  
ViewSpec：1.0

本文定义 Mod 如何独立运行、嵌入 Newma-Desk、调用数据与 AI 能力，以及如何被人和 Agent 共同理解。文中的“必须”“应该”“可以”分别对应 MUST、SHOULD、MAY。

## 1. 核心边界

一个 Mod 是：

> 独立网页入口 + 运行 Manifest + 明确 Action + 可选数据服务 + 可选 Agent 语义。

Newma-Desk 负责导航、隔离、身份、权限、Gateway、跨 Mod 上下文和统一展示范式。Mod 负责自己的业务页面和业务后端。Newma-Desk 不复制上游项目源码，也不要求上游项目迁入同一个后端。

同一个 Mod 必须同时支持：

- 通过稳定 URL 独立访问。
- 在 Newma-Desk iframe 中运行。
- 保持自己的发布、路由和后端生命周期。

## 2. 三级兼容等级

等级是累积关系。Level 3 必须同时满足 Level 1 和 Level 2。

### Level 1：Embed Ready（可嵌入级）

Mod 必须：

- 有可独立访问的 HTTP(S) 页面。
- 允许被配置的 Newma-Desk Origin 嵌入。
- 在 320px 至桌面宽度下保持可用。
- 完成 `hello → init → ack` Bridge 握手。
- 接收主题、语言和时区。
- 不依赖第三方 Cookie 才能显示基础内容。
- 提供可自动检查的健康状态。

Level 1 不得声明 Connected Action。

### Level 2：Connected Mod（连接级）

Mod 必须额外：

- 使用 Manifest 1.1 显式声明所有 Action Binding。
- 区分 Agent、Model、Data 和 Local Action。
- 声明每个 Action 的权限、执行模式和确认级别。
- 使用 Newma-Desk Gateway，而不是把密钥下发到浏览器。
- 使用标准事件协议交换确定性事件。
- 提供结构化输入输出 Schema。
- 长任务必须返回可查询、可取消的任务状态。

### Level 3：Agent Native（原生协同级）

Mod 必须额外：

- 声明并使用 ViewSpec 版本。
- 向 Agent 返回结构化页面上下文，不要求截图或任意 DOM 抓取。
- 声明当前选择、筛选器、数据时间、来源和可执行 Action。
- 所有 Agent 可执行操作都必须对应 Manifest Action。
- 页面在人类不可见的情况下仍能提供等价的语义状态。
- 通过无障碍和 Agent Context 自动测试。

### 2.1 声明等级与认证等级

Manifest 中的 `compatibility.level` 是 Mod 声明等级，不等于 Newma-Desk 已认证等级。静态合同检查只能确认字段、权限、Action Binding 和 Schema 关系有效，不能证明页面当前可运行。

运行认证必须在真实 Desk 与 Mod 运行时上验证：

- 页面入口返回可用 HTML。
- iframe 可以加载并显示页面。
- 完成 `hello → init → ack` Bridge 握手。
- 独立页面在 320px 宽度下没有文档级横向溢出。
- Level 3 返回结构化 Agent Context，并成功持久化到当前用户与 Workspace。

只有全部必需检查通过后，认证等级才等于声明等级。任何必需检查失败时，`certifiedLevel` 必须为空，不能降级显示成另一个已认证等级，也不能仅凭 Manifest 展示“已认证”徽章。认证结果必须包含 `testedAt` 和每项检查证据。

项目命令：

```bash
npm run mods:compat
npm run mods:certify -- --mod market-daily,multi-timeframe
```

前者输出 `CONTRACT PASS/FAIL` 和 `certification=pending`；后者连接当前运行环境生成 JSON 认证报告。

## 3. 版本边界

以下版本必须独立演进：

- Manifest `schemaVersion`
- Bridge `bridgeProtocol`
- Mod SDK `sdkVersion`
- ViewSpec `viewSpecVersion`
- Newma-Desk HTTP API 版本

新增可选字段属于兼容变更；删除字段、重命名、类型变化、认证方式变化必须发布新主版本。公开版本至少保留当前版本和前一版本的兼容期。

Manifest 1.0 是兼容模式。Manifest 1.1 是新 Mod 的标准入口。1.0 Mod 可以继续使用 `agentCapabilities` 和旧 `vibedesk:ready/config` 消息，但不能获得 Level 2 或 Level 3 认证。

## 4. 标准文件

- `mod.json`：商店描述、作者、上游仓库、截图和安装信息。
- `module.json`：运行 Manifest；Newma-Desk 1.x 为兼容现有包继续使用此文件名。
- `data-service.json`：数据服务与能力描述。
- `schemas/*.json`：Action 和数据服务的 JSON Schema。
- `view.json`：可选的 ViewSpec 页面定义。

运行合同的唯一规范来源应该是 JSON Schema。TypeScript、Python 和其他语言类型应该由规范 Schema 生成或接受一致性测试。

Git 商店 MVP 推荐在 Manifest 和 `data-service.json` 中使用内联 Draft 2020-12 JSON Schema，便于安装时完成离线校验。字符串形式的 Schema 文件引用仅作为兼容语法；在解析、路径隔离和真实验证实现完成前，不应获得 Schema 认证徽章。远程 `$ref` 必须禁止。

## 5. Manifest 1.1

```json
{
  "schemaVersion": "1.1",
  "id": "factor-lab",
  "name": "因子实验室",
  "version": "1.0.0",
  "category": "quant",
  "navigation": {
    "groupLabel": "Vibe Trading",
    "groupOrder": 30,
    "itemOrder": 10,
    "label": "因子实验室",
    "project": {
      "id": "vibe-trading",
      "name": "Vibe Trading",
      "order": 30,
      "description": "量化研究、因子实验、回测分析与交易运行。"
    },
    "directory": {
      "id": "factor-research",
      "label": "因子研究",
      "order": 10
    },
    "icon": "quant"
  },
  "entry": {
    "type": "external",
    "url": "https://quant.example/mods/factor-lab"
  },
  "compatibility": {
    "level": 2,
    "bridgeProtocol": "1.0",
    "sdkVersion": "^0.2.0"
  },
  "permissions": ["quant.execute", "research.read"],
  "dataServices": ["vibe-trading"],
  "actions": {
    "factor.backtest": {
      "binding": {
        "type": "data",
        "service": "vibe-trading"
      },
      "execution": "task",
      "permission": "quant.execute",
      "inputSchema": "./schemas/factor-backtest.input.json",
      "outputSchema": "./schemas/factor-backtest.output.json",
      "confirmation": "user"
    },
    "research.explain": {
      "binding": {
        "type": "agent",
        "memoryScope": "user-agent-mod"
      },
      "execution": "task",
      "permission": "research.read"
    }
  },
  "events": {
    "emits": ["security.selected"],
    "accepts": ["date.changed"]
  }
}
```

约束：

- Level 1 的 `actions` 必须为空。
- Level 3 必须声明 `viewSpecVersion`。
- Action 使用的权限必须存在于 `permissions`。
- Data Action 指定 `service` 时，该 Service 必须存在于 `dataServices`；省略
  `service` 时由 Newma-Desk 统一数据路由选择 Provider。
- Agent Action 必须使用 `task` 执行方式。
- Model Action 必须使用 `request` 执行方式。
- `trade.execute` 必须使用 `strong` 确认。

### 5.1 项目与页面导航合同

导入多页面项目时，每个可独立授权、独立运行、独立提供 Agent Context 的页面仍然编译为一个独立 Mod，但完整来源项目必须作为一个 Suite 整体进入 Desk。`navigation.project` 选择十四个核心栏目之一或“其他”，`navigation.directory` 标识栏目内的完整项目；所有兄弟页面继承相同值。不能丢失上游页面，也不能按页面业务分类把同一项目拆散到多个栏目。

```json
{
  "navigation": {
    "groupLabel": "宏观面",
    "groupOrder": 20,
    "itemOrder": 20,
    "label": "扫描器",
    "project": {
      "id": "fundamentals",
      "name": "宏观面",
      "order": 20,
      "description": "经济数据、宏观指标、行业、产业链与宏观事件。"
    },
    "directory": {
      "id": "example-research-suite",
      "label": "Example Research",
      "order": 5
    },
    "icon": "market"
  }
}
```

字段约束：

- `project.id`：稳定栏目 ID，必须属于十四个核心栏目或 `other`。
- `project.name`、`project.description`：一级栏目身份。
- `project.order`：栏目的固定默认顺序。
- `project.logo`：仅用于旧版 Manifest 兼容读取；当前 Desk 的一级标志不会使用或展示它，新项目应该省略。
- `itemOrder`：页面在项目或项目内 section 中的默认顺序。
- `label`：导航中的紧凑页面名称；省略时使用 Mod `name`。
- `directory`：完整项目在栏目内的固定分组，Suite 不得省略。
- `directory.id`：必须等于 Suite ID；`label` 是项目名，`order` 是栏目内项目顺序。
- `groupLabel`、`groupOrder`：仅供旧客户端和业务分类兼容；新导航不得用它们覆盖 `project` 归属。

一级标志统一由宿主根据栏目名称生成 1–2 个汉字，例如 `市场面 → 市场`、`宏观面 → 宏观`。英文自定义栏目标题通过受控词典转换；无法识别时回退默认栏目名、稳定 `project.id` 和业务图标语义，最终结果不得包含拉丁字母。一级栏和设置预览必须共享同一算法，导入项目不得通过图片、图标或自定义字符覆盖它。

`navigation.project` 对旧的普通单页 Mod 保持可选，Desk 可暂时以 Mod 自身身份兼容显示；所有新 Mod 必须选择正式栏目。旧 Suite 未声明栏目时，Suite Compiler 将整套项目放入 `other`，不会按页面猜测归属。`navigation.directory` 对完整 Suite 是必填项目身份，不是可选页面分类。

Desk 中的用户配置优先于 Manifest 默认值，并只保存在本地 Workspace：用户可以重排栏目、完整项目和项目内页面，也可以冻结、隐藏或修改栏目标题；这些操作不得修改上游 Manifest。标题覆盖会同步用于栏目标志的无障碍名称、二级面板标题和自动中文短标，但不会改变 `project.id`。页面或项目冻结后进入稳定区域并禁止拖拽，取消冻结后才可再次移动；页面不能被拖出所属完整项目。导入器必须保持 Suite ID 和页面 ID 稳定，不能使用随机值或随显示文案变化的值。

每个完整项目由 Desk 提供项目设置入口，或由 Suite 中 `navigation.role = "settings"` 的真实设置页承载。其作用域是 `用户 + Workspace + directory.id`，至少包含：项目页面清单、统一数据 Provider 路由和 Agent 设置入口。栏目 `project.id` 不能作为此作用域，否则同一栏目下的多个完整项目会错误共享配置。

推荐的项目接入流程是：完整盘点上游路由 → 选择一个主要投资栏目 → 以原项目为单位定义 Suite 和同 ID directory → 每个原有路由生成一个页面 Manifest → 运行完整性与兼容性检查 → 整套注册到商店。这样上游不需要实现 Newma-Desk 侧边栏组件，也不会在接入过程中被拆散。

## 6. Action Binding

Action ID 是对人、Agent 和服务都稳定的公开能力名称。页面不能通过请求参数改变 Action 的处理链路。

### Agent

用于需要工具、工作流或长期上下文的任务。

- `memoryScope: user-agent-mod`：同一用户、同一 Agent、同一 Mod 复用记忆。
- `memoryScope: task`：单次任务，不读取也不保存长期记忆。
- 具体 Agent 由用户设置选择，Mod 不得强制指定供应商。

### Model

用于传统无状态模型请求。Model Action 不得自动继承 Agent Session，也不得在内部串接 Agent。

### Data

用于确定性业务接口。必须声明 Capability、输入输出 Schema 和权限。密钥只保存在 Newma-Desk 或对应数据服务端。

推荐使用统一路由，不写具体 Provider：

```json
{
  "market.quote": {
    "binding": {
      "type": "data"
    },
    "execution": "request",
    "permission": "market.read",
    "inputSchema": {"type": "object"},
    "outputSchema": {"type": "object"},
    "confirmation": "none"
  }
}
```

此时 Action ID 默认就是 Capability ID；也可以通过 `binding.capability` 显式映射。Desk 使用完整项目的 `navigation.directory.id`（即 Suite ID）作为数据路由作用域；单页 Mod 回退到 Mod ID。Provider 默认按 `priority` 从小到大选择，用户可以在项目设置中按 Capability 覆盖。

旧的固定服务方式继续兼容：

```json
{
  "binding": {
    "type": "data",
    "service": "market-data",
    "capability": "market.quote"
  }
}
```

固定方式只适合必须绑定某个专有后端的 Mod。使用统一路由时，Mod 不声明 `dataServices`，也不得获得 Provider URL、Token、Secret 或内部服务 ID。

嵌入式 Mod 应使用 SDK 的 `createUnifiedDataClient({ invokeAction })`，通过受 Session 保护的宿主 Action 通道请求数据：

```ts
const data = createUnifiedDataClient({
  invokeAction: hostConnection.invokeAction,
});

const quote = await data.query("market.quote", {
  symbol: "600519",
  market: "CN",
});
```

Desk 后端提供统一目录与偏好资源：

```http
GET /api/data-services/catalog
GET /api/data-services/preferences/{suite-id}
PUT /api/data-services/preferences/{suite-id}
```

客户端应向 `{suite-id}` 传入完整项目的 `navigation.directory.id`；单页 Mod 使用自身 Mod ID。不得传栏目 `project.id`。

偏好接口使用 `X-User-Id` 与 `X-Workspace-Id` 隔离。保存时必须验证 Provider 确实提供对应 Capability；失效偏好不得静默切换到另一个 Provider。

### Local

用于 Newma-Desk 自身提供的受控能力，例如本地刷新。未注册的 Local Handler 必须返回不可用，不得回退到 Agent 猜测执行。

## 7. Bridge Protocol 1.0

### Mod → Desk

```json
{
  "type": "vibedesk:hello",
  "modId": "factor-lab",
  "protocolVersions": ["1.0"],
  "sdkVersion": "0.2.0",
  "capabilities": ["events", "actions", "data", "theme"]
}
```

### Desk → Mod

`vibedesk:init` 必须包含：

- 已协商的协议版本。
- 本次 iframe 的 `instanceId`。
- `user` 与 `workspace`。
- 主题、语言和时区。
- Actions、Agent、Model、Data Gateway 地址。
- Newma-Desk 实际批准的权限与 Action。

### Mod → Desk

Mod 收到并验证配置后必须发送 `vibedesk:ack`。所有消息必须验证准确的 `source`、`origin`、`modId` 和 `instanceId`。

Manifest 1.0 的 `vibedesk:ready/config` 在 1.x 兼容期继续可用。

### 7.1 主题同步

- `vibedesk:init.environment.theme` 是主题的唯一正式来源，取值只允许 `light` 或 `dark`。主题变化时 Desk 重发同一 `instanceId` 的 `vibedesk:init`，不得通过刷新 iframe 切换主题。
- `vibedesk:init.appearance` 是可选的 Newma Theme Contract 1.0，携带与当前模式一致的语义色、图表色和安全 CSS Custom Properties。它用于继承具体 Newma 色板，不替代 `environment.theme`，旧 SDK 可以直接忽略。
- 使用 `@newma-desk/mod-sdk` 的 Mod 默认由 `connectModHost()` 自动应用主题：同步 `html[data-theme]`、`.light/.dark`、`html.style.colorScheme`、`data-vibedesk-theme` 和 `appearance.cssVars`，并派发 `newma:themechange`。只有确需自行管理文档根节点的运行时才可显式设置 `applyAppearance: false`。
- SDK 同时同步 Bootstrap 5 使用的 `data-bs-theme`；统一模板提供 Tailwind / shadcn、Bootstrap 5，以及 Bootstrap 3 / Ace 公开 primary 语义类的适配。框架适配只转换品牌与表面主题，不改写组件 DOM，也不覆盖金融涨跌、成功、警告和错误语义。
- Mod 前端入口 SHOULD 导入 `@newma-desk/desk-ui/mod-theme.css`。该模板同时提供 `--vibe-*` / `--newma-*`、Tailwind / shadcn 语义变量、页面基础背景与可复用控件表面。旧页面只导入 `tokens.css` 仍然兼容。
- Mod 应使用语义化颜色变量映射 Newma-Desk Design Tokens，包括页面背景、表面层、边框、正文、弱化文本、强调色、正负值、警告和错误状态。页面主体、表格、输入控件、弹层和图表不得各自维护互相冲突的浅色或深色色板。
- Canvas、SVG、ECharts 等不能自动继承 CSS 的可视化必须在主题变化后重新读取语义变量并重绘，且不得丢失当前数据、选择项或筛选条件。
- 独立打开且尚未收到宿主主题时，Mod 应跟随 `prefers-color-scheme`；一旦收到 Desk 配置，宿主主题立即取得优先权。

最小接入模板：

```ts
import "@newma-desk/desk-ui/mod-theme.css";
import { connectModHost } from "@newma-desk/mod-sdk";

const host = await connectModHost({
  modId: "example-mod",
  parentOrigin: new URL(document.referrer).origin,
  capabilities: ["theme", "context"],
});
```

主题自动适配只作用于 Mod 自己的文档。Desk 不得尝试直接改写跨域 iframe DOM，也不得用 CSS filter 强制染色。导入的第三方页面如果不消费桥接消息，必须通过 Newma 控制的 Wrapper 接入，并在 `css-vars`、`class-toggle` 或 `postMessage` 三种转发方式中选择一种；完全不协作的外部页面只能统一 Wrapper 外壳，不能承诺其内部颜色自动替换。

发布前 SHOULD 运行 `npm run mods:theme:check`；外部项目可以把前端绝对路径作为参数传入。服务启动后 SHOULD 再运行 `npm run mods:theme:audit`，在与系统主题相反的 Desk 浅色 / 深色环境中逐页检查主题握手、语义变量、大面积蓝白主体和控件颜色。运行态中确属数据系列的例外只能在最小 DOM 子树使用 `data-newma-theme-allow` 或 `.newma-theme-allow` 标记。两类检查都不能代替对金融涨跌色、告警色和图表系列色的人工语义审查。

### 7.2 最小权限 Mod Session

Manifest 1.1 Mod 在调用 Action 前必须获得短期 Session。Session 绑定：

- 用户、Workspace、Mod 和已发布 Revision。
- 本次 iframe 或独立页面的 `instanceId`。
- Manifest 实际声明的权限与 Action。
- 明确的过期时间；MVP 默认 15 分钟。

Desk 嵌入模式下，Access Token 只能保存在宿主页面，不得发送给 iframe。`vibedesk:init` 只向 Mod 暴露 Session ID、过期时间和批准后的 Grants。独立访问的 Mod 可以通过 SDK 自行申请 Session，但仍必须使用稳定的独立页面 `instanceId`。

Action 和 Context HTTP 请求必须同时携带：

```http
Authorization: Bearer <mod-session-token>
X-Newma-Desk-Instance-Id: <instance-id>
```

Token 与 `instanceId`、Mod、Revision 或 Action 任一不匹配时必须拒绝。生产环境和多进程部署必须配置固定的 `NEWMA_DESK_MOD_SESSION_SECRET`；不得依赖进程启动时生成的临时密钥。

兼容期内，宿主仍接受旧的 `X-Newma-Desk-Instance-Id` 请求头与
`NEWMA_DOCK_*` 环境变量；新接入统一使用 `Newma-Desk` 命名。

### 7.3 Agent Context 消息

Desk 请求当前页面语义状态：

```json
{
  "type": "vibedesk:context-request",
  "requestId": "request-123",
  "instanceId": "instance-123",
  "modId": "market-daily",
  "reason": "agent"
}
```

Mod 使用相同 `requestId` 返回 Context：

```json
{
  "type": "vibedesk:context",
  "requestId": "request-123",
  "instanceId": "instance-123",
  "modId": "market-daily",
  "context": {
    "view": {"id": "market-daily", "title": "市场行情"},
    "visibleBlocks": [{"id": "leaders", "type": "table"}],
    "selection": {"symbol": "600519", "market": "CN"},
    "filters": {},
    "data": {
      "asOf": "2026-07-23T09:30:00+08:00",
      "source": "vibe-research",
      "freshness": "fresh"
    },
    "actions": [{"id": "market.explain", "available": true}],
    "tasks": []
  }
}
```

Agent Action 执行前，Desk 应使用 `reason: agent` 主动刷新一次 Context；持久化成功或短超时后再创建任务。Agent Gateway 按“用户 + Workspace + Mod”读取 Context，并放入统一的 `context.vibedesk.page`，不得把页面 Context 清空。

### 7.4 宿主代理 Action

嵌入 Mod 不直接持有 Gateway Token，而是向 Desk 发出：

```json
{
  "type": "vibedesk:action-request",
  "requestId": "action-123",
  "instanceId": "instance-123",
  "modId": "market-daily",
  "actionId": "market.explain",
  "input": {"prompt": "解释当前行情"}
}
```

Desk 校验来源、实例、Manifest、Session、权限和 Schema 后代理调用，并通过 `vibedesk:action-result` 返回成功结果或标准错误。Mod 不得通过输入参数改变 Manifest 声明的 Agent、Model、Data 或 Local 路由。

### 7.5 Desk Mod Copilot

Newma-Desk 在宿主层提供统一的右侧 Mod Copilot。该能力属于 Desk，不属于单个 Mod：

- 抽屉、会话显示、停止任务、Agent 选择、问答/修改模式由 Desk 统一实现。
- 每次发送前，Desk 必须使用 `reason: agent` 请求当前页面 Context。
- 支持 Context Bridge 的 Mod 显示“已同步当前页面”；未支持的 Mod 使用 Manifest、入口和版本作为明确标注的降级上下文。
- 对话记忆按“用户 + Agent + Mod”隔离，切换 Mod 不得串用前端消息或后端长期上下文。
- “提问”模式必须只读；本机 Agent 应使用只读沙箱，不得修改工程或外部状态。
- “修改”模式必须由用户在界面显式选择，并以 `capability: module.edit` 和 `context.vibedesk.mode: edit` 双重声明；Agent 只能写入当前 Mod 映射的 Workspace。
- 修改完成后必须返回改动文件、行为变化和验证结果，不得读取或输出 `.env`、密钥和登录凭据。

Mod 可以在独立运行时保留自己的问答入口；嵌入 Newma-Desk 时，通用“针对本页问答”入口应该隐藏，避免出现两套会话、两套 Agent 设置和重复的右侧抽屉。业务专属的 AI 复盘、摘要、自动回复、研究沉淀和 Action 不属于重复能力，不应因此移除。

### 7.6 报告型 Skill 的 Agent-only 规则

主要产物是分析文字、研究报告、备忘录、摘要或一次性图表的 Skill，默认只作为 Desk / Numa Agent 能力，不创建 Mod 页面，不进入一级或二级导航，也不启动独立服务。用户从当前 Mod 右侧 Agent 或 Numa 对话触发，Skill 可以读取当前 Mod Context，并通过统一数据接口补充更长区间行情、财务、公告、新闻和研究档案。

结果遵循渐进展示：短结果直接作为对话消息；较长结果在消息中折叠；带图表、HTML 或完整文档的结果生成可展开 Artifact；需要长期沉淀时由用户执行“保存到研究档案”。Artifact 仍属于当前会话和来源 Mod，不因此获得独立导航身份。

只有同时满足下列条件的能力才应进入现有或新 Mod 页面：

- 用户需要持续筛选、排序、比较、拖拽或联动操作；
- 页面存在可恢复的工作状态，而不只是一次报告结果；
- 可视化本身是主要工作界面，例如 K 线、产业链图谱、回测实验或组合管理；
- 多次 Agent 对话不能替代该交互工作台。

Agent-only Skill 必须复用用户统一 Agent 设置和 Secret Interface；不得声明页面路由、`navigation`、独立端口、自带对话抽屉或第二套模型配置。报告需要确定性计算或数据时，Agent 通过声明的 Data Action 调用，不把 API Key 放入提示词或浏览器。

运行时由 Desk 后端根据当前已发布 Mod 的 `navigation.project.id`，从 `config/finance-project-intake.json` 筛出该栏目允许使用的 `agent-capability`，并在进入已选 Agent 前注入 `vibedesk.agentOnlyCapabilities`。该目录只包含来源 ID、名称、能力 ID 和输出策略，不包含仓库地址、依赖、Secret 名称或任何凭据；浏览器和 Mod 不能自行声明或扩充此目录。它是能力白名单而非安装状态，Agent 必须先核验实际可用性，不可用时说明缺口并降级到 Desk 数据。`module.edit` 不注入此目录，避免把投研能力误当成源码修改权限。

## 8. 数据合同

每项数据能力必须定义：

- 输入和输出 JSON Schema。
- HTTP 方法或其他传输方式。
- 同步、任务或流式执行方式。
- 权限、超时、重试和幂等规则。
- `asOf` 数据时间。
- `source` 数据来源。
- `freshness` 或过期状态。
- 标准错误码。

Newma-Desk 必须在调用前验证输入，在返回 Mod 前验证输出。未安装、未授权或 Schema 不匹配的 Service 不得被调用。

## 9. 事件与 Workspace Context

事件用于“发生了什么”，Context 用于“当前是什么”。两者不能混用。

标准 Context 至少覆盖：

- 当前证券或研究对象。
- 日期范围。
- 当前组合。
- 当前研究主题。
- 当前数据集和回测任务。

跨 Origin、独立打开和切换页面的 Context 必须由 Newma-Desk 后端持久化；不能只依赖 iframe 或 BroadcastChannel。

## 10. 安全要求

- 浏览器不得收到上游 API Key、模型 Key 或 Agent 凭据。
- Newma-Desk 必须按照 Manifest 权限生成最小权限运行环境。
- iframe `sandbox` 和 Permissions Policy 必须由声明权限推导。
- Mod Origin 与 Desk Origin 应隔离。
- 所有写入、交易和外发动作必须可审计。
- 安装包必须记录来源仓库、固定 Commit、校验值和发布者。
- 调用必须携带可关联的 traceId，但日志不得记录密钥和完整敏感输入。

## 11. 展示与 Agent 语义

所有级别应该使用 Newma-Desk Design Tokens：字体、字号、间距、颜色、边框、加载、空状态和错误状态。

Level 3 的 Agent Context 至少应返回：

- 当前 View 和可见区块。
- 当前选择和筛选器。
- 数据时间、来源和过期状态。
- 可执行 Action 与输入 Schema。
- 当前任务状态。

Agent 使用 `vibedesk:context-request/context` 获取这些信息，不应抓取截图或遍历任意 DOM。

## 12. 认证与自动验收

兼容等级不能由作者自行声称，必须由标准检查器生成。最低检查项：

- Manifest Schema。
- URL、安全头和 iframe 可嵌入性。
- Bridge 握手。
- 主题、语言和响应式布局。
- Action Binding 与权限闭环。
- 数据 Schema。
- Agent 与 Model 链路隔离。
- 独立访问。
- Level 3 ViewSpec 与 Context。

商店展示的等级、徽章、健康状态和测试时间都必须来自检查结果。
