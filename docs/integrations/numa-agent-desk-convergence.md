# Numa Agent × Newma-Desk 一体化需求

状态：Desk 侧框架已完成，Numa Agent 侧待对齐
版本：0.2
日期：2026-07-29

## 1. 产品目标

Numa Agent 与 Newma-Desk 不应是两个割裂产品，而应共享同一会话、同一工作区和同一 MODS 项目模型，并根据用户是否打开 Mod 自动切换布局：

1. **纯对话模式**：没有打开 Desk Mod 时，Numa 保持传统对话界面。
2. **Desk 协作模式**：打开 Mod 后，左侧显示项目导航，中间显示 Mod 可视化工作区，Numa 对话压缩到右侧，并继续使用原会话。
3. **跨界面连续性**：Desk 中针对 Mod 发起的提问可以在 Numa 中继续；Numa 中的同一会话也能一键返回原 Mod、原页面和最近上下文。

目标结构：

```text
┌──────────────────┬──────────────────────────────┬──────────────────────┐
│ 项目 Logo / 页面 │ 当前 Mod 可视化工作区         │ Numa Agent 当前会话   │
│ Project → Pages  │ selection / filters / actions │ history / tools / edit │
└──────────────────┴──────────────────────────────┴──────────────────────┘
```

## 2. 共同视觉基线

Desk 侧采用 Numa Desktop 当前的 Verdigris 设计体系，Numa 后续不要为嵌入 Desk 再建立第二套主题。

### 2.1 默认深色主题

- 主背景：`#0f1714`
- 次级背景：`#121d18`
- 内容表面：`#16211c`
- 抬升表面：`#1a2821`
- 悬停表面：`#203129`
- 暖金强调：`#c89a5a`
- 主文字：`#f3ecdd`
- 次文字：`#cfc7b7`
- 弱文字：`#a8b4a5`

### 2.2 默认浅色主题

- 主背景：`#f4efe3`
- 次级背景：`#eae1d0`
- 内容表面：`#fbf7ef`
- 抬升表面：`#fffaf1`
- 暖金强调：`#a87432`
- 主文字：`#173128`
- 次文字：`#3f5c51`
- 弱文字：`#66766e`

要求：无渐变、低噪声、紧凑但不拥挤；圆角、边框、悬停和选中态使用同一组 token。字体优先 `Cairo` / `Manrope`，中文使用系统可靠回退。

## 3. MODS 项目导航接口

Desk 的一级菜单固定为十四个核心投研栏目，并保留“其他”作为非投研工具和暂未归类项目的兜底。二级面板按完整来源项目分组，再显示该项目的全部页面。Numa 未来读取 MODS 时必须复用该模型，不能重新硬编码一套导航，也不能按页面用途拆分完整项目。

页面 Manifest 使用：

```json
{
  "navigation": {
    "project": {
      "id": "fundamentals",
      "name": "宏观面",
      "order": 20,
      "description": "经济数据、行业、产业链与宏观研究"
    },
    "directory": {
      "id": "research-suite",
      "label": "Vibe Research",
      "order": 10
    },
    "label": "个股研究",
    "itemOrder": 10,
    "role": "page"
  }
}
```

一级栏目标志由宿主根据有效栏目标题自动生成中文短标。用户改名后，一级栏、二级标题与标志同步更新，但跨 Desk / Numa 的路由和会话交接始终使用稳定的 `project.id`。栏目内的完整项目身份使用稳定的 `navigation.directory.id`，显示名称使用 `navigation.directory.label`。

Suite Discovery 在展开页面时必须把同一个 `navigation.project` 和 `navigation.directory` 保留到每个页面。`navigation.project` 只能选择十四个核心投研栏目之一或“其他”；`navigation.directory.id` 必须等于 Suite ID，代表不可拆分的完整项目。旧 Suite 未声明栏目时整套落入“其他”，不能把兄弟页面分别归入不同栏目或项目组。

