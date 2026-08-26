# 视频文稿模板映射指导

Date: 2026-06-13

## 去重结论

当前模板池来自两个外部仓库：

- HTML Anything：`${HOME}/Documents/html一切`，当前路由扫描到 78 个模板。
- html-video：`${EXTERNAL_VOLUME}/html-video`，当前 CLI 扫描到 23 个可执行视频模板。
- 重名交集 6 个：`frame-data-chart-nyt`、`frame-glitch-title`、`frame-light-leak-cinema`、`frame-liquid-bg-hero`、`frame-logo-outro`、`vfx-text-cursor`。
- 去重后当前是 95 个模板，不是固定 100 个。后续 skill 必须每次扫描外部仓库生成候选池，不能硬编码数量。

## 使用原则

模板选择按“文稿语义部件”触发，不按模板名称触发。正确流程：

`口播稿/文章 -> 语义切片 -> 内容槽位 -> 可执行 html-video 模板 -> HTML Anything 视觉参考 -> 时间轴 -> 渲染`

模板路由只解决“这段内容用什么视觉语言”。实际剪辑还必须经过导演驱动机制，见 [video-editing-driving-mechanism.md](video-editing-driving-mechanism.md)：`证据需求 / 注意力债务 / 信任债务 / 认知负荷 / 新鲜度 / 竖屏可读性` 共同决定是否切镜头、上证据、回真人、放慢图表或加转场。

优先级：

1. 如果要直接渲染视频，首选 `html-video` 可执行模板。
2. 如果 `html-video` 没有合适模板，使用 HTML Anything 模板作为视觉参考，再生成自定义 HTML scene。
3. 数据、表格、截图、引用必须来自 Draft 文章或已验证素材，不允许用 Lottie/装饰动画替代事实层。
4. 一个文稿片段只映射一个主槽位；辅助信息可以作为同一 scene 的变量，不要叠三四套模板。

## 文稿槽位映射表

