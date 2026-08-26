# Newma Media Studio项目目录

> 本文件由 `scripts/build_project_catalog.py` 根据机器注册表生成，请不要手工维护列表。

更新日期：`2026-08-14`

## 总览

- 正式主链：`intake -> brief -> draft -> transwrite -> publish -> postmortem`
- 正式/按需 Skill 登记：`26`
- 已保留上游项目：`40`
- 候选储备：`18`
- 已剔除项目：`13`
- 内部功能模块：`10`

### 储备分布

| 类别 | 数量 |
| --- | ---: |
| `catalog` | 1 |
| `design` | 9 |
| `publish` | 14 |
| `render` | 2 |
| `video` | 14 |

### 级别分布

| 级别 | 数量 |
| --- | ---: |
| `account_management_console` | 1 |
| `advisory` | 1 |
| `archived_historical_fallback` | 1 |
| `backup` | 13 |
| `browser_cli_fallback` | 1 |
| `browser_session_fallback` | 1 |
| `catalog_source` | 1 |
| `experimental` | 2 |
| `preferred_local_experiment` | 1 |
| `primary_execution` | 1 |
| `production_candidate` | 14 |
| `reference` | 2 |
| `reference_only` | 1 |

## 六阶段处理流程

### 1. 内容采集 (`intake`)

- 入口：`newma-daily-intake` / `scripts/run_stage1_intake.py`
- 输入：网页、公众号、热点数据源、人工指定素材
- 处理：采集 -> 标准化 -> 去重 -> 聚类 -> 保留来源
- 输出：intake_manifest.json 、raw/intake_records.json 、01_内容采集_报告.md
- 门禁：无

### 2. 选题与研究 Brief (`brief`)

- 入口：`newma-daily-phase2` / `scripts/phase2_rebuilder.py`
- 输入：intake_manifest.json 、raw/intake_records.json
- 处理：事件归并 -> 角度分流 -> 证据缺口识别 -> 题卡排序
- 输出：brief_manifest.json 、topic_cards.json 、selected_topics.json
- 门禁：selected_topics.json

### 3. 初稿与证据底稿 (`draft`)

- 入口：`newma-daily-draft` / `scripts/build_stage3_draft.py`
- 输入：brief_manifest.json 、selected_topics.json
- 处理：事实底稿 -> 数据/图表 -> 长文结构 -> HTML -> 封面与插图意图
- 输出：draft_manifest.json 、final_structure_snapshot.json 、每题 Markdown/HTML
- 门禁：final_structure_snapshot.json

### 4. 多通路转写生产 (`transwrite`)

- 入口：`newma-stage-transwrite` / `scripts/build_stage4_transwrite.py`
- 输入：draft_manifest.json 、final_structure_snapshot.json 、transwrite_decision.json
- 处理：公众号文章 -> 普通无头 HTML 视频 -> VOX 调查解释视频 -> 真人出镜口播 -> AI 数字人口播或双人访谈 -> 电影短剧规划包（默认暂缓执行） -> 广告宣传片 -> 播客包 -> 导演与渲染 QC
- 输出：transwrite_manifest.json 、lane manifests 、可发布文章/视频/音频包
- 门禁：publish_decision.json

### 5. 账号路由与发布 (`publish`)

- 入口：`newma-stage-publish` / `scripts/build_stage5_publish.py`
- 输入：transwrite_manifest.json 、publish_decision.json
- 处理：平台包装 -> 账号矩阵 -> 表单预检 -> 本地 API/CLI/浏览器执行 -> 回执验真
- 输出：publish_manifest.json 、channel packs 、publish_verification_report.json 、平台链接/稿件 ID
- 门禁：Publish Guard

### 6. 复盘与知识回写 (`postmortem`)

- 入口：`newma-daily-postmortem` / `scripts/postmortem_writeback.py`
- 输入：publish_manifest.json 、publish verification 、平台数据 、人工反馈
- 处理：效果聚合 -> 差异归因 -> 继续/停止/试验建议 -> DNA 与规则回写
- 输出：postmortem_manifest.json 、08_复盘报告.md 、08_L1回写建议.md
- 门禁：无

## 六阶段储备路由

> 储备路由只表示对应环节可以发现该项目；`cloned_not_promoted`、`blocked` 和 `methodology_only` 不会取代生产主路由。

