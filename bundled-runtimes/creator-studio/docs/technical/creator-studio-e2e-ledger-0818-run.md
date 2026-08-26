# Creator Studio P0 全流程实测台账（0818 run）

记录对象：Run `creator-d0237de8590c`（标题「P0 全流程实测 0818」，选题 T01「黄金白银剧烈波动：贵金属行情的驱动逻辑与仓位启示」，Lane `wechat_article`）。

实测方式：六阶段（intake → brief → draft → transwrite → publish → postmortem）逐节点经 Desk API（8911）真实执行，边跑边修。AI 会话型节点（capability-session / editor-session）以「人工回写真实文件 + register/save」模式推进；发布执行经用户确认后**真实调用微信 API 推草稿成功**（direct_script 路径，见 §6.4）。

最终状态（经 0819 五批修复后）：run `status=succeeded`、`progress=100%`（rev 181）——29 节点全终态（含 4 个 video lane 节点 skipped），发布经真实微信 API 推草稿成功。

## 1. 节点推进记录

| 阶段 | 节点 | 状态 | 备注 |
|---|---|---|---|
| intake | source_setup / collect / normalize / intake_review | 全部 succeeded | normalize 残留 waiting_user（capability-session 语义） |
| brief | event_cluster / topic_pool / research_brief / brief_review | 全部 succeeded | topic_pool / research_brief 残留 waiting_user（同上） |
| draft | evidence_base / outline / article_draft / visual_package / draft_review | 全部 succeeded | outline / article_draft / visual_package 残留 waiting_user |
| transwrite | route_select / script_rewrite / transwrite_review | 全部 succeeded | video lane 三节点（director_storyboard 等）不适用文章 lane |
| publish | channel_package / account_route / publish_preflight / publish_execute / receipt_verify | 全部 succeeded | account_route 走完整 editor-session（launch 千帆控制台→save→close）；execute 二次确认门禁验证通过；回执为人工补录 |
| postmortem | metrics_collect / performance_analysis / knowledge_writeback / next_cycle | 全部 succeeded | metrics/analysis 走 editor-session；writeback 走 review-gate approve；next_cycle 为 package kind 直接 succeeded |

## 2. 已修复缺陷（本次实测修复）

### 2.1 代码修复（媒体仓库）

| # | 文件 | 问题 | 修复 |
|---|---|---|---|
| C1 | `scripts/run_mainline_stage.py` | brief 阶段产物脱节：event_clusters 未复制到 brief 阶段目录 | phase2_rebuilder 执行后补复制 event_clusters.json + `import shutil` |
| C2 | `scripts/build_stage3_draft.py` | `card['structure_hint']` 等硬访问崩溃（卡片缺字段时 KeyError） | render_reasoning_sheet_md / render_template_draft 改 `.get()` 链带中文默认值 |
| C3 | `scripts/skill_invoker.py` | skill 搜索路径与路由判定侧（prepare_publish_execution.SKILL_ROOTS）失配：判定侧含 `~/.codex/skills`、`~/.agents/skills`，执行侧不含 → "Skill not found in any search path" | SKILL_SEARCH_PATHS 补齐两路径 |
| C4 | `scripts/execute_publish_request.py` | **发布失败被记成功**：skill 路径不检查 `result.success`，失败也返回 `executed_and_recorded` → 节点 succeeded、回执 recorded、verify 全绿 | 失败时返回 `status: skill_execution_failed`（上游 execute_confirmed_publish 按 executed_and_recorded 判定成功，自动落入 failed → blocked） |
| C5 | `scripts/skill_invoker.py` | Anthropic API 异常（无 key 等）裸崩，CLI/上层拿不到结构化错误 | invoke 内层 try/except 返回 `success: False` 结构化结果 |

### 2.2 配置修复（registry）

