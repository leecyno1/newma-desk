# Agent API Gateway

本项目新增统一 Agent 网关接口，目标是让其他 Agent 不需要了解前端细节，即可发现并调用全部后端 API 能力。

## Base

- `GET /api/agent/health`
- `GET /api/agent/capabilities`
- `GET /api/agent/modules`
- `GET /api/agent/openapi`
- `GET /api/agent/policy`
- `POST /api/agent/invoke`
- `POST /api/agent/invoke-batch`
- `POST /api/agent/policy`

## 鉴权（可选启用）

当配置了 `AGENT_API_TOKEN` 或 `AGENT_API_TOKENS` 后，`/api/agent/*` 全部接口将要求 token。

- Header 方式 1: `Authorization: Bearer <token>`
- Header 方式 2: `X-Agent-Token: <token>`

环境变量：

```bash
# 单 token
AGENT_API_TOKEN=change-me

# 多 token（逗号分隔）
AGENT_API_TOKENS=token-a,token-b

# 可选：路径白名单/黑名单（前缀匹配，逗号分隔）
AGENT_API_ALLOWLIST=/api/messages,/api/email
AGENT_API_BLOCKLIST=/api/admin
```

未配置上述变量时，网关保持开放模式（兼容本地开发）。

## 1) 能力发现

### `GET /api/agent/capabilities`

返回所有可调用 `"/api/*"` 接口（自动排除 `"/api/agent/*"`），包括：

- method / path
- tags / summary
- query 参数（是否必填）
- 是否有 body

示例：

```bash
curl -sS http://127.0.0.1:8001/api/agent/capabilities \
  -H 'Authorization: Bearer change-me' | jq '.count, .items[0]'
```

## 2) OpenAPI 导出

### `GET /api/agent/modules`

返回按业务模块组织的推荐接口清单，方便 Agent 快速编排工作流（微信聚合、邮件聚合、发送管理、同步、配置等）。

示例：

```bash
curl -sS http://127.0.0.1:8001/api/agent/modules \
  -H 'X-Agent-Token: change-me' | jq
```

## 3) OpenAPI 导出

### `GET /api/agent/openapi`

返回过滤后的 OpenAPI（仅保留 `/api/*`，排除 `/api/agent/*`），便于其他 Agent 自动生成调用器。

示例：

```bash
curl -sS http://127.0.0.1:8001/api/agent/openapi \
  -H 'Authorization: Bearer change-me' | jq '.openapi, (.paths|keys|length)'
```

## 3) 统一调用入口

### `POST /api/agent/invoke`

通过一个统一入口，转调任意现有业务接口。

请求体：

```json
{
  "method": "GET",
  "path": "/api/messages",
  "query": {
    "size": 20,
    "page": 1
  },
  "headers": {},
  "body": null,
  "timeout_ms": 10000
}
```

返回：

- `ok`
- `status_code`
- `duration_ms`
- `path` / `method`
- `data`（目标接口返回内容）

示例：

```bash
curl -sS -X POST http://127.0.0.1:8001/api/agent/invoke \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer change-me' \
  -d '{"method":"GET","path":"/api/mp/articles","query":{"limit":5}}' | jq
```

## 4) 批量调用入口

### `POST /api/agent/invoke-batch`

一次提交多个调用请求，返回逐条执行结果和成功/失败统计，适合其他 Agent 批量拉取模块数据。

请求体：

```json
{
  "requests": [
    {"method": "GET", "path": "/api/messages", "query": {"size": 10}},
    {"method": "GET", "path": "/api/email/messages", "query": {"size": 10}}
  ],
  "stop_on_error": false,
  "max_workers": 4
}
```

示例：

```bash
curl -sS -X POST http://127.0.0.1:8001/api/agent/invoke-batch \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer change-me' \
  -d '{"requests":[{"method":"GET","path":"/api/messages","query":{"size":5}}],"stop_on_error":false}' | jq
```

说明：

- `stop_on_error=true` 时按顺序执行，遇错即停。
- `stop_on_error=false` 时并发执行，线程数由 `max_workers` 控制（1-32）。

## 5) 调用策略（白名单/黑名单）

### `GET /api/agent/policy`

查看当前生效策略（数据库配置 + 环境变量合并后）。

### `POST /api/agent/policy`

写入数据库策略：

```json
{
  "allowlist": ["/api/messages", "/api/email"],
  "blocklist": ["/api/admin", "/api/config/extensions"]
}
```

规则：

- 先命中 `blocklist` 则拒绝（`403`）。
- 若 `allowlist` 非空，必须命中 `allowlist` 才允许。
- 前缀匹配，例如 `/api/messages` 可匹配 `/api/messages/effective`。

## 约束

- `path` 必须以 `/api/` 开头
- 禁止通过 invoke 调用 `/api/agent/*`（防止递归）
- 仅允许 `GET/POST/PUT/PATCH/DELETE`
