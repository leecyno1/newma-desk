---
name: dasheng-stage-transwrite
description: Use when converting confirmed Newma drafts into channel-ready WeChat article, faceless explainer, VOX investigative explainer, real talking-head, AI digital-human, commercial promo, deferred cinematic short-drama, and opt-in podcast production packages.
---

# Newma Stage: Transwrite｜转写生产

## 定位

这是 Draft 之后、Publish 之前的正式主链阶段。

正式阶段顺序：

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

Draft 负责事实、数据、图表、配图和自包含 HTML。Transwrite 只负责把已确认稿转成不同渠道的表达形态，不重新发明事实链。

本阶段采用轻内核：Python 只生成任务包、提示词、请求体、最终产物槽位、QC 契约和 manifest；真正生产由 Agent 调用对应技能完成，并回写 lane manifest。

## 正式输入

- `draft_manifest.json`
- `final_structure_snapshot.json`
- `transwrite_decision.json`
- 可选：`~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/style_profile.json`

缺少 `final_structure_snapshot.json` 或 `transwrite_decision.json` 时禁止执行。

## 三类通路

### 1. wechat_article｜公众号文章

目标：

- 调用 Style DNA / humanize 规则做文字调教
- 内容扩展、节奏重排、微信格式转写
- 封面如需生成，统一走当前已就绪的 MiniMax CLI `mmx`；本地 Baoyu 路线只负责 Markdown/HTML 排版
- 最终输出 `wechat_article.final.md` 与 `wechat_article.final.html`
- 最终必须有 `wechat_article_qc_report.json`，确认图表、表格、图片、事实锚点没有丢失
- 读取 Draft 的 `03_IllustrationIntents_<topic>.json`。公众号版必须保留已确认的柠檬漫画，并紧跟原比喻/举例段落；humanize 新增重要比喻时补充 intent 后再生成，不得无记录地临时配图。
- 漫画采用 `dasheng-lemon-illustrations`，长文通常 4-8 个高价值认知锚点；不得把漫画集中堆在文末，也不得用漫画替代真实证据。
- 公众号排版必须遵守 `configs/publish/wechat_layout_rules.json`：除“引言”外，H2 使用阿拉伯数字大标题并左对齐，不用居中块状标题；表格内文字约 12px，单元格紧凑，避免手机端换行挤压；正文不得全篇蓝色或全篇加粗。
- 博士署名或“资本奏鸣曲”内容默认独占读取 `引擎/00_控制中心/rewrite_dna_profiles/doctor-capital-sonata.yaml`，不得并行混入其他作者 DNA。
- 开头硬约束：先给可核验出处的名人名言，再进入“引言”；引言必须使用具体故事、人物场景或段子切入，最后自然翻转到核心判断。禁止用摘要、新闻清单或“本文将分析”替代引言。
- 正文硬约束：删除不增加事实、机制或判断的段落；同一结论只完整表达一次；每节最多保留两个比喻，避免用连续漂亮话填充字数。
- 强调语言：风险/反转使用 `mark-red`，事实/核心结论使用 `mark-blue`，全文最重要的一句话使用 `mark-underline`；每 500 个中文字符最多约 3 处强调，不得整段染色。
- 图表硬约束：标题只出现一次，放在 HTML 图表卡顶部，静态 PNG 内不再绘制标题；图表标题约 16px，图源放在下方；白底轻网格，统一蓝红金调色，禁止仪表盘式大标题和重复图注。
- 素材硬约束：真实图片优先，尽可能选择横版，推荐 16:9，优先使用宽高比不低于 1.35 的素材；存在同等横版素材时不得使用方图或竖图。

继承技能：

- `dasheng-style-profiler`
- `wechat-style-profiler`
- `baoyu-markdown-to-html`
- `scripts/wechat_layout_variants.py`（生成候选排版预览，并可做最终 HTML 版式后处理）

文字洁癖：

- 少用“不是...而是...”
- 少用“一方面...另一方面...”
- 避免把事实稿洗成模板腔

### 2. 视频｜六条独立 Lane

目标：

- 支持真人口播素材可选
- 支持透明 / 非透明 HTML 视觉层
- 支持真人音频 / 合成音频
- 支持主动对齐（跟随已有音频）/ 被动对齐（跟随动画配音）

正式路由：

