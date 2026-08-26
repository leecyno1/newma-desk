# 0913 微信自动化 — 完整部署与迁移指南

> 版本: 2026-05-19 | 适用于全新服务器部署

本文件是 0913 / Deepsee 仓库内唯一维护的部署与迁移 source of truth。
注意：这不影响 `wx-auto/DEPLOY.md`，后者仍然是 Agent 侧 / 跨机部署视角的独立手册。

---

## 快速开始（新服务器）

```bash
# 1. 克隆项目
git clone <your-repo-url> /opt/0913
cd /opt/0913

# 2. 一键部署
bash scripts/deploy-0913.sh /opt/0913
```

部署脚本会交互式询问：
1. wechatapi token + app_id
2. Callback public URL
3. SiliconFlow API key
4. MiniMax API key
5. API Token

最小上线检查：
- `curl http://127.0.0.1:8001/api/health`
- `curl http://127.0.0.1:8642/health`
- `bash scripts/manage.sh migrate apply`
- `bash scripts/manage.sh release-check`
- 配置公网隧道到 8001
- 绑定 `/api/wechat-gateway/callback`
- 微信发送 `ai test` 验证自动回复

公网部署建议：
- `.env` 设置 `APP_ENV=production`
- `.env` 设置 `API_AUTH_REQUIRED=true` 与强随机 `API_TOKEN`
- 反向代理只暴露必要路径，并保留 `/api/wechat-gateway/callback` 给 WeChat API 回调
- 本地微信历史兜底只在用户本机运行 `chatlog_alpha` / `wx-cli`，云服务器默认以 WeChat API 为主链路

---

## 架构概览

```
                    公网                       内网 (127.0.0.1)
微信用户 ──→ wechatapi.net ──→ natapp隧道 ──→ 0913:8001          Hermes:8642
                                    │              │                   │
                               callback      FastAPI server      API Server
                                    │         (reins)             (brain)
                                    │              │                   │
                                    │    ┌─ wechat_gateway.py ─→ hermes_bridge.py ──→ /v1/chat/completions
                                    │    │  (入库+规则评估)         (格式约束+bridge-scoped session key)
                                    │    │                             │
                                    │    └─ reply_generation.py (降级)  ├─ wiki / 记忆 / web search
                                    │                                   ├─ skills (llm-wiki, 0913-wechat-smart-reply)
                                    │                                   └─ MiniMax-M2.7 模型
                                    │
                               media-collector/ (定时采集热榜+搜索)
                                    │
                               cron job (每30min/1h/12h)
```

**核心原则**: 0913 = reins（收发+规则UI），Hermes = brain（wiki/记忆/工具/skills）。自动回复走 Hermes API Server 为主路径，不可用时降级到 SiliconFlow 直调。

---

## 一、资产清单 — 需要打包迁移的内容

### 1.1 0913 项目 (`/Volumes/PSSD/Projects/0913/`)

| 类别 | 路径 | 说明 | 必须 |
|------|------|------|:--:|
| **核心源码** | `app/` (全部) | FastAPI 入口 + 29 routers + 35 services | ✓ |
| **网关核心** | `app/services/wechat_gateway.py` | 回调入库 + 触发规则 + 自动回复编排 | ✓ |
| **Hermes桥接** | `app/services/hermes_bridge.py` | API Server 桥接（bridge-scoped session key；优先 subsession，缺省回落 chat） | ✓ |
| **降级回复** | `app/services/reply_generation.py` | SiliconFlow 直调降级路径 | ✓ |
| **API客户端** | `app/services/wechatapi_client.py` | 125 方法 wechatapi.net 客户端 | ✓ |
| **消息过滤** | `app/services/message_filters.py` | gh_*/system 噪声过滤 | ✓ |
| **媒体采集** | `app/services/media_collector_store.py` | 热榜+搜索+作者合并存储 | ✓ |
| **前端** | `static/index.html` | Dashboard 前端 (1.4MB) | ✓ |
| **前端资源** | `static/vendor/`, `static/assets/` | html2canvas, 图标 | ✓ |
| **热榜采集** | `media-collector/` (全部) | 13个平台采集脚本 + shell | ✓ |
| **部署脚本** | `scripts/deploy-0913.sh` | 一键部署 (8步) | ✓ |
| **服务管理** | `scripts/manage.sh` | install/start/stop/status/dev/backup | ✓ |
| **E2E测试** | `scripts/hermes_e2e_test.py` | Hermes API 端到端验证 | ✓ |
| **DB查询** | `scripts/query_db.py` | SQLite 快速查询 | ✓ |
| **种子数据** | `scripts/seed_sample_data.py` | 测试数据生成 | ✓ |
| **依赖** | `requirements.txt` | Python 依赖清单 | ✓ |
| **文档** | `docs/wechatapi-docs/` | 142页 API 文档镜像 | ✓ |
| **配置模板** | `.env.example`, `data/ai_config.json.example` | 配置模板 | ✓ |
| **项目文档** | `DEPLOY_FULL.md`, `ARCHITECTURE.md`, `MODULES.md` | 项目说明 | ✓ |
| **计划文档** | `docs/plans/` | 历史架构决策记录 | 可选 |
| **测试** | `tests/` | pytest 测试套件 | 可选 |
| **数据库** | `data/app.db` | **不要打包** (含敏感聊天记录) | ✗ |
| **备份** | `backups/` | **不要打包** (太大) | ✗ |