| 文稿部件 | 触发特征 | 首选可执行模板 | HTML Anything 参考 | 使用说明 |
| --- | --- | --- | --- | --- |
| 总标题 | 标题、视频开头第一句、核心命题 | `frame-liquid-bg-hero` | `poster-hero`、`magazine-poster` | 适合“AI一定等于美国吗”这类总命题。只放标题和一句副题，不塞大段逻辑。 |
| 强冲突开场 | “不是因为…而是…”，“真正的问题是…” | `frame-glitch-title` | `motion-frames`、`deck-hermes-cyber` | 用于前 3-8 秒 Hook。避免开发标签、不要出现 slot/position 字样。 |
| 金句打字 | 一句判断、短 quote、结论悬念 | `vfx-text-cursor` | `card-twitter`、`blog-post` | 用于逐字揭示，不适合长句。金融视频里只做少量强调。 |
| 章节标题 | “第一/第二/第三”，“壹/贰/叁” | `frame-bold-signal` | `deck-swiss-international`、`deck-dir-key-nav` | 用作段落切换。标题 8-20 字，配当前章节序号。 |
| 社论海报标题 | 重大判断、强观点、开篇封面 | `frame-bold-poster` | `article-magazine`、`deck-guizang-editorial` | 比 `frame-liquid-bg-hero` 更强硬，适合爆点标题，不适合数据页。 |
| 极简高级标题 | 单词/短词概念，如“流动性”“地心引力” | `frame-build-minimal` | `ppt-keynote`、`deck-simple` | 留白型，不适合中文长句和信息密集段。 |
| 电影化情绪转场 | “回到正题”，“真正的风险开始了” | `frame-light-leak-cinema` | `motion-frames`、`sprite-animation` | 用于气氛、章节换挡、B-roll 过渡。不能承载核心数据。 |
| 结构总览 | “今天讲三件事”，“逻辑链是…” | `frame-decision-tree` | `frame-flowchart-sticky`、`deck-blueprint` | 左右/上下关系清晰时用。若是三段式大纲，也可用 `frame-bold-signal` 分段。 |
| 因果链 | “A 导致 B，B 又导致 C” | `frame-decision-tree` | `frame-flowchart-sticky`、`wireframe-sketch` | 画链路，不画泛泛“研究框架”。每个节点必须来自文稿实义。 |
| 时间线 | 政策先后、事件演化、市场节奏 | `frame-swiss-grid` | `weekly-update`、`deck-blueprint` | 当前 html-video 时间线模板弱，可先用 Swiss grid 或 HTML Anything 时间线参考自制。 |
| 单一关键数字 | “1500亿-2000亿美元”，“2万亿” | `frame-pentagram-stat` | `data-report`、`finance-report` | 巨数字锚点。只讲一个数字和它的含义，不做多组比较。 |
| 多指标对比 | 多资产涨跌、公司财务对比 | `frame-data-chart-nyt` | `finance-report`、`data-report` | 首选真实数据柱状/折线。标题必须是结论，不是“某某图表”。 |
| 动态柱状滚动 | 3-7 个数值需要“长出来” | `frame-data-rollup` | `dashboard`、`live-dashboard` | Remotion 原生模板，适合短促数据冲击。超过 7 个项目会拥挤。 |
| 折线趋势 | 利率、股价、指数、收益率曲线 | `frame-data-chart-nyt` 或 `frame-nyt-graph` | `finance-report` | 有真实时间序列时使用；没有时间序列不要伪造折线。 |
| 表格证据 | 财报表、政策表、事件清单 | 自定义 HTML scene | `data-report`、`finance-report`、`dashboard` | html-video 当前没有强表格模板，优先用 HTML Anything 表格视觉生成 scene。 |
| 资产仪表盘 | 股债汇商/多市场同屏 | 自定义 HTML scene | `dashboard`、`live-dashboard`、`social-media-dashboard` | 用于信息密度高的金融页。必须控制字号，竖屏最多 4-6 个核心模块。 |
| 风险警报 | “风险在于…”，“最危险的是…” | `frame-glitch-title` | `deck-safety-alert`、`deck-hermes-cyber` | 用红/黑/警示动效，但不要做廉价大警报。风险后必须跟证据。 |
| 文档/政策引用 | 文件、公告、新闻原文、来源 | 自定义 HTML scene | `doc-kami-parchment`、`docs-page`、`article-magazine` | 用文档 zoom/highlight。引用要有来源行和日期。 |
| 社交反馈 | 网友吐槽、评论、X/小红书截图 | 自定义 HTML scene | `social-x-post-card`、`social-reddit-card`、`card-xiaohongshu` | 适合开场“被骂/争议”段。真实截图优先，合成卡片需标注为整理。 |
| 对话/问答 | “有人问…我的回答是…” | 自定义 HTML scene | `chat_box` 路由：`social-x-post-card`、`frame-macos-notification` | 做聊天气泡或问答卡。不要把严肃数据做成聊天框。 |
| 手机展示 | App、小红书、移动端页面 | 自定义 HTML scene | `mobile-app`、`mobile-onboarding`、`mockup-device-3d` | 适合手机截图/竖屏内容，不适合宏观逻辑。 |
| 桌面展示 | 网站、数据终端、后台页面 | 自定义 HTML scene | `mockup-device-3d`、`prototype-web`、`web-proto-editorial` | 适合截图证据或工具演示。金融终端要偏 Bloomberg 克制风。 |
| 产品/工具解释 | Agent、工作流、软件能力 | `frame-product-promo` 或 `frame-product-promo-30s` | `saas-landing`、`prototype-web` | 仅用于讲工具/产品，不用于市场分析主体。 |
| 暖调 B-roll | 宏观叙事、历史类比、缓冲段 | `frame-warm-grain` | `article-magazine`、`magazine-poster` | 用作非数据段的视觉呼吸。不要承担事实证明。 |
| 活泼短视频段 | 轻松解释、生活化比喻 | `frame-play-mode` | `deck-xhs-pastel`、`card-xiaohongshu` | 当前财经主线少用，除非目标平台是小红书/抖音轻知识。 |
| 人物观点卡 | 一段强 quote、对立观点 | `frame-electric-studio` | `card-twitter`、`blog-post` | 适合“市场以为 X，但政策在表达 Y”。不要塞表格。 |
| 创意能量标题 | 转折强、节奏快、视觉冲击 | `frame-creative-voltage` | `deck-hermes-cyber` | 用于科技/AI 题材章节标题，金融宏观慎用，防止太花。 |
| 柔和系统图 | 产业链、生态关系、扩散关系 | `frame-takram-organic` | `deck-graphify-dark`、`frame-flowchart-sticky` | 适合产业生态，不适合严肃因果链和真实图表。 |
| 竖屏强观点 | 手机竖版中的一句核心判断 | `frame-vignelli` | `poster-hero`、`deck-swiss-international` | 适合短视频金句卡。少字、大字、红黑体系。 |
| 收尾 CTA | 关注、下期预告、免责声明前 | `frame-logo-outro` | `poster-hero`、`card-twitter` | 只做结尾，不在中段复用。可带品牌名和一句 tagline。 |

