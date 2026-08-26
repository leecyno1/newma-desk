# 微信自动化网关接入分析与实施方案

> For Hermes: follow strict TDD for every code change after this analysis. Prefer adding failing tests first, then minimal implementation.

更新时间：2026-05-06

## 1. 目标

把 `wechatapi` 的“接收 / 控制 / 发送 / 去重 / 聚合”能力收敛进 `0913` 项目内部，形成一个只对“微信自动化体系”生效的网关模块；规则流水线参考 `LangBot` 的 pipeline/stage/config 设计，但实现落点必须是 `0913` 自身的后端、数据库和 8001 端口设置页。

## 2. 本次代码级分析结论

### 2.1 0913 当前技术栈与结构

项目位于 `/Volumes/PSSD/Projects/0913`。

核心栈：
- Python 3.11+
- FastAPI (`app/main.py`)
- SQLAlchemy 2.x + SQLite (`app/db.py`)
- 单文件静态前端 UI (`static/index.html`)
- 配置混合模式：
  - `.env` / `app/config.py`
  - `data/ai_config.json` / `app/services/llm_client.py`
  - `sync_state` 表 / `app/routers/configs.py`

关键目录：
- `app/main.py`: 应用入口，统一挂载所有 router
- `app/models.py`: 主消息表、扩展消息表、发送任务表、配置状态表
- `app/routers/configs.py`: 设置页对应的后端配置接口
- `app/routers/send.py`: 发送管理 API
- `app/services/send_dispatcher.py`: 发送分发器
- `app/services/langbot_gateway_client.py`: 现有 LangBot 网关客户端
- `app/services/wechat8061_sync.py`: 现有微信同步备用链路
- `app/services/wechat8061_store.py`: 独立微信备用库（`wechat8061_backup.db`）
- `app/services/sync_service.py`: 扩展适配器消息合并进主 `messages` 表
- `static/index.html`: 统一前端与设置页

### 2.2 0913 已有可复用能力

#### A. 主消息聚合模型已经存在
`app/models.py` 里已有：
- `Message`: 主消息表
- `Chat` / `Contact`: 主联系人与会话维度
- `SyncState`: 轻量配置/游标持久化
- `ExtAdapter`: 外部适配器定义
- `AdapterMessage`: 扩展来源消息暂存表
- `SendCampaign` / `SendDelivery`: 发送任务与投递记录

这意味着本次无需新造独立微信子系统，可以复用两层结构：
1. `AdapterMessage` / 或新的微信事件暂存表承接原始入站
2. `Message` 作为最终聚合展示表

#### B. 设置页基础设施已经成熟
`static/index.html` 已经不是简单页面，而是一个大型配置控制台。已有成熟模式：
- `loadAiConfig()` 从 `/api/ai/config` 拉取复杂配置
- `/api/config/*` + `SyncState` 保存模块配置
- 已有发送配置、分钟聚合、自媒体聚合、公众号聚合、扩展配置等多个 section
- 已经有“可视化大表单 + JSON/配置回填”的实现经验（如 model router）

因此微信网关规则可直接按现有设置页范式接入，不需要新前端框架。

#### C. 发送链路已经抽象成 provider
`app/services/send_dispatcher.py` 当前支持：
- `langbot_gateway`
- `wechatpad_direct`

核心函数：
- `get_send_provider()`
- `provider_capabilities()`
- `dispatch_send_item()`
- `dispatch_send_items()`

这给微信自动化网关接入提供了最直接的插槽：
- 新增 provider，例如 `wechatapi_gateway`
- 或把现有 `langbot_gateway` 的抽象上提为“网关型 provider”，由微信网关接管微信出站

#### D. 现有微信同步是“备用库”模式
`wechat8061_store.py` 使用单独 SQLite：
- 表：`wx_messages`
- 唯一键：`UNIQUE(wxid, msg_id)`

`wechat8061_sync.py` 负责从 HTTP/WS 拉消息，再写入该备份库。

这说明 `0913` 里已经有“微信消息先落备用区，再并入主聚合”的现成思路。新的 `wechatapi` 网关不必从零设计，可沿用：
- 原始事件/回调落地
- 去重
- 规范化
- 合并到主 `Message`

#### E. 扩展消息合并逻辑已经存在
`app/services/sync_service.py` 已经支持：
- 从 `ExtAdapter` 读取启用的适配器
- 把 `AdapterMessage` 去重合并到 `Message`
- 应用黑白名单过滤
- 自动 upsert `Chat` / `Contact`