| # | 文件 | 问题 | 修复 |
|---|---|---|---|
| R1 | `configs/workflow/newma_creator_studio_registry.json` | adapter `newma.mainline.brief` artifacts spec 指向旧 phase2 文件名，与现行管线脱节 | 改为 `event_clusters: event_clusters.json` 等 |
| R2 | 同上 | publish/channel_package 缺 `publish_decision` requirement 声明（media 侧需要该输入） | 补声明（required: false, sources: upstream/manual） |

### 2.3 数据契约补齐（Gate 状态机，属「人工回写」而非代码修复）

- **Brief Gate**：selected_topics.json 补 `status: approved` + selected_topics 非空。
- **Final Structure Gate**：final_structure_snapshot.json 手动置 approved + final_primary_sections（draft_review approve 不写盘 gate 文件，双状态轨道，见 §4-1）。
- **Channel Gate**：publish_decision.json 补 `topics` 字段（与 tasks 同值）。
- **Lane 状态机**：transwrite_manifest 的 T01/wechat_article lane 手动翻转 `ready_for_agent_execution → completed`（AI 终稿回写后无工具翻转，见 §4-2）。

## 3. 发现未修复问题（open，按优先级；F7/F8 已于 0819 修复，见 §6）

1. ~~**F7 succeeded 节点不可重跑**~~ → 已修复（creator.node.rerun，见 §6）。
2. ~~**F8 AI 终稿回写后 lane status 无工具翻转**~~ → 已修复（scripts/record_final_delivery.py，见 §6）。
3. ~~**F9 发布执行环境凭证缺失**~~ → 已修复（2026-08-19 第五批：真实发布闭环打通，见 §6.4）。
4. ~~**F-dual 双状态轨道**~~ → 核心断点已修复（review-gate approve 联动写盘 gate 文件 + 确认 executor 产物已自动登记，见 §6.3）。
5. ~~**F-packet review-gate packet 语义**~~ → 已修复（2026-08-19 第六批：origin=packet 标记 + handoff/discover 双侧排除，见 §6.5）。
6. ~~**F-env dev:stack 意外崩溃 + 重启 revision 异常增量**~~ → 已修复（2026-08-19 第六批：重启不再自动重跑未完成 job + 探针超时放宽，见 §6.5）。
7. ~~**F-progress 会话型节点 waiting_user 残留**~~ → 已修复（creator.node.complete + 自动完成 + creator.node.skip，见 §6.2）。
8. ~~**F-activeNode activeNode 指针陈旧**~~ → 已修复（命令后自动刷新，见 §6.2）。

## 4. 验证通过的关键契约（本轮新增证据）

- 跨阶段 handoff：`targetStageId + targetNodeId + artifactIds`；superseded artifact 不可 handoff（取 created/approved）。
- editor-session 完整生命周期：run → waiting_user → `creator.editor.launch`（publish_console 真实启动千帆控制台 backend:5409 / frontend:5173；artifact_preview 素材即 open）→ `creator.editor.save`（outputs 回写 + 节点 succeeded）→ `creator.editor.close`。
- 发布二次确认：未 confirm 时 `creator.node.run` 422；`creator.publish.confirm`（confirmed + confirmationText=确认发布）→ run 时 desk 注入 `consumedByJobId=job_id` → media 校验闭环。
- 发布预检发现链：account_routes.json 内嵌 execution_request 路径字符串 → `discover_named_material_files` 的 JSON walk 递归发现 → build_plan 路由选择 → 账号健康检查（available/configured_unverified 均放行）。
- 失败显性化（C4 修复后磁盘直跑验证）：skill 找到 → API 凭证缺失 → `status: skill_execution_failed` + 结构化 error（修复前为 not found + executed_and_recorded 假成功）。
- review-gate approve：产物翻 approved；素材门禁（0817 修复）生效。
- package kind：write_node_packets 按 node.outputs 直接产 packet 并 succeeded。

## 6. 目录结构重构（2026-08-19 追加）

实测后按用户决策将桌面交付目录从「按环节分顶层目录」重构为「按任务建文件夹」：

