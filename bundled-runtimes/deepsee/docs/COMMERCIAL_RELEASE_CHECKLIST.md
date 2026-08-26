# 商业化客户机交付验收清单

## 1. 目标部署形态
- 平台：macOS 本地单机包优先。
- 低配目标：2G 内存 / 2 核 / 10G 磁盘可轻量运行。
- 默认不启用高频后台任务，所有重任务由用户手动触发。

## 2. 首次安装
```bash
cp .env.production-lite.example .env
bash scripts/manage.sh prod-lite
bash scripts/manage.sh start
bash scripts/manage.sh status
```

验收：
- `http://127.0.0.1:8001/api/health` 返回 `ok`。
- `http://127.0.0.1:8001/api/ready` 返回检查列表，核心项不为 `fail`。
- `bash scripts/manage.sh diagnose` 可输出完整诊断报告。

## 3. macOS 开机自启
```bash
bash scripts/manage.sh launchd install
bash scripts/manage.sh launchd status
bash scripts/manage.sh launchd health
```

验收：
- launchd service loaded。
- 重启服务后端口仍为 `.env` 中的 `HOST:PORT`。
- 日志可通过 `bash scripts/manage.sh launchd logs` 查看。

## 4. 数据安全
```bash
bash scripts/manage.sh backup
CONFIRM_RESTORE=RESTORE bash scripts/manage.sh restore backups/backup-YYYYmmdd-HHMMSS
bash scripts/manage.sh start
```

验收：
- 备份目录包含 `.env`、`app.db`、`ai_config.json`（如存在）。
- 恢复前服务会自动停止。
- 恢复后健康检查通过，数据库可查询。

## 5. 关键业务链路
- 消息列表可打开并查询关键词。
- chatlog 未启动时，页面显示可恢复错误，不应白屏。
- 模型 Key 未配置时，AI 总结显示明确提示，不应 500 空白。
- 配置 Key 后，主模型/小模型测试按钮返回成功或明确错误。
- 发送管理保存草稿、生成回复、失败重试均有状态提示。

## 6. 低配运行建议
- `.env` 保持 `SYNC_INTERVAL_SECONDS=0`、`NEWSNOW_REFRESH_INTERVAL_SECONDS=0`、`NEWS_SNAPSHOT_INTERVAL_SECONDS=0`。
- `AI_MAX_PARALLEL=2`。
- 不在客户机上启动 Playwright/Chromium 常驻进程。
- 每日自动聚合清理保留开启：`AGGREGATION_RETENTION_INTERVAL_SECONDS=86400`。

## 7. 发布门槛
- 关键测试集通过。
- `bash scripts/manage.sh restart` 后 `/api/health` 和 `/api/ready` 可访问。
- `bash scripts/manage.sh backup` 可生成非空备份。
- `bash scripts/manage.sh diagnose` 能输出给技术支持直接定位的问题报告。

## 前端截图验收

- 最新截图验收报告：`docs/qa-screenshots/commercial-2026-05-04/README.md`
- 覆盖页面：AI总结、数据看板、微信聚合、分析师评分、消息群发、功能设置、公众号聚合。
- 自动检查：无控制台错误、无桌面横向溢出、模块切换正常。

## 低配与数据安全验收

- 最新低配/备份恢复报告：`docs/qa-smoke/commercial-2026-05-04/README.md`
- 低配烟测：20 次 health 探测、`/api/ready` 通过、RSS 低于 250MB。
- 备份恢复：真实备份 `integrity_check=ok`；临时目录恢复演练通过。