这个服务最像未来“微信网关规范化合并器”的前身。

### 2.3 0913 当前不足

1. 还没有面向 `wechatapi` 的正式 adapter/client
2. 微信入站没有统一回调入口并入主库
3. 发送 provider 还没做到“所有微信发送都经统一网关规则审查”
4. 规则配置目前只有黑白名单，没有 stage/pipeline 概念
5. 微信同步目前在 `wechat8061_backup.db`，还没有完整并入主聚合闭环
6. 还没有“规则仅作用于微信渠道”的强边界定义

---

### 2.4 LangBot 当前技术与可借鉴点

项目位于 `/Volumes/PSSD/Projects/LangBot`。

核心结构：
- 后端：Quart / SQLAlchemy / DB migrations
- 前端：Next.js + shadcn + Tailwind (`web/`)
- 核心模块：`pkg/pipeline`, `pkg/api`, `pkg/platform`, `pkg/provider`

关键结论：

#### A. LangBot 的规则体系是“数据库持久化流水线”
关键文件：
- `src/langbot/pkg/entity/persistence/pipeline.py`
- `src/langbot/pkg/api/http/service/pipeline.py`
- `src/langbot/pkg/pipeline/pipelinemgr.py`
- `src/langbot/templates/default-pipeline-config.json`

其中 `LegacyPipeline` 存储：
- `stages`
- `config`
- `extensions_preferences`

说明 LangBot 的核心不是硬编码 if/else，而是：
- stage 顺序固定/可扩展
- config 数据驱动
- 运行时根据 pipeline config 执行

#### B. LangBot 的默认 stage 顺序值得直接借鉴
默认顺序：
1. `GroupRespondRuleCheckStage`
2. `PersonRespondRuleCheckStage`
3. `BanSessionCheckStage`
4. `PreContentFilterStage`
5. `PreProcessor`
6. `ConversationMessageTruncator`
7. `RequireRateLimitOccupancy`
8. `MessageProcessor`
9. `ReleaseRateLimitOccupancy`
10. `PostContentFilterStage`
11. `ResponseWrapper`
12. `LongTextProcessStage`
13. `SendResponseBackStage`

对 0913 的可迁移思想：
- 先触发判断，再访问控制，再去重/频控，再处理，再出站
- 规则应有明确顺序，不能散落在发送/接收函数里

#### C. LangBot 触发/控制规则的配置模型非常适合复用到微信网关
默认配置见 `default-pipeline-config.json`：
- `trigger.person-respond-rules`
- `trigger.group-respond-rules`
- `trigger.access-control`
- `trigger.ignore-rules`
- `trigger.misc`
- `safety.rate-limit`
- `output.misc.human-reply-guard-enabled`
- `output.misc.auto-reply-loop-guard-enabled`

这几块可以映射成 0913 微信网关规则：
- 私聊触发规则
- 群聊触发规则
- 黑白名单/访问控制
- 忽略规则
- 去重/最小文本长度
- 频控
- 人工接管保护
- 自动回复循环保护

#### D. LangBot 的几个具体 stage 可以直接转成 0913 微信网关 stage
1. `resprule/resprule.py`
   - 群/私聊响应规则检查
2. `bansess/bansess.py`
   - access-control 黑白名单
3. `dedup/stage.py`
   - 消息去重开关和策略
4. `guard/replyguard.py` + `respback/respback.py`
   - 人工接管窗口
   - 自动回复循环保护

这些是本次最有价值的参考，而不是整套 LangBot 平台适配层。

#### E. LangBot 前端是 metadata 驱动表单
- `/api/v1/pipelines/_/metadata`
- `PipelineFormComponent.tsx`
- 动态 form 根据 metadata 渲染 trigger/safety/output/ai 配置

对 0913 的启发：
- 不需要复制 Next.js UI
- 但应复制“后端给 schema，前端渲染规则表单”的思路
- 0913 最适合先做“轻量 schema + 表格表单 + JSON 预览”版本

## 3. 综合判断：最终接入策略

不是把 LangBot 嵌进 0913，也不是继续让 Hermes 直接读 `wechatapi`。

正确做法是：
1. 在 `0913` 内实现一个 `wechatapi gateway module`
2. 借鉴 `LangBot pipeline config` 的数据结构和 stage 顺序
3. 复用 `0913` 已有的：
   - `SyncState` 配置存储
   - `Message` 聚合模型
   - `SendCampaign/SendDelivery`
   - `static/index.html` 设置页
