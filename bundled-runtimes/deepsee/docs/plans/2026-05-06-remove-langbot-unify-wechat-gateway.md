# 0913 完全替代旧 LangBot，统一为微信自动化网关 Implementation Plan

> For Hermes: use subagent-driven-development style execution where useful, but keep ownership of verification in the main session. Follow strict TDD. No production-code changes without failing tests first.

Goal: 让 /Volumes/PSSD/Projects/0913 完全脱离旧 LangBot 发送/同步/聚合依赖，所有微信自动化能力统一收敛到 0913 内嵌 wechat gateway，且不影响 main / terminal UI / 非微信渠道。

Architecture:
- 删除 0913 中所有旧 LangBot 网关、LangBot DB、LangBot 备份同步、LangBot 前端配置入口。
- 保留并增强 0913 自身的 wechat gateway：入站 callback、触发规则、出站规则、统一发送、主消息聚合。
- 前端设置页只保留 0913 微信网关主路径；WeChatPad 仅作为可选 legacy 备用直连，不再作为 LangBot 派生路径。
- Agent/OpenAPI/Send/Sync/AI Config 元数据全部去 LangBot 化，避免未来系统和用户再走回头路。

Tech Stack: FastAPI, SQLAlchemy, SQLite, static/index.html 单页前端, pytest

---

## Phase 0: 现状冻结与基线验证

### Task 0.1: 记录当前 LangBot 相关入口清单
Objective: 在动手前锁定所有待删除入口，避免漏删。

Files:
- Read: `app/routers/send.py`
- Read: `app/routers/sync.py`
- Read: `app/routers/langbot.py`
- Read: `app/services/langbot_gateway_client.py`
- Read: `app/services/send_dispatcher.py`
- Read: `app/services/sync_service.py`
- Read: `app/routers/ai.py`
- Read: `app/routers/agent_api.py`
- Read: `static/index.html`

Step 1: 人工清单确认
- 删除目标：
  - `/api/send/langbot`
  - `/api/send/langbot/health`
  - `/api/send/langbot/bots`
  - `/api/sync/langbot`
  - `/api/langbot/*`
  - `LangBotGatewayClient`
  - `sync_from_langbot_adapters()` 主路径依赖
  - 前端所有 `langbot*` DOM、函数、文案、配置键

Step 2: 记录 git 状态
Run: `git status --short`
Expected: 能看到当前工作树状态，便于后续分辨本次改动。

### Task 0.2: 跑基线测试
Objective: 确认变更前与微信网关相关的测试是绿色的。

Step 1: Run tests
Run:
`pytest -q tests/test_send_campaigns.py tests/test_wechat_gateway_frontend.py tests/test_wechat_gateway_backend.py tests/test_wechat_gateway_reply_local.py tests/test_wechat_gateway_routes.py tests/test_wechat_gateway_settings_modules.py tests/test_wechat_gateway_trigger_rules.py`
Expected: 全绿。

---

## Phase 1: 先写/改失败测试，锁定最终目标

### Task 1.1: 新增 AI config 去 LangBot 化测试
Objective: 先让 `/api/ai/config` 的旧 LangBot 约束暴露为失败测试。

Files:
- Create: `tests/test_ai_config_send_provider_cleanup.py`
- Modify: `app/routers/ai.py`（后续实现）

Step 1: Write failing tests
Test cases:
1. `test_ai_config_accepts_wechatapi_gateway_as_primary_provider`
   - POST `/api/ai/config` with `send_provider=wechatapi_gateway`
   - GET `/api/ai/config` returns `wechatapi_gateway`
2. `test_ai_config_defaults_to_wechatapi_gateway_when_provider_missing_or_invalid`
3. `test_ai_config_response_does_not_expose_langbot_fields`
   - response 不应再含 `langbot_gateway_base`
   - 不应再含 `langbot_gateway_bot_uuid`
   - 不应再含 `langbot_gateway_has_token`
4. `test_ai_config_rejects_removed_langbot_provider`
   - POST with `send_provider=langbot_gateway`
   - 结果不能继续落盘为该值

Step 2: Run test to verify failure
Run: `pytest -q tests/test_ai_config_send_provider_cleanup.py`
Expected: FAIL

### Task 1.2: 新增 send routes cleanup 测试
Objective: 锁定 send router 删除 LangBot 路由后的目标。

Files:
- Create: `tests/test_send_routes_cleanup.py`
- Modify later: `app/routers/send.py`, `app/services/send_dispatcher.py`