- `talking_head_video`：只处理真人出镜。先剪口误、重说、口水词和静音，再做基础滤镜、美颜、降噪、压缩、响度放大、字幕、花字、B-roll、HTML 动画和 Remotion 合成。
- `vox_explainer_video`：问题驱动的调查解释视频，默认横版 `16:9`；以中心问题、证据地图、历史、机制、真人/现场证据、反证和有限结论组织全片，不能退化成文章章节朗读。
- `explainer_html_video`：无真人财经，默认横版 `16:9`；`1:1`、`9:16` 保留为发布适配规格。
- `digital_human_video`：处理授权肖像驱动的单人数字人口播或双人访谈。双人必须分别生成两个人物源，再按说话轮次由 Remotion 合成。
- `cinematic_short_drama_video`：电影短剧规划 Lane。只注册编剧、角色圣经、导演分镜和官方模型 API 技术栈，默认 `execution_enabled=false`。
- `commercial_promo_video`：第六条视频 Lane，处理 15/30/60 秒品牌片、产品宣传片、新品预告和效果广告。必须提供品牌、产品、受众、唯一目标、产品承诺、Proof、品牌记忆和主 CTA。
- Remotion 是六条 Lane 的主时间轴；HTML Video、GSAP、HyperFrames、Lottie 是场景动画层；FFmpeg 负责终检和封装。
- `video-use`、`freecut`、Seedance 等继续保留在注册表，只在导演明确命中或主路由失败时启用。

典型模式：

- 真人口播：`human video/audio -> transcription -> claim/evidence -> HTML scene layer -> Remotion compose -> FFmpeg QC`
- 数字人口播：`authorized portrait + MiniMax audio -> imagegen reference -> Luma lip/eye motion -> silent presenter source -> Remotion compose -> FFmpeg QC`
- 双人数字人访谈：`two authorized portraits + two speaker audio tracks -> two independent presenter sources -> dialogue turn plan -> two-shot/close-up/split-screen Remotion compose -> QC`
- 无真人财经：`Draft HTML -> voiceover -> claim/evidence -> real footage + HTML scenes -> Remotion compose -> FFmpeg QC`
- VOX 调查解释：`Draft HTML -> central question/evidence map -> archival/news/interview research -> counterargument -> HTML/Remotion editorial compose -> FFmpeg QC`
- 广告宣传片：`brand/product brief -> commercial script -> product/proof storyboard -> HTML/HyperFrames scenes -> Remotion compose -> brand/claims/QC`
- 视频生成必须先走导演审核门禁：`script/storyboard -> storyboard_template_review.html -> storyboard_review_decision.json -> storyboard_review_gate.json -> TTS/material/render`。审核表必须一行一个分镜，并包含模板截图或缺失占位、模板 ID、口播、核心意思、证据资产、动效/运镜、风险点、审核控件。
- `scripts/build_stage4_transwrite.py` 会按实际模式写入对应 Lane。旧决策若把无真人任务写成 `talking_head_video`，兼容迁移到 `explainer_html_video`；旧真人 Lane 若声明 `presenter_source.kind=digital_human`，兼容迁移到 `digital_human_video`。新任务必须显式选择正确 Lane。
- storyboard 通过后还必须依次通过 `claim_evidence_gate`、`renderer_asset_gate`、`renderer_contract_gate` 和完整 `video_render_qc`。
- `storyboard_review_gate.json` 必须由 `scripts/validate_storyboard_review_gate.py` 生成，且 `status=approved`、`render_allowed=true` 才能继续。
- 若已有 TemplateShowcase 视频，先用 `scripts/extract_template_preview_frames.py` 抽取模板截图，再生成 `storyboard_template_review.html`；没有截图的模板必须显示“缺失占位”，不得用无关画面冒充。

推荐模块：

- `dasheng-html-video-bridge`
- `dasheng-html-anything-bridge`
- `dasheng-video-style-trainer`（仅引用已训练的 `style_profile.json`，不在本阶段存放样板视频）
- `dasheng-video-talking-head`
- `dasheng-digital-human-talking-head`
- `dasheng-video-explainer-html`
- `dasheng-video-vox`
- `dasheng-commercial-promo-video`
- `dasheng-lemon-illustrations`（消费 Draft illustration intent，将比喻/举例改造成全屏或透明叠加漫画分镜）
- `motion-frames`
- `remotion-best-practices`（正式主时间轴）
- `WhisperX` / `stable-ts`
- MiniMax CLI `mmx`（生产配音、配乐、图片生成、口播音频）
- `FFmpeg`

视频生产默认标准：

