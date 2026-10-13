# ADR-0005: Newma Runtime 独占 Agent 执行权

- 状态：Superseded by ADR-0006
- 日期：2026-08-29

## 背景

Newma-Desk 是挂载在 Newma / Hermes Agent Runtime 下的 Mod Surface。Desk 曾同时保留 Agent Gateway、Model Gateway、CLI Adapter、模型设置和本地 Copilot，造成两套会话、两套模型配置、上下文分叉，并让 Mod 无法判断 AI 请求究竟由 Desk 还是 Newma 执行。

## 决策

1. Newma / Hermes Runtime 是模型、Agent、会话、记忆、Skills 和工具执行的唯一所有者。
2. Desk 只掌握 Mod Surface、Mod Page Context、Mod Visual Context、领域 Action、Artifact 和 Workflow State，不创建第二套 Agent 内核。
3. `vibedesk:init.runtime` 只在 Desk 真实挂载 Newma 会话时出现；独立 Desk 不声明 Runtime，也不显示 Agent 设置、本地 Copilot 或模型配置。
4. Mod 使用带 `instanceId + modId` 的 `vibedesk:copilot-open` 请求 Newma Agent。Desk 校验来源与 Bridge 握手后转交当前 Newma 会话，不在 iframe 后台自动执行。
5. Agent / Model Action 由 Desk 同步页面 Context 后转成 Runtime Handoff。直接调用 Desk Control Plane 时返回 `409 runtime_required`，不得在 Desk 内创建任务或调用模型。
6. 结构化 Context 优先；同源渲染 DOM / HTML 是第一兜底，受限 PNG 视觉快照是第二兜底。三条链路都只为 Newma Runtime 提供页面证据。
7. Desk 内旧 Agent / Model Gateway、CLI Adapter、会话存储和模型配置已删除；测试不得通过注入 Adapter 重新启用第二套 Runtime。

## 结果

- Agent Runtime Ownership 只有一个事实源，模型配置、会话和工具权限不再分叉。
- Desk Bridge 的 Interface 更小，Mod 只需发布 Context、Visual Context 和受控 Action，获得更高 locality。
- 独立 Desk 可以完整测试数据、交互、Artifact 和 Workflow State，但 AI 功能会明确要求 Newma Runtime。
- Newma 可以在同一会话中组合多个 Mod 的 Context，而 Desk 不需要理解 Agent 内部调度。

## 后续

该决策错误地把“挂载 Newma 时避免双重执行”扩大为“Desk 永远不能独立运行 Agent”。ADR-0006 改为统一 Agent Runtime Seam，并保留 Newma Host Adapter 与 Desk Gateway Adapter 两种运行方式。

## 否决方案

- 保留 Desk Agent Gateway 作为离线备用：会重新形成第二套会话和权限事实源。
- Mod 直接调用模型或 CLI：凭据、记忆、工具权限和审计会散落到各 Mod。
- 裸 `postMessage` 打开 Copilot：缺少实例和 Mod 作用域，无法可靠验证来源。