Step 1: Write failing tests
Test cases:
1. `test_send_capabilities_no_longer_lists_langbot_provider`
2. `test_send_langbot_routes_are_absent_from_app`
   - 路由表不含 `/api/send/langbot`
   - 不含 `/api/send/langbot/health`
   - 不含 `/api/send/langbot/bots`
3. `test_send_out_rejects_removed_langbot_provider`
   - 若配置或 override 试图走 `langbot_gateway`，返回错误或归一化失败（推荐明确报错）

Step 2: Run test to verify failure
Run: `pytest -q tests/test_send_routes_cleanup.py`
Expected: FAIL

### Task 1.3: 重写前端 provider 测试
Objective: 让前端不再允许 LangBot provider。

Files:
- Modify: `tests/test_wechat_gateway_frontend.py`
- Modify later: `static/index.html`

Step 1: Rewrite failing assertions
Replace/extend with:
1. 不再出现 `option value="langbot_gateway"`
2. 不再出现 `sendProviderLangbot`
3. `getSendProvider()` 只接受：
   - `wechatapi_gateway`
   - `wechatpad_direct`（若保留 legacy）
4. 不再出现：
   - `loadLangbotBots(`
   - `fillGatewayBotUuidFromLangbot(`
   - `importLangbotBotToDirect(`
   - `testLangbotGatewayHealth(`

Step 2: Run test to verify failure
Run: `pytest -q tests/test_wechat_gateway_frontend.py`
Expected: FAIL

### Task 1.4: 替换 LangBot send_campaign 测试
Objective: 删除唯一直接绑定 LangBot 的 send_campaign 测试，改成 wechat gateway 行为测试。

Files:
- Modify: `tests/test_send_campaigns.py`
- Modify later: `app/services/send_dispatcher.py`

Step 1: Replace test
Replace:
- `test_dispatch_send_item_langbot_rich_falls_back_to_text`
With:
- `test_dispatch_send_item_wechat_gateway_media_renders_text_fallback`
Assertions:
- provider = `wechatapi_gateway`
- 含图片/文件时仍会渲染为文本/URL 回退
- 调用 `WechatApiClient.send_text`
- 返回 ok

Step 2: Run test to verify failure
Run: `pytest -q tests/test_send_campaigns.py`
Expected: FAIL

### Task 1.5: 新增 agent API cleanup 测试
Objective: 防止 agent/openapi 继续对外暴露 LangBot。

Files:
- Create: `tests/test_agent_api_cleanup.py`
- Modify later: `app/routers/agent_api.py`

Step 1: Write failing tests
Test cases:
1. `test_agent_modules_do_not_advertise_langbot_send_or_sync_routes`
2. `test_agent_openapi_paths_do_not_include_removed_langbot_routes`

Step 2: Run test to verify failure
Run: `pytest -q tests/test_agent_api_cleanup.py`
Expected: FAIL

---

## Phase 2: 后端删除 LangBot 依赖，统一到 wechat gateway

### Task 2.1: 清理 send_dispatcher 的 LangBot provider
Objective: 移除 `LangBotGatewayClient` 分支与 `langbot_gateway` provider 枚举。

Files:
- Modify: `app/services/send_dispatcher.py`

Step 1: Minimal implementation
- 删除 `from .langbot_gateway_client import LangBotGatewayClient`
- `get_send_provider()` 只允许：
  - `wechatapi_gateway`
  - `wechatpad_direct`（若保留）
- 默认值改为 `wechatapi_gateway`
- 删除 `provider_capabilities()` 中 LangBot 分支
- 删除 `dispatch_send_item()` 中 LangBot 发送分支
- 明确禁止 `provider_override='langbot_gateway'`

Step 2: Run focused tests
Run:
`pytest -q tests/test_send_routes_cleanup.py tests/test_send_campaigns.py tests/test_wechat_gateway_backend.py`
Expected: 逐步转绿

### Task 2.2: 清理 send router 的 LangBot 路由
Objective: 删除 `/api/send/langbot*` 入口。

Files:
- Modify: `app/routers/send.py`

Step 1: Minimal implementation
- 删除 import `LangBotGatewayClient`
- `/api/send/capabilities` 不再返回 `langbot_gateway`
- 删除：
  - `@router.get("/send/langbot/health")`
  - `@router.get("/send/langbot/bots")`
  - `@router.post("/send/langbot")`
- `/api/send/out` 合法 provider 集合去掉 `langbot_gateway`

Step 2: Run tests
Run:
`pytest -q tests/test_send_routes_cleanup.py tests/test_wechat_gateway_frontend.py`
Expected: PASS