- 无真人口播默认使用 MiniMax `tianxin_xiaoling`，语速 `1.2x`，轻科技解释 / 数据揭示 BGM。
- 改变语速后必须同步重算视觉时间轴或等比例压缩画面，禁止只改音频导致音画漂移。
- 无真人口播正式版必须使用真实音频时长驱动时间轴：优先逐分镜 TTS 或供应商对齐时间戳；没有时用 ASR/强制对齐回填。整段 TTS + 字数估算字幕只能作为预览版。
- 若已经生成整段 TTS，必须用 `scripts/align_video_subtitles_to_asr.py --project-dir <remotion_project> --asr-json <whisper_json> --speed 1.2 --write` 回填字幕时间轴后再交付审核版。
- 任何无头/真人视频在素材生成前必须先输出 `storyboard_template_review.html`；未获确认不得调用 MiniMax 生成配音/配乐/图片，也不得渲染最终 MP4。
- 导演必须读取 `illustration_intents.json`。原文比喻/举例采用“设置 -> 柠檬人动作 -> 结果”三拍；简单比喻通常 4-7 秒，完整举例通常 7-12 秒。漫画后必须回到真人、真实证据或下一论证，不得连续卡通化整段视频。
- 仅有口头确认或静态 HTML 不算确认；必须有导出的 `storyboard_review_decision.json` 和通过的 gate report。
- 图表、折线、表格必须来自 Draft 真实数据、文章内图表或重新取数；没有数据时回到 Draft/取数环节，不得生成“看起来像数据”的假图。
- 字幕必须覆盖完整口播全文，不能只显示分镜摘要；必须输出 timed JSON/SRT，并与当前语音句子同步。
- 字幕显示文本中的年份、百分比、数量、计数优先转为阿拉伯数字，例如 `2022-2025`、`50%`、`3个月`。
- 最终视频必须做 midpoint contact sheet 抽检，检查穿模、遮盖、字幕/底栏压图、模板同质化和无意义内容。
- 无真人财经默认输出 `1920x1080`、30fps、16:9；需要方形或竖版时从同一导演计划生成独立适配版本，不能简单拉伸。
- `final_delivery_manifest.json` 必须登记最终视频、字幕、门禁报告、完整 QC、尺寸、时长和 SHA-256；其视频必须与 QC 实际检测文件完全一致。

### 3. podcast｜播客

默认关闭。只有 `transwrite_decision.json` 同时把 `podcast` 写入 `lanes`，并明确设置 `podcast.enabled=true` 时才生成播客任务包；不得因为进入 Transwrite 或检测到 MiniMax 已登录而自动开启。

目标：

- 生成播客脚本和 API 请求体
- 优先通过 MiniMax CLI 或 Coze 既有工作流生成音频，不重复造轮子
- 最终必须有音频文件和 `podcast_qc_report.json`

默认 MiniMax CLI：

```bash
mmx auth status --no-color
mmx speech synthesize --text-file <podcast_script.txt> --out <podcast.wav> --model speech-2.8-hd --voice "Chinese (Mandarin)_Radio_Host"
```

未配置 CLI/auth/API key 时，manifest 必须标记 `blocked_missing_audio_provider`，不得误报“已生成音频”。

## 标准命令

```bash
.venv/bin/python scripts/build_stage4_transwrite.py \
  --draft-manifest ~/Desktop/自媒体创作/<run_id>/03_初稿/draft_manifest.json \
  --transwrite-decision ~/Desktop/自媒体创作/<run_id>/04_转写/transwrite_decision.json
```

统一入口：

```bash
.venv/bin/python scripts/run_mainline_stage.py transwrite --run-id <run_id>
```

## transwrite_decision.json 示例

```json
{
  "run_id": "<run_id>",
  "gate": "Transwrite Gate",
  "status": "approved",
  "topics": [
    {
      "topic_id": "topic-demo",
      "lanes": ["wechat_article", "vox_explainer_video", "podcast"],
      "wechat_article": {
        "dna_profile": "project_or_user_default",
        "humanize": true,
        "cover_generation": {"enabled": true}
      },
      "vox_explainer_video": {
        "central_question": "这个现象背后的决定变量是什么？",
        "visual_layer": {
          "mode": "editorial_investigation_composite",
          "background": "opaque"
        },
        "audio": {"mode": "synthetic_audio"},
        "alignment": {
          "mode": "passive_to_generated_audio"
        },
        "render": {
          "engine": "remotion",
          "scene_renderer": "html-video",
          "template_id": "frame-liquid-bg-hero",
          "aspect_ratios": ["16:9", "1:1", "9:16"]
        }
      },
      "podcast": {
        "enabled": true,
        "provider": "minimax",
        "mode": "solo"
      }
    }
  ]
}
```

普通文章型无头视频使用 `explainer_html_video`；调查型 VOX 使用 `vox_explainer_video`；真人出镜使用 `talking_head_video`；单人或双人数字人使用 `digital_human_video`；广告宣传片使用 `commercial_promo_video`；电影短剧使用 `cinematic_short_drama_video`，但默认只生成规划包。广告任务必须提供品牌系统、官方产品资产、可核验 Proof、Offer/免责声明和唯一 CTA。

