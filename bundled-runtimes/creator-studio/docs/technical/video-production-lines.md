# Video Production Lines

Date: 2026-08-14

本文件定义 video 环节的六条生产流水线。真人、VOX、无头口播、AI 数字人和广告宣传片可执行；电影短剧只注册规划能力，默认暂缓外部 API 调用。

六条线统一按：`素材接收 → 编剧/口播重写 → 导演分镜 → 素材生成 → 剪辑合成 → 渲染 → QC/交付` 执行。六个导演档案位于 `configs/video/director_registry.json`。

流水线治理、阶段产物契约、工具注册表和审核门见 [video-pipeline-governance.md](video-pipeline-governance.md)。视频生产不再直接从脚本跳到渲染，而是按：

`project run manifest -> pipeline manifest -> stage artifact -> tool registry -> checkpoint/review -> render/publish`

执行。对应配置位于：

- `configs/video/pipelines/talking_head.yaml`
- `configs/video/pipelines/vox_explainer.yaml`
- `configs/video/pipelines/explainer_html.yaml`
- `configs/video/pipelines/digital_human.yaml`
- `configs/video/pipelines/cinematic_short_drama.yaml`
- `configs/video/pipelines/commercial_promo.yaml`
- `configs/video/pipelines/style_training.yaml`
- `configs/video/director_registry.json`
- `configs/video/artifact_schemas/*.schema.json`
- `configs/video/tool_registry.json`
- `configs/workflow/project_run_manifest.schema.json`

## Lane A: 真人出镜口播

定位：用户提供真人口播素材，系统完成粗剪、音频优化、字幕校对、导演时间轴、证据层、HTML 贴纸/图表、转场与质检。

导演机制见 [video-editing-driving-mechanism.md](video-editing-driving-mechanism.md)。Lane A 不按“每句话贴一个模板”执行，而按 `speaker_anchor -> claim_closeup -> evidence_fullscreen -> broll_with_pip -> speaker_return` 状态机执行。编辑微镜头生成后，必须先归并为 8-12 个核心命题并通过 Claim/Evidence Ledger，才允许生成正式素材。

外部依赖：

- `html-video` 和 `html-anything` 都是外部依赖，不进入本仓库，不锁版本。
- 首次使用或换机器时运行 `.venv/bin/python scripts/ensure_video_external_deps.py --dep all --mode install --install-node-deps`。
- 默认路径可用 `HTML_VIDEO_ROOT` / `HTML_ANYTHING_ROOT` 覆盖。
- MiniMax CLI 是配音、配乐、图片生成、口播音频生成的默认入口；使用前运行 `mmx auth status --no-color` 和 `mmx quota --no-color`。

第一产物：

```bash
.venv/bin/python scripts/video_director_timeline.py \
  --srt <agent_proofread.srt> \
  --source-video <speaker.mp4> \
  --title "<title>" \
  --output <talking_head_timeline.json>
```

关键约束：

- 真人音频/视频是主时间轴。
- 先用 FunASR/剪映或 `cut-talking-head` 清除口误、重说、口水词、重复和静音，再进入导演包装。
- 粗剪后可做低风险滤镜、美颜、降噪、压缩、响度放大和限幅；不得造成脸部失真、爆音、抽吸或音画漂移。
- Remotion 是主时间轴与合成器；HTML Video、HyperFrames、GSAP 和 Lottie 负责具体场景动画。
- HTML 动画只做证据层、标题卡、图表卡或素材层，不替代真人层。
- 字幕必须先经过 Agent 语义校对，再进入终版渲染。
- 图表和数据必须来自 Draft 文章或已验证数据源，不允许假图。
- 事实、估值比较、因果与历史命题必须有逐项直接证据；传闻、预测和测算必须在画面中披露。
- 最终视频不允许出现开发说明、slot 名、position 名等工作流标签。

参考节奏：

| 指标 | 目标 |
| --- | --- |
| 中位视觉段落 | 2.5-4 秒 |
| B-roll/证据画面占比 | 45%-65% |
| 真人回归间隔 | 8-20 秒 |
| 人声音量 | 约 -16 LUFS |
| 字幕 | 1-2 行，语义断句，无重叠 |

