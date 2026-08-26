# 真人口播精简能力复盘

Date: 2026-07-09

## 结论

当前版本的业余感来自导演层能力不足，不是单个模板问题。

最新 v4 成片虽然去掉了字幕、黄线和左上角小卡片问题，但仍然没有达到“小林说”类真人口播的剪辑密度和证据质感。它更像一套深色讲义卡片覆盖在真人视频上，而不是“真人信任锚 + 证据主画面 + 高频镜头语法”的成片。

## 对照标杆

本地小林说参考样本的量化数据：

| 指标 | 小林说参考 | 当前 v4 |
| --- | ---: | ---: |
| 视觉变化/分钟 | 17-25 | 3.64 |
| 中位镜头间隔 | 1.4-2.7 秒 | 17.0 秒 |
| 4-5 分钟视频分镜量级 | 70-100 个微镜头 | 16 个大分镜 |
| 证据画面 | 新闻、网页、图表、资料、B-roll 混合 | 自制深色卡片为主 |
| 人物使用 | 全屏、PIP、隐藏、回归交替 | 长期侧脸 + 固定 PIP |

## 这版为什么不行

1. 分镜颗粒度错了：16 个大段平均 16.5 秒，观众感受就是 PPT 持续停留。
2. 证据不够真：多数画面是内部生成的逻辑卡，不是市场截图、网页、公告、表格、公司产品、真实图表或 B-roll。
3. 构图变化不够：虽然去掉了左上小卡，但仍然反复使用同一深色卡片视觉系统。
4. 人物不是信任锚：源视频长期侧脸看屏幕，导演层没有用回真人、Punch-in、PIP morph、全屏证据之间的节奏弥补。
5. QC 口径太浅：之前只检查黄线、字幕、音视频、路径，没有检查镜头密度、证据真实性和重复构图。

## 新硬门禁

已新增 `scripts/video_scene_plan_quality_gate.py`：

- 真人口播每分钟有效视觉变化低于 14，失败。
- 中位分镜时长超过 4.5 秒，失败。
- 超过 8 秒的大分镜没有 `micro_shots`，失败。
- 连续超过 2 个相同 `speaker_state + material_state + pip_shape`，失败。
- 出现黄线、scanline、扫光等已否定动效，失败。
- 证据镜头缺少 `evidence_authenticity`，至少警告；正式生产应补齐。

当前 v4 回扫结果：

```text
status: fail
scene_count: 16
duration: 263.613s
cuts_per_min: 3.64
median_scene_duration: 17.0s
long_scene_without_micro_shots: 15
evidence_authenticity_missing: 10
```

报告路径：

`${HOME}/Desktop/自媒体创作/20260709_金融投资口播_精简导演/qc/director_quality_gate_v4_reaudit.json`

## 下一版进化方向

导演层必须先生成“微镜头表”，再渲染：

| 层级 | 作用 | 产物 |
| --- | --- | --- |
| 语义段 | 保持口播逻辑，不丢核心观点 | 15-25 个语义段 |
| 微镜头 | 控制观感和节奏 | 70-100 个 micro_shots |
| 证据素材 | 支撑可争议判断 | real_data / source_screenshot / user_claim_card / schematic |
| 构图状态 | 控制人物与资料关系 | speaker_full / punch / PIP / hidden / split |
| 转场 | 服务语义，不做装饰 | hard_cut / push_zoom / pip_morph / speaker_return_cut |

下一版不应先写 Remotion 组件，而应先过这三关：

1. `scene_plan.json` 包含微镜头。
2. `scene_plan_quality_gate.json` 通过。
3. `storyboard_review.html` 能让用户看到每个微镜头、证据等级、构图和模板预览。

## 执行原则

- 不再把“模板名不同”当成“视觉不同”。
- 不再把“卡片有动画”当成“镜头有变化”。
- 不再把“自制图表”默认当成证据。
- 不再让最终 QC 只检查技术可播放性。
- 真人口播精简的核心能力是：删废话、保逻辑、给证据、快切换、常回人。