## 标准输出

- `04_转写计划.md`
- `transwrite_manifest.json`
- 每题独立目录：
  - `wechat_article/wechat_article_manifest.json`
  - `wechat_article/agent_rewrite_prompt.md`
  - `wechat_article/cover_prompt.md`
  - `explainer_html_video/explainer_html_video_manifest.json`
  - `explainer_html_video/voiceover_script.md`
  - `explainer_html_video/video_production_contract.json`
  - `explainer_html_video/delivery/final_delivery_manifest.template.json`
  - `vox_explainer_video/vox_explainer_video_manifest.json`
  - `vox_explainer_video/voiceover_script.md`
  - `vox_explainer_video/video_production_contract.json`
  - `vox_explainer_video/delivery/final_delivery_manifest.template.json`
  - `talking_head_video/talking_head_video_manifest.json`
  - `talking_head_video/presenter_source_manifest.json`
  - `talking_head_video/video_storyboard.json`
  - `talking_head_video/storyboard_template_review.html`
  - `talking_head_video/storyboard_review_decision.json`
  - `talking_head_video/storyboard_review_gate.json`
  - `talking_head_video/talking_head_script.md`
  - `talking_head_video/html_overlay.html`
  - `talking_head_video/render_plan.json`
  - `talking_head_video/html_video_project_vars.json`
  - `talking_head_video/html_video_project_plan.json`
  - `talking_head_video/html_video_commands.sh`
  - `digital_human_video/digital_human_video_manifest.json`
  - `digital_human_video/presenter_source_manifest.json`
  - `digital_human_video/digital_human_script.md`
  - `digital_human_video/video_storyboard.json`
  - `digital_human_video/video_production_contract.json`
  - `cinematic_short_drama_video/cinematic_short_drama_video_manifest.json`
  - `cinematic_short_drama_video/cinematic_screenplay.md`
  - `cinematic_short_drama_video/video_storyboard.json`
  - `commercial_promo_video/commercial_promo_video_manifest.json`
  - `commercial_promo_video/commercial_script.md`
  - `commercial_promo_video/director_scene_plan/commercial_brief.normalized.json`
  - `commercial_promo_video/director_scene_plan/script.json`
  - `commercial_promo_video/director_scene_plan/scene_plan.json`
  - `commercial_promo_video/director_scene_plan/brand_brief_gate.json`
  - `commercial_promo_video/video_production_contract.json`
  - `podcast/podcast_manifest.json`
  - `podcast/podcast_script.md`
  - `podcast/provider_request.json`

## 状态语义

脚本初次生成的 lane 通常只到：

- `ready_for_agent_execution`：等待 Agent 做文字转写、DNA、人味化、封面、QC。
- `ready_for_skill_execution`：等待具体技能/API/渲染器执行，例如视频、播客。
- `blocked_missing_human_media` / `blocked_missing_audio_provider`：缺少输入素材或外部服务。

只有以下状态可进入 Publish 执行包：

- `packageable`
- `completed`

兼容旧产物时，`ready_base_package` 可被 publish 当作文字包可用；新产物不要再主动使用这个状态。

## 强约束

1. 不在本阶段补事实、补数据或重做图表；这些都必须回到 Draft。
2. Python 脚本只生成包、提示词、请求体和 manifest；真正的 DNA/humanize、生图、渲染、播客 API 调用由 Agent/技能执行。
3. 真人、普通无头、VOX、数字人和广告宣传片使用独立 Lane；旧配置只做兼容迁移。
4. 外部 API 或素材缺失时必须显式写入状态，不得把计划当成完成品。
5. `transwrite_manifest.json` 是进入 Publish 的唯一正式输入。
6. Agent/技能完成生产后，必须更新对应 lane manifest 的 `final_artifacts`、`qc.status` 和 lane `status`，否则 Publish 只能等待。
7. 文章、HTML、封面、图片、音频、视频、字幕、审核页等运行产物不得写入任何 `skills/` 目录或项目根目录；默认写入 `~/Desktop/自媒体创作/<run_id>/04_转写/...`，实验缓存写入桌面创作目录下的 `_tmp/`。
8. 如需复用样板视频风格，先在独立 `video-style-training` 环节生成 `style_profile.json`；Transwrite 只消费该档案，不接收大批训练视频。

## 外部项目桥接

- 视频渲染见 `references/html-video-workflow.md`。
- HTML 模板与视觉语言见 `references/html-anything-workflow.md`。
