# 6 阶段主链 -> 模块映射表

更新时间：`2026-04-01`

## 主映射

### 可选前置能力

| 能力 | 对外语义 | 当前主入口 | 内部模块 / 脚本 | 交付接口 |
| --- | --- | --- | --- | --- |
| `paradigm-learning` | 从标准文章/模板学习文章范式 | `dasheng-paradigm-profiler` | `引擎/03_全链路SOP工作流/00_范式学习_prompt.md`、`skills/dasheng-paradigm-profiler` | `00_范式画像.md` / `paradigm_profile.yaml` / `paradigm_prompt_block.md` / `paradigm_manifest.json` |
| `video-style-training` | 从大量样板视频学习剪辑/视觉风格 DNA | `dasheng-video-style-trainer` | `scripts/learn_blogger_video_style_local.py`、`scripts/read_video_with_crv.py`、`configs/video/blogger_style_schema.json` | `training_manifest.json` / `per_video/*/analysis.json` / `crv/*/dasheng_video_reading_manifest.json` / `style_profile.json` / `style_profile.md` |
| `video-self-learning` | 每日跟踪目标博主更新并沉淀导演、审美与技术栈候选规则 | `dasheng-video-self-learning` | `scripts/run_video_creator_self_learning.py`、`scripts/install_video_self_learning_schedule.py`、`configs/video/creator_learning_watchlist.json` | `notes/*/analysis.md` / `creator_profiles/*/style_profile.rolling.json` / `knowledge/*.md` / `runs/*/run_manifest.json` |

说明：`paradigm-learning`、`video-style-training` 与 `video-self-learning` 都不是正式主链阶段，不改变 `intake -> brief -> draft -> transwrite -> publish -> postmortem`。前两者生成一次性资产，自学习模块维护增量候选知识；它们都不能静默覆盖人工批准的 DNA。

| 阶段 | 对外语义 | 当前主入口 | 内部模块 / 脚本 | 交付接口 |
| --- | --- | --- | --- | --- |
| `intake` | 内容采集 | `dasheng-media-sop` | `dasheng-daily-intake`、`scripts/` 下采集脚本 | `01_内容采集_底稿.md` / `01_内容采集_报告.md` / `intake_manifest.json` |
| `brief` | AI-only 编辑题池 | `dasheng-media-sop` | `dasheng-daily-phase2`、`scripts/phase2_rebuilder.py` | `02_编辑Brief库.md` / `02_研究Brief库.md` / `02_编辑Brief_报告.md` / `brief_manifest.json` |
| `draft` | 可审核、可发布正文底稿及比喻/举例漫画意图 | `dasheng-media-sop` / `dasheng-lemon-illustrations` | 项目级 Draft 流程、草稿模板、`scripts/build_stage3_draft.py` | `03_标准初稿_<topic>.md` / `03_IllustrationIntents_<topic>.json` / `final_structure_snapshot.json` / `draft_manifest.json` |
| `transwrite` | 公众号、普通无头、VOX 调查解释、真人口播、播客转写生产 | `dasheng-media-sop` / `dasheng-stage-transwrite` | `scripts/build_stage4_transwrite.py`、`dasheng-style-profiler`、`dasheng-video-vox`、MiniMax CLI `mmx`、`dasheng-video-style-trainer`、`dasheng-lemon-illustrations`、`video-hyperframes`、`remotion-best-practices` | `04_转写计划.md` / `transwrite_manifest.json` / lane `illustration_intents.json` / lane manifests |
| `publish` | 发布执行（验收、打包、推草稿/人工包、链接回收） | `dasheng-media-sop` / `dasheng-stage-publish` | `scripts/build_stage5_publish.py`、平台发布 skill 组合、`publish-guard` | `channel_execution_manifest.json` / `publish_verification_report.json` / `07_发布包.md` / `07_发布计划.md` / `publish_manifest.json` |
| `postmortem` | 复盘回写 | `dasheng-media-sop` | `dasheng-daily-postmortem` | `08_复盘报告.md` / `08_L1回写建议.md` / `postmortem_manifest.json` |

## 按需工具

| 工具 | 对外语义 | 当前入口 | 交付接口 |
| --- | --- | --- | --- |
| `rewrite-variants` | 额外多版本改写 | `dasheng-stage-rewrite-v3` | `rewrite_manifest.json` / per-topic variant files |

## 入口原则

1. 对外只记一个入口：`dasheng-media-sop`
2. 旧 `dasheng-daily-*` 只分为三类：
   - `internal module`
   - `historical module`
   - `legacy`
3. 任何阶段调整，先改：
   - 总控 skill
   - 本映射表
   - `STAGE_INTERFACES.md`
   - 对应技能矩阵（如 `publish-skill-matrix.md`）
4. `rewrite` 只能作为 Transwrite 按需工具出现，不得重新变成主链 gate。

## 已退出主链的旧模块

- `dasheng-daily-outline`
- `dasheng-daily-final`

说明：

- `dasheng-daily-draft` 已恢复为主链 Draft 单阶段执行器，旧 outline/final 不再作为正式入口暴露。

## 已归档的旧模块

- `dasheng-caiji`
- `dasheng-clustering`
- `dasheng-xuanti`
- `dasheng-xuanti-skill`
- `dasheng-intake-brief-prod`
- `dasheng-brief-builder`