## 4. 会话交接协议

### 4.1 语义

- **Desk → Numa**：继续当前 Agent 会话，同时携带当前 `projectId`、`modId`、页面上下文版本和返回地址。
- **Numa → Desk**：返回同一个 Mod，并自动打开右侧 Agent 面板；Desk 从最近持久化的 Mod Context 恢复选择项、筛选条件和页面摘要。
- 切换界面不创建新的 Agent 会话，不复制一份脱离上游的本地聊天记录。

### 4.2 交接载荷

```json
{
  "version": "1.0",
  "conversation": {
    "agentId": "hermes-webui",
    "upstreamSessionId": "opaque-session-id"
  },
  "desk": {
    "origin": "https://desk.example",
    "workspaceId": "workspace-id",
    "projectId": "research-suite",
    "modId": "stock-research",
    "contextUpdatedAt": "2026-07-29T00:00:00Z",
    "returnUrl": "https://desk.example/?mod=stock-research&copilot=1"
  },
  "presentation": {
    "mode": "desk",
    "agentPane": "right"
  }
}
```

### 4.3 安全要求

生产环境不要把长期凭据、用户身份或完整页面数据直接写入 URL。

推荐流程：

1. Desk 向统一后端申请一次性交接令牌。
2. 令牌绑定用户、工作区、上游会话和允许的 Desk Origin，5 分钟内有效且只能消费一次。
3. Numa 只接收 `handoff=<opaque-token>`，登录后向后端换取载荷。
4. `returnUrl` 必须经过 Origin allowlist，只允许回传 `mod`、`copilot` 和受控恢复标识。

本地开发可以使用 URL fragment 传递不含凭据的临时载荷，但不能作为公网最终实现。

Desk 当前已实现的本地协议为：

```json
{
  "protocol": "newma-desk.v1",
  "source": "newma-desk",
  "projectId": "vibe-research",
  "moduleId": "stock-research",
  "workspaceId": "workspace-id",
  "upstreamSessionId": "opaque-session-id",
  "returnTo": "https://desk.example/?mod=stock-research&copilot=1#newma-handoff=..."
}
```

- `workspaceId`、`upstreamSessionId` 和交接载荷只进入 fragment，不进入 query、HTTP 请求、访问日志或 referrer。
- Numa 目标必须命中显式 Origin allowlist；Desk 回链必须与当前 Desk 同源。
- Desk 成功消费返回载荷后会立即从地址栏清除 `newma-handoff` fragment。
- 本地聊天记录按 `workspaceId + moduleId` 隔离保存；Numa 继续使用 Hermes 的同一 `upstreamSessionId`，不复制第二份上游会话。
- Shell 可通过 `VITE_NUMA_AGENT_URL` 与 `VITE_NUMA_AGENT_ALLOWED_ORIGINS`，或同名运行时配置 / meta 标签配置配套入口。

## 5. Numa Agent 需要实现的工作

### 5.1 自适应三栏 Shell

- 增加 `chat-only` 与 `desk-collaboration` 两种布局状态。
- `chat-only` 保持现有对话体验。
- `desk-collaboration` 中间挂载 Desk/Mod 工作区，现有聊天区变为右栏。
- 右栏建议宽度 `360–420px`；窗口不足时改为覆盖抽屉，不压坏 Mod 页面。
- 用户关闭 Mod 后，右栏平滑恢复为主对话区，不丢失输入草稿、滚动位置和工具运行状态。

### 5.2 复用项目导航

- Numa 不维护项目名称和页面清单的硬编码数组。
- 从 Desk Navigation Compiler 的结果或同一 Suite Descriptor 读取项目、Logo、页面、设置入口和排序。
- 项目设置页、冻结、排序和隐藏偏好需要与 Desk 共用同一份用户偏好。

### 5.3 消费 Desk 会话交接

