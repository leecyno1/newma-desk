---
name: dasheng-media-sop
description: Use when running, resuming, auditing, or updating the Newma self-media workflow in this repo. This is the only formal orchestration entry and it governs the simplified canonical chain.
---

# dasheng-media-sop

## 定位

这是本仓库唯一正式总控 skill。

唯一正式主仓：`{DASHENG_ROOT}`（环境变量，默认为本仓库根目录）

唯一正式主链：

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

可选前置资产：`paradigm-learning` / `dasheng-paradigm-profiler`、`video-style-training` / `dasheng-video-style-trainer`。用户提供标准文章、内容模板、爆款样本或渠道模板时，先生成 `ParadigmProfile`；用户提供大量样板视频或指定视频风格时，先生成 `Video Style DNA`。这些资产供下游消费，但不改变正式主链，也不是强制 gate。

`distribute` 不再单列为正式阶段；平台适配与分发动作并入 `publish`。

独立素材环节已删除。数据、图表、配图和 HTML 嵌入由 Draft 负责；公众号转写、口播视频、播客生产进入 `transwrite`；真正 `publish` 只负责验收、打包、推草稿/发布包和链接回收。

## 何时使用

- 从头开始跑当天创作流
- 继续下一阶段
- 审核某一阶段是否能进入下游
- 收口或更新 workflow / skill / SOP
- 检查某次 run 是否符合 canonical stage contract

## 统一规则

- 只允许 canonical manifest + gate 文件驱动阶段切换。
- 禁止通过"最新目录""旧命名习惯""历史 skill 别名"猜阶段。
- 每个选题独立目录、独立文档、独立素材、独立改写包。
- 文档只是交付视图，不是唯一状态源；状态源以本地 manifest + gate 为准。
- 阶段 1-3 直接形成可发布底稿，不把内部流程统计当正文论据。
- `ParadigmProfile` 与 `Style DNA` 必须分离：前者控制结构范式、场景适配和渠道框架；后者控制作者口吻、语言节奏和表达习惯。
- `Video Style DNA` 与正文事实链必须分离：它只控制剪辑节奏、镜头结构、转场、模板偏好、动效和声音氛围，不生成市场事实或图表数据。
- 数据、图表和配图都在 Draft 内完成，不能扩大成独立阶段。
- 所有文章和视频共用一份 `illustration_intents`：Draft 识别原文比喻、举例、类比、拟人和抽象机制，公众号消费为段后漫画，视频导演消费为柠檬人动态分镜。不得由各渠道重新发明互相冲突的比喻。
- 漫画路由默认使用 `dasheng-lemon-illustrations`；它只承担概念解释和认知锚点，真实图表、网页、表格、文档、地图和人物仍走证据/实拍通路。
- 多版本改写并入 `transwrite` 的渠道表达，不再单独设置阶段。
- `transwrite` 负责公众号、无头口播、VOX、真人出镜、AI 数字人、广告宣传片和播客生产包；电影短剧只生成默认禁用的规划包。
- 六条视频流水线共用 `configs/video/director_registry.json` 的标准顺序：素材接收 → 编剧/口播重写 → 导演分镜 → 素材生成 → 剪辑合成 → 渲染 → QC/交付。
- `publish` 负责 `Publish Gate -> Package -> Draft Push/Manual Pack -> Link Recovery -> Publish Guard` 执行闭环。
- 所有发布动作都必须绑定正式平台执行 skill，不允许把"生成了文案/视频"误报为"已发布"。
- 所有运行产物、临时文章、HTML、图片、音频、视频、审核页、训练缓存都必须写入 `~/Desktop/自媒体创作/`（或 `DASHENG_OUTPUT_ROOT` 指定目录）下的阶段目录；不得写入项目根目录、`skills/`、`openclaw-skill-exports/` 或任意 skill 根目录。

## 阶段路由

- `paradigm-learning`（可选）→ `dasheng-paradigm-profiler` → `引擎/03_全链路SOP工作流/00_范式学习_prompt.md`
- `video-style-training`（可选）→ `dasheng-video-style-trainer` → `scripts/learn_blogger_video_style_local.py`

- `intake` → `dasheng-daily-intake` → `scripts/run_stage1_intake.py`
- `brief` → `dasheng-daily-phase2` → `scripts/phase2_rebuilder.py`
- `draft` → Draft 主链脚本 / Prompt / gate / 可选风格化
- `transwrite` → `dasheng-stage-transwrite` → `scripts/build_stage4_transwrite.py`
- `publish` → `dasheng-stage-publish` → `scripts/build_stage5_publish.py` + 平台发布 skill 组合
- `postmortem` → `dasheng-daily-postmortem` → `scripts/postmortem_writeback.py`

## 全链路CLI

- 诊断：`python3 scripts/workflow_doctor.py --latest`
- 统一 CLI：`python3 scripts/run_mainline_stage.py`
- 分阶段：`scripts/run_mainline_stage.py <stage> --run-id <run_id>`

## 参考文档

- 阶段契约：`docs/STAGE_INTERFACES.md`
- 阶段地图：`skills/dasheng-media-sop/references/stage-map.md`
- 模块映射：`skills/dasheng-media-sop/references/stage-module-map.md`
- 交付接口：`skills/dasheng-media-sop/references/file-contracts.md`
- Publish 架构：`skills/dasheng-media-sop/references/publish-architecture.md`
- Publish 技能矩阵：`skills/dasheng-media-sop/references/publish-skill-matrix.md`
- 迁移表：`skills/dasheng-media-sop/references/legacy-migration-map.md`
- 无真人方形视频正式生产标准：`docs/technical/no-human-square-video-production-standard.md`

## OpenClaw 能力集成

| 平台 | Skill | 来源 |
|------|-------|------|
| 微信公众号 | wechat-multi-publisher | OpenClaw |
| 小红书 | xiaohongshu-auto | OpenClaw |
| 抖音 | douyin-upload-skill | OpenClaw |
| 微博 | baoyu-post-to-weibo | OpenClaw |

## 运行时目录结构

```
{DASHENG_ROOT}/
├── scripts/          # 所有阶段脚本
├── skills/           # 所有技能包
├── configs/          # 配置与路由
└── 引擎/             # SOP文档与规范

~/Desktop/自媒体创作/
├── 00_范式学习/
│   └── 视频训练/
├── <run_id>/              # 每个任务一个文件夹，任务内按环节组织
│   ├── 01_采集/
│   ├── 02_选题/
│   ├── 03_初稿/
│   ├── 04_转写/
│   ├── 05_发布/
│   ├── 06_复盘/
│   └── nodes/             # 节点执行工作区（<stage>/<node>/）
└── _tmp/
```

## 安装与配置

详见 `docs/INSTALLATION.md` 或执行安装脚本 `bash scripts/install.sh`。

环境变量：
- `DASHENG_ROOT`：项目根目录（默认自动检测）
- `DASHENG_OUTPUT_ROOT`：产物输出根目录（默认 `~/Desktop/自媒体创作`）
- `DASHENG_WORLDMONITOR_ROOT`：WorldMonitor项目目录（可选）
- `DASHENG_FINANCE_MOTION_ROOT`：Finance Motion项目目录（可选）
