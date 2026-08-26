# Sync Run 深层模块实施计划

> 约束：严禁修改候选 1 / `app/routers/ai.py`；不改变具体 chatlog、wx-cli、WeChatAPI adapter 的抓取实现。保留未提交修改，不暂存、不提交。

## 目标

深化现有 `app/services/sync_runtime.py`：让手动 chatlog 同步、微信三轨同步和后台 chatlog job 共享同一运行接口、重试、运行记录、后处理和错误语义。router/后台入口只负责参数转换与依赖装配。

## Task 1：定义 Sync Run 契约

**Files**

- Create: `tests/test_sync_run_orchestration.py`

**步骤**

1. 写 chatlog run 成功测试：`sync -> fallback/overlay/snapshot -> persist -> commit` 顺序稳定，结果含 run_id/attempts。
2. 写可重试错误测试：rollback 后重试，最终成功只持久化成功 run。
3. 写终止错误测试：稳定 error_code、attempts、fetched/inserted=0，并持久化失败 run。
4. 写后处理局部失败测试：主同步仍成功，错误进入结果而不丢 run 记录。
5. 写 dual-track 测试：按 enabled/order 执行；单轨只执行第一项，多轨按顺序执行；每轨失败不阻断后续轨。
6. 写后台入口测试：`_run_chatlog_sync_job` 调用同一 Sync Run interface，而非直接调用 `sync_from_chatlog`。
7. 运行新测试确认 RED。

## Task 2：深化 sync_runtime

**Files**

- Modify: `app/services/sync_runtime.py`
- Test: `tests/test_sync_run_orchestration.py`

**步骤**

1. 定义 `ChatlogSyncRunAdapters` 和 `DualTrackSyncAdapters`，默认函数在调用时解析。
2. 实现 `execute_chatlog_sync_run`：策略、重试、rollback、后处理、run 记录、最终 commit 和稳定返回集中。
3. 将 fallback summary、tool overlay（异步/内联模式）和 snapshot refresh 放入默认后处理实现；单个后处理失败不抹掉主同步结果。
4. 实现 dual-track policy 规范化/持久化公共函数。
5. 实现 `execute_dual_track_sync_run`，集中探活结果、轨道选择、执行、commit/rollback、run 记录。
6. 保留现有 `classify_sync_error`、policy/state helper 兼容接口。

## Task 3：迁移 HTTP router

**Files**

- Modify: `app/routers/sync.py`
- Test: `tests/test_sync_stability.py`
- Test: `tests/test_sync_run_orchestration.py`

**步骤**

1. `/chatlog` 只解析 since 并调用 `execute_chatlog_sync_run`。
2. 保留 `_load_chatlog_sync_policy`、dual-track 私有函数为兼容 wrapper。
3. `/wechat/dual-track` 只装配当前 router globals 为 adapters 并调用 runtime。
4. `/state`、`/policy` 和现有响应字段保持不变。
5. 既有 monkeypatch 继续通过 router globals 生效。

## Task 4：迁移后台入口

**Files**

- Modify: `app/background.py`
- Test: `tests/test_sync_run_orchestration.py`
- Test: `tests/test_background_summary_overlay.py`

**步骤**

1. `_run_chatlog_sync_job` 改为调用同一 chatlog Sync Run，overlay 使用 inline 模式。
2. 删除该入口独立的 sync/overlay/commit 编排，避免入口语义漂移。
3. 保持后台 loop 的异常捕获和运行状态行为；生命周期统一留给候选 6。

## Task 5：验收

1. 运行新测试、`tests/test_sync_stability.py`、后台相关测试。
2. 运行全量 `pytest -q` 与 `bash scripts/release_check.sh`。
3. 确认 router/background 不再直接编排 chatlog run。
4. 确认 `app/routers/ai.py`、Hermes 和前端禁区哈希不变。
5. 无暂存、无提交。

## 非目标

- 不修改底层抓取 adapter。
- 不修改 AI 报告运行模块。
- 不拆前端。
- 不实现后台 task handle/cancel；留给候选 6。