**打包命令**:
```bash
cd /Volumes/PSSD/Projects/0913
tar czf /tmp/0913-source.tar.gz \
  --exclude='data/app.db' --exclude='data/app.db*' \
  --exclude='backups' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.venv' --exclude='.env' --exclude='uvicorn.log' \
  --exclude='data/hot' --exclude='data/search' --exclude='data/authors' \
  --exclude='data/datasets' --exclude='data/recordings' \
  --exclude='data/minutes' --exclude='chatlog_*' \
  app/ static/ media-collector/ scripts/ docs/ tests/ \
  .env.example data/ai_config.json.example \
  requirements.txt DEPLOY_FULL.md ARCHITECTURE.md MODULES.md AGENTS.md \
  VERSION pytest.ini
```

### 1.2 Hermes 端

| 类别 | 路径 | 说明 | 必须 |
|------|------|------|:--:|
| **Hermes安装** | 官方安装脚本 | `curl -fsSL https://raw...install.sh \| bash` | ✓ |
| **0913 skill** | `~/.hermes/skills/software-development/0913-wechat-smart-reply/` | 含所有 references + deploy 脚本 | ✓ |
| **热榜 skill** | `~/.hermes/skills/software-development/media-hot-collector/` | 采集器文档和 references | 推荐 |
| **Wiki skill** | `~/.hermes/skills/note-taking/llm-wiki/` | 如需每日对话复习功能 | 可选 |
| **包装脚本** | `~/.hermes/scripts/0913_*.sh` | 4个 cron 包装脚本 | ✓ |
| **每日摘要** | `~/.hermes/scripts/0913_daily_digest.py` | 对话复习→Wiki 脚本 | 可选 |
| **config.yaml** | `~/.hermes/config.yaml` | providers + api_server + platform_toolsets | ✓ |
| **.env** | `~/.hermes/.env` | API_SERVER_KEY + MiniMax Key | ✓ |

**打包 Hermes 配置和 skills**:
```bash
# Skills
tar czf /tmp/hermes-skills.tar.gz \
  -C ~/.hermes/skills/software-development 0913-wechat-smart-reply \
  -C ~/.hermes/skills/software-development media-hot-collector

# Scripts
tar czf /tmp/hermes-scripts.tar.gz \
  -C ~/.hermes/scripts 0913_hot_collect.sh 0913_batch_search.sh \
  0913_batch_author_search.sh 0913_daily_digest.py
```

### 1.3 外部依赖

| 依赖 | 获取方式 | 用途 |
|------|---------|------|
| wechatapi.net token | 购买/注册 wechatapi.net | 微信消息收发 |
| natapp/ngrok/frp | 各自官网 | 公网隧道 |
| MiniMax API Key | platform.minimax.chat | Hermes 微信自动回复模型 |
| SiliconFlow API Key | siliconflow.cn | 降级路径 + AI摘要 |
| Python 3.11+ | 系统包管理器 | 运行 0913 |

---

## 二、新服务器部署流程

### 2.1 服务器环境准备

```bash
# 确保 Python 3.11+
python3 --version

# 安装 Hermes Agent
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# 创建目录
mkdir -p /opt/0913
```

### 2.2 部署 0913 项目

```bash
# 方式A：从打包文件解压
tar xzf /tmp/0913-source.tar.gz -C /opt/0913

# 方式B：从 Git 克隆（如有）
git clone <repo-url> /opt/0913

# 进入项目
cd /opt/0913

# 一键部署（交互式输入凭证）
bash scripts/deploy-0913.sh /opt/0913
```

