# Video Pipeline Governance

Date: 2026-08-14

本文件定义 video 环节的新中控层。它吸收 OpenMontage 的优点：流水线清单、阶段产物、工具能力注册、审核门和失败条件；外部上游统一保存在被 Git 忽略的 `vendor/reserved/`，不复制进主仓库历史，也不把媒体、缓存或登录状态写入源码目录。

## 核心原则

Newma 继续保持 `skills + scripts + external deps`，但 video 生产必须经过统一治理：

```text
project run manifest -> pipeline manifest -> stage artifact -> tool registry -> checkpoint/review -> render/publish
```

这层治理不负责“亲自剪视频”，而负责回答八个问题：

| 问题 | 由谁回答 |
| --- | --- |
| 这次生产的总账本在哪里？ | `project_run_manifest.json` |
| 这条视频走哪条生产线？ | `configs/video/pipelines/*.yaml` |
| 当前阶段必须吃什么、吐什么？ | `configs/video/artifact_schemas/*.schema.json` |
| 哪个脚本/Skill/CLI/储备项目有资格做这件事？ | `configs/video/tool_registry.json` + `configs/external/reserved_projects.json` |
| 本分镜主工具和后备工具是什么？ | `scripts/video_director_tool_router.py` → `tool_routing_plan.json` |
| 这条 Lane 由哪个导演、哪些阶段能力和硬门禁负责？ | `configs/video/director_registry.json` |
| 是否允许进入下一阶段？ | `scripts/video_pipeline_governance.py` |
| 失败时挡在哪里？ | pipeline `fail_conditions` + stage `success_criteria` |

## 当前流水线

| Pipeline | 用途 | 关键审核门 |
| --- | --- | --- |
| `talking_head` | 真人出镜口播，粗剪后进入导演包装、证据动画、PIP 和转场 | 粗剪门禁、核心命题/证据审核、渲染器契约、成片 QC |
| `vox_explainer` | 问题驱动的调查解释视频，默认横版 16:9 | 中心问题、证据地图、反证/边界、真实资料来源、完整 QC |
| `explainer_html` | HTML 文章转无真人财经视频，默认横版 16:9 | storyboard、Claim/Evidence、live HTML 场景、Remotion 主时间轴、完整 QC |
| `digital_human` | 授权肖像驱动的单人数字人口播或双人访谈 | 授权、逐人短样、身份/口型、active speaker、AI 披露、完整 QC |
| `cinematic_short_drama` | 电影短剧规划包，暂缓外部 API 执行 | 供应商/预算/授权/安全预检、角色与镜头连续性；默认禁用 |
| `commercial_promo` | 品牌片、产品宣传片、新品预告和效果广告，默认竖版 9:16 | 品牌 Brief、产品真实性、声明/Offer 合规、多比例安全区、完整 QC |
| `style_training` | 样片学习和训练 | 只学习形式，不复制事实/文案/专属视觉；素材放桌面训练目录 |

Transwrite 对外使用六个独立视频 Lane：`talking_head_video`、`vox_explainer_video`、`explainer_html_video`、`digital_human_video`、`cinematic_short_drama_video` 和 `commercial_promo_video`。旧“无真人 talking_head”迁移到 `explainer_html_video`；旧“数字人 talking_head”迁移到 `digital_human_video`。电影短剧 Lane 默认只生成规划包。

## 项目总账本

每次正式生产都应该先创建 `project_run_manifest.json`。它记录输入素材、流水线、阶段状态、阶段产物、审核结果、重试记录和最终输出目录。

初始化一条生产：

```bash
.venv/bin/python scripts/project_run_manifest.py init \
  --title "地产周期论无头科普" \
  --pipeline explainer_html \
  --source article_html=/path/to/article.html
```

正式主链入口 `scripts/run_mainline_stage.py` 已默认接入总账本。只要阶段命令带 `--run-id`，成功后会自动在：

```text
~/Desktop/自媒体创作/<run_id>/project_run_manifest.json
```

回写阶段状态和关键 manifest。也可以显式指定：

```bash
.venv/bin/python scripts/run_mainline_stage.py draft \
  --run-id <run_id> \
  --project-manifest ~/Desktop/自媒体创作/<run_id>/project_run_manifest.json
```

临时调试时可关闭：

```bash
.venv/bin/python scripts/run_mainline_stage.py draft --run-id <run_id> --no-project-manifest
```

注册阶段产物：

```bash
.venv/bin/python scripts/project_run_manifest.py add-artifact <project_run_manifest.json> \
  --stage scene_plan \
  --type scene_plan \
  --path <scene_plan.json>
```

更新阶段状态：

```bash
.venv/bin/python scripts/project_run_manifest.py set-stage <project_run_manifest.json> \
  --stage scene_plan \
  --status pending_review \
  --checkpoint <director_checkpoint.json>
```

检查总账本：

```bash
.venv/bin/python scripts/project_run_manifest.py validate <project_run_manifest.json>
```

默认输出目录必须在 `~/Desktop/自媒体创作` 下。总账本会拒绝把媒体产物放进项目根目录、`skills/`、`.codex/skills/` 或 `node_modules/`。