4. 把未来所有微信出入站统一经该网关
5. 把规则作用域严格限定为 `channel=wechat_gateway` / `source=wechatapi`

## 4. 建议的 0913 目标架构

### 4.1 新模块划分

建议新增：
- `app/services/wechatapi_client.py`
  - 封装 `http://api.wechatapi.net/finder/v2/api`
  - 统一 header/token/appid/callback 行为
- `app/services/wechat_gateway_rules.py`
  - 规则配置默认值、schema、规范化
- `app/services/wechat_gateway_pipeline.py`
  - stage 执行器
- `app/services/wechat_gateway_ingest.py`
  - callback 入站事件解析、落库、去重、媒体二次下载调度
- `app/services/wechat_gateway_sender.py`
  - 微信出站统一入口，先跑规则再调 wechatapi
- `app/services/wechat_gateway_store.py`
  - 微信网关事件暂存/审计/去重查询

建议新增 router：
- `app/routers/wechat_gateway.py`
  - `/api/wechat-gateway/health`
  - `/api/wechat-gateway/callback`
  - `/api/wechat-gateway/status`
  - `/api/wechat-gateway/events`
  - `/api/wechat-gateway/send`
- `app/routers/wechat_gateway_config.py`
  - `/api/config/wechat-gateway`
  - `/api/config/wechat-gateway/test`

建议新增模型：
- `WechatGatewayEvent`
  - 保存回调原始事件、规范化结果、去重键、处理状态
- `WechatGatewayRuleSet` 或直接复用 `SyncState` 存整对象
  - v1 建议先用 `SyncState`
- `WechatGatewayDeliveryAudit`
  - 审计微信发送结果（可选；若复用 `SendDelivery.meta` 则可不单独建表）

### 4.2 推荐 v1 配置存储方案

第一版优先用 `SyncState` 保存网关配置，避免一上来就做复杂迁移。

建议 key：
- `wechat_gateway_config`
- `wechat_gateway_runtime`
- `wechat_gateway_callback_binding`

其中 `wechat_gateway_config` 结构建议：

```json
{
  "enabled": true,
  "base_url": "http://api.wechatapi.net/finder/v2/api",
  "token_header": "X-Gateway-Token",
  "has_token": true,
  "appid": "[REDACTED]",
  "uuid": "[REDACTED]",
  "region": "11000",
  "device": "ipad",
  "callback_url": "http://.../api/wechat-gateway/callback",
  "ack_timeout_ms": 2500,
  "pipeline": {
    "enabled": true,
    "trigger": {
      "person_respond_rules": {"prefix": [], "regexp": [], "random": 0.0},
      "group_respond_rules": {"at": true, "prefix": [], "regexp": [], "random": 0.0},
      "access_control": {"mode": "blacklist", "blacklist": [], "whitelist": []},
      "ignore_rules": {"prefix": [], "regexp": []},
      "message_deduplication": {"enabled": true}
    },
    "safety": {
      "rate_limit": {"window_length": 60, "limitation": 30, "strategy": "drop"}
    },
    "output": {
      "misc": {
        "human_reply_guard_enabled": true,
        "human_reply_guard_window_ms": 30000,
        "auto_reply_loop_guard_enabled": true,
        "auto_reply_loop_window_ms": 60000,
        "auto_reply_loop_max_count": 8,
        "auto_reply_loop_cooldown_ms": 180000
      }
    }
  },
  "media": {
    "download_image": true,
    "download_voice": true,
    "download_video": false,
    "download_file": true
  },
  "scope": {
    "apply_to_channels": ["wechat_gateway"],
    "exclude_channels": ["main", "terminal_ui"]
  }
}
```

## 5. 入站链路设计

### 5.1 回调处理原则

已验证外部约束：
- 3 秒内返回 200 / 空串
- 去重键建议：`Appid + Data.NewMsgId`
- 图片/语音/视频/文件通过二次下载接口获取

因此 `POST /api/wechat-gateway/callback` 处理流程：
1. 接收原始 payload
2. 立刻提取 dedup key
3. 原始事件快速落地（或写入内存队列 + 本地持久化）
4. 立刻 ACK
5. 后台异步执行 pipeline 和消息规范化

### 5.2 入站 stage 建议顺序

v1 建议：
1. `AckStage`（仅保证 3 秒返回，逻辑上最先）
2. `DedupStage`
3. `EventTypeStage`（`AddMsg` / `ModContacts` / `DelContacts` / `Offline` / `FinderSyncMsg` / `FinderBypMsg`）
4. `TriggerRuleStage`
5. `AccessControlStage`
6. `IgnoreRuleStage`
7. `NormalizeMessageStage`
8. `MediaFetchStage`
9. `AggregateInsertStage`
10. `AuditStage`