- 新结构：`<desktop>/<run_id>/{01_采集, 02_选题, 03_初稿, 04_转写, 05_发布, 06_复盘, nodes/<stage>/<node>/}`；全局目录（00_范式学习/00_热点捕捉/00_改写）保留在根。
- 核心改造：`path_config.py` 新增 `STAGE_DIR_NAMES/get_run_root/get_stage_dir`（六阶段 key 从 `get_output_root` 移除并 fail-fast）；`canonical_workflow.canonical_stage_dir` 改为 `get_stage_dir(stage, run_id)`，约 30 处主线调用自动跟随；`newma_creator_control.node_execution_dir` 的 `creator_nodes/` 改名 `nodes/`。
- 废除 desktop_delivery 平铺导出（原 4 个调用方 + workflow_doctor 诊断段），删除复制件与 `desktop_delivery.py`。
- 批量替换硬编码路径：scripts 8 处 + SKILL.md/docs 80+ 处（含 `<run_id>`/`{run_id}` 占位符形态）；`feishu-plan.js` 增加 `stageDir` 新结构优先发现。
- 存量迁移：`scripts/migrate_desktop_layout.py`（dry-run→apply），全部 run 搬迁，删除空野目录 `07_发布与增长`（AI 误建）与全部平铺复制件。
- **内嵌路径迁移**（`--fix-paths` 阶段）：manifest/报告/HTML 内的绝对路径同步改写（161 文件/797 处，含无尾斜杠形态），transwrite_manifest→final_markdown 等引用链抽验全部存在。
- 验证：全量 pytest 488 passed；六阶段 canonical 解析与磁盘全对上；workflow_doctor 在新结构下正确诊断；batch-ingest 冒烟（run 根 + _tmp 路径正确）。
- 顺手修复：品牌更名测试断言过期 2 处（DashengPublishProfiles/PublishSessions→Newma，含 draft_html_pack 内联注释断言）；newma_creator_control batch-ingest 临时文件双重「自媒体创作」路径 bug。
- 已知影响：desk SQLite 中旧 run 的 artifact 绝对路径失效（历史 run 重放需重新 register，或如 F7 验证所示经 rerun 重建）；测试隔离缺陷依旧（test_mainline_hardening 直接写真实桌面，已手动清理其产物）。

### 6.5 P1 修复（2026-08-19 第六批：F-packet 语义区分 + F-env 恢复/崩溃治理）

- **F-packet（origin 标记全链路 + 双侧排除）**：
  - 受害面：7 个节点（2 package + 5 review_gate）的 write_node_packets 自产 packet 与真实交付物同名同类型；rerun 后 packet 可成为唯一 USABLE 产物，经 `creator.handoff.create` 转交下游。
  - media：`execution_artifact` 加 `origin` 参数（默认 deliverable）；write_node_packets 产物标 `origin=packet` 且文件内容加 `packet: true`；`discover_named_material_files` 按名查找时跳过 packet 文档（`is_packet_document`）。
  - desk：`lineage.register_artifact` 透传 `origin` 字段（历史记录无该字段按 deliverable，行为不变）；`_execution_finished` 登记时透传；**handoff 筛选排除 origin=packet**。
  - 真实验证（0818 run knowledge_writeback）：rerun→run→新 packet 3 个全带 origin=packet → register 真实产物 3 个（deliverable，packet 自动 superseded）→ approve → run 自动收尾 succeeded/100%（rev 189）。
- **F-env（根因定位 + 两项修复）**：
  - 根因 1（revision +14）：`CreatorExecutionRuntime.startup` 恢复时 running job 置 interrupted（+1/次），**queued job 直接重新 dispatch 真跑**（started+finished +2/次）——非幂等且 queued 的 publish_execute job 会自动重新真实发布（consumedByJobId 匹配原 job_id）。
  - 修复 1：startup 对所有未完成执行（含 queued）一律显式中断（「排队中的执行已取消，请重新发起」/「原执行已中断，请重试」），重试需重新走 confirm 门禁；恢复写入每 job 只收尾一次。
  - 根因 2（supervisor 消失）：domain-suites 探针 1.5s 超时，API 繁忙时误判 UNAVAILABLE，3 次（15s）即 restart，重启后仍不就绪则 `onCoreFailure → shutdown(1)` 整个 stack。
  - 修复 2：domain-suites 探针超时 1.5s → 5s（dev-stack.mjs）。
  - 验证：desk 测试 +1（`test_startup_interrupts_queued_and_running_jobs_without_redispatch`，20 passed）；真实重启 dev:stack 服务就绪、0818 run 状态无损（rev 189 零增量）。