## Lane B: 无真人 HTML 科普

定位：用户提供 HTML 文章，系统生成口播稿、TTS、分镜、HTML 动画、配乐和最终无真人财经视频。默认母版为横版 16:9，方形和竖版作为独立发布适配。

导演机制见 [video-editing-driving-mechanism.md](video-editing-driving-mechanism.md)。Lane B 不做 PPT 翻页，而按 `hook_card -> question_setup -> chapter_card -> evidence_scene -> logic_animation -> cinematic_bridge -> recap_card` 状态机执行。

生产音频/素材默认走 MiniMax CLI：

```bash
mmx speech synthesize \
  --text-file <scene.txt> \
  --out <voice.wav> \
  --model speech-2.8-hd \
  --voice "Chinese (Mandarin)_Radio_Host" \
  --speed 1.08 \
  --format wav \
  --sample-rate 44100 \
  --channels 1 \
  --language Chinese

mmx music generate \
  --prompt "cinematic financial documentary, restrained tension, no vocals" \
  --instrumental \
  --out <bgm.mp3>

mmx image generate \
  --prompt "<article-specific visual prompt>" \
  --aspect-ratio 9:16 \
  --out <image.jpg>
```

第一产物：

```bash
.venv/bin/python scripts/build_html_anything_template_router.py \
  --output configs/video/html_anything_template_router.json

.venv/bin/python scripts/video_explainer_storyboard.py \
  --html <article.html> \
  --template-router configs/video/html_anything_template_router.json \
  --output <explainer_storyboard.json> \
  --preview-html <storyboard_preview.html>

.venv/bin/python scripts/build_html_anything_video_timeline.py \
  --storyboard <explainer_storyboard.json> \
  --article-html <article.html> \
  --template-router configs/video/html_anything_template_router.json \
  --output <html_anything_video_timeline.json>
```

关键约束：

- HTML 文章是事实源，不新建第二条事实链。
- 文章里的表格、图表、图片、claim 是分镜证据来源。
- 外部 `html-video` 是默认场景渲染器；Remotion 是主时间轴与最终合成器。
- 外部 `html-anything` 只提供视觉语言和模板参考。
- TTS、配乐、AI 配图默认使用 MiniMax CLI；macOS `say` 只能作为本地烟测 fallback。
- 渲染前必须先把文章内容部件映射到 HTML Anything 模板，不能再直接用自绘兜底卡片生成全片。
- 视觉层默认采用 HyperFrames 思路；GSAP 控制动画时间轴；Lottie 只做辅助动效素材。
- 数据图表、表格、截图和来源证据必须来自文章或取数链路，Lottie 不能伪装成事实图表。
- 先审 storyboard，再通过 Claim/Evidence、素材、渲染器契约和最终 QC 门禁。

参考节奏：

| 指标 | 目标 |
| --- | --- |
| 平均 scene | 5-7 秒 |
| 中位 scene | 4-5 秒 |
| 证据画面 | 每 20-35 秒至少一次 |
| 章节卡 | 每 45-90 秒一次 |
| 动效 | 数据 reveal、文档 zoom、路径高亮、标题 kinetic |

### Motion Stack

| Layer | Responsibility |
| --- | --- |
| HyperFrames | HTML/CSS/JS 场景组织和本地渲染模型 |
| GSAP | scene 内动画编排：入场、出场、错峰、路径、数字、图表 reveal |
| Lottie | 现成设计师动效：警报、数据流、金融 ticker、文档扫描、品牌 outro |
| Draft Data | 真实事实层：图表、表格、截图、来源、claim |

`scripts/render_html_anything_timeline_pack.py --motion-runtime auto` 会从外部 `html-video` 读取并内联真实 `gsap` / `lottie-web`。如果依赖缺失，用 `scripts/ensure_video_external_deps.py --dep html-video --mode install --install-node-deps` 补齐。

## Lane C: VOX 调查解释视频

定位：从确认 Draft 提炼一个中心问题，用 3-6 个证据支柱组织历史、机制、新闻/访谈/现场资料、数据、反证和有限结论。它不是无头口播的视觉主题，而是独立叙事和研究链路。

