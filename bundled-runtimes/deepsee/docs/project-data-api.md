# Deepsee 项目数据 API v1

## 定位与范围

供研究助手、知识库、内部看板等项目读取 Deepsee 已保存的数据。Newma-Desk 内嵌版和独立浏览版共用同一后端，不需要分别适配。

- 本机地址：`http://127.0.0.1:8001/api/v1`
- 每个项目独立 Bearer 密钥、资源权限和请求限额。
- 仅 GET，只读取已有数据；请求不会同步微信、抓取网站、调用模型、群发消息或修改标签。
- 不导出设备密钥、邮箱密码、原始协议 XML、内部配置或本地文件路径。授权读取的正文和联系人信息本身仍属于敏感业务数据。
- 现有 `/api/*` 页面接口和 `/api/agent/*` 保持兼容；新项目应依赖 `/api/v1/*`。

当前 API 版本为 1.1.0。没有配置任何项目时返回 503；已配置项目但密钥无效时返回 401，不对匿名调用开放数据。

## 1. 配置项目

推荐在本机页面 **功能设置 → 开发者中心** 创建项目，勾选资源权限并设置每分钟额度。完整密钥只显示一次；数据库仅存密钥摘要。可以编辑权限、停用/启用项目、轮换密钥，立即生效，不必重启服务。轮换不会自动启用已停用项目。

开发者中心只接受本机同源请求，并检查来源与管理请求头；它不是远程管理员认证方案。禁止通过反向代理开放 `/api/developer/*`。启用全站 API 鉴权时，管理接口也受该鉴权保护。

也兼容在**实际运行副本**的环境变量或 `.env` 中设置（JSON 放在同一行）：

```dotenv
DATA_API_CLIENTS='{"research":{"token":"REPLACE_WITH_RANDOM_SECRET","scopes":["messages:read","contacts:read","chats:read","news:read"],"requests_per_minute":120},"knowledge":{"token":"REPLACE_WITH_ANOTHER_SECRET","scopes":["mp:read","meetings:read"],"requests_per_minute":60}}'
DATA_API_TIMEZONE=Asia/Shanghai
```

示例占位符必须换成不同的随机密钥，至少 24 个字符。可在可信终端运行 `python -c 'import secrets; print(secrets.token_urlsafe(32))'` 为每个项目生成密钥。不要将密钥写进代码、浏览器前端、URL 或 Git。

当前 Desk 使用的副本为 `newma-desk/bundled-runtimes/deepsee`；只改开发仓库的 `.env` 不会自动配置该副本。修改配置后重启对应 Deepsee 服务。轮换密钥时替换该项目 token；撤销时移除项目配置。

权限为**资源级**：例如 `messages:read` 能读取本实例内全部微信消息，不是只读某个群聊或某个微信账号。查询参数不是权限边界。需要严格账号/群聊隔离的项目，暂时使用独立实例，不应共享同一权限密钥。

限流按项目计算，默认 120 次/分钟，当前为单进程内滑动窗口；多 worker 部署需在网关统一限流。

## 2. 接口清单

所有接口均使用 `Authorization: Bearer <项目密钥>`。

