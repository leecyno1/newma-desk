# 交付接口

## 总目录约定

- 引擎：`${DASHENG_PROJECT_ROOT:-.}/引擎`
- Skills：`${DASHENG_PROJECT_ROOT:-.}/skills`
- 产物：`~/Desktop/自媒体创作`（可通过 `DASHENG_OUTPUT_ROOT` 覆盖）
- 项目根目录：只放代码、配置、SOP、skill，不放文章、图片、音频、视频、字幕、审核页或训练缓存

## 控制中心

- 总控入口：`引擎/00_控制中心/README.md`
- 当前阶段接口：`引擎/03_全链路SOP工作流/STAGE_INTERFACES.md`

## 阶段交接最小集合

| 阶段 | 交给下游的最小集合 |
| --- | --- |
| Video Style Training（可选） | `style_profile.json`、`training_manifest.json`，供视频通路引用 |
| Intake | 原始链接清单、来源摘要、采集结论 |
| Brief | 独立题卡、核心判断、证据缺口、研究入口、来源包 |
| Draft | 分题标准初稿、证据清单、待补证据项、最终结构确认 |
| Transwrite | 公众号、口播视频、播客生产包、Agent prompt、API 请求体、lane manifest |
| Publish | 各渠道执行包、平台路由、发布时间计划、执行结果、发布验真报告 |
| Postmortem | 效果结论、失效点、L1 回写建议 |

## 飞书协作最小集合（主链强制）

| 阶段 | 飞书共享文档 | 飞书群动作 | 飞书文件夹动作 |
| --- | --- | --- | --- |
| Intake | `01_内容采集_底稿` + `01_内容采集_报告` | 发送审阅摘要 + 文档链接 | 归入当日日期文件夹 |
| Brief | `02_编辑Brief库` + `02_编辑Brief_报告` | 发送候选题摘要 + 文档链接 | 归入当日日期文件夹 |
| Draft | `03_标准初稿_<topic>` + `03_初稿_报告` | 发送初稿摘要 + 全部文档链接 | 归入当日日期文件夹 |
| Transwrite | `04_转写计划` + lane manifest | 发送转写生产状态 + 阻塞项 | 归入当日日期文件夹 |
| Publish | `07_发布计划` + `07_发布包` | 发送发布计划 + 待人工确认项 | 归入当日日期文件夹 |
| Postmortem | `08_复盘报告` + `08_L1回写建议` | 发送复盘结论 | 归入当日日期文件夹 |

## 按需素材回填接口

- Draft 正文必须保留稳定章节位置，并在 HTML 内完成真实图片、图表、表格和数据图嵌入。
- 若 Draft 缺少必要资产，`draft_manifest.status` 必须标记为 `incomplete_assets`，不得把缺口留给独立素材环节。

## 发布前审核门

- `transwrite` 之前，主链至少要满足：
  - 飞书共享文档已创建
  - 飞书群已发送审阅消息
  - `final_structure_snapshot.json` 已确认
  - `transwrite_decision.json` 已确认转写通路

- `publish` 之前，主链至少要满足：
  - `transwrite_manifest.json` 已存在
  - `publish_decision.json` 已确认标题、路由、发布时间
  - 视频/音频/封面缺口已在 lane manifest 中明确标记

## Transwrite 最小交付集合

- `04_转写计划.md`
- `transwrite_manifest.json`
- `wechat_article_manifest.json`
- `explainer_html_video_manifest.json`
- `vox_explainer_video_manifest.json`
- `talking_head_video_manifest.json`
- `digital_human_video_manifest.json`
- `commercial_promo_video_manifest.json`
- `cinematic_short_drama_video_manifest.json`（规划包）
- `podcast_manifest.json`
- 可选：引用 `~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/style_profile.json`

## Video Style Training 最小交付集合

- `training_manifest.json`
- `per_video/*/analysis.json`
- `style_profile.json`
- `style_profile.md`

说明：

- 默认目录：`~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/`
- 样板视频源文件只记录路径，不复制进项目仓库。
- 超大视频的压缩上传副本只能写入 `<style_id>/_upload_cache/`。

## Publish 最小交付集合

- `07_发布计划.md`
- `07_发布包.md`
- `channel_packs/<topic_id>/<channel>/channel_pack.json`
- `channel_packs/<topic_id>/<channel>/execution_request.json`
- `channel_packs/<topic_id>/<channel>/verification_request.json`
- `channel_packs/<topic_id>/<channel>/platform_form_validation.json`（发布前平台字段 Gate）
- `channel_packs/<topic_id>/<channel>/publish_payload.json`（执行器统一输入）
- `channel_packs/<topic_id>/<channel>/publish_result.json`（执行器或人工发布后回填）
- `channel_packs/<topic_id>/<channel>/<task_id>/channel_pack.json`（矩阵任务独立发布包）
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_result_history.json`（不可覆盖的任务重试历史）
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_results/attempt-XXXX.json`（单次尝试回执）
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_retry_request.json`（失败分类、退避时间和人工动作）
- `channel_execution_manifest.json`
- `publish_verification_report.json`
- `publish_manifest.json`

说明：

- 只有 `channel_execution_manifest.json` 不能视为发布成功。
- `platform_form_validation.json` 存在阻断错误时，不得生成或执行真实发布命令。
- 发布前平台字段 Gate 与发布后 Publish Guard 是两道独立检查，不能互相替代。
- 必须通过 `scripts/record_publish_result.py` 写回平台 URL、草稿 ID、截图或错误状态。
- 带 `task_id` 的结果以 `task_id` 为唯一身份；只有旧包才回退到 `(topic_id, channel)`。同平台多账号不得互相覆盖。
- 失败重试请求只允许生成计划，必须包含 `automatic_execution=false` 和 `requires_user_confirmation=true`。
- 必须同时存在 `publish_verification_report.json`，并且平台状态通过验真，才能对外汇报“已发布”；草稿只能回报“已推草稿”。
- `published_links` 只允许写入 `status=published`、`verification_status=verified` 且存在正式 `platform_url` 的结果。
- `draft_records` 只允许写入 `status=draft|scheduled`、`verification_status=verified` 且存在 `draft_id` 的结果。
- `draft_url` 必须与 `platform_url` 分离，草稿链接不得进入 `published_links`。
- `publish_summary` 是唯一汇总口径，必须包含 `total_channels`、`recorded_count`、`pending_count`、`failed_count`、`draft_count`、`published_count`、`verified_count`、`needs_manual_verification_count`、`pending_channels`。
- Postmortem 按 `topic_id` 聚合多渠道结果，只从已验真的 `publish_results` 中计算 `published/drafted`，不得读取旧 `channel_pack.wechat_article_url` 作为成功发布证据。

## 人工干预原则

- 每阶段结尾都要留人工干预位。
- 人工可改：
  - 选题去留
  - 大纲顺序
  - 标题
  - 节奏
  - 素材优先级
  - 发布时间
- 人工不可直接绕过：
  - 事实校验
  - 证据缺失标记
  - 阶段交接文档

## 当前默认顺序

`intake -> brief -> draft -> transwrite -> publish -> postmortem`