### 6.4 P1 修复（2026-08-19 第五批：F9 真实发布闭环 + execution 收尾缺口）

- **F9 修复（真实发布打通）**：
  - 凭证：`WECHAT_APP_ID`/`WECHAT_APP_SECRET`（公众号「默丘利Lab」）写入 `.env`；IP 白名单由用户在 mp.weixin.qq.com 添加（出口 IP 111.193.80.93）。
  - **架构改进（execute_publish_request.py）**：新增 `direct_script` 确定性路径——`baoyu-post-to-wechat` 路由直跑 `wechat-api.ts`（bun，仅 `WECHAT_APP_ID/SECRET`，无 LLM 中转），定位不到脚本或非 wechat-article 通道时回退 SkillInvoker 旧路径。推草稿不再依赖 `ANTHROPIC_API_KEY`。
  - 封面：纯文字文章无图——按 run 内 `cover_prompt.md` 生成封面（1536x1024→裁剪 900x383）落 `04_转写/t01/wechat_article/cover/cover.png`，回填 `channel_pack.publish_metadata.cover`。
- **desk DB document_json 路径迁移**（目录重构遗留）：nodeStates 的 materials/artifacts 路径仍指旧结构（`01_内容采集`/`creator_nodes` 等）导致 executor 素材定位失败。已备份（`runtime/newma-desk.db.bak-0819`）后按新结构（`<run_id>/<01_采集..06_复盘>` + `nodes/`）全量改写并重启。
- **execution 收尾缺口（新发现）**：`_refresh_active_pointer` 原仅在命令入口触发，executor 异步完成（`execution.finished`）不刷新 run 状态——节点全终态后 run 停 pending/100%。修复：`_execution_finished` mutate 尾部同样调用指针刷新。desk 测试 +1（`test_execution_finished_marks_run_succeeded`，18 passed）。
- **真实验证（0818 run，全链路）**：confirm（二次确认）→ retry → media `execute_confirmed_publish`（materials 新路径定位 preflight 报告）→ `execute_publish_request` direct_script → **真实推草稿成功（media_id 已返回，record=recorded）** → publish_jobs/platform_receipts 落盘 `nodes/publish/publish_execute/` → run **succeeded/100%（rev 181）**。
- 附注：草稿箱现有 2 份相同草稿（手动链路验证 + desk 闭环各推 1 份），可在公众号后台删 1 份。

### 6.3 P1 修复（2026-08-19 第四批：F-dual 核心断点）

- **查证**：desk `_execution_finished` 已自动登记 executor 返回的 artifacts（producerJobId 去重）——「executor 产物回写 nodeState」轨道本已打通；F-dual 剩余断点为 **review-gate approve 不写盘 gate 文件**。
- **media 侧 `newma_creator_control.py approve-gate` 命令**：按 GATE_FILENAMES 映射（intake_review/selected_topics/final_structure_snapshot/transwrite_decision/publish_decision）定位 canonical gate 文件，status→approved + approved_at；missing/幂等分支齐全；支持 --gate-file 显式路径。
- **desk 联动**：`adapter.approve_gate`（allow_failure，missing 不阻断）+ approve 分支对 review-gate executor 调用写盘并记 log（异常捕获，写盘尽力而为不阻断审批）。
- **真实验证（0818 run）**：brief_review rerun→run→waiting_user→approve：desk log 出现「阶段门禁写盘：succeeded …/02_选题/selected_topics.json」，磁盘 selected_topics.json approved_at None→新时间戳；run 自动回 succeeded/100%（rev 171）。desk 测试 +1（17 passed）。
- 遗留小项：人工回写模式下 desk 状态与磁盘的对账（register 主动登记仍靠人工/AI），可后续提供「磁盘产物对账」Action 作为补无。