| 环节 | 项目 | 角色 | 可用性 | 执行方式 | 回退 | 阻断/约束 |
| --- | --- | --- | --- | --- | --- | --- |
| 内容采集 (`intake`) | — | — | — | — | 未强行登记 | — |
| 选题与研究 Brief (`brief`) | `governed-dcf-skill` | `auditable_valuation_methodology` | `methodology_only` | `reference_only` | anthropic-fs-financial-analysis-dcf-model | 禁止克隆、上游无许可证 |
| 初稿与证据底稿 (`draft`) | `taste-skill` | `visual_language_and_anti_slop_review` | `ready` | `advisory_skill` | high-end-visual-design、brand-guidelines |  |
| 初稿与证据底稿 (`draft`) | `impeccable` | `html_css_design_audit_reserve` | `ready` | `advisory_skill` | design-taste-frontend、review-animations | newma_adapter_required、browser_audit_smoke_test_required |
| 初稿与证据底稿 (`draft`) | `governed-dcf-skill` | `dcf_assumption_audit_methodology` | `methodology_only` | `reference_only` | anthropic-fs-financial-analysis-dcf-model | 禁止克隆、上游无许可证 |
| 多通路转写生产 (`transwrite`) | `baoyu-skills` | `article_visual_cover_and_infographic_suite` | `ready` | `skill_suite_with_first_party_provider_allowlist` | imagegen、newma-lemon-illustrations |  |
| 多通路转写生产 (`transwrite`) | `minimax-skills` | `official_model_visual_and_brand_suite` | `ready` | `official_model_and_local_skills` | design-taste-frontend、brand-guidelines |  |
| 多通路转写生产 (`transwrite`) | `seedance2-skill` | `official_generated_broll_prompt_route` | `ready` | `official_model_skill` | newma-video-broll-generator、remotion-video-toolkit |  |
| 多通路转写生产 (`transwrite`) | `claude-code-video-toolkit` | `local_remotion_template_and_transition_reference` | `cloned_not_promoted` | `local_reference_only` | remotion-video-toolkit、newma-html-video-bridge | local_template_adapter_required |
| 多通路转写生产 (`transwrite`) | `video-shotcraft` | `shot_design_and_remotion_reserve` | `adapter_ready` | `newma_vox_adapter` | remotion-video-toolkit、newma-video-director |  |
| 多通路转写生产 (`transwrite`) | `openchatcut` | `primary_collaborative_editor_runtime` | `adapter_ready` | `complete_upstream_thin_adapter` | roughcut_review、html_video_project_studio、newma-video-editing-bridge |  |
| 多通路转写生产 (`transwrite`) | `video-autopilot-kit` | `batch_video_production_adapter_reserve` | `blocked` | `adapter_required` | newma-stage-transwrite、newma-video-editing-bridge | no_standard_skill_md、capcut_schema_review_required、output_contract_guard_required、smoke_test_required |
| 多通路转写生产 (`transwrite`) | `gsap-skills` | `html_motion_suite_reserve` | `cloned_not_promoted` | `suite_router` | hyperframes:gsap、animation-vocabulary、improve-animations | suite_router_adapter_required、html_video_performance_smoke_test_required |
| 多通路转写生产 (`transwrite`) | `taste-skill` | `scene_visual_review` | `ready` | `advisory_skill` | high-end-visual-design |  |
| 多通路转写生产 (`transwrite`) | `impeccable` | `html_scene_browser_qc_reserve` | `ready` | `advisory_skill` | design-taste-frontend、review-animations | newma_adapter_required、browser_audit_smoke_test_required |
| 账号路由与发布 (`publish`) | `impeccable` | `cover_and_publish_surface_visual_qc_reserve` | `ready` | `advisory_skill` | design-taste-frontend、newma-stage-publish | newma_adapter_required、browser_audit_smoke_test_required |
| 账号路由与发布 (`publish`) | `video-autopilot-kit` | `batch_delivery_and_capcut_handoff_reserve` | `blocked` | `adapter_required` | newma-stage-publish、qianfan-sync | no_standard_skill_md、capcut_schema_review_required、output_contract_guard_required |
| 复盘与知识回写 (`postmortem`) | `opencli` | `authenticated_platform_readback` | `ready` | `browser_cli` | manual_platform_snapshot |  |
| 复盘与知识回写 (`postmortem`) | `postiz` | `multi_platform_metrics_console` | `cloned_not_promoted` | `external_server_adapter` | opencli、manual_platform_snapshot | server_stack_not_installed、analytics_export_adapter_required |
| 复盘与知识回写 (`postmortem`) | `wechatpy` | `official_wechat_datacube_metrics` | `blocked` | `official_api_python_dependency` | manual_wechat_backend_snapshot | candidate_not_cloned、wechat_account_permission_required |
| 复盘与知识回写 (`postmortem`) | `mixpost` | `platform_analytics_console_reserve` | `blocked` | `external_server_adapter` | postiz、opencli | candidate_not_cloned、analytics_contract_smoke_test_required |
| 复盘与知识回写 (`postmortem`) | `xhs-downloader` | `xiaohongshu_competitor_metrics_collector` | `cloned_not_promoted` | `cli_adapter` | zeeschuimer、manual_competitor_capture | login_state_required、metric_field_normalizer_required |
| 复盘与知识回写 (`postmortem`) | `4cat` | `cross_platform_competitor_analysis_runtime` | `blocked` | `external_service_dataset_handoff` | minet、xhs-downloader | candidate_not_cloned、dataset_handoff_adapter_required |
| 复盘与知识回写 (`postmortem`) | `mediacrawler` | `domestic_multi_platform_competitor_worker` | `blocked` | `isolated_collection_worker` | xhs-downloader、zeeschuimer、manual_competitor_capture | candidate_not_cloned、login_state_guard_required、collection_rate_policy_required |
| 复盘与知识回写 (`postmortem`) | `minet` | `public_competitor_discovery_cli` | `blocked` | `cli_adapter` | opencli、manual_competitor_search | candidate_not_cloned、competitor_dataset_adapter_required |
| 复盘与知识回写 (`postmortem`) | `tiktok-api` | `tiktok_public_metrics_adapter` | `blocked` | `optional_python_adapter` | zeeschuimer、manual_platform_snapshot | candidate_not_cloned、unofficial_api_change_risk |
| 复盘与知识回写 (`postmortem`) | `twscrape` | `x_public_metrics_adapter` | `blocked` | `optional_python_adapter` | opencli、manual_competitor_capture | candidate_not_cloned、account_rotation_policy_required |
| 复盘与知识回写 (`postmortem`) | `youtube-operational-api` | `youtube_public_data_fallback` | `blocked` | `fallback_service` | official_youtube_data_api、minet | candidate_not_cloned、official_api_must_remain_primary |
| 复盘与知识回写 (`postmortem`) | `yt-dlp` | `public_video_sample_and_metadata_cli` | `blocked` | `cli_json_adapter` | minet、official_youtube_data_api | candidate_not_cloned、competitor_dataset_adapter_required |
| 复盘与知识回写 (`postmortem`) | `bertopic` | `comment_theme_and_question_clustering` | `blocked` | `analysis_dependency` | llm_topic_summary | candidate_not_cloned、chinese_embedding_selection_required |
| 复盘与知识回写 (`postmortem`) | `pyabsa` | `aspect_level_comment_opinion_analysis` | `blocked` | `analysis_dependency` | llm_aspect_summary | candidate_not_cloned、chinese_domain_calibration_required |
| 复盘与知识回写 (`postmortem`) | `dowhy` | `cross_run_causal_hypothesis_refutation` | `blocked` | `gated_analysis_dependency` | descriptive_comparison | candidate_not_cloned、minimum_sample_gate_required、causal_graph_required |