### 5.3 主聚合落库策略

建议最终落入 `Message`，并在 `meta` 中保留微信专有字段：
- `source = wechat_gateway`
- `provider = wechatapi`
- `event_type`
- `new_msg_id`
- `appid`
- `wxid / from_user / to_user`
- `raw_msg_type`
- `appmsg_type`
- `media_download_status`

同时：
- `chat_id`: 归一化后的会话 id
- `sender_id`: 微信发送方 id
- `talker_name` / `sender_name`: 尽可能从联系人数据补齐
- `direction`: `in` / `out`
- `type`: `text/image/voice/video/file/link/system/other`

## 6. 出站链路设计

### 6.1 目标

以后所有微信发送必须进入：
`0913 send API -> wechat gateway pipeline -> wechatapi_client`

不能再绕过 0913 直接打 wechatapi。

### 6.2 接入点

最适合修改：
- `app/services/send_dispatcher.py`
- `app/routers/send.py`

方案：
- 新增 provider: `wechatapi_gateway`
- 当 channel 命中微信自动化体系时，强制使用该 provider
- `dispatch_send_item()` 中进入 `WechatGatewaySender.send()`

### 6.3 出站 stage 建议

1. `OutboundScopeStage`（仅微信通道进入）
2. `AccessControlStage`
3. `TemplateRenderStage`
4. `HumanReplyGuardStage`
5. `AutoReplyLoopGuardStage`
6. `RateLimitStage`
7. `SendStage`
8. `DeliveryAuditStage`

### 6.4 与现有发送记录复用

复用现有：
- `SendCampaign`
- `SendDelivery`

把网关审查结果写入：
- `SendDelivery.provider = wechatapi_gateway`
- `SendDelivery.channel = wechat_gateway`
- `SendDelivery.provider_result`
- `SendDelivery.meta.pipeline_trace`

## 7. 去重与聚合并入方案

### 7.1 去重分层

建议三层去重：

第一层：回调事件去重
- 键：`appid + new_msg_id`

第二层：原始消息去重
- 键：`chat_id + sender_id + timestamp + normalized_content_hash`

第三层：聚合入主表去重
- 复用 `sync_service.py` 现有 best-effort 逻辑，但对微信来源增加 `source/external_id` 优先判定

### 7.2 数据库建议

若建新表 `wechat_gateway_events`，建议唯一约束：
- `unique(dedup_key)`

若不新建表，只落 `Message`，也至少要把：
- `meta.external_id = Data.NewMsgId`
- `meta.source = wechat_gateway`

并在插入前查询同来源同 external_id。

### 7.3 与现有微信聚合页面的关系

当前 0913 已有：
- 主消息页（`Message`）
- `wechat8061` 备用同步页面

本次建议：
- 新网关最终写主 `Message`
- `wechat8061` 保留为旧链路/备份观察页
- 后续可把 `wechat8061` 入口逐步弱化为 debug 页面

## 8. 规则隔离边界

这是本次最重要的非功能要求。

必须做到：
- 微信自动化规则只影响 `source=wechat_gateway` 或 `channel=wechat_gateway`
- `main`、`terminal ui`、其它聚合源不进入这些 stage

推荐实现：
- 新增统一判断函数：
  - `is_wechat_gateway_message(...)`
  - `is_wechat_gateway_delivery(...)`
- 所有规则执行前先检查 scope
- 在配置里保留 `scope.apply_to_channels = [wechat_gateway]`

不要：
- 直接复用当前 `/api/filters` 全局黑白名单去拦所有渠道
- 把微信网关规则写进全局 AI runtime 开关

## 9. 前端设置页落点

最佳位置：`static/index.html` 的“功能设置”里新增一节，例如：
- `settingsWechatGateway`

建议分 4 个块：
1. 基础连接
   - base_url
   - token（只显示已配置）
   - appid / uuid / 地区 / 设备
   - callback_url
   - 测试连接按钮
2. 入站控制
   - 启用网关
   - 启用去重
   - 是否下载图片/语音/文件/视频
3. 规则流水线
   - 私聊响应规则
   - 群聊响应规则
   - access control
   - ignore rules
   - 频控
   - 人工接管
   - 自动回复循环保护
4. 运行状态
   - 最近 callback
   - 最近错误
   - 最近去重命中
   - 最近发送审计

