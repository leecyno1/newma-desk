# 微信本地数据源依赖

Deepsee 的微信引擎现在支持三类来源：

1. **wechatapi**：云端实时主链路，负责回调与发送。
2. **chatlog / chatlog_alpha**：本机 HTTP sidecar，沿用 Deepsee 现有 `CHATLOG_HTTP_BASE` 查询链路。
3. **wx-cli**：本机 CLI + daemon 兜底源，可用于 Windows/macOS；macOS 初始化可能需要额外授权，用于 chatlog 不可用时读取私聊/群聊历史。

## 依赖安装

Chatlog 源码已内置在 `third_party/chatlog/`，安装脚本会从仓库源码本地构建，
不再从其他 Chatlog 仓库下载。生成的二进制放在 `.local/wechat-local/`；
wx-cli 仍按 `deps/wechat-local-deps.json` 下载：

```bash
python scripts/install_wechat_local_deps.py --tool all
```

只安装其中一个：

```bash
python scripts/install_wechat_local_deps.py --tool chatlog_alpha
python scripts/install_wechat_local_deps.py --tool wx_cli
```

也可以直接构建 Chatlog：

```bash
bash scripts/build_chatlog.sh
```

Chatlog 当前需要 Go 1.24+ 和本机 CGO 编译环境。源码许可证及免责声明保留在
`third_party/chatlog/LICENSE` 和 `third_party/chatlog/DISCLAIMER.md`。

Windows 在本机 PowerShell 中可以直接构建仓库版本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 build
```

## Windows 推荐流程

1. 打开并登录 Windows 微信电脑版。
2. 从仓库源码构建 Chatlog，并安装 wx-cli：
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 build
   python scripts\install_wechat_local_deps.py --tool wx_cli --platform windows-amd64
   ```
3. 初始化 wx-cli：
   ```powershell
   .\.local\wechat-local\wx_cli\wx-windows-x86_64.exe init
   .\.local\wechat-local\wx_cli\wx-windows-x86_64.exe sessions --json
   ```
4. 启动 chatlog_alpha HTTP sidecar：
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\run_chatlog_windows.ps1 start
   ```
5. Deepsee 中执行“微信双轨同步”。如果 chatlog HTTP 不可用，后端会自动尝试 wx-cli。

## macOS wx-cli 注意事项

1. 打开并登录 macOS 微信。
2. 安装依赖：
   ```bash
   python scripts/install_wechat_local_deps.py --tool wx_cli
   ```
3. 初始化 wx-cli：
   ```bash
   ./.local/wechat-local/wx_cli/wx-macos-arm64 init
   ```
4. 如果出现 `task_for_pid` 失败，说明 macOS 拦截了读取微信进程密钥。需按 wx-cli 提示授权/重签微信并用管理员权限重新初始化；完成前 Deepsee 会把 wx-cli 标记为未就绪，但不会影响 WeChat API 和 chatlog 链路。

## 数据进入规则

- 微信模块只接收 `private` 与 `group` 消息。
- `official_account` 与 `folded` 默认跳过，避免公众号内容干扰微信消息列表。
- 公众号文章后续应走公众号引擎，wx-cli 的 `biz-articles --json` 可作为增强来源。

## 云服务器限制

chatlog 和 wx-cli 都依赖本机微信数据文件或本机微信进程。Deepsee 部署到云服务器后，云端不能直接读取用户 Windows/Mac 上的微信本地库。推荐方案：

- 云端使用 wechatapi 作为主链路；
- 用户本机运行 chatlog_alpha 或 wx-cli sidecar；
- 本机定时同步到云端，或通过安全隧道把本机服务暴露给云端。
