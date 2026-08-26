# chatlog-1 深入分析（chatlog_alpha 代码库）

> 范围说明：本分析基于当前工作区代码（`/Volumes/PSSD/Projects/chatlog_alpha`）。该仓库的 `go.mod` 模块名仍为 `github.com/sjzar/chatlog`，代码整体定位为 **Windows + 微信 4.x** 的聊天记录解密、查询与本地 HTTP/MCP 服务。

## 1. 项目定位（What / Why）

- **目标问题**：从运行中的微信进程获取数据库/图片密钥 → 解密加密 SQLite 数据库 → 提供 TUI/HTTP/MCP 查询与导出能力（含 ChatLab 标准化导出）。
- **主要使用者**：
  - 普通用户：用 TUI 一键获取密钥、解密数据库、启动本地 HTTP 控制台。
  - 开发者/AI：通过 MCP tools + HTTP API 拉取消息、分析、导出。

## 2. 构建与发布（Build / Release）

- Go 版本：`go 1.24.0`（见 `go.mod`）。
- 目标平台：`windows/amd64`（见 `Makefile`、`.goreleaser.yaml`）。
- 关键依赖：
  - `github.com/mattn/go-sqlite3`（CGO）
  - `github.com/gin-gonic/gin`（HTTP API）
  - `github.com/mark3labs/mcp-go`（MCP server）
  - `github.com/klauspost/compress/zstd`（消息内容解压）
- 发布：`.goreleaser.yaml` 仅配置 Windows amd64，并支持 UPX 压缩。

## 3. 代码结构与职责边界（Module Map）

- 入口
  - `main.go`：设置标准库 log flag，调用 `cmd/chatlog.Execute()`。
  - `cmd/chatlog/root.go`：cobra root 命令；默认进入 TUI 模式（`internal/chatlog.Manager.Run`）。
- UI（TUI）
  - `internal/chatlog/app.go`：tview 应用；定时刷新进程状态/菜单状态；菜单触发“获取密钥/解密/启停 HTTP/自动解密”等动作。
  - `internal/ui/*`：具体组件（menu/infobar/footer/form/help/style）。
- 服务编排（应用核心）
  - `internal/chatlog/manager.go`：统一编排 `wechat`/`database`/`http` 服务；同时提供 CLI 子命令入口（`CommandKey`/`CommandDecrypt`/`CommandHTTPServer`）。
  - `internal/chatlog/ctx/context.go`：运行时状态 + 历史配置（账号/目录/密钥/HTTP 开关等）。
- WeChat 进程/密钥/解密
  - `internal/wechat/process/*`：进程检测（V4 通过 `session.db` 推导 `DataDir`、账号名等）。
  - `internal/wechat/key/*`：密钥提取（优先 DLL 注入方式，失败回退原生内存扫描）。
  - `internal/wechat/decrypt/*`：数据库解密（Windows v4：PBKDF2 + AES/HMAC 校验）。
- 数据访问（解密后 DB 的读取层）
  - `internal/wechatdb/wechatdb.go`：聚合 `datasource` + `repository`。
  - `internal/wechatdb/datasource/v4`：按 V4 表结构读取消息/联系人/群/媒体/朋友圈；管理多库与 watcher。
  - `internal/wechatdb/repository/*`：做“显示名/群成员名”等 enrich、昵称→ID 解析等。
- HTTP / MCP
  - `internal/chatlog/http/service.go`：Gin server + MCP server 初始化（SSE/Streamable）。
  - `internal/chatlog/http/route.go`：`/api/v1/*`、`/image|video|file|voice/*`、`/data/*` 等路由与导出逻辑（json/csv/xlsx/chatlab/plain）。
  - `internal/chatlog/http/mcp.go`：注册 MCP tools/prompts/resources，并实现订阅推送监控逻辑。
- 工具与基础设施
  - `pkg/util/*`：时间解析、列表解析、ZSTD、音频 silk、dat 图片解密等。
  - `pkg/util/dat2img/*`：V4 图片 `.dat` 的 AES+XOR 解密与类型识别（含 XOR key 扫描）。
  - `pkg/filemonitor`、`pkg/filecopy`：文件监控与 Windows 下临时拷贝读取（规避锁占用）。
- 可能的遗留/未使用模块
  - `internal/mcp/*`：自研 MCP SSE/JSONRPC 实现，当前代码路径未被引用（可能是历史遗留）。

## 4. 核心链路（从输入到输出）

### 4.1 TUI 启动链路

1. `main.go` → `cmd/chatlog/root.go` → `internal/chatlog.Manager.Run`
2. `ctx.New()` 加载 TUI 配置与历史账号信息
3. 初始化服务对象：`wechat.NewService` + `database.NewService` + `http.NewService`
4. 启动 `internal/chatlog.App.Run()`（阻塞），内部 ticker 每秒刷新一次状态

### 4.2 获取密钥（DataKey / ImgKey）

- 入口：
  - TUI：`internal/chatlog/app.go` 菜单项 → `Manager.GetDataKey()` / `Manager.GetImageKey()`
  - CLI：`chatlog key` → `Manager.CommandKey(...)`
- 关键实现：
  - `internal/wechat/wechat.go`：`Account.GetKey()` 做“已有密钥复用 / 缺图钥补全 / 走 Extractor”。
  - `internal/wechat/key/extractor.go`：`NewExtractor()` 优先 `NewDLLExtractor()`（`wx_key.dll` 可用则启用），否则回退 `windows.NewV4Extractor()` 原生扫描。
  - `internal/wechat/key/windows/dll_extractor.go`：调用 DLL 导出函数（见 `dll调用指南.md`），并行执行：
    - DLL 轮询获取 DataKey/ImgKey
    - 原生扫描补 ImgKey（等待 `DataDir` 就绪后启动）