实现方式建议：
- v1 使用现有风格：原生 JS + `requestJson('/api/config/wechat-gateway')`
- 保留一个“高级 JSON”折叠区，方便和 LangBot pipeline config 对齐

## 10. 推荐实施顺序（按 TDD）

### Task 1: 建立微信网关配置读写
文件：
- Modify: `app/main.py`
- Create: `app/routers/wechat_gateway_config.py`
- Test: `tests/test_wechat_gateway_config.py`

目标：先打通 `/api/config/wechat-gateway` 的 GET/POST。

### Task 2: 建立 wechatapi client
文件：
- Create: `app/services/wechatapi_client.py`
- Test: `tests/test_wechatapi_client.py`

目标：封装 health/checkOnline/getProfile/postText/setCallback/download*。

### Task 3: 建立入站事件表或暂存策略
文件：
- Modify: `app/models.py`
- Modify: `app/db.py`
- Test: `tests/test_wechat_gateway_store.py`

目标：支持 dedup key、原始 payload、处理状态。

### Task 4: 建立 callback router
文件：
- Create: `app/routers/wechat_gateway.py`
- Test: `tests/test_wechat_gateway_callback.py`

目标：3 秒内 ACK；重复消息不重复处理。

### Task 5: 建立 pipeline/rules 执行器
文件：
- Create: `app/services/wechat_gateway_rules.py`
- Create: `app/services/wechat_gateway_pipeline.py`
- Test: `tests/test_wechat_gateway_pipeline.py`

目标：最少实现：trigger/access-control/ignore/dedup/rate-limit。

### Task 6: 把入站消息规范化写入主 Message
文件：
- Create: `app/services/wechat_gateway_ingest.py`
- Modify: `app/models.py`（如需）
- Test: `tests/test_wechat_gateway_ingest.py`

目标：微信消息出现在主聚合页。

### Task 7: 打通发送 provider
文件：
- Modify: `app/services/send_dispatcher.py`
- Modify: `app/routers/send.py`
- Create: `app/services/wechat_gateway_sender.py`
- Test: `tests/test_wechat_gateway_send.py`

目标：所有微信自动化发送经网关规则审查后再发出。

### Task 8: 设置页接入
文件：
- Modify: `static/index.html`
- Test: `tests/test_wechat_gateway_config.py`（后端），前端手测

目标：在 8001 设置页可视化配置规则。

### Task 9: 运行态与审计
文件：
- Modify: `app/routers/wechat_gateway.py`
- Modify: `static/index.html`
- Test: `tests/test_wechat_gateway_runtime.py`

目标：显示 callback、去重、错误、发送状态。

### Task 10: 通道隔离回归测试
文件：
- Test: `tests/test_wechat_gateway_scope.py`

目标：证明 main/terminal ui/其它聚合源不被微信规则影响。

## 11. 当前已确认的外部接入事实

- `wechatapi` 稳定 base URL 使用：`http://api.wechatapi.net/finder/v2/api`
- HTTPS 版本当前存在证书主机名不匹配问题，不作为稳定基址
- callback 已经在外部验证过可用
- 主动发送、在线状态、profile、callback 绑定都已验证成功

## 12. 本次分析后的推荐下一步

直接进入实现前，先完成：
1. `tests/test_wechat_gateway_config.py`
2. `app/routers/wechat_gateway_config.py`
3. `tests/test_wechat_gateway_callback.py`
4. `app/routers/wechat_gateway.py`

也就是先把“配置 + callback ACK + dedup 壳子”打出来，再接聚合与发送。

## 13. 2026-05-06 实施落地状态

### 13.1 wechatapi AI 辅助开发要点落地

外部文档 `https://post.wechatapi.net/doc-8561747` 的 AI 辅助开发部分强调：上线前必须本地跑通主流程，重点核对接口地址、传参格式，以及发送前随机休眠（Sleep）防封逻辑。当前落地如下：

- `app/services/wechatapi_client.py` 统一封装 `base_url`、`VideosApi-token` header、`appId`、`/message/postText`、`/login/checkOnline`、`/login/setCallback`。
- `app/services/wechat_gateway.py` 新增 `outbound_random_delay_min_seconds` / `outbound_random_delay_max_seconds`，发送前通过 `apply_outbound_random_delay()` 执行随机休眠。
- `static/index.html` 设置页已可视化配置随机休眠区间，建议客户生产环境设置为 3-5 秒模拟人工节奏。
- `tests/test_wechat_gateway_agent_ws.py` 覆盖随机休眠配置归一化，`tests/test_wechat_gateway_frontend.py` 覆盖前端字段存在与配置回填。