## 产物契约

所有阶段产物都以 JSON 为主，必须能被 schema 验证：

| Artifact | 说明 |
| --- | --- |
| `brief` | 输入任务、素材路径、目标平台、输出目录 |
| `script` | 口播稿/旁白段落、beat 分类、证据引用 |
| `scene_plan` | 导演分镜、时间轴、模板、构图、动效、转场 |
| `claim_evidence_ledger` | 将微分镜归并为核心命题，记录直接证据、情境素材、假设、披露和缺口 |
| `spoken_revision_sheet` | 记录被证据反驳、无定义或过度确定的原口播，以及时间码、替换句、原因和应用状态 |
| `asset_manifest` | HTML 场景、图表、图片、音频、字幕、Lottie 等素材清单 |
| `edit_decisions` | 可执行剪辑决策：构图、PIP、转场、BGM、字幕策略 |
| `render_report` | 渲染结果、终片路径、警告和失败项 |
| `review` | 人审/机审结果，是否允许继续 |
| `final_delivery_manifest` | 绑定最终视频、字幕、全部门禁、完整 QC、尺寸、时长和 SHA-256 |

真人口播还必须在阶段产物中保留三项可追溯信息：

- `timeline_alignment`：说明字幕/分镜来自最终粗剪 ASR，还是通过离散 EDL 映射；禁止 `global_scale`。
- `evidence_binding`：把命题绑定到具体数据序列、文档页、段落、表格行或截图区域。
- `core_claim_id`：把 70-100 个编辑微镜头归并到约 8-12 个可审核核心命题；一个镜头只能归属一个核心命题。
- `spoken_revision_requirements`：证据与原音频冲突时，必须明确删句、替换、配音覆盖或重录；不能只把命题改成“观点”后继续渲染。
- `renderer_contract`：声明模板对应的真实组件/变体，以及渲染器实际消费的导演字段。
- `renderer_asset_gate`：阻断生产渲染中的占位文档、模拟 B-roll、空图表、空估值和空表格；展示模式必须显式声明才允许占位。

## 使用方式

列出当前视频流水线：

```bash
.venv/bin/python scripts/video_pipeline_governance.py list
```

检查某条流水线是否完整：

```bash
.venv/bin/python scripts/video_pipeline_governance.py validate-pipeline talking_head
.venv/bin/python scripts/video_pipeline_governance.py validate-pipeline explainer_html
.venv/bin/python scripts/video_pipeline_governance.py validate-pipeline vox_explainer
.venv/bin/python scripts/video_pipeline_governance.py validate-pipeline digital_human
.venv/bin/python scripts/video_pipeline_governance.py validate-pipeline commercial_promo
.venv/bin/python scripts/video_pipeline_governance.py validate-pipeline cinematic_short_drama
.venv/bin/python scripts/video_pipeline_governance.py validate-pipeline style_training
```

检查阶段产物：

```bash
.venv/bin/python scripts/video_pipeline_governance.py validate-artifact scene_plan <scene_plan.json>
.venv/bin/python scripts/video_pipeline_governance.py validate-artifact claim_evidence_ledger <claim_evidence_ledger.json>
```

建立核心命题和证据账本：

```bash
.venv/bin/python scripts/video_claim_evidence_ledger.py \
  --scene-plan <scene_plan.real_evidence.json> \
  --claim-spec <claim_spec.json> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/claim_evidence
```

该命令同时生成 `spoken_revision_sheet.html`。只有 `claim_evidence_gate.json` 通过且修订表 `pending_count=0`，才允许进入素材生成和渲染。

生成导演分镜包：

```bash
.venv/bin/python scripts/dasheng_video_director.py \
  --lane explainer_html_video \
  --article-html <article.html> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/video_director
```

VOX 调查分镜包：

```bash
.venv/bin/python scripts/dasheng_video_director.py \
  --lane vox_explainer_video \
  --article-html <article.html> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/vox_director
```

如果字幕来自粗剪前素材，先锁定离散时间轴：

```bash
.venv/bin/python scripts/video_timeline_edl.py \
  --scene-plan <precut_scene_plan.json> \
  --edl <roughcut_edl.json> \
  --output <scene_plan.timeline_locked.json>
```

渲染前检查模板是否真正实现：

```bash
.venv/bin/python scripts/video_renderer_contract_gate.py \
  --scene-plan <scene_plan.json> \
  --renderer-contract <renderer_contract.json> \
  --output <renderer_contract_gate.json>
```

生成 Remotion 主时间轴渲染工程：

```bash
.venv/bin/python scripts/build_remotion_renderer_pack.py \
  --scene-plan <scene_plan.claim_bound.json> \
  --source-video <roughcut.mp4> \
  --bgm <bgm.mp3> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/remotion_project
```

渲染后检查暗场脉冲、纯色空白转场、强视觉变化密度、时长漂移和响度：

```bash
.venv/bin/python scripts/video_render_qc.py \
  --video <final.mp4> \
  --scene-plan <scene_plan.json> \
  --output <render_qc_report.json>
```

完整 QC 通过后，绑定最终文件和全部门禁，生成唯一交付清单：