### 6.2 P1 修复（2026-08-19 第三批：F-progress / F-activeNode）

- **`creator.node.complete`**：waiting_user 且无 gate 的会话型节点可显式收尾（人工确认会话完成，产物可不齐）。
- **register 自动完成**：会话型 executor（editor-session/capability-session）登记产物覆盖全部 node.outputs 声明时自动 succeeded（严格契约标准）。
- **`creator.node.skip`**：未终态节点可跳过（不适用 lane，如文章 run 的 video lane 四节点），不受素材门禁限制；skipped 按 progress=100 计。
- **activeNode 刷新 + run 完成判断**：每次命令后把 activeStageId/activeNodeId 指到顺序上第一个未完成节点；全部节点终态时 run status 自动置 succeeded（原仅 workflow.continue 到末点才置）。
- **真实验证（0818 run）**：6 个残留 waiting_user 会话节点 complete 收尾 + 4 个 video lane 节点 skip → **run status=succeeded、progress=100%**（原 86%/pending 封顶）；activeNode 从 intake/source_setup 刷新至实际推进位置。
- 附带发现：uvicorn（dev:stack）无 --reload，改 service.py 后必须重启才生效（本轮重启 3 次）；submit-feedback 会置 changes_requested（非无副作用，收尾勿误用）。desk 测试 16 passed。

### 6.1 P1 修复（2026-08-19 第二批）

- **F7 修复：`creator.node.rerun`**（desk service.py）：succeeded 节点提供 rerun，重置为 pending、旧交付物转 superseded、清除 publishConfirmation（需重新走确认门禁）；复用素材门禁。真实验证：0818 run channel_package rerun→run→succeeded，新 artifact 落新结构（`05_发布/`），旧 artifact superseded 指旧路径，execution_request 重建为 ready_for_user_confirmation。desk 测试 +1（16 passed）。
- **F8 修复：`scripts/record_final_delivery.py`**（media 侧）：校验终稿（final_markdown/final_html）存在后翻转 lane status→completed + completed_at；幂等（already_ready）；缺终稿 blocked（exit 2）。三分支单测通过；0818/53fec run 幂等验证通过。

## 5. 磁盘产物索引（桌面目录）

- `creator-d0237de8590c/01_采集/`：intake_manifest、raw/intake_records
- `creator-d0237de8590c/02_选题/`：event_clusters、topic_cards、selected_topics、brief_manifest
- `creator-d0237de8590c/03_初稿/`：draft_manifest、article_outline、标准初稿 md/html、ReasoningSheet、DraftAssets
- `creator-d0237de8590c/04_转写/`：transwrite_decision、lane_jobs、transwrite_manifest（lane=completed）、final_delivery_manifest、t01/wechat_article/wechat_article.final.md/html
- `creator-d0237de8590c/05_发布/`：publish_decision、account_routes、publish_manifest、channel_execution_manifest、publish_verification_report、channel_packs/t01/wechat-article/（execution_request、channel_pack、publish_result[failed·真实]、account_operations_request）
- `creator-d0237de8590c/06_复盘/`：performance_dataset、platform_snapshot、postmortem_report、experiment_findings、dna_updates、director_updates、publish_policy_updates
- `creator-d0237de8590c/nodes/`：各节点 execution_request / packet / editor_session / publish_preflight_report / publish_jobs / platform_receipts（manual/）/ postmortem_handoff 等

## 6.6 UI 产品化改造：节点工作卡 + 任务总览（2026-08-20）

用户定调「每个节点不要复杂文档，就产品+说明」。落地形态：人工介入点统一为一张**节点工作卡**（产品区 + 一句话说明 + 直达操作按钮）。

