# Chatlog 本地兜底链路

Deepsee 的微信引擎采用双轨：

- **主轨道：wechatapi** — 负责实时回调、发送消息和云端部署后的在线链路。
- **兜底轨道：chatlog** — 读取本机微信聊天记录，用于历史补齐和网关异常时的本地恢复。

Chatlog 源码已内置于 `third_party/chatlog/`。构建和 wx-cli 安装方式见
`docs/wechat-local-sources.md`。

## 使用条件

chatlog 只能读取本机微信数据，因此必须满足：

1. 本机已登录并打开微信电脑版。
2. chatlog HTTP 服务可访问，例如 `http://127.0.0.1:5030/api/v1/session`。
3. `.env` 中配置了微信原始数据目录与 chatlog 工作目录：
   - `CHATLOG_DATA_DIR`：微信原始目录，通常是 `.../Documents/xwechat_files/<wxid>`。
   - `CHATLOG_WORK_DIR` / `CHATLOG_DIR`：chatlog 解密后的工作目录。

如果 Deepsee 部署在云服务器，云端无法直接读取用户本机微信文件。推荐架构是：

- 云端 Deepsee 使用 wechatapi 作为主链路。
- 本机 Mac/Windows 运行 chatlog sidecar。
- 本机 sidecar 定时把补齐数据同步到 Deepsee，或通过安全隧道暴露给 Deepsee 使用。

## Windows 适配结论

Deepsee 调用 chatlog 的方式是 HTTP API，因此后端本身不依赖 macOS。Windows 当前不可用的主要原因通常不是 Deepsee 同步逻辑，而是本地缺少可运行的 `chatlog.exe` 服务，或 `.env` 仍沿用 macOS 的 `darwin`、`xwechat_files` 路径。

Chatlog 提供 `/api/v1/session`、`/api/v1/chatlog` 等 HTTP API。Deepsee 已将所用
源码内置到仓库，建议把它作为本机 sidecar 使用：Windows 负责启动 `chatlog.exe`，
Deepsee 只连接 `CHATLOG_HTTP_BASE`。

Windows 使用前请确认：

1. 使用 Windows 微信电脑版，并保持微信已登录。
2. 从仓库内置源码构建 Windows 版 `chatlog.exe`。
3. 使用 Windows Terminal 或 PowerShell 运行，避免 TUI 显示异常。
4. `.env` 中设置：
   - `CHATLOG_BIN=C:\tools\chatlog\chatlog.exe`
   - `CHATLOG_PLATFORM=windows`
   - `CHATLOG_DATA_DIR=C:\Users\<user>\Documents\WeChat Files\<wxid>`
   - `CHATLOG_WORK_DIR=C:\Users\<user>\Documents\chatlog\<wxid>`
   - `CHATLOG_HTTP_BASE=http://127.0.0.1:5030` 或灰度端口 `5031`

Windows 启动与检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 build
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 status
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 start
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 probe
```

如果希望登录 Windows 后自动启动：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 install-task
```

停止或移除自启：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 stop
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 remove-task
```

## macOS 灰度新版 chatlog

项目提供了 sidecar 脚本，不直接替换现有 `5030` 主服务，而是使用 `5031` 做灰度验证。
`build`（兼容别名 `build-v031`）从仓库内置源码构建，不再执行远程 `go install`：

```bash
bash scripts/chatlog_sidecar.sh build
bash scripts/chatlog_sidecar.sh status
bash scripts/chatlog_sidecar.sh start-gray
bash scripts/chatlog_sidecar.sh logs
```

确认 `5031` 稳定后，再考虑把 `.env` 的 `CHATLOG_HTTP_BASE` 切到 `http://127.0.0.1:5031`。

首次启动可能需要二三十秒完成索引与目录扫描，脚本默认最多等待 `45` 秒。探针与日志输出会自动隐藏聊天内容和密钥。

如果需要常驻运行，使用 launchd 保活：

```bash
bash scripts/chatlog_sidecar.sh disable-old-autostart
bash scripts/chatlog_sidecar.sh launchd-install
bash scripts/chatlog_sidecar.sh launchd-status
```

`disable-old-autostart` 会停用旧的 `5030` 自动启动项，避免老版本 `--auto-decrypt` 进程反复拉起。

## 当前建议

- 不建议让 HTTP 服务长期带 `--auto-decrypt` 运行；它可能在微信数据库变化或自动解密时高 CPU 卡住。
- 更稳的方式是：HTTP 服务负责查询，解密/刷新作为单独定时任务执行。
- Deepsee 后端已对 chatlog 会话接口做快速失败：如果 `/api/v1/session` 超时，不再继续按天轮询消息，避免页面长时间卡住。

## 常见现象

- **端口开着但接口超时**：chatlog 进程假死，通常需要重启 chatlog，或拆分自动解密任务。
- **云服务器无法用 chatlog**：这是预期限制；chatlog 依赖本机微信文件。
- **消息长时间不更新**：先检查 `bash scripts/chatlog_sidecar.sh status`，再检查 Deepsee 的微信双轨状态页。
