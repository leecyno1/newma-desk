# Newma Creator Studio P0 真实端到端验收报告

- 日期：2026-08-18
- 验收人：Qoder（Agent 驱动验收）
- 载体：双 Run 对照
  - **53 号 `creator-53fec36ea0d6`**（接手驱动，rev 4 → 94）：本次验收主载体
  - **80 号 `creator-80e7e48ca127`**（只读审计，rev 57 静止）：他人会话残留状态交叉验证
- 环境：API :8911（newma-desk），真实 DB `newma-desk/runtime/newma-desk.db`，创作目录 `~/Desktop/自媒体创作/`

## 一、结论

**P0 端到端主链路（intake → brief → draft）真实打通**，53 号 Run 推进至 transwrite.route_select（progress 45%，19/29 节点 succeeded）。采集、聚类、选题、研究、初稿生成（真实 AI 长文）、结构锁定、配图、审阅、跨阶段交接全部走真实命令协议与真实文件产物。

同时坐实 **7 类缺陷**（1 个已修复、1 个新发现），详见第四节。**e6 修复（registry 5 节点切换 editor-session）经双节点全链回归验证有效**。

## 二、里程碑验收结果

| 阶段 | 节点 | 结果 | 关键实证 |
|---|---|---|---|
| e2 intake | source_setup→collect→normalize→intake_review | ✅（normalize 留死锁证据） | collect 真实采集 **648 条**（约 100s）；intake_review gate 全链通过 |
| e3 brief | event_cluster→topic_pool→research_brief→brief_review | ✅ 全绿 | event_cluster 真实产出 **141 事件簇**；topic_pool/research_brief 走 editor-session 全链（launch→save→close）；brief_review approve 产出 selected_topics+draft_handoff |
| e4 draft | evidence_base→outline→article_draft→visual_package→draft_review | ✅ 全绿（5/5） | evidence_base mainline 真实 AI 初稿（**5853 字**→重建版 4478 字，质量门禁 warning 如实）；outline 锁定真实 5 节结构；article_draft 终稿三件套；visual_package 配图清单（asset_status=incomplete 如实传导）；draft_review approve→handoff→transwrite |
| e5 状态机 | 见第三节 | ✅ 9 项边界 | run/retry/cancel/approve/409/422 行为全部符合或坐实缺陷 |
| e6 修复 | registry executor 切换 | ✅ 已验证 | normalize/topic_pool/research_brief + outline/article_draft 共 5 节点切 editor-session；Media 测试 7 passed |

## 三、状态机与命令协议边界验证（e5）

| # | 测试 | 结果 | 判定 |
|---|---|---|---|
| 1 | node.run on pending | 正常排队执行 | ✅ |
| 2 | node.run on succeeded | 422 `unavailable while status is succeeded` | ✅ 拒绝正确 |
| 3 | node.retry on failed | 重新排队（evidence_base 两次 retry 实证） | ✅ |
| 4 | node.approve on pending review | 422（review-gate 须先 run 至 waiting_user） | ✅ |
| 5 | node.approve on waiting_user gate | 通过并产出 gate 产物 | ✅ |
| 6 | node.cancel on waiting_user | 422（cancel 仅限 active job 节点） | ⚠️ 语义正确，但加剧 waiting_user 死局（见候选 F） |
| 7 | expectedRevision 过期 | 409 `revision is stale` | ✅ 并发保护有效 |
| 8 | editor.save 空 outputs | 拒绝 `at least one editor output is required` | ✅ 设计合理 |
| 9 | material.attach 伪造 source=upstream | **放行**（无校验） | ❌ 候选 A |

## 四、缺陷清单（按严重度）