```bash
.venv/bin/python scripts/video_final_delivery.py \
  --lane explainer_html_video \
  --video <final.mp4> \
  --qc-report <render_qc_report.json> \
  --storyboard-gate <storyboard_review_gate.json> \
  --claim-evidence-gate <claim_evidence_gate.json> \
  --renderer-asset-gate <renderer_asset_gate.json> \
  --renderer-contract-gate <renderer_contract_gate.json> \
  --output <final_delivery_manifest.json>
```

真人口播分镜包：

```bash
.venv/bin/python scripts/dasheng_video_director.py \
  --lane talking_head_video \
  --srt <agent_proofread.srt> \
  --source-video <roughcut.mp4> \
  --roughcut-gate <roughcut_gate_report.json> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/video_director
```

数字人分镜包：

```bash
.venv/bin/python scripts/dasheng_video_director.py \
  --lane digital_human_video \
  --srt <dialogue_or_narration.srt> \
  --duration <master_duration_sec> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/digital_human_director
```

广告宣传片分镜包：

```bash
.venv/bin/python scripts/dasheng_video_director.py \
  --lane commercial_promo_video \
  --commercial-brief <commercial_brief.json> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/commercial_promo_video/director_scene_plan
```

该入口会统一输出：

- `scene_plan.json`
- `storyboard_template_review.html`
- `director_checkpoint.json`
- 无头视频额外输出 `explainer_storyboard.raw.json` 和 `storyboard_preview.html`
- 真人口播额外输出 `talking_head_timeline.raw.json`

生成某阶段 checkpoint：

```bash
.venv/bin/python scripts/video_pipeline_governance.py checkpoint explainer_html scene_plan \
  --artifact script=<script.json> \
  --artifact scene_plan=<storyboard.json> \
  --status pending_review \
  --output <checkpoint.json>
```

检查视频工具注册表：

```bash
.venv/bin/python scripts/video_tool_registry.py --check
.venv/bin/python scripts/video_tool_registry.py --capability live_html_animation_recording
```

生成可浏览的技术注册站：

```bash
.venv/bin/python scripts/build_video_technical_site.py
```

技术站同时读取 `configs/workflow/creator_technology_candidates.json`，展示经过 Boutique Skills 评分和人工复核、且与自媒体生产直接相关的高分候选。候选仅用于发现和适配排期，不会自动进入生产主路由。

导演入口默认会读取全部工具、Skill 和保留项目登记，为每个分镜写入 `tool_routing`，并单独输出 `tool_routing_plan.json`。缺 API Key、模型权限、登录态、桌面 App 或标记为 `reference_only` 的项目只能进入后备/受阻列表，不能成为主路由。

## 强制红线

- 媒体产物、临时音频、视频、图片、样片训练结果不得写入 `skills/` 或项目根目录；默认写入 `~/Desktop/自媒体创作`。
- 无真人视频终片必须来自 live HTML/GSAP/Lottie 动画录制，不允许 PNG 拼接或 FFmpeg `zoompan` 冒充动画。
- 真人口播不得长期固定成“左上 HTML + 右下人物”，必须有语义驱动的 PIP、全屏证据、真人回归和转场。
- 粗剪未通过，不得进入真人口播终片渲染。
- Claim/Evidence Ledger 未通过，不得生成正式素材或完整成片。
- storyboard 模板审核未通过，不得进入无真人终片渲染。
- 图表、数字、表格必须来自文章、用户素材或验证数据链路，不允许装饰性假图表。
- 离散粗剪不得使用统一比例缩放旧时间轴；必须重新 ASR 或使用 keep-segment EDL。
- 官方网页或真实行情只能证明其覆盖的具体命题；背景素材不得标成直接证据。
- 模板名称只有在映射到生产级组件、变体和动效签名后才计入多样性。
- Remotion 是真人口播主时间轴；HTML Video、HyperFrames、GSAP 和 Lottie 作为场景动画工人或素材来源接入。
- 成片出现重复低亮度入场脉冲、分镜时长漂移或响度不达标时不得交付。
- `final_delivery_manifest.json` 指向的视频必须与完整 QC 实际检查文件完全一致；只有闪屏报告、旧版本 QC 或不同哈希均不得进入 Publish。
- 字幕必须覆盖完整口播/旁白，年份、数量、百分比优先使用阿拉伯数字，最终版不能只按字数比例粗分时间。

## 与 Skills 的关系

Skill 仍然负责任务执行：

- `dasheng-video-roughcut` 负责粗剪门禁。
- `dasheng-video-director` 负责真人口播和无真人视频的分镜、构图、模板、动效、转场、音频策略和审核门。
- `dasheng-video-talking-head` 负责真人口播包装规则和执行约束。
- `dasheng-video-explainer-html` 负责无真人科普 storyboard、模板审核和渲染约束。
- `dasheng-video-style-trainer` 负责样片学习。
- `dasheng-html-video-bridge` 负责外部 `html-video`、HTML/GSAP/Lottie 渲染衔接。

治理层只做“契约 + 门禁 + 注册表”。这能避免 skill 越写越重，也能避免每个脚本都重新发明流程。