状态机：

`cold_open -> central_question -> evidence_map -> historical_context -> mechanism_explainer -> field_or_human_evidence -> counterargument -> data_resolution -> qualified_conclusion`

关键约束：

- 默认 `1920x1080`、16:9、30fps。
- 先锁中心问题，再检索证据；不得把文章章节标题直接当最终分镜结构。
- 精确搜索事件、公司、人物、日期和论点，优先新闻、访谈、演讲、历史影像、现场资料、原始文档和真实数据。
- 真实素材必须记录来源、时间段、本地路径和 direct/context 关系；泛化 B-roll 不能冒充证据。
- 新闻主播默认 PIP 或分屏；只有人物原话或原始下三分之一是证据时才全屏。
- 必须保留反证或边界条件，并在结尾区分已知、推演、条件和未知。
- 口播先拆成 10-25 秒叙事审核段，批准后再拆成约 8-12 秒生产镜。
- 网页、文档、图表、重点字卡和高价值转场优先绑定 Shotcraft 卡片并在本地 Remotion 实现；真实证据走真实素材 Remotion；只有抽象隐喻和解释性 B-roll 才进入 Gemini/Omni。
- Gemini Omni 只生成逐镜运动底片；Remotion 再叠加真实资料、图表、精确文字、字幕、配音和转场；FFmpeg 负责最终封装检查。
- MMX、Seedance、HTML/GSAP/HyperFrames 保留为单镜后备，不再是 VOX 默认镜头生成器。
- 禁止重新接入已剔除的 `vox-director` 或 AtlasCloud。

入口：

```bash
.venv/bin/python scripts/dasheng_video_director.py \
  --lane vox_explainer_video \
  --article-html <article.html> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/vox_director
```

## Lane D: AI 数字人口播与访谈

定位：用授权肖像和每位说话人的独立音轨生成单人数字人口播或双人 AI 访谈。

主路线：

`授权肖像 → imagegen 角色参考图 → omni（Gemini 图生视频）口型/眨眼/微动作 → 无声人物源 → 数字人导演分镜 → Remotion 合成 → QC`

【2026-08-22 用户裁决：Luma 路线上一版已废弃，禁止再用 luma_dream_machine】

双人模式必须遵守：

- 两位人物分别建立 `speaker_id`、肖像、音轨、生成任务、短样和 QC。
- 不让一个图生视频任务同时控制两个人物口型。
- 每个对话 turn 只有一个 `active_speaker`；非发言者只保留自然待机。
- 构图在双人全景、发言者近景、反应镜头和分屏之间切换。
- 两个人物源都静音，各自 MiniMax 音轨只在对应 turn 挂载一次。
- 发布必须包含 AI 生成披露。

## Lane E: 电影短剧（Deferred）

定位：登记电影感短剧的编剧、角色圣经、连续性、逐镜分镜、官方视频模型 API、声音和后期技术栈。

当前状态：`execution_enabled=false`。只允许生成剧本和分镜规划包；用户明确批准供应商、预算、角色授权和内容安全边界后，才可启用 Seedance、Gemini/Veo 或 MiniMax 官方路线。第三方聚合商不进入默认路由。

## Lane F: 广告宣传片

定位：把品牌或产品 Brief 转成 15、30、60 秒品牌片、产品宣传片、新品预告或效果广告，默认竖版 `9:16`。

主路线：

`品牌/产品素材接收 → 广告脚本重写 → 导演分镜 → 产品与品牌素材生成 → Remotion 合成 → 多比例渲染 → 品牌/声明/QC 交付`

关键约束：

- 一条广告只保留一个主要目标和一个主 CTA。
- 脚本必须包含钩子、产品承诺、卖点收益、Proof、品牌记忆和 CTA；出现 Offer 时必须有有效免责声明。
- 产品能力、比较、客户结果、价格和优惠必须绑定来源；生成式画面不能冒充真实产品 UI、客户证言或效果证明。
- 官方 Logo、产品录屏、实拍和品牌资产优先；概念视觉、氛围和转场才进入生成式路线。
- 产品、Logo、字幕、Offer、法律说明和 CTA 必须通过 `9:16`、`16:9`、`1:1`、`4:5` 安全区检查。