## 高分自媒体创作备选技术

> 候选项目供各环节导演发现与安排适配，不会绕过依赖、许可证、质量门禁或人工复核成为生产主路由。

| 项目 | 评分 | 类别 | 环节 | 可用性 | 依赖 | 阻断项 |
| --- | ---: | --- | --- | --- | --- | --- |
| `codex-imagegen-luma-animal-presenter` | 96/100 | `animal_head_digital_human` | transwrite | `ready_requires_signed_in_luma` | codex_builtin_imagegen、luma_dream_machine_account、minimax_audio | portrait_consent_required、image_review_required、generation_credits_required、short_sample_review_required |
| `joyvasa-liveportrait` | 94/100 | `local_digital_human` | transwrite | `ready_setup_on_first_use` | python_3_10、pytorch_mps、ffmpeg、local_model_weights、minimax_audio | portrait_consent_required、short_sample_review_required、insightface_weight_license_review_or_detector_swap |
| `echomimic-v3` | 89/100 | `semi_body_digital_human` | transwrite | `cuda_experiment_only` | cuda_12_1、12gb_plus_vram、large_model_weights | current_machine_has_no_cuda、mac_port_not_supported、quality_benchmark_required |
| `sadtalker` | 85/100 | `digital_human_fallback` | transwrite | `fallback_not_installed` | legacy_python_stack、ffmpeg、local_model_weights | older_visual_quality、modern_mac_dependency_compatibility、performance_benchmark_required |
| `html-anything` | 96/100 | `html_publishing` | draft、transwrite、publish | `ready` | browser、node |  |
| `taste-skill` | 92/100 | `visual_direction` | draft、transwrite、publish | `ready` |  |  |
| `impeccable` | 92/100 | `visual_quality_control` | draft、transwrite、publish | `existing_reserve` | browser、node | newma_adapter_required、browser_audit_smoke_test_required |
| `emilkowalski-skills` | 92/100 | `motion_design_review` | transwrite | `ready` |  |  |
| `gsap-skills` | 92/100 | `html_motion` | transwrite | `existing_reserve` | node | suite_router_adapter_required、html_video_performance_smoke_test_required |
| `ian-xiaohei-illustrations` | 92/100 | `article_illustration` | draft、transwrite | `ready` |  |  |
| `baoyu-skills` | 92/100 | `article_visual_production` | draft、transwrite、publish | `ready` | codex_or_official_model_provider |  |
| `humanizer-zh` | 92/100 | `chinese_copy_editing` | draft、transwrite | `candidate_not_cloned` |  | style_dna_compatibility_review_required、anchor_preservation_regression_required |
| `khazix-skills` | 92/100 | `longform_writing` | brief、draft | `candidate_not_cloned` |  | qoder_context_compatibility_review_required、evidence_contract_regression_required、style_dna_regression_required |
| `finance-skills-social-readers` | 92/100 | `multi_source_research` | intake、brief | `candidate_not_cloned` | opencli、browser_session_for_some_sources | read_only_adapter_required、source_dedupe_contract_required、cookie_source_policy_required |
| `video-autopilot-kit` | 88/100 | `batch_video_production` | transwrite、publish、postmortem | `existing_reserve` | ffmpeg_with_libass、python、capcut_optional | newma_adapter_required、capcut_schema_review_required、output_contract_guard_required、smoke_test_required |
| `uzi-skill` | 86/100 | `finance_content_research` | brief、draft、transwrite | `candidate_not_cloned` | python、optional_browser、multiple_public_data_sources | heavy_runtime_review_required、data_provenance_adapter_required、persona_authority_guard_required、browser_state_guard_required |
| `agent-skills-launch-pack` | 85/100 | `account_growth_operations` | brief、publish、postmortem | `existing_retained` |  |  |

