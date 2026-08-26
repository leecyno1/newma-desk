# 安装指南

Newma Media Studio 的核心工作流只要求 Python 与 Git；视频渲染、ASR、浏览器发布和外部储备按需安装。

## 1. 系统要求

| 依赖 | 要求 | 用途 |
| --- | --- | --- |
| Python | 3.10+ | 主流程、注册表、测试 |
| Git | 2.x | 主仓库与外部储备同步 |
| Node.js | 18+，可选 | Remotion、HTML 动画、发布控制台 |
| FFmpeg / ffprobe | 5+，可选 | 音视频探测、剪辑、转码、QC |
| pnpm / bun | 可选 | 部分上游项目的依赖管理 |
| yt-dlp | 可选 | 公开素材下载与参考视频采集 |

建议预留 15 GB 以上空间。ASR 模型、浏览器、Node 依赖和 46 个外部项目不会进入主仓库，但会占用本地磁盘。

## 2. 安装核心项目

```bash
git clone https://github.com/leecyno1/newma-media-studio.git
cd newma-media-studio
chmod +x scripts/install.sh
./scripts/install.sh
source .venv/bin/activate
```

安装脚本会创建 `.venv`、安装 `requirements.txt`、复制本地路径配置模板并运行基础验证。仓库根目录没有统一的 Node 包，因此不会执行无意义的根目录 `npm install`。

手动安装等价命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp configs/paths.default.yaml configs/paths.local.yaml
python scripts/verify_installation.py
```

## 3. 配置环境

```bash
cp .env.template .env
cp configs/paths.default.yaml configs/paths.local.yaml
```

最常用的路径变量：

```bash
export DASHENG_PROJECT_ROOT="$PWD"
export DASHENG_OUTPUT_ROOT="$HOME/Desktop/自媒体创作"
```

只填写当前实际使用的服务。财经数据、飞书、图片模型、MiniMax、发布平台等均为可选集成。密钥应放在 `.env`、系统钥匙串或仓库外的配置文件中，不要写入被 Git 跟踪的 JSON、Markdown 或 Skill。

## 4. 安装 Skills

```bash
bash install_to_openclaw.sh
```

默认复制到 `~/.openclaw/skills` 和 `~/.openclaw/workspace`。也可指定目标：

```bash
bash install_to_openclaw.sh /path/to/skills /path/to/workspace
```

总控 Skill 是 `dasheng-media-sop`，完整登记见 `skills/SKILL_ALIASES.md`。

## 5. 同步外部储备

检查本地状态：

```bash
python scripts/sync_reserved_projects.py --mode check
```

克隆全部保留项目与候选储备：

```bash
python scripts/sync_reserved_projects.py --mode clone
```

也可按类别或名称安装：

```bash
python scripts/sync_reserved_projects.py --mode clone --category video
python scripts/sync_reserved_projects.py --mode clone --name qianfan-sync
```

更新只允许干净工作树的快进合并：

```bash
python scripts/sync_reserved_projects.py --mode update --name opencli
```

外部源码默认位于 `vendor/reserved/` 或 `vendor/publish/`，并被主仓库忽略。

## 6. 应用上游兼容补丁

```bash
python scripts/apply_upstream_patches.py --mode check
python scripts/apply_upstream_patches.py --mode apply
```

补丁包括千帆发布窗口策略、B 站封面假超时修复、HTML Video 动画依赖和若干本地构建兼容项。补丁登记见 `configs/external/upstream_patches.json`。

更新上游前，先确认其工作树是否包含本地修改；不要对有修改的外部仓库直接执行更新。

## 7. 视频与发布依赖

ASR 与媒体扩展：

```bash
python -m pip install -r requirements-media.txt
```

检查视频外部依赖：

```bash
python scripts/ensure_video_external_deps.py --dep all --mode check
```

发布相关上游检查：

```bash
python scripts/check_publish_upstreams.py
python scripts/publish_doctor.py
```

千帆、Social Auto Upload、PostBot 和 OpenCLI 各自拥有独立依赖与登录会话。账号状态应保存在仓库外的命名 Session 目录中。

千帆作为默认视频发布路线时，复制一份本地账号映射并填写每个平台槽位的 `qianfan_account_id` 或 `qianfan_account_name`：

```bash
cp configs/publish/account_registry.json configs/publish/account_registry.local.json
export DASHENG_PUBLISH_ACCOUNT_REGISTRY="$PWD/configs/publish/account_registry.local.json"
export QIANFAN_API_BASE="http://127.0.0.1:5409"
```

本地映射文件被 Git 忽略，不要把真实账号名称和 ID 写回公开模板。

## 8. 验证

```bash
python scripts/verify_installation.py
python scripts/run_mainline_stage.py doctor --strict
python scripts/build_project_catalog.py --check
python -m pytest tests -q
```

## 9. 更新

```bash
git pull --ff-only origin main
source .venv/bin/activate
python -m pip install -r requirements.txt --upgrade
python scripts/sync_reserved_projects.py --mode check
python scripts/apply_upstream_patches.py --mode check
python scripts/verify_installation.py
```

外部储备与主仓库分开更新。不要使用会覆盖本地补丁或账号会话的递归重置命令。

## 常见问题

- `missing_checkout`：运行储备克隆命令，或只克隆所需项目。
- `patch conflict`：上游文件已经变化；对照补丁目的手工迁移后重新导出补丁。
- FFmpeg 不可用：先安装 FFmpeg，再重跑媒体依赖检查。
- 发布登录失效：在对应命名账号 Session 中重新登录，不要把 Cookie 导出到仓库。
- 路径错误：设置 `DASHENG_PROJECT_ROOT` 和 `DASHENG_OUTPUT_ROOT`，再运行 doctor。
