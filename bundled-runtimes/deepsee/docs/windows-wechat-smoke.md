# Windows 微信本地链路实机验证

此清单用于验证本地版 fallback：`chatlog_alpha` 与 `wx-cli`。

## 前置条件

1. Windows 微信电脑版已安装、登录并保持运行。
2. PowerShell 以管理员身份运行。
3. Deepsee 项目已安装 Python 依赖。

## 安装依赖

```powershell
python scripts\install_wechat_local_deps.py --tool all --platform windows-amd64
```

## 验证 wx-cli

```powershell
.\.local\wechat-local\wx_cli\wx-windows-x86_64.exe init
.\.local\wechat-local\wx_cli\wx-windows-x86_64.exe sessions --json
.\.local\wechat-local\wx_cli\wx-windows-x86_64.exe history "文件传输助手" -n 10 --json
```

通过标准：

- `sessions --json` 返回 `sessions` 数组。
- `history --json` 返回 `messages` 数组或明确提示找不到会话。

## 验证 chatlog_alpha

配置 `.env`：

```env
CHATLOG_PLATFORM=windows
CHATLOG_BIN=.local\wechat-local\chatlog_alpha\chatlog-windows-amd64.exe
CHATLOG_DATA_DIR=C:\Users\<user>\Documents\WeChat Files\<wxid>
CHATLOG_WORK_DIR=C:\Users\<user>\Documents\chatlog\<wxid>
```

启动并探测：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 start
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 status
```

通过标准：

- `/api/v1/session` 可返回。
- Deepsee `功能设置 → 微信引擎` 中 chatlog_alpha 指示灯为可用。

## 验证 Deepsee 三轨同步

```powershell
curl -X POST "http://127.0.0.1:8001/api/sync/wechat/dual-track?days=1"
curl "http://127.0.0.1:8001/api/messages?size=20&page=1&fast=1"
```

通过标准：

- 有 WeChat API 时，优先显示 `wechatapi` 轨道。
- 无 WeChat API 时，chatlog_alpha 可用则走 `chatlog`。
- chatlog_alpha 不可用但 wx-cli 可用时，走 `wx_cli`。
- 微信模块不混入公众号/折叠入口消息。