### Task 2.3: 清理 AI config 的 LangBot 字段
Objective: 让 `/api/ai/config` 完全转为 0913 wechat gateway + legacy wechatpad 模型。

Files:
- Modify: `app/routers/ai.py`

Step 1: Minimal implementation
- GET `/api/ai/config`
  - `send_provider` 仅允许 `wechatapi_gateway` / `wechatpad_direct`
  - 默认回退改为 `wechatapi_gateway`
  - 不再返回：
    - `langbot_gateway_base`
    - `langbot_gateway_bot_uuid`
    - `langbot_gateway_has_token`
- POST `/api/ai/config`
  - 不再接受 `langbot_gateway`
  - 删除：
    - `langbot_gateway_base`
    - `langbot_gateway_bot_uuid`
    - `langbot_gateway_auth_token`
  的保存逻辑
- 删除 `LangBotGatewayClient` import

Step 2: Run tests
Run:
`pytest -q tests/test_ai_config_send_provider_cleanup.py tests/test_wechat_gateway_frontend.py`
Expected: PASS

### Task 2.4: 清理 sync 路由中的 LangBot 备份同步
Objective: 停掉旧 LangBot adapter 作为微信消息备用来源。

Files:
- Modify: `app/routers/sync.py`
- Modify: `app/services/sync_service.py`
- Consider delete later: `app/services/ext_adapter_service.py`（若完全无用）

Step 1: Minimal implementation
- `app/routers/sync.py`
  - 删除 `sync_from_langbot_adapters` import
  - 删除 `_langbot_backup_enabled()`
  - 删除 `/api/sync/langbot`
  - 删除 chatlog/full sync 中附加的 `res["langbot"] = ...`
- `app/services/sync_service.py`
  - 删除 `sync_from_langbot_adapters()` 全段
  - 删除 `_LANGBOT_CURSOR_KEY`
  - 删除 `_get_extensions_log_dir()` 和默认 LangBot log path fallback
  - 删除 `meta_payload.setdefault("source", "langbot")` 这一旧逻辑（保留 ext adapter 其他非 LangBot 逻辑时要改成通用 source）

Step 2: Run tests
Run:
`pytest -q tests/test_send_routes_cleanup.py tests/test_agent_api_cleanup.py tests/test_wechat_gateway_routes.py`
Expected: PASS

### Task 2.5: 清理独立 LangBot router
Objective: 删除 `/api/langbot/*`。

Files:
- Delete: `app/routers/langbot.py`
- Modify: `app/main.py`

Step 1: Minimal implementation
- 从 `app/main.py` 的 router import 中删除 `langbot`
- 删除 `app.include_router(langbot.router)`
- 删除文件 `app/routers/langbot.py`

Step 2: Run tests
Run:
`pytest -q tests/test_send_routes_cleanup.py tests/test_agent_api_cleanup.py tests/test_wechat_gateway_routes.py`
Expected: PASS

### Task 2.6: 清理 agent API 元数据
Objective: 不再向其他 agent 公布旧 LangBot 路由。

Files:
- Modify: `app/routers/agent_api.py`

Step 1: Minimal implementation
- `agent_modules()` 中：
  - sending 只保留 `/api/send`, `/api/send/out`, `/api/send/wechatpad`（若保留）
  - sync_and_backup 去掉 `/api/sync/langbot`
- openapi 无需特殊处理，只要路由本身移除了就自然不会暴露

Step 2: Run tests
Run: `pytest -q tests/test_agent_api_cleanup.py`
Expected: PASS

---

## Phase 3: 前端删除 LangBot 入口，改成 0913 微信网关主控台

### Task 3.1: 删除 LangBot 发送面板与 provider 选项
Objective: 发送设置页不再出现 LangBot。

Files:
- Modify: `static/index.html`
- Related tests: `tests/test_wechat_gateway_frontend.py`

Step 1: Minimal implementation
- 删除 `option value="langbot_gateway"`
- 删除 `#sendProviderLangbot` 整块
- 删除 `.langbot-bot-picker` / `.langbot-bot-actions` / `#langbotGatewayAuthToken` 样式
- 标题从“推荐：LangBot 网关”改为“0913 微信网关”

Step 2: Run tests
Run: `pytest -q tests/test_wechat_gateway_frontend.py`
Expected: PASS

### Task 3.2: 删除 LangBot 前端 helper 函数
Objective: 去掉所有 LangBot JS helper，避免 UI 残留入口。