### 4.3 解密数据库（encrypted DataDir → decrypted WorkDir）

- 入口：
  - TUI：菜单“解密数据”
  - CLI：`chatlog decrypt`
  - Server 模式：`chatlog server` 在 WorkDir 为空或 DB 启动失败时会触发解密
- 核心逻辑：
  - `internal/chatlog/wechat/service.go`：`DecryptDBFile(s)` 按相对路径将 `.db` 解密输出到 WorkDir（临时文件 `.tmp` 落盘后 rename）。
  - `internal/wechat/decrypt/windows/v4.go`：按 SQLite page 解密与 HMAC 校验；密钥派生 PBKDF2（iter=256000）。

### 4.4 查询消息与“多库/多 talker”策略

- HTTP：`GET /api/v1/chatlog`
  - `internal/chatlog/http/route.go` → `database.Service.GetMessages()` → `wechatdb.DB.GetMessages()` → `repository.GetMessages()` → `datasource/v4.GetMessages()`
- V4 数据源要点（`internal/wechatdb/datasource/v4/datasource.go`）：
  - message_*.db 通过 `Timestamp` 表定位起始时间，按时间排序后形成 `[StartTime, EndTime)` 区间，查询时按时间范围挑选 DB。
  - Msg 表名：`Msg_{md5(talker)}`；支持 talker 逗号分隔的多会话查询。
  - 过滤策略：sender/keyword（keyword 为 Go 层正则，匹配 `PlainTextContent()`），非 SQL 层过滤。
  - ZSTD：消息 `message_content` 可能是 ZSTD 压缩；Wrap 时解压（`internal/model/message_v4.go`），数据库浏览器 `/db/data` 对 message_content 字段也做自动解压。
- Repository enrich（`internal/wechatdb/repository/message.go`）：
  - 群聊：补群名、补群成员显示名
  - 私聊：补联系人显示名

### 4.5 媒体访问与解密（图片/语音/文件/视频）

- 路由：`/image/*key`、`/video/*key`、`/file/*key`、`/voice/*key`、`/data/*path`
- 关键策略（`internal/chatlog/http/route.go`）：
  - 优先通过 DB（hardlink 等表）找媒体记录；失败则走 md5→path 缓存与目录递归搜索（图片）。
  - `.dat`（或无后缀）文件：使用 `pkg/util/dat2img` 解密/识别并可选落盘缓存，再通过 `/data/` 访问。
  - V4 dat 解密：AES(ImgKey) + XOR(XorKey)；XorKey 可通过扫描 `_t.dat` 推导（`dat2img.ScanAndSetXorKey`）。

### 4.6 MCP（AI Agent 接入）

- 服务端：`internal/chatlog/http/mcp.go` 基于 `mcp-go` 注册 tools/prompts/resources，并通过：
  - `/mcp`（streamable http）
  - `/sse` + `/message`（SSE）
- 订阅推送：`startMCPMessageMonitor()` 每 30 秒拉取增量消息并 POST 到 webhook。

## 5. 关键风险点与改进建议（按优先级）

1. 路径穿越/任意文件读取风险（HTTP `/data/*path`）
   - `internal/chatlog/http/route.go` 的 `handleMediaData` 使用 `filepath.Clean(c.Param("path"))` 后直接 `filepath.Join(dataDir, relativePath)`。
   - 由于 `*path` 参数天然带前导 `/`，`Clean` 后可能变成绝对路径，导致 `Join` 忽略 `dataDir`，从而读取宿主机任意路径文件。
2. 非 Windows 构建失败
   - `internal/wechat/key/windows/dll_extractor.go` 直接导入 `golang.org/x/sys/windows`，但文件名未带 `_windows.go` 且无 `//go:build windows`，导致在 darwin 下 `go test ./...` 直接失败。
3. talker 解析疑似变量误用
   - `internal/wechatdb/repository/message.go`：`parseTalkerAndSender` 中 `GetChatRoom(ctx, talker)` 看起来应为 `GetChatRoom(ctx, talkers[i])`，会影响“用群名称/备注名当 talker”时的解析。
4. 媒体回退逻辑对视频不完整
   - md5→path 缓存与 `tryFindFileWithSuffixes` 的 suffix 主要面向图片（`.dat/_h/_t`），若视频 DB 记录缺失，回退可能找不到 `.mp4`。
5. 性能与稳定性
   - `/api/v1/chatlog` 的 keyword 为 Go 层正则过滤：在大时间范围/高并发下可能成为瓶颈。
   - `/db/data` 的 keyword 查询会对表的所有列拼 `LIKE` 条件，可能导致慢查询。
6. 安全/隐私默认值
   - server 模式默认监听 `0.0.0.0:5030`（见 `internal/chatlog/conf/server.go`），若用户在公网/局域网暴露端口可能泄露敏感数据；建议默认改为 `127.0.0.1` 或提供鉴权/白名单提示。

## 6. 建议的“下一步深入”清单

- 代码层修正（小改动高收益）：
  - 补齐 `dll_extractor.go` 的 Windows build 约束，使非 Windows 能跑 `go test ./...`（至少对纯逻辑包）。
  - 修正 talker 解析变量误用，并补一个单元测试覆盖“昵称/群名→ID”的转换。
- 分析/文档层：
  - 产出“关键流程时序图”（Key 获取/DB 解密/HTTP 查询/MCP 订阅），便于维护与二开。