| GET 路径（省略 `/api/v1`） | 权限 | 功能与参数 |
| --- | --- | --- |
| `/capabilities` | 有效项目密钥 | 返回当前项目可读资源、版本、限流额度 |
| `/openapi.json` | 有效项目密钥 | 独立 OpenAPI 契约，含全部 v1 资源定义；实际权限由 capabilities 和服务端校验决定 |
| `/messages` | `messages:read` | 微信消息；`limit,cursor,after_id,q,chat_id,sender_id,since,until` |
| `/messages/{message_id}` | `messages:read` | 单条消息 |
| `/contacts` | `contacts:read` | 联系人备注、昵称、原标签名、标签 ID；`limit,cursor,q` |
| `/contacts/{contact_id}` | `contacts:read` | 单个联系人；ID 需要 URL 编码 |
| `/labels` | `contacts:read` | 标签名称缓存、标签成员计数、缓存时间 |
| `/chats` | `chats:read` | 会话名称与群聊标识；`limit,cursor,q` |
| `/emails` | `emails:read` | 邮件正文与已有摘要；`limit,cursor,after_id,q` |
| `/emails/{email_id}` | `emails:read` | 单封邮件，不含邮箱认证配置 |
| `/articles?source=news` | `news:read` | 本地新闻快照；`limit,offset,q` |
| `/articles?source=media` | `media:read` | 本地自媒体内容；`limit,offset,q` |
| `/articles?source=mp` | `mp:read` | 本地公众号内容；`limit,offset,q` |
| `/meetings` | `meetings:read` | 本地会议文字/已有转写；`limit,offset,q` |
| `/search` | 所选来源对应权限 | 跨来源字面搜索；`q,sources,limit,offset`，结果按来源分组 |
| `/contacts/{contact_id}/scorecard` | `scores:read` | 已落库评分、独立样本量、标的/基准价格与回测结果；`limit,offset` 分页观点 |
| `/messages/{message_id}/attachment` | `messages:read` + `attachments:read` | 下载已保留的本地 Chatlog 媒体，不触发微信下载 |

列表 `limit` 默认 100，范围 1–200。搜索和评分默认 20、最多 100。`q` 为字面子串搜索，不是向量检索。

`search` 的 `sources` 为逗号分隔的 `messages,contacts,chats,emails,news,media,mp,meetings`；省略时仅查询已授权来源，显式指定未授权来源返回 403。各组独立分页，不做全局相关性排序；搜索 offset 最大 1000。快照来源仍只有本地 1000 条窗口，不因此成为完整历史库。

评分接口只导出结构化证据，不附带原始消息正文、内部元数据或实时调用行情。`accuracy_score` 等无有效已验证样本时为 null，不能把联系人旧字段 `rating=50` 当成已验证成绩。`evidence.status` 标识未评分/等待验证/样本有限/样本较充分；`as_of` 表示已保存评分的时间，可能落后于新入库观点。

## 3. 返回格式与字段

列表返回 `data` 和 `meta`，详情返回 `data`。下面是虚构示例（省略部分字段）：

```json
{
  "data": [{
    "id": 123,
    "source": "wechat",
    "chat_id": "example-room@chatroom",
    "chat_name": "示例研究群",
    "sender_id": "example-contact",
    "sender_name": "张老师（备注）",
    "occurred_at": "2026-10-15T01:00:00Z",
    "type": "text",
    "text": "示例消息正文",
    "summary": "已生成的摘要"
  }],
  "meta": {
    "limit": 100,
    "has_more": false,
    "next_cursor": null,
    "next_offset": null,
    "last_id": 123,
    "coverage": "database",
    "truncated": false,
    "warnings": []
  }
}
```

- 联系人/消息显示名优先使用备注名，其次昵称或已有会话名，最后才回退 ID。没有同步到名称时，不会凭空生成名字。
- 图片、语音等原始 XML 不透传；可读正文可能是 `[image]` 等占位符。`attachment_path` 表示记录指向可尝试读取的本地媒体，不保证文件仍存在。下载要求双权限，未留存返回 404，媒体服务异常返回 502；不返回底层路径或微信密钥。不支持任意 URL 代理，也不保证补齐缺失历史图片。
- `summary` 是已保存的摘要，可能为空，不保证 AI 已处理或内容已核验。
- 标签接口返回 `data` 列表以及 `name_source/account_id/names_cached_at`。上游无法返回名称时使用本地原名称缓存；未知名称为 null，不修改微信标签名称。
- 内容资源使用 `source:identifier` 形式的 ID；只在对应实例/来源中使用，不应当作全球唯一 ID。会议文件修改可能改变 ID，自媒体链接变化也可能改变 ID。
- 时间统一为 RFC3339 UTC，未知为 null。旧库无时区值按 `DATA_API_TIMEZONE` 解释（默认上海时间）；若旧数据混用多个时区，应先清洗，API 无法推断其原始时区。
- 微信 `since` 为包含边界，`until` 为不包含边界，均必须含时区，例如 `2026-10-15T00:00:00+08:00`。用 URL 查询参数传递时注意编码 `+`。