## 功能模块

| 模块 | 主要路径 | 职责 |
| --- | --- | --- |
| Creator Studio 运行控制 | `configs/workflow/newma_creator_studio_registry.json`<br>`scripts/newma_creator_control.py`<br>`configs/workflow/project_run_manifest.schema.json` | 六阶段与节点注册、状态快照、素材校验、交付物转接、本地能力检测与调用、通知投影 |
| 总控与契约 | `scripts/run_mainline_stage.py`<br>`scripts/canonical_workflow.py`<br>`skills/newma-media-sop` | 阶段路由、manifest/gate、输出路径、失败恢复 |
| 采集、选题与写作 | `skills/newma-daily-intake`<br>`skills/newma-daily-phase2`<br>`skills/newma-daily-draft` | 来源池、题卡、研究底稿、文章 HTML |
| 财经数据与证据 | `skills/newma-finance-data`<br>`scripts/video_claim_evidence_ledger.py`<br>`scripts/video_finance_evidence.py`<br>`scripts/video_official_evidence.py` | 数据表、图表、官方文档、命题-证据台账 |
| 视频导演与分镜 | `skills/newma-video-director`<br>`skills/newma-digital-human-talking-head`<br>`skills/newma-commercial-promo-video`<br>`configs/video/director_registry.json`<br>`configs/video/pipelines`<br>`scripts/newma_video_director.py` | 六类导演注册与阶段工具路由、真人/数字人人物源、广告品牌与产品资产、口播节奏、分镜、构图、真实 B-roll、工具路由 |
| 动画与渲染 | `skills/newma-html-video-bridge`<br>`skills/newma-caption-motion`<br>`scripts/build_remotion_renderer_pack.py` | HTML Video、Remotion、HyperFrames、GSAP/Lottie、字幕与动态图表 |
| 剪辑与媒体处理 | `skills/newma-video-roughcut`<br>`skills/newma-ffmpeg-toolkit`<br>`skills/newma-video-editing-bridge` | ASR、粗剪、EDL、FFmpeg、媒体 QC |
| 发布与账号中心 | `skills/newma-stage-publish`<br>`configs/publish`<br>`scripts/start_publish_console.py` | 多账号、多平台、封面/标签/声明、发布队列、链接回收 |
| 范式学习与进化 | `skills/newma-paradigm-profiler`<br>`skills/newma-video-style-trainer`<br>`skills/newma-video-self-learning` | 文章范式、视频 DNA、每日增量学习、导演笔记 |
| 质量门禁与治理 | `tests`<br>`scripts/workflow_doctor.py`<br>`scripts/video_render_qc.py`<br>`scripts/publish_guard.py` | 契约测试、渲染 QC、发布验真、仓库卫生 |

## Skill 注册表

