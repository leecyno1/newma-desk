# AI 执行与会议录音迭代（2026-10-17）

## 已上线

- 驾驶舱：会议邀请/表情不构成机会；过滤文件后缀；不把任意相邻词拼成主题；缺少上期样本不计算增长百分比。
- AI 分析：没有摘要时使用正文；独立与嵌入页面均调用同一个分析接口；空输出及通道错误不再伪装为成功。
- 设置 → AI 执行：Agent 与独立模型并行，高级/轻量档位独立选择。旧模型配置折叠保留。
- 当前部署：高级 Hermes CLI，轻量保持原独立模型；未修改微信自动回复总开关、人工回复抑制及发送策略。
- 会议：当前设备录音、暂停/继续、试听、下载、导入、服务本地 Whisper 转写、共享 AI 纪要、失败重试；重启中断可恢复，已有转写不重复识别。
- Desk 仅会议嵌入页声明 microphone 权限，仍须用户点击并授权。相关修改在 newma-desk/apps/shell/src/components/ModuleFrame.tsx。

## 验证与边界

- Deepsee 定向回归 93 项通过，Desk ModuleFrame 32 项通过。
- Codex 真实连通、合成音频 → 本地 Whisper → Codex 纪要链路通过。
- 从独立页面生成当天市场分析成功，已显示非空分析与消息引用。
- 独立会议页、Desk 嵌入会议页和 AI 设置页已目视检查。
- Hermes CLI 已通过真实连通与结构化分析测试，后续按用户要求改为 Deepsee 专用的 MiniMax-M3 连接（不修改个人 Hermes 默认配置）。Claude 适配已实现，但当前 CLI 未登录。通用接口要求 OpenAI 兼容 chat completions。Qoder 未接入。
- Windows/iPhone/Android 未做真机麦克风验证。移动端网页录音需要 HTTPS；普通内网 HTTP 使用系统录音后导入。
- “本地转写”指服务电脑本地执行，不代表手机离线转写；纪要会使用选定的 AI 服务。
- 当前设备录音依赖网页保持前台，不承诺锁屏/后台录音。

## 运行版本

源代码：`/Volumes/PSSD/Projects/0913`。部署：`/Volumes/PSSD/Projects/newma-desk/bundled-runtimes/deepsee`。
部署前代码与配置备份：`/Volumes/PSSD/Projects/newma-desk/backups/deepsee-ai-20261017-001611`。
仅同步本轮文件，未复制数据库或环境密钥；由原 Desk supervisor 重启 Deepsee 服务。

## Hermes CLI 接入补充

- 设置 → AI 执行 → Agent 提供方选择 Hermes CLI。未指定模型服务地址时，模型 ID 留空会沿用 Hermes 默认模型。指定专用模型服务地址后，需要同时填写模型 ID。
- 读取服务账号的 `HERMES_HOME`（未设置时为 `~/.hermes`），只复用模型连接和认证，不加载个人记忆、规则、工具、MCP 或钩子。
- 每次调用使用同一 Hermes 根目录下的临时 profile，复用已安装的运行环境，结束自动删除，避免每次重新安装依赖。
- 使用 stream-json 的最终成功事件作为结果，启动提示和中间输出不再混入分析正文。
- 定向回归 62 项通过；结构化测试正确将 AI 交流会邀请归类为会议，并标明没有投资证据。
- 在线服务 `/api/ai/execution/test` 返回 `ok=true`、`provider=hermes`、`fallback_used=false`。本次耗时 140.2 秒，终端测试约 13–34 秒；响应延迟仍有波动，轻量与实时回复通道保持独立模型。
- 本轮部署前备份：`/Volumes/PSSD/Projects/newma-desk/backups/deepsee-hermes-20261017-164335`。

## MiniMax M3 默认调用

- Deepsee 的 Hermes 高级/轻量模型 ID 均设为 `MiniMax-M3`；轻量通道仍选独立模型，因此没有切换微信自动回复的执行方式。
- 复用 Deepsee 已有的 MiniMax M3 服务地址与凭据，在临时 Hermes profile 中指定 `chat_completions` 连接。密钥通过子进程环境传递，不放进命令行或临时 YAML。
- 设置页允许单独维护 Hermes 模型服务地址和密钥；不会修改 `~/.hermes/config.yaml`，也不会更改其他 Hermes 会话。
- 本轮定向回归 63 项通过。直接 MiniMax M3 连通测试约 1.8 秒，Hermes 成功样本约 12 秒；另一次 Hermes 调用超过 90 秒，尚不能将所有延迟归因于模型。
- 上线后的实际服务测试成功：`provider=hermes`、`final_model=MiniMax-M3`、`fallback_used=false`，耗时 37 秒；核对确认其他业务配置未改变。
- 部署前备份：`/Volumes/PSSD/Projects/newma-desk/backups/deepsee-hermes-m3-20261017-165625`。