## 文字稿切片规则

| 切片类型 | 建议时长 | 模板数量 | 备注 |
| --- | --- | --- | --- |
| Hook | 3-8 秒 | 1 | `frame-glitch-title` / `vfx-text-cursor` / `frame-liquid-bg-hero` 三选一。 |
| 大纲 | 5-10 秒 | 1 | 三点以内用结构图；超过三点拆章节。 |
| 普通论述 | 6-12 秒 | 0-1 | 不要每句话都上模板，避免变 PPT。 |
| 数据证据 | 6-15 秒 | 1 | 必须绑定真实表格/图表/来源。 |
| 风险提示 | 4-8 秒 | 1 | 警示后必须给解释，不要只制造情绪。 |
| 章节切换 | 3-6 秒 | 1 | 尽量统一使用同一章节模板。 |
| 结尾 | 4-8 秒 | 1 | `frame-logo-outro`，可加免责声明/关注提示。 |

## 模板去重策略

同名模板优先使用 html-video 版本，因为它可直接 `project-render`：

- `frame-data-chart-nyt`
- `frame-glitch-title`
- `frame-light-leak-cinema`
- `frame-liquid-bg-hero`
- `frame-logo-outro`
- `vfx-text-cursor`

HTML Anything 独有模板不直接视为可渲染模板，而是视为视觉参考或自定义 scene 的生成依据：

- 文章/文档类：`article-magazine`、`doc-kami-parchment`、`docs-page`、`blog-post`
- 数据/金融类：`data-report`、`finance-report`、`dashboard`、`live-dashboard`
- 结构/流程类：`frame-flowchart-sticky`、`deck-blueprint`、`wireframe-sketch`
- 社交/手机类：`social-x-post-card`、`card-xiaohongshu`、`mobile-app`、`mockup-device-3d`
- 运营/看板类：`kanban-board`、`team-okrs`、`pm-spec`、`eng-runbook`

html-video 独有模板直接纳入可执行候选：

- 标题/章节：`frame-bold-poster`、`frame-bold-signal`、`frame-build-minimal`、`frame-creative-voltage`、`frame-vignelli`
- 数据：`frame-data-rollup`、`frame-nyt-graph`、`frame-pentagram-stat`
- 结构/概念：`frame-decision-tree`、`frame-swiss-grid`、`frame-takram-organic`
- 氛围/产品：`frame-warm-grain`、`frame-play-mode`、`frame-product-promo`、`frame-product-promo-30s`

## 未来 Skill 形态

建议新增 skill：`dasheng-video-template-router`。

Skill 只保留核心流程，详细映射放 references：

```text
dasheng-video-template-router/
├── SKILL.md
├── references/
│   ├── script-slot-mapping.md
│   ├── html-video-template-capabilities.md
│   └── html-anything-visual-references.md
└── scripts/
    ├── scan_template_pool.py
    ├── classify_script_segments.py
    └── build_video_template_timeline.py
```

Skill 工作流：

1. 扫描 HTML Anything 和 html-video，生成去重模板池。
2. 将文稿切成 `hook / outline / chapter / claim / evidence / quote / table / chart / risk / transition / outro`。
3. 读取 `configs/video/video_editing_driver_rules.json`，计算 beat 类型和导演分数。
4. 每个切片只选一个主模板，并填充模板 schema 需要的变量。
5. 生成 `video_template_timeline.json`，包含 `slot`、`start_sec`、`duration_sec`、`template_id`、`template_source`、`variables`、`evidence_refs`。
6. 交给 html-video 或自定义 HTML scene renderer 渲染。

硬规则：

- 模板不是越多越好；一条 3 分钟视频通常 18-35 个视觉段足够。
- 数据段必须绑定真实数据；没有数据就用观点/文档/结构模板，不许伪造图表。
- 同一期视频限定 1 个主视觉系统，最多 2 个辅助模板族，避免风格乱跳。
- 竖屏优先检查 `supported_aspects` 是否包含 `9:16`；不支持时只能作为参考，不能直接渲染。
