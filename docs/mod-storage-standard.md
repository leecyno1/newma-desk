# Newma-Desk MOD Storage Standard 1.0

MOD Storage Standard 定义 Mod 如何声明、访问、升级和清理持久化数据。它标准化的是存储 Interface，而不是数据库产品或物理表结构。

## 1. 目标

- 简单 Mod 无需自建数据库、端口和账号。
- 本地 SQLite 与云端 PostgreSQL 对 Mod 保持同一 Interface。
- 用户、工作区、Mod 和 namespace 默认隔离。
- 复杂领域数据继续保留独立存储，避免公共数据库膨胀。
- 安装、升级、卸载、备份和迁移行为可以自动检查。

## 2. 存储模式

| mode | 用途 | 规则 |
| --- | --- | --- |
| `stateless` | 无持久化页面 | 不得调用 Storage API |
| `desk-managed` | 设置、笔记、筛选器、小型业务文档 | 通过 Desk Storage API 读写 JSON 文档 |
| `dedicated` | 交易、回测、搜索索引等复杂关系数据 | 使用声明的独立 Adapter，不得直接访问 Desk 主库 |
| `artifact` | HTML、图表、报告和其他大对象 | 使用 Artifact Interface，不写入文档数据库 |

第一版运行实现支持 `desk-managed`。其他模式用于明确数据边界，并由对应 Interface 或 Adapter 承载。

## 3. Manifest 声明

`storage` 只允许出现在 Manifest 1.1 中。

Suite 页面可以在 `pages[].manifest.storage` 中声明自己的 namespace；Suite Compiler 必须把该字段和页面级 `storage.read` / `storage.write` 权限一起编译到最终 Mod Manifest。不同页面不会因为属于同一 Suite 而自动共享 namespace。

```json
{
  "schemaVersion": "1.1",
  "id": "research-notes",
  "permissions": ["storage.read", "storage.write"],
  "storage": {
    "mode": "desk-managed",
    "namespaces": [
      {
        "id": "settings",
        "scope": "user-workspace",
        "schemaVersion": 1,
        "quotaMb": 2,
        "maxItemKb": 128
      },
      {
        "id": "notes",
        "scope": "user-workspace",
        "schemaVersion": 1,
        "quotaMb": 20
      }
    ]
  }
}
```

约束：

- namespace ID 在一个 Mod 内必须唯一。
- `desk-managed` 必须声明 `storage.read` 和 `storage.write`。
- `scope` 第一版固定为 `user-workspace`。
- 单 namespace 最大配额为 100MB；单文档默认上限为 256KB。
- Mod 不得声明数据库 URL、账号、密码、物理表名或宿主机路径。

## 4. Desk Storage API

所有请求必须携带 Desk 签发的 Mod Session：

```http
Authorization: Bearer <mod-session-token>
X-Newma-Desk-Instance-Id: <instance-id>
```

标准资源：

```text
GET    /api/mods/{modId}/storage/{namespace}
GET    /api/mods/{modId}/storage/{namespace}/{key}
PUT    /api/mods/{modId}/storage/{namespace}/{key}
DELETE /api/mods/{modId}/storage/{namespace}/{key}?expectedRevision={revision}
```

写入请求使用乐观锁：

```json
{
  "expectedRevision": 0,
  "value": {
    "layout": "compact"
  }
}
```

- 新建文档时 `expectedRevision` 为 `0`。
- 更新时必须传当前 revision。
- revision 不一致返回 `409 Conflict`。
- 未声明 namespace 或权限不足返回 `403 Forbidden`。
- 单文档或 namespace 超过配额返回 `413 Content Too Large`。

## 5. 隔离与安全

Desk 根据 Mod Session 固定以下维度，Mod 不能通过请求参数覆盖：

```text
user_id + workspace_id + mod_id + namespace + key
```

- 禁止跨用户、跨工作区、跨 Mod 直接读取。
- 禁止保存 API Token、Cookie、密码、券商凭据和私钥；密钥必须进入 Desk Secret Interface。
- 新闻、行情和财务数据通过 Data Service 获取，不应在每个 Mod 重复持久化。
- HTML、图片、PDF、压缩包和大型时间序列进入 Artifact Interface。
- 外部文本始终视为不可信数据。
- 研究历史等轻量索引只保存报告 ID、状态、时间、质量与覆盖率；原始行情、财务明细、新闻正文和完整报告不得重复写入 Mod Storage。

## 6. Schema 与升级

- `schemaVersion` 属于 namespace，而不是整个数据库。
- Desk 返回每条文档写入时的 Schema 版本。
- Mod 升级 Schema 后必须能读取旧版本并显式迁移。
- 禁止安装或启动时执行不可逆的破坏性迁移。
- 降级时不能静默覆盖更高版本数据。

## 7. 生命周期

- 安装：只注册声明，不预建 Mod 自定义表。
- 升级：保留文档和 revision，由 Mod 执行显式迁移。
- 禁用：保留数据，不再授予新会话。
- 卸载：默认保留数据；清理必须由用户确认。
- 导出：按用户、工作区和 Mod 输出带版本的 JSON 包。

## 8. 部署 Adapter

- 本地和单服务器默认使用 SQLite Adapter。
- 多用户、多 API 实例部署使用 PostgreSQL Adapter。
- Mod SDK 不得因 Adapter 切换而修改业务代码。
- Redis、消息队列和分布式数据库不属于第一版依赖。

## 9. 接入验收

兼容性测试至少验证：

1. Manifest 声明合法且 namespace 唯一。
2. 未授权请求被拒绝。
3. 用户、工作区和 Mod 数据互不可见。
4. revision 冲突不会覆盖数据。
5. 单文档和 namespace 配额有效。
6. 列表分页稳定。
7. 禁用或升级后数据生命周期符合声明。

## 10. Desk 共享领域数据

跨多个 Mod 使用、且需要统一业务语义的小型结构化数据，应优先由 Desk 提供共享领域 API，而不是每个 Mod 分别写入 `localStorage` 或创建自有数据库。

当前标准能力包括：

| 能力 | 标准接口 | 存储边界 |
| --- | --- | --- |
| 自选分组 | `/api/watchlists` | `user_id + workspace_id` |
| 价格预警 | `/api/market-alerts` | `user_id + workspace_id` |

共享领域 API 的约束：

- 复用 Desk 主数据库 Adapter，不新增端口、进程或常驻线程。
- 所有读写必须按 `X-User-Id` 与 `X-Workspace-Id` 隔离。
- Mod 内手动操作和 Agent Action 必须调用同一接口，禁止维护两份状态。
- 价格预警第一版只保存规则；行情触发监控由未来统一 Scheduler 承担，Mod 不得自行启动轮询守护进程。
- 大型历史行情、回测明细和新闻正文仍通过 Data Service 或 Artifact Interface 获取，不进入共享领域表。