### 13.2 0913 网关模块已实现能力

后端模块：

- `app/routers/wechat_gateway.py`
  - `GET/POST /api/wechat-gateway/config`：网关主配置。
  - `GET/POST /api/wechat-gateway/trigger-rules`：触发规则配置。
  - `POST /api/wechat-gateway/callback`：wechatapi 回调接收，3 秒内 ACK。
  - `POST /api/wechat-gateway/bind-callback`：调用 wechatapi `setCallback` 绑定公网回调。
  - `POST /api/wechat-gateway/agent-event`：Hermes/OpenClaw 等 agent 侧微信事件写入 0913 聚合。
  - `POST /api/wechat-gateway/agent-send-text`：agent 侧微信文本出站统一经 0913 规则、随机休眠、wechatapi 发送与出站记录。
  - `WS /api/wechat-gateway/ws/agent`：agent 侧 WebSocket 微信事件接入。

服务模块：

- `app/services/wechat_gateway.py`
  - 使用 `SyncState` 存储网关配置和去重 key。
  - 入站 callback 和 agent event 均写入主 `Message` / `Chat` / `Contact`。
  - 规则作用域限定为微信自动化渠道，非微信 `channel` 返回 `non_wechat_channel`，不会污染 main / terminal UI。
  - 出站通过 `evaluate_outbound_message()` 执行黑白名单、关键词、开关规则。

前端模块：

- `static/index.html`
  - 设置页增加 `wechatapi_gateway` provider 入口。
  - 可视化配置 wechatapi base URL、token header、token、appId、callback URL、设备/区域、黑白名单、关键词屏蔽、频控、随机休眠。
  - 可视化配置私聊/群聊触发规则、前缀、最小长度、人工回复保护、自动回复循环保护。
  - 支持保存、重新加载、配置检测、回调绑定。

### 13.3 Hermes / OpenClaw 接入边界

Hermes 当前事实：

- `/Volumes/PSSD/Projects/hermes-agent/gateway/platforms/weixin.py` 内置 Weixin/iLink 适配器，默认直连 `https://ilinkai.weixin.qq.com`，不是 wechatapi。
- 本轮新增默认关闭的 0913 网关桥接，只作用于 `Platform.WEIXIN`：
  - `WEIXIN_0913_GATEWAY_ENABLED=true`
  - `WEIXIN_0913_GATEWAY_URL=http://127.0.0.1:8001`
  - `WEIXIN_0913_GATEWAY_TOKEN=<0913 API_TOKEN，可选>`
- 开启后，Hermes Weixin 入站会先转发到 `0913 /api/wechat-gateway/agent-event`；Hermes Weixin 出站文本会调用 `0913 /api/wechat-gateway/agent-send-text`。
- 默认关闭，且只改 `gateway/platforms/weixin.py`，不会影响 Hermes CLI、terminal UI、main 交互或其他平台。

OpenClaw 当前事实：

- `/Volumes/PSSD/Projects/OpenClaw` 主仓未发现内置微信发送/接收实现，只有社区插件 `@icesword760/openclaw-wechat` 文档。
- 因此 0913 提供统一契约：OpenClaw 或其微信插件必须只调用 `POST /api/wechat-gateway/agent-event` / `WS /api/wechat-gateway/ws/agent` 入站记录，和 `POST /api/wechat-gateway/agent-send-text` 出站发送。
- 若客户安装具体 OpenClaw 微信插件，需要对插件包单独做一次直连 wechatapi 审计，并替换为上述 0913 契约。

### 13.4 当前验证结果

已运行并通过：

```bash
pytest -q tests/test_wechat_gateway*.py
# 27 passed

pytest -q \
  tests/test_wechat_gateway_trigger_rules.py \
  tests/test_wechat_gateway_frontend.py \
  tests/test_wechat_gateway_agent_ws.py \
  tests/test_wechat_gateway_ai_config.py \
  tests/test_wechat_gateway_websocket_route.py \
  tests/test_wechat_gateway_routes.py \
  tests/test_wechat_gateway_backend.py \
  tests/test_send_campaigns.py \
  tests/test_messages_derive_fallback.py \
  tests/test_commercial_readiness.py
# 41 passed

cd /Volumes/PSSD/Projects/hermes-agent && pytest -q tests/gateway/test_weixin.py -q
# 47 passed
```

