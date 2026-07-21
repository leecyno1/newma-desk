# Model Gateway 与 Agent Gateway 分离设计

日期：2026-07-20

## 目标

VibeDesk 提供两条并列的 AI 链路，由 Mod 明确选择，任何一条都不自动转发到另一条：

```text
Mod -> Model Gateway -> GPT / Claude / OpenAI-compatible / 本地模型
Mod -> Agent Gateway -> Hermes / Codex / 其他 Agent Runtime
```

Model Gateway 用于传统的一次性模型请求。Agent Gateway 用于拥有 Session、Memory、Skills 和工具的真实 Agent。

## MVP 边界

- 当前固定本地单用户，但接口保留 `X-User-Id`，默认值为 `local-user`。
- 不实现多租户权限、公共 Mod 市场或跨设备事件网络。
- 不复制 Hermes 的完整对话记录。
- 不让基座替 Hermes 选择模型。
- 不通过截图或浏览器自动化读取 Mod；传给 AI 的页面信息来自 ViewSpec 语义数据和服务端 Snapshot。

## Model Gateway

接口：

- `GET /api/model/providers`：列出可用模型适配器。
- `POST /api/model/responses`：执行传统模型请求并同步返回结果。

请求可以指定 `adapter` 和 `model`。未指定时使用服务端默认值。API Key、Base URL 等连接信息只保存在服务端。

Model Gateway 不创建 Agent Task，也不创建或更新 Agent Session。

## Agent Gateway

保留异步 Task 与 SSE 事件接口：

- `POST /api/agent/tasks`
- `GET /api/agent/tasks/{taskId}`
- `GET /api/agent/tasks/{taskId}/events`
- `POST /api/agent/tasks/{taskId}/cancel`

第一版真实适配器为 `hermes-webui`。VibeDesk 调用 Hermes WebUI 的现有接口：

1. 首次使用 Mod 时调用 `POST /api/session/new`。
2. 保存 `(userId, agentId, moduleId) -> upstreamSessionId` 映射。
3. 调用 `POST /api/chat/start` 开始一次 Agent Turn。
4. 读取 `GET /api/chat/stream?stream_id=...` 的 SSE 结果。
5. 下一次调用同一 Mod 时继续使用同一个 Hermes Session。

映射表只保存上游 Session ID 和时间，不保存 Hermes 全量消息。

## Mod 调用

Mod Action 使用 `gatewayMode` 明确选择链路：

```json
{
  "gatewayMode": "model",
  "prompt": "解释当前市场行情",
  "modelAdapter": "openai-compatible",
  "model": "gpt-5.6"
}
```

或：

```json
{
  "gatewayMode": "agent",
  "prompt": "解释当前市场行情",
  "agentAdapter": "hermes-webui"
}
```

Market Pulse Mod 第一版提供“模型 / Agent”切换。模型模式返回一次性答案；Agent 模式返回异步任务，并持续复用该 Mod 对应的 Hermes Session。

## 验收

- 原 OpenAI-compatible 调用从 Agent Gateway 迁入 Model Gateway。
- 连续两次 Agent 模式调用只创建一个 Hermes Session。
- Model 模式不写入 Agent Session 映射，也不创建 Agent Task。
- Hermes 请求中不传入 Model Gateway 的模型配置。
- 前端清楚显示当前使用“模型”还是“Agent（长期上下文）”。
- 单元测试、类型检查、构建和 E2E 不回归。
