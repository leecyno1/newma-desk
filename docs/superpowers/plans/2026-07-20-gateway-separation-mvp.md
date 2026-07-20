# Gateway 分离 MVP 实施计划

## 1. 建立 Model Gateway

- 新建 Model 请求、结果、适配器协议、注册表、服务和路由。
- 将 OpenAI-compatible 实现从 Agent Gateway 迁入 Model Gateway。
- 支持请求级 `adapter` 与 `model` 选择，密钥仍只在服务端。

## 2. 接入 Hermes Agent

- Agent 请求增加本地用户标识。
- 新增 `agent_module_sessions` 映射表。
- 新增 Hermes WebUI Adapter，调用 Session、Chat Start 和 Chat Stream 接口。
- 上游 Session 失效时仅重建一次并更新映射。
- 取消 Agent Task 时同步取消 Hermes Stream。

## 3. 拆分 Module SDK

- 保留兼容的 Gateway Client。
- 新增独立 Model Client 和 Agent Client，避免概念继续混用。

## 4. 更新 market-daily

- 增加“模型 / Agent”模式切换。
- 两种模式继续使用同一个 `market.explain` 能力和同一份服务端 Snapshot。
- Agent 模式展示长期上下文提示，Model 模式展示一次性调用提示。

## 5. 验证

- Fake Model 验证 Model 模式不触发 Agent。
- Fake Hermes 验证同一用户、同一 Agent、同一 Module 连续调用复用 Session。
- 验证不同 Module 或不同用户不会共享 Session。
- 运行全部后端、前端、构建、类型检查和 E2E。