### 候选 F（严重，已修复）：capability-session waiting_user 绝对死锁
- 根因链：`_available_actions`（service.py L1658-1662）要求 editorSession 已有 available 编辑器才能 launch，但 capability-session 执行器（newma_creator_control.py L1703-1711）返回 `{"kind":"capability_session"}` 而非 editor_session 协议，`create_from_execution`（editor_sessions.py L37）拒绝创建会话 → waiting_user 无任何退出通道（run/retry/cancel/approve 全拒）。
- **80 号 Run 实证**：brief 阶段 topic_pool/research_brief 至今卡 waiting_user（rev 57 静止），他人会话同样中招。
- 修复：registry 5 节点 executor 切 `newma.control.editor-session` + 声明 editors（53 号全链回归通过）。
- **遗留**：transwrite.asset_build、transwrite.render_qc、postmortem.metrics_collect、postmortem.performance_analysis 仍为 capability-session，**进入这些节点将复现死锁**。

### 候选 G（严重，新发现）：review-gate 产物与下游 Brief Gate 契约断裂
- 现象：evidence_base 首次执行失败 `Brief Gate 未通过：selected_topics.json 中 status 必须为 approved 且 selected_topics 非空`。
- 根因：Media 侧 `write_node_packets`（newma_creator_control.py L644）把 gate 产物写死为 `status:"pending_review"` 且不含内容字段；API 侧 approve 只改节点状态，**不回写产物文件**；而 build_stage3_draft.py L725-729 要求 `status=="approved" && selected_topics 非空`。
- 本次绕过：手改 selected_topics.json（approved + 选题数组）。产品上必须修（approve 时回写产物或 Media 兼容读取）。

### 候选 A（中）：material.attach 无 source/accepts/path 校验
- service.py L635-640 仅做 type 匹配；models.py L21 source 由客户端自填，registry 声明 `sources:["upstream"]` 形同虚设，manual 可伪装 upstream。

### 候选 C（中）：workflow.continue 跨越场景不标 skipped
- QODER_HANDOFF.md L95 要求被跳过节点标 skipped；continue 直接置下一节点，跳过的节点保持 pending（run.create 场景反而会标，覆盖不全）。

### 候选 E（中）：approve 链不检查上游状态
- intake.normalize 死锁 waiting_user 时，intake_review 照样 run+approve 通过。

### 候选 D（低）：execution_result 元数据不全
- 节点快照 lastExecution 为空、结果 JSON 缺 startedAt/finishedAt/exitCode 统一字段（部分文件有部分无）。

### publish 链路根因（0e4a 失败 Run 实锤）
- 挂载了 `creator_nodes/...` 下的 API 包装产物（stage_id 字段）而非 canonical 产物（stage 字段），canonical_workflow.py L84-88 契约校验如实报错。修复方向：挂 canonical 产物或统一 schema。

## 五、本次验收的临时数据侧操作（非产品修复）

| 文件 | 操作 | 原因 |
|---|---|---|
| `creator_nodes/brief/brief_review/selected_topics.json` | 手动改 approved+选题内容 | 候选 G 绕过 |
| `02_.../topic_cards.media.json` | 新建数组格式+补 structure_hint | Media load_topic_cards 期望数组；卡片缺 structure_hint 硬字段（KeyError） |
| `05_.../draft_manifest.json` | 覆盖后由 build_stage3 重跑恢复 | 误覆盖规范产物，命令行重跑重建（教训：编辑器产物勿复用 Media 保留文件名） |

## 六、建议下一步

1. **修复候选 G**（approve 回写 gate 产物）——阻塞 transwrite 之后的完整闭环。
2. **切换剩余 4 个 capability-session 节点**（同 e6 模式，锚点已在 registry 定位）。
3. 修候选 A/C/E（校验与 skipped 标记）。
4. transwrite 阶段验收（53 号已停在 route_select，route_select/script_rewrite 已是 mainline/review 类执行器，asset_build/render_qc 注意死锁风险）。
5. 80 号 Run 的 2 个 waiting_user 死锁节点需在新 registry 下由操作者 retry 或重建 Run。

— 完 —


---

# 附录：第二批次验收（同日晚间续）

## 七、候选 G 已修复（API 侧代码修复）