- 接收一次性交接令牌，打开/恢复对应 Hermes 会话。
- 在会话顶部显示来源卡片：项目名、Mod 名、上下文更新时间、“返回 Mod”按钮。
- 后续消息继续附带 Mod Context，但应只引用后端保存的结构化上下文，不信任 URL 自带页面正文。
- 会话发生新的选择或 Agent 动作后，更新来源卡片和可返回地址。

### 5.4 从 Numa 打开 Desk

- “打开可视化工作区”动作必须复用当前会话，不创建新线程。
- 若目标 Mod 已安装，直接进入；未安装时显示明确安装确认，不静默安装。
- 回到 Desk 的最小地址格式为 `?mod=<id>&copilot=1`。
- Desk 不可达时继续保留对话，并给出重试/独立打开选项。

## 6. Desk 侧对应能力

Desk 侧当前已经提供：

- 项目级一级 Logo rail 与项目内二级页面面板。
- `navigation.project` 与 Project Logo 标准。
- 当前 Mod Context 的宿主持久化。
- Hermes 任务结果中的 `agentId` / `upstreamSessionId`。
- `?mod=<id>&copilot=1` 深链恢复。
- “继续到 Numa”入口；只有配置了合法 Numa 目标且存在可续接会话时才显示。
- 专业预置问题与 Mod 修改模式。
- 项目标志与页面面板的一体折叠、项目/页面拖拽排序与冻结。
- Vibe Research、Vibe Trading 作为独立项目入口，继续使用 Desk 统一数据与 Agent 设置。

## 7. 验收场景

1. 用户在“个股研究”中提问，得到回复后点击“继续到 Numa”；Numa 打开的是同一 Hermes 会话，历史不重复、不丢失。
2. 用户在 Numa 中继续三轮对话，点击“返回个股研究”；Desk 回到原 Mod 并自动打开右栏。
3. 用户切换到 Vibe Trading，一级 Logo 变化，二级页只显示 Trading 页面；Research 页面不混入。
4. 关闭 Desk 后 Numa 恢复传统对话布局，输入草稿和会话滚动位置保持。
5. 视口缩窄时，左侧导航与右侧 Agent 采用折叠/覆盖策略，中间 Mod 不出现水平挤压或不可操作区域。
6. 交接令牌过期、被重复消费、用户不匹配或 return Origin 不在 allowlist 时必须拒绝。
7. Mod 未提供结构化上下文时，Numa 明确标注“仅使用 Manifest 基础信息”，不能伪装为已读取页面。

## 8. 不在本轮范围

- 不把 Numa 的模型或凭据重新配置到单个 Mod。
- 不允许 Mod 自带 Agent 绕过 Desk/Numa 的统一 Agent 设置。
- 不在 URL 中传输完整聊天历史、访问令牌或用户隐私数据。
- 不要求所有第三方 Mod 立即达到最高 Bridge 等级；低等级 Mod 使用 Manifest 回退上下文。

## 9. 当前 Desk 实现快照（2026-07-29）

本节描述的是 Newma-Desk 当前已经落地、Numa Agent 可以据此对接的真实行为，不等于最终目标协议。

### 9.1 已落地的 Desk 侧代码边界

- `apps/shell/src/lib/numaHandoff.ts` 已实现本地 `newma-desk.v1` 协议生成与解析，包括：
  - `buildNumaHandoffUrl()`：把 `moduleId`、`projectId`、`workspaceId`、`upstreamSessionId` 和 `returnTo` 写入 `newma-handoff` fragment。
  - `buildDeskReturnUrl()`：把 Desk 返回地址规范化为 `?mod=<id>&copilot=1`，并把连续性标识写入 fragment。
  - `readNumaHandoffPayload()` / `readDeskReturnHandoff()`：校验往返载荷、模块、工作区和项目是否匹配。
  - `resolveNumaAgentUrl()`：限制 Numa 入口必须与 Desk 同源、loopback，或命中显式 allowlist。
