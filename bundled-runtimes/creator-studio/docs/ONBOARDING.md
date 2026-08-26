# Onboarding Guide: Newma Media Studio

## 项目概览

Newma 是一个面向中文自媒体生产的多模态工作流仓库。它不是单一视频生成器或发布机器人，而是用 Manifest、质量门禁和可路由 Skills 把内容研究、写作、视频生产、发布与复盘连接起来。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 主流程 | Python 3.10+、JSON/YAML Manifest |
| Agent 能力 | 项目本地 `SKILL.md` 注册表 |
| 动画视频 | HTML Video、Remotion、HyperFrames、GSAP、Lottie |
| 媒体处理 | FFmpeg/ffprobe、FunASR、EDL |
| 浏览器发布 | 千帆云递、Playwright/CloakBrowser、Social Auto Upload |
| 数据与图表 | pandas、NumPy、Matplotlib、AkShare、Tushare |
| 测试 | pytest、生成器陈旧检查、渲染与发布门禁 |

## 架构

```text
sources
  -> intake manifest
  -> brief + selected topics gate
  -> draft + structure gate
  -> article / talking-head / headless-video / podcast lanes
  -> account matrix + platform adapters
  -> publish receipt verification
  -> postmortem + knowledge writeback
```

总控只负责契约和路由；具体能力由阶段 Skill、功能脚本和外部项目适配器完成。第三方源码在 `vendor/` 独立管理，不属于主仓库历史。

## 关键入口

| 需求 | 入口 |
| --- | --- |
| 跑一个阶段 | `scripts/run_mainline_stage.py` |
| 查看阶段契约 | `skills/dasheng-media-sop/references/` |
| 查看所有模块 | `configs/workflow/module_registry.json` |
| 查看 Skill | `skills/SKILL_ALIASES.md` |
| 查看外部项目 | `configs/external/reserved_projects.json` |
| 克隆外部项目 | `scripts/sync_reserved_projects.py` |
| 应用上游补丁 | `scripts/apply_upstream_patches.py` |
| 视频导演路由 | `skills/dasheng-video-director/`、`scripts/dasheng_video_director.py` |
| 发布路由 | `skills/dasheng-stage-publish/`、`configs/publish/` |
| 系统诊断 | `scripts/workflow_doctor.py` |

## 目录地图

```text
core/                 共享引擎与路径逻辑
scripts/              阶段构建器、路由器、检查器、生成器
skills/               正式与按需 Agent Skills
configs/workflow/     主链与模块注册表
configs/video/        导演、工具、模板、证据和 QC 契约
configs/publish/      账号矩阵、平台字段、路由和窗口策略
configs/external/     外部项目与补丁登记
patches/upstreams/    第三方兼容补丁
templates/            视频与内容模板
tests/                契约、回归、渲染、发布和卫生测试
docs/                 使用说明、技术研究和生成目录
```

## 请求生命周期

一次正常运行从 `run_mainline_stage.py` 进入。调度器按 `run_id` 读取上一阶段 Manifest，验证 Gate 后调用阶段构建器。构建器写出人读文档与机器 Manifest；Transwrite 再按通路调用视频导演、渲染器和 QC；Publish 根据账号矩阵生成平台包，经本地 API、队列或 CLI 执行，并以平台回执判定成功；Postmortem 最后回写规则和经验。

## 常见任务

```bash
# 安装和诊断
./scripts/install.sh
source .venv/bin/activate
python scripts/run_mainline_stage.py doctor --latest --strict

# 外部储备
python scripts/sync_reserved_projects.py --mode check
python scripts/sync_reserved_projects.py --mode clone --category video
python scripts/apply_upstream_patches.py --mode apply

# 目录和测试
python scripts/build_project_catalog.py
python scripts/build_project_catalog.py --check
python -m pytest tests -q
```

## 约定

- 文件和配置优先使用 `snake_case`；Skill 目录使用 `kebab-case`。
- Manifest 是状态真源，目录时间戳不是。
- 失败应显式返回原因，不静默降级为成功。
- 发布成功必须有可验证回执。
- 任何外部依赖修改先登记为补丁，再更新上游。
- 公开提交前运行卫生测试，确认没有个人路径、凭证或运行态。

## 从哪里开始

先读 `README.md` 和 `docs/PROJECT_CATALOG.md`，再根据任务打开对应阶段的 `SKILL.md`。如果要改主链，先看 `skills/dasheng-media-sop/references/stage-contract.md`；如果要改视频，先看导演 Skill 与 `configs/video/pipelines/`；如果要改发布，先看 `skills/dasheng-media-sop/references/publish-architecture.md`。