部署脚本会交互式询问：
1. wechatapi token + app_id
2. Callback public URL (natapp 隧道地址)
3. SiliconFlow API key
4. MiniMax API key
5. API Token (前端登录密码)

### 2.3 配置 Hermes

```bash
# 创建/编辑 ~/.hermes/.env
cat >> ~/.hermes/.env <<'EOF'
API_SERVER_ENABLED=true
API_SERVER_PORT=8642
API_SERVER_KEY=<your-hermes-api-server-key>
HERMES_MINIMAX_CN_API_KEY=<你的MiniMax API Key>
EOF

# 编辑 ~/.hermes/config.yaml
hermes config edit
```

**config.yaml 必须包含的关键节**:

```yaml
# 模型（主对话用）
model:
  provider: deepseek
  default: deepseek-v4-pro
  base_url: https://api.deepseek.com/v1

# MiniMax CN provider（微信自动回复专用）
providers:
  minimax-cn:
    name: MiniMax CN
    api: https://api.minimax.chat/v1
    key_env: HERMES_MINIMAX_CN_API_KEY
    transport: chat_completions
    default_model: MiniMax-M2.7

# API Server 平台（0913 桥接）
platforms:
  api_server:
    enabled: true
    extra:
      host: 127.0.0.1
      port: 8642

# API Server 工具限制（安全隔离，不给 terminal/file/memory/delegation）
platform_toolsets:
  api_server:
    - file        # 读文件能力
    - skills      # 加载 skills
    - todo        # 任务跟踪
    - vision      # 图片识别
    - web         # 网络搜索
```

**注意**: `api_server` toolsets 不给 `terminal`/`memory`/`delegation`，防止微信侧越权。

### 2.4 安装 Hermes Skills

```bash
# 解压 skills
tar xzf /tmp/hermes-skills.tar.gz -C ~/.hermes/skills/software-development/

# 安装包装脚本
tar xzf /tmp/hermes-scripts.tar.gz -C ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/0913_*.sh
```

### 2.5 启动服务

```bash
# 启动 0913
cd /opt/0913
bash scripts/manage.sh start

# 启动 Hermes Gateway（含 API Server）
hermes gateway start

# 验证
curl http://127.0.0.1:8001/api/health    # 0913
curl http://127.0.0.1:8642/health        # Hermes API Server
```

### 2.6 设置 Cron Jobs

部署后在 Hermes 中创建以下 cron：

```bash
# 热榜采集（每30分钟，no_agent script模式）
hermes cron create "*/30 * * * *" \
  --script 0913_hot_collect.sh \
  --no-agent \
  --workdir /opt/0913 \
  --deliver local \
  --name "0913热榜采集-每30分钟"

# 关键词搜索（每小时第30分，no_agent script模式）
hermes cron create "30 * * * *" \
  --script 0913_batch_search.sh \
  --no-agent \
  --workdir /opt/0913 \
  --deliver local \
  --name "0913关键词搜索-每1小时"

# 作者追踪（每12小时，no_agent script模式）
hermes cron create "0 */12 * * *" \
  --script 0913_batch_author_search.sh \
  --no-agent \
  --workdir /opt/0913 \
  --deliver local \
  --name "0913财经博主作者搜索更新"

# 每日对话复习→Wiki（如有 wiki 需求）
hermes cron create "0 22 * * *" \
  --skill llm-wiki \
  --prompt "复盘过去24小时0913中的微信私聊对话，提取有价值的投资知识点，写入 ~/wiki..." \
  --workdir /opt/0913 \
  --deliver feishu:<chat_id> \
  --name "0913对话复习→Wiki"

# 验证
hermes cron list | grep 0913
```

### 2.7 配置公网隧道

```bash
# 以 natapp 为例
./natapp -authtoken=<token> -subdomain=<domain> -lport=8001

# 确认回调路径: https://<domain>/api/wechat-gateway/callback
```

### 2.8 绑定微信回调

1. 访问 `http://127.0.0.1:8001` → WeChat Settings
2. 确认 callback_public_url 为完整路径 `https://<domain>/api/wechat-gateway/callback`
3. 点击 "Bind Callback"
4. 在微信中发 `ai hello` 验证自动回复

---

## 三、验证清单

### 3.1 基础健康检查

```bash
# 0913 服务
curl http://127.0.0.1:8001/api/health
# 期望: {"status":"ok"}

# Hermes API Server
curl http://127.0.0.1:8642/health
# 期望: {"status":"healthy"}

# 微信在线状态
curl -X POST http://127.0.0.1:8001/api/wechat-gateway/check-online
# 期望: {"online":true}
```

