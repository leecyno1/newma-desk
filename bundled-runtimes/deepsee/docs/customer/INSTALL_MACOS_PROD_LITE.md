# macOS 客户机生产轻量安装指南

## 前置要求
- macOS 12+。
- Python 3.11 或 3.12。
- 至少 10G 可用磁盘空间。
- 如需微信聊天接入，请先启动本机 chatlog 服务。

## 安装步骤
```bash
cd /path/to/0913
cp .env.production-lite.example .env
bash scripts/manage.sh prod-lite
bash scripts/manage.sh start
bash scripts/manage.sh status
```

打开：`http://127.0.0.1:8001`

## 配置 AI
1. 打开“功能设置”。
2. 填入 SiliconFlow API Key。
3. 点击主模型/小模型测试。
4. 成功后再运行 AI 总结。

## 开机自启
```bash
bash scripts/manage.sh launchd install
bash scripts/manage.sh launchd health
```

## 诊断报告
```bash
bash scripts/manage.sh diagnose > diagnostics.txt
```
将 `diagnostics.txt` 发给技术支持。

## 备份与恢复
```bash
bash scripts/manage.sh backup
CONFIRM_RESTORE=RESTORE bash scripts/manage.sh restore backups/backup-YYYYmmdd-HHMMSS
```

## 卸载自启
```bash
bash scripts/manage.sh launchd uninstall
bash scripts/manage.sh stop
```