Files:
- Modify: `static/index.html`

Step 1: Minimal implementation
Delete functions:
- `toggleGatewayTokenVisibility`
- `loadLangbotBots`
- `fillGatewayBotUuidFromLangbot`
- `importLangbotBotToDirect`
- `importLangbotBot`
- `testLangbotGatewayHealth`

Step 2: Run tests
Run: `pytest -q tests/test_wechat_gateway_frontend.py`
Expected: PASS

### Task 3.3: 改写前端 provider 逻辑
Objective: 前端 provider 语义与后端统一。

Files:
- Modify: `static/index.html`

Step 1: Minimal implementation
- `getSendProvider()` 改成：
  - 保留 legacy 方案：只接受 `wechatapi_gateway` / `wechatpad_direct`，默认 `wechatapi_gateway`
- `applySendProviderUi()` 删除 `pLangbot` 分支
- `loadAiConfig()` 中 send_provider fallback 改为 `wechatapi_gateway`
- `saveSendConfig()` 不再读写任何 `langbot_gateway_*`

Step 2: Run tests
Run: `pytest -q tests/test_wechat_gateway_frontend.py tests/test_ai_config_send_provider_cleanup.py`
Expected: PASS

### Task 3.4: 删除旧 LangBot 聚合/备份 UI
Objective: 让“微信聚合”只表达 0913 主消息聚合，不再保留 LangBot 备份/导入心智。

Files:
- Modify: `static/index.html`

Step 1: Minimal implementation
Remove/replace:
- `syncWeChatAggFromSendConfig()`
- `saveExtensionsConfig()` 中 langbot backup 相关片段
- `hydrateExtensionsConfigInput()` 中 langbot backup 相关片段
- `syncLangbotBackup()`
- `langbotBackupEnabled`, `langbotBackupDays`, `langbotBackupMsg` 控件
- “自定义聚合（LangBot / 多平台）”标题与同步按钮
- 若目标是完全纯化，可整段移除 ext adapter 聚合设置区

Step 2: Run tests
Run: `pytest -q tests/test_wechat_gateway_frontend.py tests/test_wechat_gateway_settings_modules.py`
Expected: PASS

---

## Phase 4: 强化微信网关终态能力

### Task 4.1: 增加 wechat gateway health/status API
Objective: 用正式 API 替代前端中“借 /api/send/out 检测”的过渡实现。

Files:
- Modify: `app/routers/wechat_gateway.py`
- Modify: `app/services/wechatapi_client.py`
- Modify: `tests/test_wechat_gateway_routes.py`
- Possibly create: `tests/test_wechat_gateway_health_status.py`

Step 1: Write failing tests
Tests:
- `GET /api/wechat-gateway/health`
- `GET /api/wechat-gateway/status`

Step 2: Implement minimal endpoints
- health: 返回 configured/check_online/callback config
- status: 返回 config + trigger rules + online status

Step 3: Run tests
Run: `pytest -q tests/test_wechat_gateway_routes.py tests/test_wechat_gateway_health_status.py`
Expected: PASS

### Task 4.2: 增加 bind-callback API
Objective: 让 8001 设置页真能完成 setCallback。

Files:
- Modify: `app/routers/wechat_gateway.py`
- Modify: `tests/test_wechat_gateway_routes.py`
- Modify: `static/index.html`

Step 1: Write failing test
- POST `/api/wechat-gateway/bind-callback`
- mock `WechatApiClient.set_callback`
- 返回 ok

Step 2: Implement minimal endpoint
- 读取当前 config.callback_public_url
- 调 `WechatApiClient.set_callback`

Step 3: Wire frontend
- `bindWechatGatewayCallback()` 改为真实调用该接口

Step 4: Run tests
Run: `pytest -q tests/test_wechat_gateway_routes.py tests/test_wechat_gateway_frontend.py`
Expected: PASS

### Task 4.3: 统一微信出站都经网关规则
Objective: 满足“0913 只对微信自动化体系消息生效，但微信自动化体系内部统一受控”。

Files:
- Modify: `app/services/send_dispatcher.py`
- Modify: tests around gateway/backend

Step 1: Decide legacy policy
Recommended:
- `wechatpad_direct` 保留为 emergency/manual provider
- 但凡被视作“微信自动化体系”的自动发送，都必须走 `wechatapi_gateway`
- 如果某入口仍用 `wechatpad_direct`，必须是显式人工 fallback，不作为默认路径

