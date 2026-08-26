# 微信自动回复事务模块实施计划

> 执行约束：候选 1（AI 报告运行模块）严禁修改；不修改 `app/services/hermes_bridge.py`、模型路由或 prompt 生成实现。保留工作区现有未提交修改，不暂存、不提交。

## 目标

把当前 router 中隐含的自动回复执行顺序收进一个可直接测试的事务模块，对外只暴露“执行某条入站消息的自动回复事务”，并返回稳定结果。HTTP callback 仍负责入队，生成与发送 provider 仍作为 adapter。

## 必须保持的顺序

1. 校验消息存在、方向为入站且类型为文本。
2. 前置触发规则与人工回复抑制等待；未通过时不得调用模型。
3. 调用 Hermes 回复 adapter。
4. 生成后再次检查人工接管；未通过时不得发送。
5. 检查出站规则。
6. 确认网关配置、应用随机延迟、发送文本。
7. 记录出站消息及完整执行元数据并提交。

## Task 1：用事务契约测试定义状态和顺序

**Files**

- Create: `tests/test_wechat_auto_reply_transaction.py`

**步骤**

1. 写测试：无效/非入站/非文本消息返回 `skipped`，不调用任何 adapter。
2. 写测试：前置规则阻断时调用顺序只有 `precheck`，生成与发送均不发生。
3. 写测试：成功路径严格按 `precheck -> generate -> recheck -> outbound_rule -> delay -> send -> record` 执行，并返回 `sent` 与 outbound id。
4. 写测试：生成期间人工接管后，停在 `recheck`，不调用 delay/send/record。
5. 写测试：生成失败、出站规则阻断、网关未配置和异常分别返回稳定状态/reason，并总是关闭 session。
6. 运行新测试，确认因事务模块不存在而 RED。

## Task 2：实现深层事务接口

**Files**

- Create: `app/services/wechat_auto_reply_transaction.py`
- Test: `tests/test_wechat_auto_reply_transaction.py`

**步骤**

1. 定义不可变 `AutoReplyTransactionResult`，至少包含 status、reason、message_id、outbound_message_id、execution。
2. 定义 `AutoReplyAdapters`，封装规则检查、生成、配置加载、出站检查、延迟、client 创建和记录 adapter；默认 adapter 延迟导入 Hermes，保持现有 monkeypatch 行为。
3. 实现 `execute_wechat_auto_reply_transaction`，集中上述顺序、日志和 session 生命周期。
4. 生成器只接收当前既有字段：正文、subsession id、会话/发送者名称与备注；不把 router 或数据库 implementation 泄漏给 provider。
5. 成功时保持现有 `meta.auto_reply` 结构和 execution 元数据；失败时不产生出站记录。
6. 运行新测试直至 GREEN。

## Task 3：将 router 缩为兼容入口

**Files**

- Modify: `app/routers/wechat_gateway.py`
- Test: `tests/test_wechat_gateway_auto_reply_flow.py`
- Test: `tests/test_wechat_gateway_hermes_bridge.py`

**步骤**

1. 保留 `_run_auto_reply_for_message` 函数名和 executor，改为调用事务模块。
2. wrapper 显式传入 router 当前的 `SessionLocal` 与 `WechatApiClient`，使既有测试 monkeypatch 和运行配置继续生效。
3. callback 的 queued 响应、入队条件和 HTTP 语义保持不变。
4. 运行现有自动回复流程测试，修复任何兼容回归。

## Task 4：回归与边界验收

**Files**

- Test: `tests/test_wechat_auto_reply_transaction.py`
- Test: `tests/test_wechat_gateway_auto_reply_flow.py`
- Test: `tests/test_wechat_gateway_trigger_rules.py`
- Test: `tests/test_wechat_gateway_hermes_bridge.py`
- Test: `tests/test_wechat_gateway_reply_local.py`

**步骤**

1. 运行上述目标测试。
2. 运行 `bash scripts/release_check.sh`。
3. 运行全量 `pytest -q`。
4. 检查 router 中不再承载事务实现，只保留入队与兼容 wrapper。
5. 检查 `app/services/hermes_bridge.py` 与 `app/routers/ai.py` 的执行前哈希不变。
6. 检查无暂存、无提交，并报告已有警告。

## 非目标

- 不改 Hermes/模型/prompt 选择。
- 不改变回复触发规则本身。
- 不替换 ThreadPoolExecutor；后台生命周期统一留给候选 6。
- 不改 Sync Run、前端模块或 AI 报告。
