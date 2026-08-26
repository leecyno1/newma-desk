# 配置与集成

本项目默认本地运行（FastAPI + SQLite），通过若干“可选集成”扩展数据源与发送通道。

## 1) chatlog（微信聊天记录）

- 作用：提供微信聊天记录的 HTTP 访问能力，本项目用于增量拉取并落库
- 运行方式：Deepsee 只连接 chatlog HTTP 服务；Windows 可用 `scripts\run_chatlog_windows.ps1` 启动本机 sidecar，macOS 可用 `scripts/chatlog_sidecar.sh`
- 配置项：
  - `CHATLOG_HTTP_BASE`：chatlog HTTP 服务地址
  - `CHATLOG_DIR`：本地聊天目录（可选，用于离线导入/兜底）
- 详细说明：见 `docs/chatlog-sidecar.md`

## 2) 邮件（IMAP/SMTP）

- 作用：多账户 IMAP 同步 + SMTP 发送
- 配置方式：在 UI「功能设置 → 邮件引擎配置」中维护账户

## 3) NewsNow（新闻聚合）

- 作用：iframe 内嵌新闻站点（本项目只负责承载与配置）
- 配置方式：UI「功能设置 → 新闻聚合（NewsNow）」

## 4) MediaCrawlerPro（自媒体聚合）

- 作用：读取本地 MediaCrawlerPro-Python 落盘结果，统一表格展示与筛选
- 配置项：
  - `MEDIA_PROJECT_DIR`（或 UI 中设置项目目录）
  - （可选）`MEDIA_SERVER_BASE`：若有外部服务能力（如转写/控制），可作为基址

## 5) we-mp-rss（公众号聚合）

- 作用：读取本地 we-mp-rss 的 SQLite 数据库，并展示文章摘要/统计数据
- 配置项：
  - `WE_MP_RSS_DIR` 或 `WE_MP_RSS_DB`（或 UI 中设置 DB 路径）

## 6) LangBot / 发送网关

- 目标：将“消息发送”抽象为网关能力，便于未来统一接入微信/QQ/Telegram 等通道，避免协议变更导致业务侧重写
- 本项目现状：
  - UI「功能设置 → 发送服务」中可配置发送 provider 与网关参数
  - UI「自定义聚合」用于未来多平台“记录/发送”按适配器拆分，避免串发

## 7) 本地会议录音（/api/recorder/*）

- 作用：监听麦克风/系统音频，出现声音自动录音；静音超过阈值后自动停止并保存文件
- 配置位置：UI「功能设置 → 会议聚合（纪要/录音）」内的设备与监听参数

## 常用启动命令

- 初次安装：`cp .env.example .env && bash scripts/manage.sh install`
- 开发热重载：`bash scripts/manage.sh dev`
- 后台服务：`bash scripts/manage.sh start|status|logs -f|stop`