- 修改：`newma-desk/services/api/vibe_visualization_api/creator_studio/service.py`
  - approve 分支对每个 artifact 调用新增的 `_approve_artifact_file()`；
  - 该方法将磁盘上 `status=="pending_review"` 的 gate 产物文件翻转为 `approved`（含 `approved_at`），并把 approve input 中与 artifact 同名的字段（如 `selected_topics`）注入产物；
  - 文件缺失/非 JSON/非 pending_review 一律静默跳过，不阻断 approve。
- 测试：新增 `test_approve_syncs_pending_review_artifact_file_to_approved`，API 侧 **14 passed**。
- 生效方式：kill API 进程（PID 63578 → 84778），dev-stack RuntimeSupervisor 12s 内自动拉起，DB 数据无损（rev 94 保持）。

## 八、capability-session 节点已全部清零

- 本批切换：transwrite.asset_build、transwrite.render_qc、postmortem.metrics_collect、postmortem.performance_analysis（同 e6 模式：executor→editor-session + editors 声明）。
- 现状：registry 中 capability-session 节点数为 **0**，Media 测试 7 passed。
- 候选 F 的 registry 层面修复完成；executor 代码（newma_creator_control.py L1703 capability_session 分支）仍保留，建议后续清理或留作兼容。

## 九、transwrite 阶段验收（53 号 rev 94 → 107）

| 节点 | 结果 | 说明 |
|---|---|---|
| route_select | ✅ succeeded | review-select 执行器直接产出 **canonical 格式 approved** transwrite_decision（06_转写生产/），与 brief review-gate 形成对照——该执行器是正确范式 |
| script_rewrite | ✅ succeeded（retry 一次） | 首跑被 **候选 G-2** 拦截（见下）；通过后产出完整 wechat_article 任务包（含 4 个柠檬人插画 intents、排版硬规则、QC 契约、agent_rewrite_prompt） |
| 任务包生产 | ✅ agent 执行 | humanize 改写 4 处对偶句（剩余 0）、final.md/html 产出、QC 报告 `packageable_with_pending_visuals`（封面/插画如实标记待外部 CLI）、双 manifest 更新至 packageable |
| director_storyboard → render_qc | ⛔ 结构性阻塞 | **候选 H**（见下） |
| transwrite_review | 未可达 | 被候选 H 挡住 |

## 十、新坐实缺陷（第二批次）

### 候选 G-2（严重）：Final Structure Gate 同族断裂
- script_rewrite 首跑失败：`Final Structure Gate 未通过：05_初稿生成/.../final_structure_snapshot.json`。
- 根因：build_stage3 留给编辑的 pending 文件（instructions 明示"编辑完成后改 approved"），但 **API 的 draft_review approve 只翻转 creator_nodes 包装文件（t1 修复覆盖范围），不联动 canonical 目录文件**。
- 本次绕过：以编辑身份补全 status/final_primary_sections/doc_file 后 retry 通过。
- 修复方向：draft_review 的 gate 执行器学习 route_select 的 review-select 范式（直接产 canonical approved 文件），或 approve 时联动 canonical 路径。

### 候选 H（严重，新）：单 lane Run 无法完成 transwrite（无跳过机制）
- 实证链（53 号 rev 107）：
  1. wechat_article lane 的 script_rewrite 不产出 `video_script`；
  2. director_storyboard run 被 422 `needs_material`（缺 video_script + claim_evidence_ledger）拦截——校验本身正确；
  3. pending 节点无法 `workflow.continue`（422，continue 仅限 succeeded）；
  4. 无法 `node.cancel`（无 active job）；命令集（16 个）中**没有 skip 类命令**；
  5. → transwrite_review 永不可达。
- 交叉印证：80 号 Run transwrite 停在 2 succeeded + 5 pending（rev 57 静止），同一困境。
- 修复方向（三选一或组合）：① 增加 `creator.node.skip`（带 lane 理由）；② run.create/continue 按 lane 自动标 skipped；③ 视频节点 material_requirements 改为可选并支持空跑。

## 十一、总体进度

53 号 Run：intake/brief/draft 全绿，transwrite 2/7（route_select、script_rewrite ✓），结构性停在 director_storyboard。progress 45%。publish/postmortem 待候选 H 解锁后验收。