## 4. 分页与增量同步

### 数据库资源

消息、邮件按数值 ID 升序；联系人、会话按字符串 ID 升序。首次请求不带 cursor；当 `has_more=true`，把 `next_cursor` 原样传给下一页，并保持搜索/筛选条件不变。cursor 是不透明值，不要解析或修改；不能与 after_id 同时传递。

微信/邮件可以用 `after_id` 获取之后**新入库**的记录，历史消息晚到也能读到。接入项目应：

1. 初次从 `after_id=0` 开始，按页接收。
2. 在自己的数据库中按 `实例 + 资源 + id` 幂等写入，成功后保存该页 `meta.last_id`。
3. 下次以保存的 ID 请求；空结果保留原进度，稍后再次读取。

这是“新增记录轮询”，不是变更日志：已有消息的新摘要、联系人改备注、删除操作不会产生新 ID。联系人和标签需要定期重新读取；需要更新/删除同步的场景暂时定期全量对账。更换/恢复数据库、清空数据或重用 ID 后也必须重置接入端进度。不要把按时间排序的消息时间当作增量进度。

### 本地快照资源

新闻、自媒体、公众号、会议用 offset 分页，按时间与 ID 倒序，每次查询最多查看本地保留窗口的 1000 条。`meta.coverage=local_snapshot`，`warnings` 会提示 `local_snapshot_only`，达到截断条件时还会提示窗口限制。

本地采集器可能只保留部分日期或部分来源；空列表表示没有读到本地记录，**不代表上游健康或全网无结果**。窗口内搜索不等于历史全库搜索。多次分页期间快照可能变化，消费端需按 ID 去重；没有快照锁定与完整历史导出保证。

## 5. 调用示例

由调用方后端设置 `DEEPSEE_API_BASE=http://127.0.0.1:8001/api/v1` 与 `DEEPSEE_API_KEY`。

```sh
curl --fail-with-body \
  -H "Authorization: Bearer $DEEPSEE_API_KEY" \
  "$DEEPSEE_API_BASE/capabilities"

curl --fail-with-body --get \
  -H "Authorization: Bearer $DEEPSEE_API_KEY" \
  --data-urlencode 'q=半导体' --data-urlencode 'limit=50' \
  "$DEEPSEE_API_BASE/messages"
```

Python：完成一轮新增消息读取（`save_page_and_checkpoint` 由接入项目实现，数据与进度应在同一事务保存）：

```python
import os
import requests

def pull_new_messages(after_id, save_page_and_checkpoint):
    base = os.environ["DEEPSEE_API_BASE"].rstrip("/")
    headers = {"Authorization": "Bearer " + os.environ["DEEPSEE_API_KEY"]}
    while True:
        response = requests.get(
            base + "/messages", headers=headers,
            params={"after_id": after_id, "limit": 200}, timeout=30,
        )
        response.raise_for_status()  # 429 时由任务调度器按 Retry-After 延迟重试
        page = response.json()
        if page["data"]:
            after_id = page["meta"]["last_id"]
            save_page_and_checkpoint(page["data"], after_id)
        if not page["meta"]["has_more"]:
            return after_id
```

Node.js 后端：

```javascript
const base = process.env.DEEPSEE_API_BASE.replace(/\/$/, "");
const response = await fetch(`${base}/contacts?limit=100`, {
  headers: { Authorization: `Bearer ${process.env.DEEPSEE_API_KEY}` },
  signal: AbortSignal.timeout(30000),
});
if (!response.ok) throw new Error(`Deepsee HTTP ${response.status}`);
const page = await response.json();
// 使用 page.data；如 page.meta.has_more，为下一次请求传入 next_cursor。
```

可用 `/openapi.json` 生成 Python/TypeScript 等客户端；新增可选字段属于兼容更新，删除字段或改变语义需新版本。

### CLI

