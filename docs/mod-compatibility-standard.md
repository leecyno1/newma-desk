# Newma-Dock Mod Compatibility Standard 1.0（工作草案）

状态：Draft 0.3  
Manifest：1.1  
Bridge Protocol：1.0  
ViewSpec：1.0

本文定义 Mod 如何独立运行、嵌入 Newma-Dock、调用数据与 AI 能力，以及如何被人和 Agent 共同理解。文中的“必须”“应该”“可以”分别对应 MUST、SHOULD、MAY。

## 1. 核心边界

一个 Mod 是：

> 独立网页入口 + 运行 Manifest + 明确 Action + 可选数据服务 + 可选 Agent 语义。

Newma-Dock 负责导航、隔离、身份、权限、Gateway、跨 Mod 上下文和统一展示范式。Mod 负责自己的业务页面和业务后端。Newma-Dock 不复制上游项目源码，也不要求上游项目迁入同一个后端。

同一个 Mod 必须同时支持：

- 通过稳定 URL 独立访问。
- 在 Newma-Dock iframe 中运行。
- 保持自己的发布、路由和后端生命周期。

## 2. 三级兼容等级

等级是累积关系。Level 3 必须同时满足 Level 1 和 Level 2。

### Level 1：Embed Ready（可嵌入级）

Mod 必须：

- 有可独立访问的 HTTP(S) 页面。
- 允许被配置的 Newma-Dock Origin 嵌入。
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
- 使用 Newma-Dock Gateway，而不是把密钥下发到浏览器。
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

Manifest 中的 `compatibility.level` 是 Mod 声明等级，不等于 Newma-Dock 已认证等级。静态合同检查只能确认字段、权限、Action Binding 和 Schema 关系有效，不能证明页面当前可运行。

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
- Newma-Dock HTTP API 版本

新增可选字段属于兼容变更；删除字段、重命名、类型变化、认证方式变化必须发布新主版本。公开版本至少保留当前版本和前一版本的兼容期。

Manifest 1.0 是兼容模式。Manifest 1.1 是新 Mod 的标准入口。1.0 Mod 可以继续使用 `agentCapabilities` 和旧 `vibedesk:ready/config` 消息，但不能获得 Level 2 或 Level 3 认证。

## 4. 标准文件

