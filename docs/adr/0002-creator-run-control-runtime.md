# ADR-0002: Creator Studio 使用统一 Run Control Runtime

- 状态：Accepted
- 日期：2026-08-15

## 背景

Creator Studio 的可视化操作、Desk Agent、媒体脚本、人工编辑器和发布连接器原本可能各自维护状态。这样会产生重复执行、前端假进度、发布确认失效、产物覆盖和下游继续消费旧素材的问题。

Video Shotcraft 的可取机制是：注册表作为事实源，Brief、设计、镜头和 QA 产物分阶段确认，每个镜头与产物都可回溯，未实现能力明确标记。

## 决策

1. Creator Run Control Module 是创作状态的唯一事实源，Agent 与前端只调用同一 Creator Command Interface。
2. Workflow Node 通过持久化 Creator Execution Job 异步运行；取消必须终止真实子进程，重启后不得把中断任务伪装成成功。
3. 人工编辑统一进入 Editor Session Runtime，并把保存结果回写为版本化 Artifact。
4. 发布采用“预检 → 一次性明确确认 → 执行 → 回执验真”。确认进入队列即消费，重试必须重新确认。
5. Artifact Lineage 统一生成版本、内容摘要、父产物、生产 Job 和参数摘要；新版本沿 Handoff 图递归传播 stale。
6. Registry 只保存稳定 Adapter ID。CLI、编辑器、发布连接器和媒体项目差异留在 Adapter Implementation 内。

## 结果

- Creator Run Control Module 的 Interface 保持小而稳定，执行、编辑、发布和 Lineage 复杂度集中在 Implementation，获得更高 Depth。
- Agent 与可视化操作共享 revision、事件和 Gate，避免双端状态分叉。
- Artifact Lineage 提供来源、版本和影响范围，旧版本可审计但不能继续作为有效输入。
- 发布的不可逆动作具有明确、可消费、可审计的确认记录。

## 否决方案

- 前端轮询脚本目录推断进度：没有真实 Job 状态，重启和取消语义不可验证。
- 每个编辑器自行保存产物：Interface 分散，无法统一版本、Gate 和 stale 传播。
- 发布按钮直接调用外部脚本：缺少一次性确认、账号预检和回执验真。
- 覆盖旧 Artifact 文件：丢失审计链，也无法判断哪些下游结果已经失效。
