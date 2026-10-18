# Chatlog 半年历史补录

完成日期：2026-10-16（北京时间）。

## 导入结果

- 范围：2026-04-15 00:00:00 至 2026-10-16 00:07:43；后续消息继续由 WebSocket 接收。
- 检查 1,707 个会话，包含已从微信会话列表移除、但本地消息表仍保留的会话。
- 读取 163,582 条；新增 **162,311 条**，合并已有/重复记录 **1,271 条**；无过滤、无未完成分页。
- 已处理文件发送时间与本地时间相差数秒的重复，以及微信公众号内部聚合表中的 8 条镜像记录。
- 完成时核对：非空微信服务端消息 ID 无重复。
- 原始微信数据库未修改；导入不触发自动回复、群发或历史消息批量 AI 分析。

导入前备份：

`/Volumes/PSSD/Projects/newma-desk/bundled-runtimes/deepsee/data/backups/before-chatlog-six-months-20261016-000719.db`

## 查看方法

直接访问 <http://127.0.0.1:8001/>，进入「微信 → 历史检索」。Newma-Desk 的「深瞳 → 微信」使用同一入口。

- 按日期、正文关键词、备注/群名、消息类型、收发方向查询。
- 查询整个已入库消息库，每页 50 条；不再局限于近期列表已加载的 600 条。
- 默认隐藏内部系统消息，可选择「系统」查看；公众号及发出消息仍可查询。
- 图片、语音、视频/封面、表情可预览；文件及原消息链接可打开。
- 直接版和 Desk 共用组件，适配浅色/深色主题、长消息折叠及表头布局。

## 同步与媒体边界

- Chatlog 自动轮询间隔保持为 0，仅用于此次历史补录和本地附件读取。
- WebSocket 已恢复连接，状态无错误；历史导入与实时同步共享服务端消息 ID 去重标记。
- Chatlog 音视频通过 Deepsee 的 `/api/messages/media/local?message_id=...` 同源读取，避免浏览器跨域拦截。仅允许已存记录指向配置的 Chatlog 服务及其本地媒体重定向，不接受任意外部 URL。
- 消息文字已写入 Deepsee 数据库；附件引用仍依赖本地微信文件与 Chatlog 服务，**本轮不是所有附件的独立永久归档**。
- 未下载或已清理的附件无法凭空恢复；视频只有封面时会明确提示。外部文章链接能否继续打开取决于原网站。
- 请保留本地微信数据目录及 Deepsee 数据库备份，不要把媒体缓存当作永久备份。

## 验证

- Python 全套回归：562 项通过。测试使用临时数据库，不使用正式数据库。
- Chatlog 历史导入专项 Go 测试通过：超过 500 会话分页、64 位服务端消息 ID 无精度丢失。
- 真实查询：2026-04-15 至 04-30，关键词「半导体」返回 257 条；前两页各 50 条且无交集。直接版及 Desk 结果一致。
- 浏览器实测图片显示、消息链接、历史检索和主题适配；历史语音解码成功（样本时长 12.69 秒），视频封面正确显示缺少原视频的提示；图片、语音、视频封面及文件均有本地接口抽样检查。
- 回归结束时旧 Hermes 外部模型端点仍记录过 502；不将此结果视为外部 AI 服务可用性验证。

截图在 `output/playwright/history-search-desk.png`、`history-image-standalone.png`、`history-links-standalone.png`。

## 维护位置

- 导入器：`app/services/chatlog_backfill.py`。
- 命令入口：`scripts/backfill_chatlog_history.py --start 2026-04-15 --account-id <已核实账号>`。
- 进度：`sync_state` 中的 `chatlog_history_backfill_v1`；状态已为 `complete`。
- 入口必须在实际运行副本目录执行并使用它的配置；同账号、同起始日期重复执行不会重复补录，结束时间沿用首次快照。
- 源码：`/Volumes/PSSD/Projects/0913`。
- 实际运行副本：`/Volumes/PSSD/Projects/newma-desk/bundled-runtimes/deepsee`；本轮相关 Python、前端和脚本已同步。
- Chatlog 使用源仓库编译的 `.local/chatlog/bin/chatlog`，由 `com.deepsee.chatlog.5031` 管理。