无需额外安装依赖，用 Python 3.11+ 运行仓库内 `scripts/deepsee.py`。先在调用方安全设置 `DEEPSEE_API_KEY`，可选设置 `DEEPSEE_API_BASE`，默认本机地址。

```sh
python scripts/deepsee.py capabilities
python scripts/deepsee.py search "半导体" --sources messages,news --limit 20
python scripts/deepsee.py messages --after-id 0 --limit 200
python scripts/deepsee.py contacts --q "备注"
python scripts/deepsee.py scorecard CONTACT_ID
python scripts/deepsee.py articles --source news
python scripts/deepsee.py attachment MESSAGE_ID --output ./saved-image
```

CLI 输出 JSON，不直接访问数据库；错误走标准错误并返回非零退出码。分页按响应 cursor/last_id/next_offset 继续，没有自动全库导出。附件不覆盖已存在文件。远程服务必须 HTTPS，客户端拒绝重定向以免密钥泄漏。

## 6. 错误与安全部署

已定义路由的错误格式为 `{"error":{"code":"insufficient_scope","message":"insufficient scope","request_id":"..."}}`。

| 状态 | 含义 |
| --- | --- |
| 401 | 未提供或无效密钥 |
| 403 | 项目无该资源权限 |
| 404 | 记录不存在 |
| 422 | 参数、时间范围或分页游标不合法 |
| 429 | 超过项目限额；按 `Retry-After` 秒后重试 |
| 500 | 数据源读取失败，可提供 `X-Request-ID` 排查 |
| 502 | 本地附件服务异常、类型不支持或重定向不安全 |
| 503 | 未配置项目或项目配置不合法 |

成功响应带 `X-RateLimit-Limit`、`X-RateLimit-Remaining`、`X-RateLimit-Reset-After`。路由响应带 `X-Request-ID` 和 `Cache-Control: no-store`。不存在的路径/不支持的 HTTP 方法仍采用框架默认 404/405 格式。

`127.0.0.1` 只供同机调用；容器或其他电脑的 localhost 不是这台机器。本次没有开放公网或修改防火墙。跨机器调用建议通过 VPN 或 HTTPS 网关，并仅放行 `/api/v1/`。

**新项目密钥不保护旧接口。** 不要直接把整个 8001 端口暴露到公网；旧 `/api/*`、管理页面、Agent 网关、静态文件各有自己的访问策略。若必须开放它们，需单独审查并正确配置鉴权。项目密钥应放在调用项目的后端，前端通过自己的后端访问。

开发者中心显示已认证项目最近调用：项目 ID、路由模板、状态码、UTC 时间和请求编号，不记录查询参数/正文/密钥。日志随调用清理超过 30 天的记录；未认证请求不归入项目日志。当前请求额度为单进程限制，不是计费或持久化用量系统。

## v1.1 验证

全套隔离测试 603 项通过，API 专项 29 项通过；运行副本专项也通过。开发者中心已部署，两种界面共用；正式实例未创建接入密钥，仍默认拒绝匿名读取。详见 `docs/2026-10-16-developer-platform.md`。

## 初版验证记录（v1.0）

- 开发仓库全套回归：551 项通过；运行副本新增 API 回归：11 项通过。
- 对实际 SQLite 使用只读连接验证了 10 个资源请求，均返回 200；标签返回 24 项，邮件和会议当时无本地记录。
- 已同步本轮代码到 Desk 内置 Deepsee 并重载后端；未配置项目密钥时实际接口返回 `503 data_api_not_configured`，没有匿名数据访问。
- 没有新增真实项目密钥、开放公网、执行真实群发或修改标签。全套测试退出时出现已有 Hermes 502 日志，外部模型联通不属于本次 API 验证结果。

## 后续扩展（尚未实现）

- 账号/群聊白名单与行级授权。
- 统一持久化内容索引、语义搜索、完整历史导出。
- 基于变更日志的 `changes` 接口与带签名 Webhook，覆盖更新/删除。
- 跨设备管理员认证、多进程统一限流、按需下载尚未留存的附件。

这些功能不包含在当前 v1 契约中，接入方不要假定已可用。