- `apps/shell/src/components/ModCopilot.tsx` 已把该协议接进真实用户流：
  - 进入 Mod Copilot 时会读取本地会话元数据，并消费从 Numa 返回的 handoff fragment。
  - 若成功返回，会立即清除地址栏里的 `newma-handoff`，并把 `upstreamSessionId` 恢复到当前 Mod 会话。
  - 只有存在可续接的 `upstreamSessionId` 时，才会生成“转到 Numa Agent 继续当前对话”链接。
- `apps/shell/src/lib/numaHandoff.test.ts` 与 `apps/shell/src/components/ModCopilot.test.tsx` 已覆盖当前协议的关键约束：
  - 连续性标识不进入 query string。
  - fragment 在消费后被移除。
  - Numa 入口需要 allowlist。
  - Mod Copilot 会把真实任务结果中的 `upstreamSessionId` 持久化并用于 handoff。

### 9.2 当前实现与目标态之间的明确断层

- 当前 Desk 只实现了**前端本地 fragment 协议**，尚未实现第 4.3 节要求的“一次性交接令牌 + 统一后端换票”。
- 当前载荷中心是 `moduleId`，而目标文案同时使用 `modId` / `moduleId` 两个词。Numa 侧对接时应视 `moduleId` 为当前真实字段，后续若升级字段名需要版本迁移。
- 当前 Desk 返回链路只保证 `?mod=<id>&copilot=1` 和受控 fragment，不包含“来源卡片”“上下文更新时间”“结构化上下文等级”等 Numa UI 所需展示字段。
- 当前 Desk 持久化的是 `workspaceId + moduleId` 级本地会话元数据，不是跨产品共享会话存储；“同一 Hermes 会话”的真实性目前依赖 `upstreamSessionId` 延续，而不是共享消息仓库。
- 当前 Desk 只负责生成可安全消费的跳转链接，不负责在 Numa 内部恢复三栏 Shell、项目导航或右栏收缩行为。

### 9.3 Numa 侧接入时的最低兼容假设

- 现阶段 Numa 若要与 Desk 联调，必须先兼容 `newma-desk.v1` fragment 协议，而不是直接假设令牌换票已经存在。
- Numa 返回 Desk 时，必须回写 `source: "numa-agent"` 形态的 Desk return payload，否则 `readDeskReturnHandoff()` 不会恢复会话。
- 在统一后端未落地前，Numa 不应把 fragment 协议误当成公网最终方案，也不应在服务端日志、重定向链或 query 参数中展开这些连续性字段。

## 10. 推荐文档结构

为避免“目标需求”“当前实现”“未来迁移”混写，建议本文件后续稳定为以下结构：

1. 产品目标与最终交互形态
2. 共享术语与对象模型
3. Desk 当前已实现接口
4. Numa 当前需兼容的最小协议
5. 目标态协议与安全模型
6. 布局与导航对齐要求
7. 会话连续性与上下文恢复
8. 验收场景
9. 非范围项
10. 迁移计划与版本切换

其中第 3、4、5 节要明确区分：

- `Current`：今天已经存在、可以按代码对接的行为。
- `Target`：统一后端完成后才成立的目标协议。
- `Migration`：从 fragment 协议迁到 token 协议时，字段、版本和回退策略如何处理。

## 11. 参考线程与本地定位说明

- `codex://threads/019f7000-acb9-79c0-9432-f4e4c6777fe3` 在本机可定位到：
  - `/Users/lichengyin/.codex/sessions/2026/07/17/rollout-2026-07-17T20-15-20-019f7000-acb9-79c0-9432-f4e4c6777fe3.jsonl`
- 该线程的 `session_meta.cwd` 指向：
  - `/Volumes/PSSD/Projects/MonkeyAI`
- 因此它可作为 Numa/MonkeyAI 侧历史上下文参考，但它不是一个可供产品运行时直接读取的标准接口，也不构成 Desk ↔ Numa 的线上协议。