入口：

```bash
.venv/bin/python scripts/dasheng_video_director.py \
  --lane commercial_promo_video \
  --commercial-brief <commercial_brief.json> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/commercial_promo_video/director_scene_plan
```

## Skill Mapping

| Skill | 责任 |
| --- | --- |
| `dasheng-video-talking-head` | Lane A 导演时间轴和真人包装规则 |
| `scripts/video_claim_evidence_ledger.py` | 将微分镜归并为核心命题，生成证据缺口门禁和 HTML 审核页 |
| `scripts/build_remotion_renderer_pack.py` | 生成 10 个生产级渲染器族及 Remotion 主时间轴工程 |
| `dasheng-video-explainer-html` | Lane B HTML 文章分镜和无真人科普规则 |
| `dasheng-video-vox` | Lane C 中心问题、证据地图、资料拼贴、反证和有限结论规则 |
| `dasheng-digital-human-talking-head` | Lane D 单人/双人数字人物源、短样和身份/口型 QC |
| `dasheng-commercial-promo-video` | Lane F 品牌 Brief、广告脚本、产品展示、Proof、品牌记忆、CTA 与多比例安全区 |
| `configs/video/director_registry.json` | 六个导演的阶段能力、核心工具、备用工具和硬门禁 |
| `cinematic_planning_router` | Lane E 可立即使用的剧本、角色圣经、连续性和分镜规划能力 |
| `cinematic_external_api_router` | Lane E 的禁用态官方视频生成路由和启用前检查 |
| `dasheng-video-omni-browser` | 使用 Chrome 已登录的 Gemini Omni 将参考图逐镜生成约 10 秒视频并下载回项目 |
| `dasheng-html-video-bridge` | 调用 html-video 创建/预览/渲染项目 |
| `dasheng-html-anything-bridge` | 借用 HTML Anything 的视觉模板和文章 HTML 经验 |
| `media-downloader` | 搜索和下载外部图片、视频素材 |
| MiniMax CLI `mmx` | 生产配音、配乐、AI 图片、口播音频，不在项目中硬编码 API key |
| `scripts/ensure_video_external_deps.py` | 检查、安装或更新 video 外部依赖，不做版本锁 |
| `scripts/build_html_anything_template_router.py` | 扫描 HTML Anything 75 个模板并生成内容部件路由表 |
| `scripts/build_html_anything_video_timeline.py` | 将文章 storyboard 扩展成 HTML Anything 模板时间轴 |

## Current Implementation

- `scripts/video_director_timeline.py`
- `scripts/video_explainer_storyboard.py`
- `scripts/video_driver_rules.py`
- `scripts/build_html_anything_template_router.py`
- `scripts/build_html_anything_video_timeline.py`
- `configs/video/video_editing_driver_rules.json`
- `configs/video/director_registry.json`
- `configs/video/pipelines/digital_human.yaml`
- `configs/video/pipelines/cinematic_short_drama.yaml`
- `configs/video/pipelines/commercial_promo.yaml`
- `skills/dasheng-commercial-promo-video/`
- `tests/test_video_production_schemas.py`
- `tests/test_html_anything_template_router.py`

这些文件先稳定中间结构。`video_driver_rules.py` 已把 `video_editing_driver_rules.json` 接入真人口播和无真人分镜，输出包含 `beat_class`、`driver_scores`、`director_state/shot`、`transition_to_next`、`audio`。`render_html_anything_timeline_pack.py` 负责生成 scene HTML 状态类、转场动效和分镜包；最终视频必须走 `render_html_anything_scene_pack_animated.py` 逐场景录制真实 HTML/GSAP/Lottie 动画。旧的静态截图、PNG 拼接和 Ken Burns/zoompan 路径已从生产链路删除。后续剪映路径、html-video 项目生成都应读取 `talking_head_timeline.json`、`explainer_storyboard.json` 或 `html_anything_video_timeline.json`，不要各自重新发明分镜格式。