- `mod.json`：商店描述、作者、上游仓库、截图和安装信息。
- `module.json`：运行 Manifest；Newma-Dock 1.x 为兼容现有包继续使用此文件名。
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
    "groupLabel": "量化",
    "groupOrder": 20,
    "itemOrder": 10,
    "label": "因子实验室",
    "directory": {
      "id": "vibe-trading-quant",
      "label": "量化工具",
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
  `service` 时由 Newma-Dock 统一数据路由选择 Provider。
- Agent Action 必须使用 `task` 执行方式。
- Model Action 必须使用 `request` 执行方式。
- `trade.execute` 必须使用 `strong` 确认。

### 5.1 导航与二级目录合同

导入多页面项目时，每个可独立授权、独立运行、独立提供 Agent Context 的页面仍然必须是一个独立 Mod。属于同一项目套件的兄弟 Mod 通过 `navigation.directory` 聚合到 Newma-Dock 的二级侧边栏，而不是把上游页面全部塞进一个 Mod 或在母侧边栏平铺。

```json
{
  "navigation": {
    "groupLabel": "市场",
    "groupOrder": 10,
    "itemOrder": 20,
    "label": "扫描器",
    "directory": {
      "id": "market-suite",
      "label": "行情工具",
      "order": 5
    },
    "icon": "market"
  }
}
```

字段约束：

- `groupLabel`：母侧边栏一级分类名称。
- `groupOrder`：一级分类默认顺序。
- `itemOrder`：页面在一级分类或二级目录内的默认顺序。
- `label`：导航中的紧凑页面名称；省略时使用 Mod `name`。
- `directory.id`：稳定目录 ID。同一 `groupLabel` 下使用相同 ID 的 Mods 会进入同一个二级侧边栏。
- `directory.label`：目录显示名称。
- `directory.order`：目录在一级分类中的默认顺序。
- 未声明 `directory` 的 Mod 直接显示在一级分类中，保持旧 Manifest 兼容。

Desk 中的用户配置优先于 Manifest 默认值，并只保存在本地 Workspace：用户可以把页面移入其他二级目录、拖拽排序或改为一级显示；这些操作不得修改上游 Manifest。页面或目录被冻结后进入稳定区域并禁止拖拽，取消冻结后才可再次移动。导入器必须保持 `id` 稳定，不能使用随机值或随显示文案变化的值。

每个实际存在的二级目录由 Desk 自动追加“项目设置”入口，上游项目不需要再开发一套设置页面。该页面的作用域是 `用户 + Workspace + directory.id`，至少包含：套件页面清单、统一数据 Provider 路由和 Agent 设置入口。用户自定义移动页面后，设置页应按当前目录成员实时更新。

推荐的项目接入流程是：上游路由清单 → 每个路由生成一个 Mod Manifest → 为同套件路由写入相同 `directory.id` → 运行 Manifest Schema 与兼容性检查 → 注册到商店。这样上游不需要实现 Newma-Dock 侧边栏组件。

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

用于确定性业务接口。必须声明 Capability、输入输出 Schema 和权限。密钥只保存在 Newma-Dock 或对应数据服务端。

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

此时 Action ID 默认就是 Capability ID；也可以通过 `binding.capability` 显式映射。Desk 使用 `navigation.directory.id` 作为套件路由作用域；未加入二级目录时回退到 Mod ID。Provider 默认按 `priority` 从小到大选择，用户可以在项目设置中按 Capability 覆盖。

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

偏好接口使用 `X-User-Id` 与 `X-Workspace-Id` 隔离。保存时必须验证 Provider 确实提供对应 Capability；失效偏好不得静默切换到另一个 Provider。

### Local

用于 Newma-Dock 自身提供的受控能力，例如本地刷新。未注册的 Local Handler 必须返回不可用，不得回退到 Agent 猜测执行。

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
- Newma-Dock 实际批准的权限与 Action。

### Mod → Desk

Mod 收到并验证配置后必须发送 `vibedesk:ack`。所有消息必须验证准确的 `source`、`origin`、`modId` 和 `instanceId`。

Manifest 1.0 的 `vibedesk:ready/config` 在 1.x 兼容期继续可用。

### 7.1 最小权限 Mod Session

Manifest 1.1 Mod 在调用 Action 前必须获得短期 Session。Session 绑定：

- 用户、Workspace、Mod 和已发布 Revision。
- 本次 iframe 或独立页面的 `instanceId`。
- Manifest 实际声明的权限与 Action。
- 明确的过期时间；MVP 默认 15 分钟。

Desk 嵌入模式下，Access Token 只能保存在宿主页面，不得发送给 iframe。`vibedesk:init` 只向 Mod 暴露 Session ID、过期时间和批准后的 Grants。独立访问的 Mod 可以通过 SDK 自行申请 Session，但仍必须使用稳定的独立页面 `instanceId`。

Action 和 Context HTTP 请求必须同时携带：

```http
Authorization: Bearer <mod-session-token>
X-Newma-Dock-Instance-Id: <instance-id>
```

Token 与 `instanceId`、Mod、Revision 或 Action 任一不匹配时必须拒绝。生产环境和多进程部署必须配置固定的 `NEWMA_DOCK_MOD_SESSION_SECRET`；不得依赖进程启动时生成的临时密钥。

### 7.2 Agent Context 消息

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

### 7.3 宿主代理 Action

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

### 7.4 Desk Mod Copilot

Newma-Dock 在宿主层提供统一的右侧 Mod Copilot。该能力属于 Desk，不属于单个 Mod：

- 抽屉、会话显示、停止任务、Agent 选择、问答/修改模式由 Desk 统一实现。
- 每次发送前，Desk 必须使用 `reason: agent` 请求当前页面 Context。
- 支持 Context Bridge 的 Mod 显示“已同步当前页面”；未支持的 Mod 使用 Manifest、入口和版本作为明确标注的降级上下文。
- 对话记忆按“用户 + Agent + Mod”隔离，切换 Mod 不得串用前端消息或后端长期上下文。
- “提问”模式必须只读；本机 Agent 应使用只读沙箱，不得修改工程或外部状态。
- “修改”模式必须由用户在界面显式选择，并以 `capability: module.edit` 和 `context.vibedesk.mode: edit` 双重声明；Agent 只能写入当前 Mod 映射的 Workspace。
- 修改完成后必须返回改动文件、行为变化和验证结果，不得读取或输出 `.env`、密钥和登录凭据。

Mod 可以在独立运行时保留自己的问答入口；嵌入 Newma-Dock 时，通用“针对本页问答”入口应该隐藏，避免出现两套会话、两套 Agent 设置和重复的右侧抽屉。业务专属的 AI 复盘、摘要、自动回复、研究沉淀和 Action 不属于重复能力，不应因此移除。

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

Newma-Dock 必须在调用前验证输入，在返回 Mod 前验证输出。未安装、未授权或 Schema 不匹配的 Service 不得被调用。

## 9. 事件与 Workspace Context

事件用于“发生了什么”，Context 用于“当前是什么”。两者不能混用。

标准 Context 至少覆盖：

- 当前证券或研究对象。
- 日期范围。
- 当前组合。
- 当前研究主题。
- 当前数据集和回测任务。

跨 Origin、独立打开和切换页面的 Context 必须由 Newma-Dock 后端持久化；不能只依赖 iframe 或 BroadcastChannel。

## 10. 安全要求

- 浏览器不得收到上游 API Key、模型 Key 或 Agent 凭据。
- Newma-Dock 必须按照 Manifest 权限生成最小权限运行环境。
- iframe `sandbox` 和 Permissions Policy 必须由声明权限推导。
- Mod Origin 与 Desk Origin 应隔离。
- 所有写入、交易和外发动作必须可审计。
- 安装包必须记录来源仓库、固定 Commit、校验值和发布者。
- 调用必须携带可关联的 traceId，但日志不得记录密钥和完整敏感输入。

## 11. 展示与 Agent 语义

所有级别应该使用 Newma-Dock Design Tokens：字体、字号、间距、颜色、边框、加载、空状态和错误状态。

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
