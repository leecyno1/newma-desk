# ADR-0003: OpenChatCut 以完整上游和薄 Adapter 接入协同剪辑

- 状态：Accepted
- 日期：2026-08-23

## 背景

Creator Studio 需要让用户在同一剪辑节点中自由切换人工时间线操作与 Desk Agent 对话操作，并保证两种入口看到同一工程、同一审核结果和同一交付物。OpenChatCut 已具备完整时间线、EditorCore Command、外部 MCP 编辑会话、修改提案、原子提交、Undo、模板和导出能力。拆取其局部组件会破坏这些能力之间的内部一致性，也会显著增加跟随上游更新的成本。

## 决策

1. OpenChatCut 保持完整上游仓库，通过 External Editor Runtime 和薄 Adapter 接入；Newma 默认不修改其核心时间线、EditorCore、MCP、项目存储和模板实现。
2. Newma Creator Run Control 继续掌握任务、Workflow Node、版本、审核、Artifact Lineage 和跨节点状态；OpenChatCut 仅在编辑会话期间掌握真实时间线和编辑器内草稿。
3. 人工操作与 Agent 操作必须落到 OpenChatCut 同一套 EditorCore Command。外部 Agent 使用 `begin_edit_session → 编辑 Draft → review_edit_session → 人工批准/拒绝`，不得绕过提案审核直接改正式时间线。
4. Newma Editor Session 保存 OpenChatCut 的稳定 Project ID、启动入口、MCP 入口、外部编辑会话 ID、提案状态和模板引用；成片、时间线交换记录和剪辑决策仍通过 Creator Command 固化并回写为版本化 Artifact。
5. 模板分三层：上游内置模板、用户收藏/节点预设、已跑通工程模板。三层均在 Creator Marketplace 展示，但模板真实内容仍由来源编辑器保存，Newma 只保存稳定引用、适用节点和参数。
6. 上游更新通过独立 Git 工作区和稳定 Adapter 字段吸收。只有上游缺少必要稳定接口时才维护小型 overlay；不得把 OpenChatCut 与 OpenCut 源码混成一个编辑器。
7. OpenCut 继续作为备用研究对象，待其 MCP、Editor Interface 和核心运行时稳定后再评估第二 Adapter，不阻塞当前上线。

## 结果

- 上线路径短：无需重写完整剪辑器，Newma 只建设会话、提案、模板和产物回写接口。
- 整合度高：人工和 Agent 共用真实时间线，Newma 双端操作共用 Creator Command 与 Run revision。
- 更新成本可控：上游主体可独立拉取更新，Newma 的兼容面集中在一个 Adapter。
- 编辑器故障不会污染主链状态；未回写 Artifact 的编辑结果不会被下游消费。
- 同一 Newma Editor Session 绑定同一 OpenChatCut Project ID，人工入口与 Agent 不再重复选工程。

## 否决方案

- 复制 OpenChatCut 的时间线组件到 Newma：短期看似统一，实际会复制项目格式、命令、Undo、MCP 和渲染状态，形成两套事实源。
- 仅嵌入网页、不建立 Editor Session：人工能操作，但 Agent 提案、审核、版本和交付物无法同步。
- 让 Newma 直接写 OpenChatCut 工程文件：绕过 EditorCore，无法保证撤销、迁移和上游兼容。
