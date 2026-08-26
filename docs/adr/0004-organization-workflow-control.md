# ADR-0004: 组织工作流使用独立 Workflow Control Module

- 状态：Accepted
- 日期：2026-08-25

## 背景

Creator Studio 已有深的创作 Run Control，但身份固定为本地单用户，定义和执行也强绑定创作 Registry。Orchestra 在 Desk 中主要是外部投决页面和 Agent 工作区桥，没有 Desk 自己掌控的组织工作流、节点责任、授权链和通用交付物模型。

直接扩展任一现有实现，会把创作 Stage、投委席位和组织级授权混进同一个 Interface，也会迫使未来研究、运营和交易流程理解不属于自身领域的状态。

## 决策

1. 新建独立 Workflow Control Module。其 Workflow Command Interface 统一管理 Workflow Template、Workflow Run、Organization Workflow Node、Node Assignment、Gate、Node Data Revision、Workflow Artifact 和 Workflow Audit Ledger。
2. Creator Run Control 继续是创作状态事实源，Orchestra 继续掌握现有投决运行；两者未来通过领域 Adapter 接入 Workflow Control，不立即迁移或复制现有状态。
3. 人和服务器 Agent 都表示为 Principal。Node Assignment 保存 accountable principal 和 reviewer principal；Delegation Grant 只提供 coverage，不转移 accountability。
4. Delegation Grant 支持 organization、template、run、node 和 role Scope。授权不得扩张 Scope、Action、有效期或转授权深度；撤销必须级联使后代 Grant 失效。
5. Organization Workflow Node 使用 Execution Claim Lease 防止重复执行。所有 Run 命令使用 expected revision；同一节点同时只能有一个有效 Claim。
6. Node Data Revision 和 Workflow Artifact 都只追加新版本，不覆盖旧版本。Artifact 保存输入引用，上游替换后沿引用图把下游 Artifact 与 Node 标记为 stale。
7. Workflow Audit Ledger 同时记录实际执行 Principal、accountable Principal 和 Delegation Grant。授权变化不得改写既有责任快照。
8. 本地 Desk 暂以 Workspace ID 作为 Organization ID，并以 `X-Workflow-Principal-Id` 作为本地 Identity Adapter。远程组织部署必须替换为可验证的身份 Adapter，不能把请求头本身当作认证。

## 结果

- Workflow Control Module 的 Interface 小于其 Implementation，模板、运行、授权、领取、版本和审计集中，获得更高 Depth。
- 组织流程获得 locality：责任、授权和交付物规则只在一个 Module 中修改和验证。
- Creator、投决、研究和未来业务 Adapter 共享同一协作语义，获得 leverage，同时保留各自领域状态。
- 服务器 Agent 可以跨多个工作流同时授权和被授权，但不能通过转授权扩大自身权限。
- 本地身份模式适合 Desk 本地测试；远程部署前必须增加强身份 Adapter 和 Agent 回调签名。

## 否决方案

- 直接把 Creator Studio 改成通用工作流：创作 Stage、编辑器和发布语义会泄漏到全部调用方。
- 从 Orchestra 页面反推通用模型：Desk 当前只掌握导航和工作区桥，没有足够的 workflow Depth。
- 授权时直接替换节点负责人：无法区分 accountability 与 coverage，也会破坏历史责任审计。
- 只依靠 Agent 会话或 Mod Session：它们证明页面或会话访问，不能表达节点 Scope、职能、转授权深度和撤销链。