### 3.2 自动回复链路测试

```bash
# E2E 测试
cd /opt/0913
python3 scripts/hermes_e2e_test.py
# 期望: 2个case全部 PASS
```

### 3.3 微信端验证

| 测试项 | 操作 | 期望 |
|--------|------|------|
| 基础回复 | 发 `ai hello` | 收到回复 |
| 会议邀约 | 发带数字号码的调研邀请 | 回复 "已知晓" |
| 前缀触发 | 发 `ai <问题>` | 收到有内容的分析回复 |
| 群聊隔离 | A群发消息 → B群发消息 | 互不污染 |

### 3.4 媒体采集验证

```bash
cd /opt/0913
bash media-collector/collect.sh
ls data/hot/$(date +%Y-%m-%d)/
# 应有 bilibili.json, weibo.json, douyin.json 等
```

### 3.5 Cron 验证

```bash
hermes cron list | grep 0913
# 应看到 3-4 个条目，均为 enabled
```

---

## 四、关键配置文件速查

### 4.1 0913 .env

```bash
# 必填
CHATLOG_HTTP_BASE=http://127.0.0.1:5030
CHATLOG_DIR=/opt/chatlog
API_TOKEN=<你的密码>
AGENT_API_TOKEN=<与API_TOKEN相同>
DATABASE_URL=sqlite:///./data/app.db
HOST=127.0.0.1
PORT=8001
SYNC_INTERVAL_SECONDS=0
AI_MAX_PARALLEL=12

# AI Keys
SILICONFLOW_API_KEY=<key>
SILICONFLOW_API_URL=https://api.siliconflow.cn/v1
MINIMAX_API_KEY=<key>

# Hermes Bridge
HERMES_API_BASE=http://127.0.0.1:8642
# 可显式设置 HERMES_API_KEY；若留空，0913 会自动回退读取本机 Hermes 的 API_SERVER_KEY（进程环境或 $HERMES_HOME/.env）
HERMES_API_KEY=
HERMES_FALLBACK_ENABLED=false   # 生产建议false，避免静默降级
```

### 4.2 Hermes .env

```bash
API_SERVER_ENABLED=true
API_SERVER_PORT=8642
API_SERVER_KEY=<your-hermes-api-server-key>
HERMES_MINIMAX_CN_API_KEY=<MiniMax key>
DEEPSEEK_API_KEY=<DeepSeek key>  # 主对话模型
```

### 4.3 wechat_gateway_config (DB SyncState)

| 字段 | 值 | 说明 |
|------|-----|------|
| enabled | true | 网关总开关 |
| outbound_enabled | true | 允许发送消息 |
| base_url | http://api.wechatapi.net/finder/v2/api | API地址 |
| header_name | VideosApi-token | 鉴权头 |
| token | <wechatapi token> | 凭证 |
| app_id | <app_id> | 应用ID |
| callback_public_url | https://xxx/api/wechat-gateway/callback | 完整回调URL |
| device_type | ipad | 设备类型 |
| region_id | 11000 | 地区 |

### 4.4 wechat_gateway_trigger_rules (DB SyncState)

| 字段 | 推荐值 | 说明 |
|------|--------|------|
| enabled | true | 触发规则开关 |
| prefixes | ["ai"] | 触发前缀（注意"AI涨价主线"也会匹配） |
| random_rate | 0 | **生产必须0**，否则随机触发导致回复错乱 |
| human_reply_suppression_seconds | 20 | 人工回复后N秒内不自动回复 |
| private_wakeup_window_seconds | 180 | 私聊唤醒窗口 |

---

## 五、已知 Pitfalls（生产避坑）

### 🔴 FATAL 级别

| # | 问题 | 现象 | 修复 |
|---|------|------|------|
| 1 | Hermes API Server 未启动 | 自动回复走降级SiliconFlow，质量断崖 | `hermes gateway start` |
| 2 | `HERMES_FALLBACK_ENABLED=true` | 超时时静默切模型，回复完全不相关 | 设为 `false` |
| 3 | `random_rate > 0` + 共享session | 随机回复张冠李戴，内容泄露 | 设为 `0` |
| 4 | 回调URL只填域名不填路径 | callback 404 | 必须完整 `/api/wechat-gateway/callback` |
| 5 | wechatapi token 过期 | 消息卡住，checkOnline 500 | 更新token + 重新bind |

### 🟡 IMPORTANT 级别