| Skill | 版本 | 状态 | 职责 |
| --- | --- | --- | --- |
| `newma-media-sop` | 1.0.0 | ✅ 正式 | 总控入口，唯一正式编排 skill |
| `newma-paradigm-profiler` | 1.0.0 | ✅ 正式 | 可选前置资产，提炼文章结构范式 |
| `newma-daily-intake` | 1.0.0 | ✅ 正式 | 内容采集阶段 |
| `newma-daily-phase2` | 1.0.0 | ✅ 正式 | 选题分析阶段（替代 newma-daily-brief） |
| `newma-daily-draft` | 1.0.0 | ✅ 正式 | 写作与可发布底稿阶段 |
| `newma-stage-transwrite` | 1.0.0 | ✅ 正式 | 转写生产阶段，生成公众号/普通无头/VOX/真人/播客包 |
| `newma-stage-publish` | 1.0.0 | ✅ 正式 | 发布执行阶段 |
| `newma-daily-postmortem` | 1.0.0 | ✅ 正式 | 复盘与知识回写 |
| `newma-finance-data` | 0.1.0 | ✅ 正式 | Draft 金融数据增强工具，生成 Chart.js 图表规格 |
| `newma-style-profiler` | 1.0.0 | ✅ 正式 | 文风 Style DNA 提炼 |
| `feishu-doc-creator` | 1.0.0 | ✅ 正式 | 飞书文档创建辅助 |
| `newma-html-video-bridge` | 0.1.0 | ✅ 正式 | 转写阶段调用本地 html-video 的口播视频桥接 skill |
| `newma-html-anything-bridge` | 0.1.0 | ✅ 正式 | Draft/Transwrite 调用 HTML Anything 模板和视觉语言的桥接 skill |
| `newma-lemon-illustrations` | 0.1.0 | ✅ 正式 | 口播视频默认概念卡通插画系统，使用柠檬人替代上游角色 |
| `newma-video-talking-head` | 0.2.0 | ✅ 正式 | 真人与数字人有头口播的导演时间轴、证据层和包装工作流 |
| `newma-digital-human-talking-head` | 0.1.0 | ✅ 正式 | 一张授权照片加 MiniMax 音频，在本地生成数字人口播并接入真人导演链 |
| `newma-video-explainer-html` | 0.1.0 | ✅ 正式 | HTML 文章转无真人财经视频，默认横版 16:9，支持方形和竖版适配 |
| `newma-vox-skills` | 1.0.0 | ✅ 正式 | VOX 制作统一入口，编排导演分镜、Codex 参考图、Gemini API/浏览器、Remotion 二剪与质检 |
| `newma-video-vox` | 1.3.0 | 🧰 内部 | `newma-vox-skills` 的调查结构、导演分镜与视觉语法组件 |
| `newma-video-omni-browser` | 0.1.0 | 🧰 按需 | 通过 Chrome 已登录的 Gemini Omni 将参考图生成约 10 秒逐镜视频 |
| `newma-video-broll-generator` | 0.1.0 | 🧰 按需 | B-roll、Vox 拼贴、生成式插入片段和贴纸动画的证据安全路由 |
| `newma-caption-motion` | 0.1.0 | 🧰 按需 | 将 SRT/词级时间戳路由为 HyperFrames 或 Remotion 字幕动效 |
| `newma-video-editing-bridge` | 0.1.0 | 🧰 按需 | 内部管线、剪映、chengfeng-videocut 与 video-use 的全流程剪辑路由 |
| `newma-ffmpeg-toolkit` | 0.1.0 | 🧰 按需 | 受控媒体探测、转码、裁剪、音频提取和图片水印工具 |
| `social-auto-upload-bridge` | 0.2.0 | ✅ 正式 | Publish 阶段调用外部 social-auto-upload，支持四平台预演、登录检查、确认执行与结果回填 |
| `bilibili-upload-bridge` | 0.1.0 | ✅ 正式 | Publish 阶段调用外部 B站上传工具的投稿桥 |

## 保留上游项目

第三方源码默认克隆到 `vendor/reserved/` 或 `vendor/publish/`，不进入主仓库 Git 历史。