Step 2: Add/adjust tests
- 自动发送默认 provider = `wechatapi_gateway`
- rule isolation 只对微信自动化 provider 生效
- 非微信模块不受影响

---

## Phase 5: 最终验证与清理

### Task 5.1: 清理残余 LangBot 字符串与文档
Objective: 保证代码、前端、测试、文案中不再残留误导性的 LangBot 主路径描述。

Files:
- Search all project files for `langbot`

Step 1: Search
Run: `search_files(pattern='langbot', path='.', target='content')`
Expected: 只剩必要历史文档或无结果

Step 2: Clean residuals
- 改注释
- 改 placeholder
- 改说明文案
- 改 agent module metadata

### Task 5.2: 运行目标回归套件
Objective: 验证主目标达成。

Step 1: Run focused suite
Run:
`pytest -q tests/test_ai_config_send_provider_cleanup.py tests/test_send_routes_cleanup.py tests/test_agent_api_cleanup.py tests/test_send_campaigns.py tests/test_wechat_gateway_frontend.py tests/test_wechat_gateway_backend.py tests/test_wechat_gateway_reply_local.py tests/test_wechat_gateway_routes.py tests/test_wechat_gateway_settings_modules.py tests/test_wechat_gateway_trigger_rules.py`
Expected: PASS

Step 2: Run broader regression
Run:
`pytest -q tests/test_agent_api_auth.py tests/test_agent_api_policy.py tests/test_production_guardrails.py`
Expected: PASS

Step 3: Optionally full test suite
Run: `pytest -q`
Expected: PASS or only known unrelated failures

### Task 5.3: 验收标准核对
Objective: 对照用户原始 5 项目标逐条验收。

Checklist:
- [ ] 0913 已不再依赖旧 LangBot 网关/DB/备份同步/前端入口
- [ ] 所有微信自动化收发通过 0913 wechat gateway
- [ ] 8001 设置页可配置 gateway config + trigger rules + callback bind
- [ ] 微信消息去重后并入主 Message 聚合
- [ ] 规则仅作用于微信自动化体系，不影响 main / terminal UI / 非微信渠道
- [ ] agent/openapi/config/send/sync 元数据无 LangBot 主路径暴露

---

## 并行执行建议（适合子 agent）

可以并行的工作流：
1. 子 agent A：测试先行
- 写/改：
  - `tests/test_ai_config_send_provider_cleanup.py`
  - `tests/test_send_routes_cleanup.py`
  - `tests/test_agent_api_cleanup.py`
  - 重写 `tests/test_wechat_gateway_frontend.py`
  - 替换 `tests/test_send_campaigns.py` 的 LangBot 测试

2. 子 agent B：后端去 LangBot
- 改：
  - `app/services/send_dispatcher.py`
  - `app/routers/send.py`
  - `app/routers/ai.py`
  - `app/routers/sync.py`
  - `app/routers/agent_api.py`
  - `app/main.py`
  - 删 `app/routers/langbot.py`
  - 删 `app/services/langbot_gateway_client.py`

3. 子 agent C：前端去 LangBot
- 改：
  - `static/index.html`
  - 删除 LangBot 面板、聚合、helper、文案、旧保存逻辑

注意：
- `app/routers/ai.py` 与 `static/index.html` 都是高冲突大文件，不要让多个子 agent 同时改同一文件。
- 子 agent 完成后，必须由主会话统一回读 diff、跑测试、验证真实结果。

---

## 推荐提交粒度
1. `test: add failing cleanup tests for langbot removal`
2. `refactor: remove langbot send provider from backend`
3. `refactor: remove langbot sync and adapter backup path`
4. `refactor: remove langbot ui and config bindings`
5. `feat: add wechat gateway health status and callback bind APIs`
6. `test: finalize gateway-only regression coverage`

---

## 风险与注意事项
- 最大风险不是删代码，而是 `app/routers/ai.py` 与 `static/index.html` 的配置读写必须同步改，否则前后端 provider 状态会漂移。
- `wechatpad_direct` 是否保留，需要在实现前固定策略；本计划默认保留为 legacy/manual fallback，但不再让它承担 LangBot 派生职责。
- 若 `ExtAdapter` / `AdapterMessage` 还服务其他非微信外部源，不要误删通用能力；只删 LangBot 相关 source_type、默认值、UI 入口和 sync 路径。
- 每一阶段结束都要重新搜一次 `langbot`，避免遗漏。

Plan complete and saved to:
/Volumes/PSSD/Projects/0913/docs/plans/2026-05-06-remove-langbot-unify-wechat-gateway.md
