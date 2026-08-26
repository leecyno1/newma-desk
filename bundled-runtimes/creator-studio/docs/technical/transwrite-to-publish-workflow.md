# Transwrite -> Publish 阶段链路

更新时间：2026-08-14

## 主链边界

正式主链：

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

- Draft：完成事实、数据、图表、配图、自包含 HTML。
- Transwrite：把确认 Draft 转成渠道表达形态，采用轻内核，真正生产由 Agent/技能执行。
- Publish：只做验收、打包、账号运营审查、推草稿/人工发布包、链接回收和验真。

## Transwrite 执行模型

`scripts/build_stage4_transwrite.py` 只负责生成任务包：

- `transwrite_manifest.json`
- `04_转写计划.md`
- 每个 lane 的 manifest、prompt、请求体、产物槽位、QC 槽位

真正生产由 Agent/skills 完成，并回写 lane manifest：

- `status`
- `final_artifacts`
- `qc.status`
- `qc.report`

## 六条视频 Lane + 公众号/播客

### wechat_article

职责：

- 调用 `dasheng-style-profiler` / `wechat-style-profiler`
- 调用 `baoyu-markdown-to-html`
- 可选调用 `baoyu-cover-image` / `baoyu-imagine`
- 输出 `wechat_article.final.md`、`wechat_article.final.html`、封面和 `wechat_article_qc_report.json`

### talking_head_video

职责：

- 真人口播：人声/视频为主时间轴，HTML 视觉层主动对齐，Remotion 负责总合成。
- 调用 `dasheng-video-talking-head`、`dasheng-html-video-bridge`、`dasheng-html-anything-bridge`。
- 输出 MP4、SRT、timeline、`video_qc_report.json`

### vox_explainer_video

职责：

- 从 Draft 提炼一个中心问题和 3-6 个证据支柱。
- 调用 `dasheng-video-vox`，组织历史、机制、真实新闻/访谈/现场资料、数据、反证和有限结论。
- 默认横版 16:9；Remotion 为主时间轴，HTML/GSAP/HyperFrames 为场景层，FFmpeg 做 QC 和封装。
- 输出 MP4、SRT、证据账本、素材来源、renderer gates、`video_render_qc.json` 和 `final_delivery_manifest.json`。

### explainer_html_video

职责：

- 无真人财经默认横版 `16:9` 母版，`1:1`、`9:16` 为独立适配。
- Draft HTML 是事实底板；MiniMax 音频驱动时间轴。
- 真实素材和 HTML/GSAP 场景进入 Remotion 主时间轴，再由 FFmpeg 完成 QC 与封装。
- 输出 MP4、SRT、Claim/Evidence、renderer gates、`video_render_qc.json` 和 `final_delivery_manifest.json`。

### digital_human_video

职责：

- 用授权肖像和每位说话人的 MiniMax 音轨分别生成无声数字人物源。
- 支持单人口播和双人访谈；双人按 turn 由 Remotion 合成全景、近景和分屏。
- 输出逐人 job/QC、`presenter_source_manifest.json`、MP4、SRT、证据与完整视频 QC。

### cinematic_short_drama_video

默认暂缓执行；只生成电影短剧剧本、角色/场景/连续性圣经和导演分镜规划包。外部官方模型 API 必须经用户明确批准供应商、预算、授权和安全边界后才能启用。

### commercial_promo_video

职责：

- 接收品牌、产品、受众、目标、核心承诺、卖点、Proof、Offer、免责声明和唯一 CTA。
- 生成 15/30/60 秒广告脚本、导演分镜、品牌 Brief 门禁、工具路由和多比例安全区计划。
- 官方产品录屏、实拍和品牌资产优先；生成画面只做概念、氛围和转场，不承担产品结果证明。
- 默认竖版 `9:16`，同时支持 `16:9`、`1:1`、`4:5`；输出完整声明、渲染和交付门禁。

### podcast

默认关闭；只有决策同时包含 `podcast` 且 `podcast.enabled=true` 才生成任务包。

职责：

- 从 Draft/转写稿生成播客脚本
- 调用 MiniMax CLI 或 Coze 工作流生成音频
- 输出音频、文字稿和 `podcast_qc_report.json`

## 状态机

初始包状态：

- `ready_for_agent_execution`
- `ready_for_skill_execution`
- `blocked_missing_human_media`
- `blocked_missing_audio_provider`

可进入 Publish：

- `packageable`
- `completed`

兼容旧文字包：

- `ready_base_package`

Publish 必须阻塞：

- `planned`
- `planned_for_render`
- `ready_for_agent_execution`
- `ready_for_skill_execution`
- `blocked_missing_*`
- `waiting_for_human_media`
- `failed_qc`

## 产物落点规则

运行产物不得写入 `skills/`、`openclaw-skill-exports/` 或任意 skill 根目录。

默认落点：

- Draft：`~/Desktop/自媒体创作/<run_id>/03_初稿/`
- Transwrite：`~/Desktop/自媒体创作/<run_id>/04_转写/`
- Publish：`~/Desktop/自媒体创作/<run_id>/05_发布/`
- 实验缓存：`~/Desktop/自媒体创作/_tmp/`
- 历史误放素材迁移：`~/Desktop/自媒体创作/_legacy_skill_runtime_data/`

代码守卫：

- `scripts/canonical_workflow.py::ensure_runtime_output_dir`

## Publish 当前开发方向

第一阶段已经完成：

- publish 只接受 `transwrite_manifest.json` + `publish_decision.json`
- 阻塞未完成 lane
- 检查关键最终产物是否存在
- 生成 `07_发布计划.md`、`07_发布包.md`、`channel_execution_manifest.json`、`publish_verification_report.json`、`publish_manifest.json`
- Publish Guard 已进入正式闭环：
  - `scripts/publish_guard.py --publish-manifest <publish_manifest.json>`
  - 默认写出 `publish_guard_report.json` / `publish_guard_report.md`
  - 回写 `publish_manifest.publish_guard`
  - Postmortem 正式门控可用 `--require-publish-guard`
- 账号运营 advisory 已接入：
  - `dasheng-publish-operations-bridge`
  - external `agent-skills-launch-pack`
  - 渠道包自动生成 `account_operations_request.json`
  - 冷启动/低流量/沉寂/风险/矩阵实验号等待 `account_operations_advice.json` 后才恢复受控执行

下一阶段要攻：

- 每个平台的必需字段校验：标题、摘要、标签、封面、正文、视频、音频。
- 发布包结构化导出：公众号包、视频平台包、播客包、人工 B 站包。
- 执行器路由：自动、半自动、人工包三类明确分流。
- 外部依赖桥：小红书、抖音、B站和视频号统一通过受控 `social-auto-upload` 路线执行，B站内部继续复用 `biliup`，海外排程候选为 `Postiz`。
- Link Recovery：草稿 ID、正式链接、账号、截图、错误状态回填。
- Publish Guard：验真报告不得为空，未验真不得标记已发布；`draft_url` 与 `platform_url` 必须分离。
- Operations Advice Recovery：发布后把曝光、打开/完播、互动、关注、转化等指标回收到 Postmortem，为下一轮选题和发布实验提供证据。