| 项目 | 类别 | 级别 | 依赖状态 | 本地路径 | 上游 |
| --- | --- | --- | --- | --- | --- |
| `boutique-openclaw-skills` | `catalog` | `catalog_source` | `source_ready` | `vendor/reserved/catalog/boutique-openclaw-skills` | [upstream](https://github.com/leecyno1/boutique-openclaw-skills.git) |
| `anthropics-skills` | `design` | `production_candidate` | `skill_ready` | `vendor/reserved/design/anthropics-skills` | [upstream](https://github.com/anthropics/skills.git) |
| `baoyu-skills` | `design` | `production_candidate` | `dependency_ready_with_official_provider_allowlist` | `vendor/reserved/design/baoyu-skills` | [upstream](https://github.com/JimLiu/baoyu-skills.git) |
| `emilkowalski-skills` | `design` | `production_candidate` | `skill_ready` | `vendor/reserved/design/emilkowalski-skills` | [upstream](https://github.com/emilkowalski/skills.git) |
| `guizang-social-card-skill` | `design` | `production_candidate` | `dependency_ready` | `vendor/reserved/design/guizang-social-card-skill` | [upstream](https://github.com/op7418/guizang-social-card-skill.git) |
| `inference-skills` | `design` | `advisory` | `local_advisory_skills_ready` | `vendor/reserved/design/inference-skills` | [upstream](https://github.com/inference-sh/skills.git) |
| `media-downloader` | `design` | `production_candidate` | `dependency_ready` | `vendor/reserved/design/media-downloader` | [upstream](https://github.com/yizhiyanhua-ai/media-downloader.git) |
| `minimax-skills` | `design` | `backup` | `skill_ready_official_provider_optional` | `vendor/reserved/design/minimax-skills` | [upstream](https://github.com/MiniMax-AI/skills.git) |
| `remotion-video-toolkit` | `design` | `production_candidate` | `skill_ready` | `vendor/reserved/design/remotion-video-toolkit` | [upstream](https://github.com/shreefentsar/remotion-video-toolkit.git) |
| `taste-skill` | `design` | `production_candidate` | `skill_ready` | `vendor/reserved/design/taste-skill` | [upstream](https://github.com/Leonxlnx/taste-skill.git) |
| `agent-skills-launch-pack` | `publish` | `backup` | `cloned` | `vendor/reserved/publish/agent-skills-launch-pack` | [upstream](https://github.com/chenjin-cmd/agent-skills-launch-pack_.git) |
| `all-in-one` | `publish` | `backup` | `cloned` | `vendor/reserved/publish/all-in-one` | [upstream](https://github.com/cv-cat/All-IN-ONE.git) |
| `autoclaw-xhs-skills` | `publish` | `backup` | `cloned` | `vendor/reserved/publish/autoclaw-xhs-skills` | [upstream](https://github.com/autoclaw-cc/xiaohongshu-skills.git) |
| `biliup-rs` | `publish` | `archived_historical_fallback` | `archived_not_primary` | `vendor/reserved/publish/biliup-rs` | [upstream](https://github.com/biliup/biliup-rs.git) |
| `opencli` | `publish` | `browser_cli_fallback` | `dependencies_installed_cli_built` | `vendor/reserved/publish/opencli` | [upstream](https://github.com/jackwener/OpenCLI.git) |
| `postbot` | `publish` | `browser_session_fallback` | `extension_dependencies_installed_build_ready` | `vendor/reserved/publish/postbot` | [upstream](https://github.com/gitcoffee-os/postbot.git) |
| `postiz` | `publish` | `backup` | `cloned_server_stack_not_installed` | `vendor/reserved/publish/postiz` | [upstream](https://github.com/gitroomhq/postiz-app.git) |
| `qianfan-sync` | `publish` | `account_management_console` | `backend_frontend_and_mcp_installed` | `vendor/reserved/publish/qianfan-sync` | [upstream](https://github.com/DevilJie/social-auto-upload-web-ui.git) |
| `social-auto-upload` | `publish` | `primary_execution` | `runtime_ready_needs_named_account_login` | `vendor/publish/social-auto-upload` | [upstream](https://github.com/dreammis/social-auto-upload.git) |
| `spider-xhs` | `publish` | `backup` | `cloned` | `vendor/reserved/publish/spider-xhs` | [upstream](https://github.com/cv-cat/Spider_XHS.git) |
| `xhs-downloader` | `publish` | `backup` | `cloned_needs_login` | `vendor/reserved/publish/xhs-downloader` | [upstream](https://github.com/JoeanAmier/XHS-Downloader.git) |
| `xhs-skills` | `publish` | `backup` | `cloned` | `vendor/reserved/publish/xhs-skills` | [upstream](https://github.com/cv-cat/XhsSkills.git) |
| `xiaohongshu-mcp` | `publish` | `backup` | `cloned_needs_login` | `vendor/reserved/publish/xiaohongshu-mcp` | [upstream](https://github.com/xpzouying/xiaohongshu-mcp.git) |
| `xurl` | `publish` | `backup` | `cloned_needs_api_credentials` | `vendor/reserved/publish/xurl` | [upstream](https://github.com/xdevplatform/xurl.git) |
| `html-anything` | `render` | `production_candidate` | `dependency_ready` | `vendor/reserved/render/html-anything` | [upstream](https://github.com/nexu-io/html-anything.git) |
| `html-video` | `render` | `production_candidate` | `dependency_ready` | `vendor/reserved/render/html-video` | [upstream](https://github.com/nexu-io/html-video.git) |
| `auto-editor` | `video` | `backup` | `cli_ready_uv_tool_29.3.1` | `vendor/reserved/video/auto-editor` | [upstream](https://github.com/WyattBlue/auto-editor.git) |
| `chengfeng-videocut-skills` | `video` | `experimental` | `runtime_incomplete` | `vendor/reserved/video/chengfeng-videocut-skills` | [upstream](https://github.com/Agentchengfeng/chengfeng-videocut-skills.git) |
| `claude-code-video-toolkit` | `video` | `reference` | `local_reference_ready` | `vendor/reserved/video/claude-code-video-toolkit` | [upstream](https://github.com/digitalsamba/claude-code-video-toolkit.git) |
| `claude-real-video` | `video` | `production_candidate` | `dependency_ready` | `vendor/reserved/video/claude-real-video` | [upstream](https://github.com/HUANGCHIHHUNGLeo/claude-real-video.git) |
| `claude-shorts` | `video` | `backup` | `dependency_ready_with_npm_audit_warnings` | `vendor/reserved/video/claude-shorts` | [upstream](https://github.com/AgriciDaniel/claude-shorts.git) |
| `freecut` | `video` | `preferred_local_experiment` | `dependency_ready` | `vendor/reserved/video/freecut` | [upstream](https://github.com/Moh4696/freecut.git) |
| `hyperframes` | `video` | `production_candidate` | `dependency_ready` | `vendor/reserved/video/hyperframes` | [upstream](https://github.com/heygen-com/hyperframes.git) |
| `ian-xiaohei-illustrations` | `video` | `production_candidate` | `skill_ready` | `vendor/reserved/video/ian-xiaohei-illustrations` | [upstream](https://github.com/helloianneo/ian-xiaohei-illustrations.git) |
| `remotion-video-skill` | `video` | `reference` | `skill_ready_runtime_not_promoted` | `vendor/reserved/video/remotion-video-skill` | [upstream](https://github.com/wshuyi/remotion-video-skill.git) |
| `seedance2-skill` | `video` | `backup` | `skill_ready_official_model_access_optional` | `vendor/reserved/video/seedance2-skill` | [upstream](https://github.com/dexhunter/seedance2-skill.git) |
| `talking-head-editor` | `video` | `reference_only` | `reference_runtime_ready` | `vendor/reserved/video/talking-head-editor` | [upstream](https://github.com/chrislema/videoeditor.git) |
| `text-to-lottie` | `video` | `production_candidate` | `built_with_local_skip_lib_check_for_upstream_kobalte_types` | `vendor/reserved/video/text-to-lottie` | [upstream](https://github.com/diffusionstudio/lottie.git) |
| `video-use` | `video` | `experimental` | `dependency_ready` | `vendor/reserved/video/video-use` | [upstream](https://github.com/browser-use/video-use.git) |
| `video-wrapper` | `video` | `production_candidate` | `dependency_ready` | `vendor/reserved/video/video-wrapper` | [upstream](https://github.com/op7418/Video-Wrapper-Skills.git) |

## 候选储备

| 项目 | 类别 | 级别 | 下一步 | 阻断项 |
| --- | --- | --- | --- | --- |
| `video-shotcraft` | `video` | `high_priority_reserve` | use_through_newma_vox_adapter_only |  |
| `openchatcut` | `video` | `highest_priority_external_editor` | retain_complete_upstream_and_integrate_through_newma_editor_adapter |  |
| `gsap-skills` | `design` | `high_priority_suite_reserve` | register_as_one_suite_router_with_subskill_dispatch |  |
| `impeccable` | `design` | `medium_high_priority_reserve` | promote_as_html_scene_visual_qc_advisor |  |
| `video-autopilot-kit` | `video` | `high_priority_adapter_reserve` | build_guarded_newma_adapter_before_registration | no_standard_skill_md、capcut_schema_and_output_contract_need_review |
| `mixpost` | `postmortem` | `high_priority_platform_analytics_reserve` | evaluate_as_metrics_console_and_thin_adapter |  |
| `4cat` | `postmortem` | `highest_priority_competitor_analysis_reserve` | retain_complete_service_and_integrate_by_dataset_handoff |  |
| `zeeschuimer` | `postmortem` | `high_priority_browser_capture_companion` | use_only_as_4cat_capture_companion |  |
| `minet` | `postmortem` | `high_priority_competitor_cli_reserve` | wrap_cli_with_newma_dataset_contract |  |
| `tiktok-api` | `postmortem` | `platform_adapter_reserve` | build_optional_platform_adapter |  |
| `twscrape` | `postmortem` | `platform_adapter_reserve` | build_optional_platform_adapter |  |
| `youtube-operational-api` | `postmortem` | `fallback_only` | keep_as_fallback_after_official_youtube_api |  |
| `bertopic` | `postmortem` | `high_priority_comment_analysis_reserve` | use_as_analysis_dependency_not_standalone_app |  |
| `wechatpy` | `postmortem` | `highest_priority_wechat_metrics_dependency` | adopt_official_datacube_client_directly |  |
| `mediacrawler` | `postmortem` | `highest_priority_domestic_competitor_worker` | retain_as_isolated_collection_worker |  |
| `yt-dlp` | `postmortem` | `highest_priority_video_sample_cli` | adopt_cli_json_output_directly |  |
| `pyabsa` | `postmortem` | `high_priority_aspect_sentiment_reserve` | use_after_comment_normalization |  |
| `dowhy` | `postmortem` | `later_stage_causal_analysis_reserve` | enable_only_after_sufficient_cross_run_data |  |

## 已剔除项目

| 项目 | 原因 |
| --- | --- |
| `video-editing-pipeline` | No stable independent upstream repository. |
| `ffmpeg-usage` | No stable independent upstream; covered by the internal FFmpeg toolkit. |
| `caption-clip` | Low adoption, no clear license, and duplicated caption capability. |
| `product-launch-video-skill` | Niche and lower quality than retained Remotion toolkits. |
| `rednote-mcp` | Duplicated by the retained xiaohongshu-mcp and stronger browser/API routes. |
| `x-cli` | Duplicated by xurl and existing publishing routes. |
| `boutique/remotion-video` | Hard-coded obsolete local paths. |
| `boutique/video-subtitles` | Hebrew/English-oriented and unsuitable for the Chinese primary workflow. |
| `boutique/demo-video` | Depends on obsolete Clawdbot browser paths. |
| `boutique/video-agent` | Documentation-only HeyGen API wrapper with no installable upstream. |
| `boutique/animation-duplicates` | Materially duplicated by retained Remotion, HyperFrames, Lottie and animation-review Skills. |
| `governed-dcf-skill` | Useful finance methodology but weak fit for video generation or self-media operations; upstream has no declared license, so keep outside the executable reserve. |
| `livo-redskill-p5-attachments` | No stable public upstream or license was verified. Generic procedural-motion ideas are already covered by algorithmic-art and GSAP; do not register as executable. |

## 依赖

### 系统依赖

| 依赖 | 最低版本 | 必需 |
| --- | --- | --- |
| Python | `3.10` | 是 |
| Git | `2.x` | 是 |
| Node.js | `18` | 否 |
| FFmpeg/ffprobe | `5.x` | 否 |
| pnpm | `9` | 否 |
| bun | `1.x` | 否 |
| yt-dlp | `current` | 否 |

### Python 核心依赖

```text
anthropic>=0.18.0
requests>=2.31.0
beautifulsoup4>=4.12.0
PyYAML>=6.0.0
pandas>=2.0.0
numpy>=1.26.0
matplotlib>=3.8.0
seaborn>=0.13.0
akshare>=1.12.0
tushare>=1.4.0
pytest>=8.0.0
```

### Python 媒体扩展

```text
-r requirements.txt
funasr>=1.3.9
modelscope>=1.37.1
torch>=2.12.0
torchaudio>=2.11.0
addict>=2.4.0
datasets>=5.0.0
sortedcontainers>=2.4.0
simplejson>=4.1.1
```

## 发布技术路线

| 优先级 | 路线 | 状态 | 技术路径 |
| ---: | --- | --- | --- |
| 1 | `qianfan_local_api` | `current_default` | `local payload -> POST http://127.0.0.1:5409/postVideo -> platform adapter -> CloakBrowser/Playwright -> verification` |
| 2 | `qianfan_async_queue` | `batch_candidate` | `draft -> /api/v2/drafts/batch-publish -> task queue -> task verification` |
| 3 | `social_auto_upload_cli` | `fallback` | `channel pack -> guarded CLI -> named account session -> result callback` |

## 克隆、安装和检查

```bash
./scripts/install.sh
source .venv/bin/activate
python scripts/sync_reserved_projects.py --mode check
python scripts/sync_reserved_projects.py --mode clone --category video
python scripts/apply_upstream_patches.py --mode check
python scripts/ensure_video_external_deps.py --dep all --mode check
python scripts/check_publish_upstreams.py
python -m pytest tests -q
```

## 公开仓库边界

- 提交：自研 Skills、脚本、非敏感配置、契约、测试、文档、上游注册表和兼容补丁。
- 不提交：第三方源码副本、虚拟环境、`node_modules`、Cookie/浏览器 Profile、API 密钥、验证码、抓取快照、视频成品和每日运行产物。
- 外部项目许可证与使用条款以各自上游仓库为准。
