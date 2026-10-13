# ADR-0006: Desk 双运行时 Agent Seam

- 状态：Accepted
- 日期：2026-08-29
- 取代：ADR-0005

## 背景

Newma-Desk 既需要作为 Newma 插件复用宿主 Agent，也需要作为完整项目独立运行。删除 Desk Agent Gateway、模型设置和本地 Copilot，会让独立部署失去 AI 能力；同时保留两套互不协调的 Copilot，又会造成上下文、会话和执行权分叉。

## 决策

1. Mod 与 Copilot 只依赖一个 Agent Runtime Seam。
2. 挂载 Newma 时使用 Newma Host Adapter：`owner=newma`、`aiExecution=host`，AI 请求交给当前宿主会话，Desk 不重复执行。
3. 独立运行时使用 Desk Gateway Adapter：`owner=desk`、`aiExecution=gateway`，由 Desk 提供 Agent / Model Gateway、Agent 设置和本地 Copilot。
4. Desk Gateway Adapter 可以连接本机 Codex、Claude、Gemini、Qoder、MiniMax CLI，也可以连接 Newma / Hermes 兼容 Runtime。
5. 设置提供 `auto`、`newma`、`local` 三种偏好。`auto` 在 Newma 挂载时固定走宿主，独立运行时使用已配置 Gateway Adapter；显式任务路由可以覆盖默认 Adapter。
6. Agent / Model Action 在 Newma 挂载模式下转成 Host Handoff；在独立模式下由 Control Plane 调用 Gateway。两种路径共享结构化 Context、DOM / HTML 与视觉快照兜底。
7. 每次本地 Agent 请求必须记录实际 Adapter；前端显示的执行入口与后台执行入口必须一致。
8. 快速问答优先使用 Model Gateway；未配置可用模型时，统一 Copilot 使用当前 Agent Adapter 的快速档，不暴露第二套界面。
9. Newma / Hermes 兼容 Adapter 必须识别实际会话接口后才可显示为可用，不能仅凭端口存在判定连接成功。
10. Shell 必须为当前 Mod 显式创建 Agent Runtime Binding；ModuleFrame 不得从嵌入状态或回调存在性推断 Newma / 本地所有权。
11. Adapter 路由必须先按运行方式与 capability 收窄，再应用全局、任务档位或 Mod 覆盖项；历史覆盖项不得跨运行方式执行。
12. Copilot 只能调用统一 `requestAgentEvidence()` Interface。取证顺序为结构化 Context、同源渲染 DOM/HTML、当前浏览器视觉快照、服务端重开 Mod 的视觉兜底、Manifest；业务组件不得自行跳过或重排该链路。
13. 本次请求取得的页面证据优先于服务端缓存。Context Store 只能补齐缺失字段，不得覆盖当前 page、Mod 元数据或视觉 Artifact。
14. 视觉 Artifact 对客户端只暴露 ID。Codex CLI Adapter 可以把受控本地图片作为真实附件传入；不支持图片输入的 Adapter 必须明确标记只收到引用，不得声称已经看图。

## 结果

- Desk 可以独立使用，也可以无缝挂载 Newma。
- Runtime Seam 有两个真实 Adapter，Interface 保持稳定，执行差异集中在一处。
- Mod 不需要理解 Newma、CLI 或模型供应商，获得更高 leverage；路由、上下文与错误处理保持 locality。
- 同一页面只显示一个 Copilot，避免宿主与 Desk 同时抢占请求。

## 否决方案

- 只保留 Newma Runtime：破坏 Desk 独立运行的通用性。
- 为 Newma 和独立模式分别开发两套 Mod AI Interface：会使每个 Mod 重复处理上下文和错误。
- 允许 Mod 直接执行 CLI：命令权限、工作区和审计会散落到各 Mod。
