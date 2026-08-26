# Creator Studio P0 端到端验收台账（0817 run）

记录对象：Run `creator-80e7e48ca127`（标题「0817 三阶段重跑测试」，选题 T01「NV Rubin升级链点燃AI算力军备赛：OpenAI新动作与台积电产能卡位」，Lane `wechat_article`）。

台账目的：交接文档「推荐开发顺序」第 1 条——记录每个节点的输入、命令、产物和 Gate，作为后续修复索引。

## 1. 节点推进记录

| 节点 | 首次执行 | 状态 | 真实产物 | 备注 |
|---|---|---|---|---|
| intake.source_setup → intake_review | 08-16 23:24–23:28 | succeeded | creator_nodes/ 各 packet + 01_内容采集 | 正常 |
| brief.event_cluster → brief_review | 08-16 23:28–08-17 02:54 | succeeded | 02_内容聚合及选题分析（brief_manifest 等） | 正常；topic_pool / research_brief 会话后停留 waiting_user |
| draft.evidence_base / outline / article_draft / visual_package | 未通过 Run Control 执行 | pending（0 登记） | 磁盘存在真实产物（05_初稿生成，08-17 10:55 由 media 侧脚本生成） | 双状态轨道问题，见 §3-1 |
| draft.draft_review | 08-17 02:57 | succeeded（异常放行） | packet：final_structure_snapshot / transwrite_handoff | 审批契约漏洞，见 §2；已修复 |
| transwrite.route_select | 08-18 19:48 | succeeded | 06_转写生产：transwrite_decision.json / lane_jobs.json | 修复后续跑首个节点，读磁盘 draft_manifest 成功 |
| transwrite.script_rewrite | 08-18 19:50 | succeeded | 06_转写生产：transwrite_manifest.json（status=prepared_for_skill_execution）+ t01/wechat_article/source_draft.md | 素材门禁拦截→人工回填真实初稿→执行成功 |
| transwrite.director_storyboard | — | pending | — | 文章 lane 不适用（需 video_script + claim_evidence_ledger） |
| transwrite.transwrite_review | — | pending | — | 等 final_delivery_manifest |

## 2. 发现并修复的缺陷

### 2.1 审核放行缺少素材门禁（已修复，08-18）

- 现象：draft_review 在本阶段零产物登记时被 `creator.node.approve` 放行，下游 handoff 停在 needs_material，链路卡死于 transwrite.route_select。
- 根因：Newma-Desk `creator_studio/service.py` 的 `execute_command` 只对 `creator.node.run/retry` 强制 Material Requirement 校验，approve 为纯状态翻转。
- 修复：校验集合扩展为 `{run, retry, approve}`；新增测试 `test_review_gate_approval_rejects_node_with_unsatisfied_materials`（修复前 200 放行、修复后 422 拒绝）。全量 API 测试 458 项通过。
- 生效验证（08-18 19:48 后）：script_rewrite 缺 illustrated_article 时 handoff=needs_material、run 不可用，行为符合契约。

## 3. 待处理问题（按优先级）

1. **双状态轨道**：media 主线脚本直接写 canonical 阶段目录（磁盘真相），Run Control（SQLite nodeState）不感知。0817 run 的 draft 四个生产节点在磁盘有真实产物但 Run 内零登记，导致下游只能人工 attach 回填。需要让 mainline executor 结束时把阶段产物回写为 nodeState artifacts（或提供「磁盘产物对账」Action）。
2. **素材存在性校验缺失**：`material.attach` 可提交自声明 type + 任意 path 的素材，`validate_materials` 不检查文件存在。修复时注意现有 7 个测试用例使用 /tmp 假路径，需一并治理。
3. **review-gate packet 语义**：review 节点自产的 packet JSON（如 transwrite_handoff.json）可被当作内容产物 handoff，类型名与真实交付物同名易混淆。需在 packet 上增加标记并在 handoff 校验中区分。
4. **异常场景零覆盖**：12+ 个 Job 全部 succeeded，失败/重试/取消/服务重启恢复尚未被真实执行过（注意：08-18 19:45 曾 kill 8911 进程由 supervisor 拉起，当时无 running Job，恢复语义未被检验）。

## 4. 续跑指引（从当前状态接续）

1. transwrite.script_rewrite 已产 `prepared_for_skill_execution`：对 t01/wechat_article 执行 AI 会话（capability-session / invoke-cli）生成公众号改写稿与 HTML。
2. 生成 final_delivery_manifest 后 handoff → transwrite_review（approve 时素材门禁已生效）。
3. 进入 publish 阶段走千帆草稿通道完成 P0-2 发布沙盒验收。

操作命令模板（Desk API）：

```bash
curl -X POST http://127.0.0.1:8911/api/creator-studio/runs/creator-80e7e48ca127/commands \
  -H "X-User-Id: local-user" -H "X-Workspace-Id: local-workspace" -H "Content-Type: application/json" \
  -d '{"actionId":"creator.node.run","stageId":"<stage>","nodeId":"<node>","expectedRevision":<rev>}'
```