### 改动清单

- **ReviewWorkCard**（desk creator-studio views.tsx）：节点 waiting_user 时渲染。产品区：brief_review 特化渲染上游 topic_pool 的 topic_cards（跨节点取材，preview API 拉 JSON 解析为三选题卡，点选高亮）；其他 review 节点显示可预览的交付物 chips。操作：批准（选中时带 selectedTopicIds）/确认完成/退回修改，无需切 Tab。
- **Dashboard 任务总览**（TASK BOARD）：全部 run 卡片网格（标题+状态+当前阶段），点击切换任务——多任务并行一目了然。
- **selectedTopicIds 透传**（三层）：desk service approve 分支提取 input.selectedTopicIds → adapter approve_gate(selected_ids) → media approve-gate --selected-ids。
- **approve-gate 新语义**：gate 文件缺失 + 带选题选择（brief/selected_topics.json）→ 直接创建 approved gate 文件（status=created，从 topic_cards.json 拉所选卡），UI 直批路径无需 AI 预生成骨架；无选择仍 missing。

### 修复过程中发现的前端缺陷（已修）

1. **actions 双字段陷阱**：snapshot 节点有 actions（展示用短名 approve/request_changes）与 availableActions（全限定名 creator.node.approve）两个字段；按钮可用性判断必须用 availableActions（原 ReviewWorkCard 用 actions.includes 全限定名恒 false，按钮不渲染）。
2. **内联箭头函数 prop 导致选中态丢失**：App 每次渲染创建新 fetchPreview 引用 → ReviewWorkCard effect（依赖 fetchPreview）每次渲染重跑 → setSelected([]) 重置用户选中。修复：useCallback 稳定引用（fetchArtifactPreview）。
3. **vite content hash 验证法**：dist/assets/index-*.js 的 hash 是判断改动是否真正进入构建的可靠手段（本轮一次 heredoc 写入被终端损坏吞掉，文件未变但脚本打印成功——hash 未变暴露了问题）。

### 真实闭环验证（creator-1426aaa8782e）

UI 点选 T02 → 「批准所选（T02）」→ brief_review succeeded（rev 44）→ selected_topics.json created（approved + selected_topic_ids=[T02] + 完整选题卡）。审批全链路不再需要 API 直发。

测试：媒体仓库 509 passed / desk creator_studio 20 passed / 前端 8 passed。

### 6.6.1 浏览交付物跳顶修复（2026-08-20 第二批）

用户反馈「浏览交付物时自动回到顶端」。根因是**两处不稳定函数引用导致内容闪烁重挂**：

1. **预览 modal 的 fetchPreview 内联箭头函数**（App.tsx）：refreshRuns 每 6 秒 setRuns（即使数据不变也 set 新数组）→ App 重渲染 → modal 收到新 fetchPreview 引用 → effect 重跑 → 内容闪回「加载中」→ modal/主容器高度骤变 → scrollTop 钳回 0。修复：改用已存在的 useCallback 稳定引用 fetchArtifactPreview。
2. **ReviewWorkCard effect 依赖 snapshot.run.revision**：任何命令 revision +1 → 卡片清空重拉 → 页面高度骤变同样触发滚动钳制。修复：依赖移除 revision（topic_cards 内容在 brief 阶段不变，无需跟随 revision 刷新）。

实测验证（creator-80e7e48ca127，waiting_user 工作卡场景）：打开 execution_request 预览 → modal 内无 loading 闪烁 → 8 秒（跨 refreshRuns 6s + events 5s 两个轮询周期）主容器 scrollTop 300 保持 → 关闭 modal 后仍 300。前端测试 8 passed。

判别要点：React 中「滚动位置丢失」几乎总是「滚动容器内容高度骤减被浏览器钳制」，而高度骤减的常见根因是 effect 依赖不稳定引发的条件渲染闪烁（loading 态/空数组态）。