| # | 问题 | 现象 | 修复 |
|---|------|------|------|
| 6 | session 膨胀到1.98M tokens | 回复来自无关对话 | 已改为 bridge-scoped session key（优先 subsession，缺省回落 chat） |
| 7 | prefix "ai" 匹配自然语言 | "AI涨价主线"触发了配置泄露 | 换更明确前缀如 "/ai" |
| 8 | 时区错误 (utcnow) | 8小时静默期 | 全部用 datetime.fromtimestamp() |
| 9 | natapp 断线 | 消息丢失 | 重连后重新 bind callback |
| 10 | B站搜索HTML标签残留 | 标题含 `<em>` | re.sub(r"<[^>]+>", "", title) |
| 11 | shell中文目录名被tr -cd过滤 | 纯中文目录名为空 | 用 sed 's/[\/ ]/_/g' |
| 12 | batch_search.sh 超时 | 部分关键词无结果 | 单独重试: `bash search.sh "关键词"` |

---

## 六、日常运维

### 服务管理

```bash
# 0913
bash /opt/0913/scripts/manage.sh status    # 查看状态
bash /opt/0913/scripts/manage.sh restart   # 重启
bash /opt/0913/scripts/manage.sh logs -f   # 实时日志
bash /opt/0913/scripts/manage.sh backup    # 备份数据库

# Hermes
hermes gateway status
hermes gateway restart
```

### 故障排查顺序

```
1. curl 0913:8001/api/health          → 0913 alive?
2. curl Hermes:8642/health              → Hermes alive?
3. 查 messages 最新 id/timestamp       → 消息在入库吗？
4. POST /login/checkOnline              → token 有效吗？
5. 查 uvicorn.log 有无 callback 200     → 回调正常吗？
6. POST /evaluate-reply 用样本消息       → 规则触发了吗？
7. hermes_e2e_test.py                   → E2E 链路通吗？
```

### 数据备份

```bash
# 每天备份一次（只备份数据库，不备份聊天数据更大）
bash /opt/0913/scripts/manage.sh backup
# 输出到 /opt/0913/backups/
```

---

## 七、完整文件清单（打包对照）

```
发送到新服务器的文件:
├── 0913-source.tar.gz           # 0913 项目源码 + 采集器
├── hermes-skills.tar.gz         # Hermes skills
├── hermes-scripts.tar.gz        # Cron 包装脚本
│
在新服务器上手动配置:
├── Python 3.11+                 # apt/brew install
├── Hermes Agent                 # 官方安装脚本
├── natapp/ngrok                 # 隧道工具
├── wechatapi token              # 购买获取
├── MiniMax + SiliconFlow keys   # 平台申请
│
部署后自动生成:
├── /opt/0913/.env               # deploy-0913.sh 第4步
├── /opt/0913/data/ai_config.json # deploy-0913.sh 第4步
├── /opt/0913/data/app.db        # deploy-0913.sh 第5步
├── ~/.hermes/.env               # 手动编辑
├── ~/.hermes/config.yaml        # 手动编辑/导入模板
```

---

## 八、快速迁移一句话

```bash
# 在源服务器
cd /Volumes/PSSD/Projects/0913
tar czf /tmp/0913-migrate.tar.gz \
  --exclude='data/app.db*' --exclude='backups' --exclude='__pycache__' \
  --exclude='.venv' --exclude='.env' --exclude='data/hot' \
  --exclude='data/search' --exclude='data/authors' \
  app/ static/ media-collector/ scripts/ docs/ requirements.txt \
  .env.example data/ai_config.json.example DEPLOY_FULL.md
tar czf /tmp/hermes-migrate.tar.gz \
  -C ~/.hermes/skills/software-development 0913-wechat-smart-reply \
  -C ~/.hermes/scripts 0913_hot_collect.sh 0913_batch_search.sh \
  0913_batch_author_search.sh

# scp 到目标服务器
scp /tmp/0913-migrate.tar.gz /tmp/hermes-migrate.tar.gz user@target:/tmp/

# 在目标服务器
mkdir -p /opt/0913 ~/.hermes/skills/software-development ~/.hermes/scripts
tar xzf /tmp/0913-migrate.tar.gz -C /opt/0913
tar xzf /tmp/hermes-migrate.tar.gz -C ~/.hermes/skills/software-development
# 手动解压 scripts
cd /opt/0913 && bash scripts/deploy-0913.sh /opt/0913
# 配置 Hermes .env + config.yaml + 启动 gateway
# 创建 cron jobs
```