### 6.6.2 「完成并继续」进度倒退修复 + approve 自动转接（2026-08-20 第三批）

用户实测反馈：点「完成并继续」进度倒退（brief 75%→「待开始」、run 28%→24%）；draft 阶段运行节点置灰（缺「初稿交接包」）。

**根因一（进度倒退）**：creator.workflow.continue 旧语义是「串行重跑」——强置当前节点 succeeded、**把已完成的下一节点重置回 pending+progress 0**。用户在 succeeded 节点上点它，下游已完成节点被回滚。修复：continue 收敛为**纯指针推进**（active 指到下一节点；校验当前节点须终态，未完成拒绝；run 完成状态交给 _refresh_active_pointer）；前端按钮文案改「下一节点」。删除一切节点状态改写。

**根因二（运行置灰/UI-Agent 双路径差异）**：UI 直批 approve 只写 gate 文件，**无人做 handoff**（Agent 路径由会话补）→ 下一节点素材门禁不过、运行按钮灰。修复：approve 分支尾部**自动转接**——本节点 USABLE 交付物自动 handoff 给 next_node（_create_handoff 幂等复用）。「批准后流程自动进入下一节点」从此在两条路径上等价。

**数据修复教训（stale 级联）**：恢复被倒退的 topic_pool 时误用 node.run——上游重跑触发下游节点与产物全量 stale 级联（research_brief/brief_review 连带失效、materials 绑定清空）。正确恢复姿势：handoff 重新绑素材 → run → register 现有磁盘文件 → auto-complete；review-gate 节点 run 后 waiting_user，approve 幂等（gate 已 approved）并触发新自动转接。

验证：evidence_base 自动收到 draft_handoff、运行按钮点亮、进度回 28%、active=draft/evidence_base。desk 21 passed（新增 test_continue_is_pointer_only_and_never_regresses：不倒退 + 未完成拒推 + approve 自动转接断言）；媒体仓库 509 passed。

注意：handoff.create 等命令的业务参数必须放 body.input（顶层字段会被 schema 拒绝 422 extra_forbidden）。

### 6.6.3 自动转接补全三条完成路径 + draft 环节真实执行（2026-08-20 第四批）

**自动转接补全**：上午只给 review-gate approve 加了自动转接，本轮补齐另外两条「节点完成」路径——执行型 succeeded（_execution_finished 尾部）与会话型 auto-complete（register 覆盖 outputs 时）。三条路径同语义：产物自动 handoff 给 next_node。修复过程中被 stale 测试抓到一次语义冲突（旧 handoff 因重复转接转 superseded 而非 stale），断言放宽为两种失效态均可。已知局限：跨节点素材链（如 evidence_base 的 evidence_ledger 需直转 article_draft，跳过中间 outline）仍需手动 handoff 补充。

**media 侧两处兼容修复**（build_stage3_draft.py）：load_topic_cards 兼容 {topic_cards:[...]} 包装结构；structure_hint 兼容 {opening, body, ending} 新版结构。修后执行器全链路跑通。

**draft 环节真实执行**（creator-1426aaa8782e，28%→45%）：
- evidence_base：Tushare 实测（518880 当日 -1.15%、90日回撤 -11.12%、YTD -17.92%、波动率 15.8→18.9%、5 资产齐跌切片、60日相关性矩阵）+ 2 张 matplotlib 图 + 证据账本/引用索引。波动率计算曾重复乘 100（1887%→18.9%），已修。
- outline：会话写 article_outline + claim_order（7 论断带证据引用）。
- article_draft：executor（qoder-cli LLM）生成 4590 字骨架 → 会话写数据注入版 4736 字（待补数据点全部替换为 Tushare 实测，含 HTML 版）。
- visual_package：ImageGen 双封面候选（齐跌K线碎裂/倾斜黄金船）+ asset_manifest。
- draft_review：waiting_user（审核卡已 register，UI 工作卡可预览初稿与审核指引）。

测试：desk 21 passed / 媒体仓库 509 passed。
