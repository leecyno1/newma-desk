# 外部 HTML 模板业务场景与适配参数分析

生成日期：2026-07-01

## 结论

本次分析覆盖两个外部项目：

| 项目 | 当前本机路径 | 定位 | 模板数量 | 说明完整度 |
| --- | --- | --- | ---: | --- |
| HTML Everything / HTML Anything | `${PROJECTS_ROOT}/html-everything` | 视觉模板、文章 HTML、图文卡、Deck、仪表盘、视频帧参考库 | 78 | 78/78 有 `SKILL.md`、`description`、`example.html` |
| html-video | `${PROJECTS_ROOT}/html-video` | 可执行视频模板、HyperFrames/Remotion 渲染层 | 23 | 23/23 有 `template.html-video.yaml`，14/23 另有 `SKILL.md` |

两个项目模板去重后共 95 个模板，重名交集 6 个：

`frame-data-chart-nyt`、`frame-glitch-title`、`frame-light-leak-cinema`、`frame-liquid-bg-hero`、`frame-logo-outro`、`vfx-text-cursor`

使用原则：

- 需要直接渲染视频时，优先用 `html-video` 同名模板，因为它有可执行 YAML、引擎、输出格式、输入 schema。
- HTML Everything 模板主要作为视觉语言、文章排版、图卡、表格/仪表盘、社交卡、文档证据和自定义 scene 的参考。
- 数据图表、表格、截图、引用必须绑定真实数据或原始素材，不能用 Lottie、动效或装饰图代替事实层。
- 未来自动适配不应按模板名触发，而应按内容部件触发：`标题 / hook / 大纲 / 章节 / 逻辑链 / 数据图 / 表格 / 引用 / 截图 / 风险 / 转场 / 结尾`。

## 模板业务场景总览

### HTML Everything 模板分组

| 业务场景 | 模板 | 用途 |
| --- | --- | --- |
| 长文与文章发布 | `article-magazine`、`blog-post`、`digital-eguide` | 公众号、博客、Substack、长图文、电子指南 |
| 社交图卡与评论展示 | `card-twitter`、`card-xiaohongshu`、`frame-macos-notification`、`social-carousel`、`social-reddit-card`、`social-spotify-card`、`social-x-post-card` | X/Reddit/小红书/通知/评论/引用卡 |
| 数据后台与仪表盘 | `dashboard`、`dating-web`、`flowai-team-dashboard`、`kanban-board`、`live-dashboard`、`social-media-dashboard`、`social-media-matrix`、`team-okrs` | KPI、运营看板、任务流、控制台、社媒数据 |
| 数据报告 | `data-report`、`experiment-readout` | CSV/JSON/实验结果/指标复盘 |
| 文档证据与决策材料 | `competitive-teardown`、`doc-kami-parchment`、`docs-page`、`eng-runbook`、`exec-briefing-memo`、`hr-onboarding`、`meeting-notes`、`pm-spec` | 报告、公告、文档截图、会议纪要、决策 memo、流程文档 |
| 邮件 | `email-marketing` | 营销邮件、产品发布邮件 |
| 金融与财务 | `finance-report`、`invoice` | 财报、P&L、财务表格、发票/账单式明细 |
| 移动端展示 | `gamified-app`、`mobile-app`、`mobile-onboarding` | 手机截图、App 页面、移动端流程 |
| 海报与封面 | `frame-liquid-bg-hero`、`magazine-poster`、`mockup-device-3d`、`poster-hero`、`sprite-animation` | 封面、海报、设备展架、像素风解释帧 |
| Web 原型 | `pricing-page`、`prototype-web`、`saas-landing`、`waitlist-page`、`web-proto-brutalist`、`web-proto-editorial`、`web-proto-soft`、`wireframe-sketch` | 产品页、落地页、桌面截图、线框图 |
| 简历 | `resume-modern` | A4 简历 |
| Deck / PPT | `deck-blueprint`、`deck-course-module`、`deck-dir-key-nav`、`deck-graphify-dark`、`deck-guizang-editorial`、`deck-hermes-cyber`、`deck-magazine-web`、`deck-obsidian-claude`、`deck-open-slide-canvas`、`deck-pitch`、`deck-presenter-mode`、`deck-product-launch`、`deck-replit`、`deck-safety-alert`、`deck-simple`、`deck-swiss-international`、`deck-tech-sharing`、`deck-xhs-pastel`、`deck-xhs-post`、`deck-xhs-white`、`ppt-keynote`、`weekly-update` | 章节卡、课程、融资、产品发布、技术分享、小红书图文、周报 |
| 视频帧参考 | `frame-data-chart-nyt`、`frame-flowchart-sticky`、`frame-glitch-title`、`frame-light-leak-cinema`、`frame-logo-outro`、`motion-frames`、`vfx-text-cursor`、`video-hyperframes` | 标题帧、数据帧、流程图、电影感转场、片尾、连续视频脚本 |

### html-video 模板分组

| 业务场景 | 模板 | 用途 |
| --- | --- | --- |
| 标题/章节/观点卡 | `frame-bold-poster`、`frame-bold-signal`、`frame-build-minimal`、`frame-creative-voltage`、`frame-electric-studio`、`frame-glitch-title`、`frame-kinetic-type`、`frame-swiss-grid`、`frame-warm-grain`、`vfx-text-cursor` | 标题、章节、金句、强观点、极简概念、技术感开场 |
| 数据可视化 | `frame-data-chart-nyt`、`frame-data-rollup`、`frame-nyt-graph`、`frame-pentagram-stat` | 折线、柱状、数据滚动、单关键数字 |
| 结构解释 | `frame-decision-tree`、`frame-takram-organic` | 决策树、流程、系统关系、产业生态 |
| 情绪与 B-roll | `frame-light-leak-cinema` | 电影感开场、纪录片冷开、氛围转场 |
| Hero / 封面 | `frame-liquid-bg-hero` | 产品发布、视频封面、强视觉 hero |
| 结尾 | `frame-logo-outro` | 品牌落版、频道片尾、CTA |
| 产品演示 | `frame-product-promo`、`frame-product-promo-30s` | 多功能产品宣传、SaaS 30 秒视频 |
| 轻短视频 | `frame-play-mode`、`frame-vignelli` | 轻松短视频、竖屏强观点、红黑社交卡 |

## HTML Everything 完整模板场景表

| 模板 | 中文名 | 类别 | 画幅 | 适配业务场景 |
| --- | --- | --- | --- | --- |
| `article-magazine` | 杂志文章 | article | A4 / 长页面 | Substack / Medium 高级感长文排版，适合公众号、博客发布 |
| `blog-post` | 博客长文 | article | 长页面 | 杂志感长文，含 masthead、hero、figures、pull quote、作者署名 |
| `card-twitter` | Twitter 分享卡 | card | 1600×900 (16:9) | 推特金句 / 数据卡，适合配推文 |
| `card-xiaohongshu` | 小红书图文卡片 | card | 1080×1440 (3:4) | 小红书风格知识卡片，多张联排可滑动浏览 |
| `competitive-teardown` | 竞品拆解 | doc | 战略长页面 | 定位图、功能矩阵、价格对比、机会窗口，适合产品/市场拆解 |
| `dashboard` | 管理后台仪表板 | dashboard | 桌面 1440 | 固定侧栏、顶栏、KPI 网格和 1-2 张图，适合后台/数据看板 |
| `data-report` | 数据可视化报告 | data | 桌面长页面 | 把 CSV/Excel/JSON 数据转成可视化报告页 |
| `dating-web` | 社区 / 配对数据墙 | dashboard | 桌面 1440 | 消费感配对仪表板：信号 ticker、KPI、柱状、趋势 |
| `deck-blueprint` | 蓝图架构 Deck | slides | 16:9 | 架构、pipeline、流程、系统设计和总纲 |
| `deck-course-module` | 课程 / 培训 Deck | slides | 16:9 | 课程模块、学习目标、MCQ 自测 |
| `deck-dir-key-nav` | 极简方向键 Keynote | slides | 16:9 | 极简章节切换、方向键导航、单色演示 |
| `deck-graphify-dark` | 暗底图谱 Deck | slides | 16:9 | 深色图谱、力导向关系、知识网络 |
| `deck-guizang-editorial` | 贵赞编辑墨水 Deck | slides | 16:9 横向翻页 | 电子杂志、电子墨水、长内容 editorial deck |
| `deck-hermes-cyber` | Cyber Terminal Deck | slides | 16:9 | 命令行、终端感、科技/安全/风险议题 |
| `deck-magazine-web` | 杂志风网页 PPT | slides | 16:9 横向翻页 | 杂志化网页 PPT、WebGL 氛围、衬线标题 |
| `deck-obsidian-claude` | GitHub Dark 紫渐变 Deck | slides | 16:9 | GitHub-dark、代码、Claude/AI 工程演示 |
| `deck-open-slide-canvas` | 1920 画布自由 Deck | slides | 1920×1080 | React 组件级自由组合，不绑固定模板 |
| `deck-pitch` | 投资人 Pitch Deck | slides | 16:9 ×10 | 融资 deck、traction、市场、商业计划 |
| `deck-presenter-mode` | 演讲者模式 Deck | slides | 16:9 | 带提词器和主题切换的演讲 deck |
| `deck-product-launch` | 产品发布 Keynote | slides | 16:9 | 产品发布、特性、定价、CTA |
| `deck-replit` | Replit Slides 风 Deck | slides | 16:9 | Replit 风主题演示 |
| `deck-safety-alert` | 安全 / 风险红色 Deck | slides | 16:9 | 风险警示、安全事故、政策红线、异常提醒 |
| `deck-simple` | 通用 Simple Deck | slides | 16:9 | 通用横向 HTML deck |
| `deck-swiss-international` | 瑞士国际主义 Deck | slides | 16:9 横向翻页 | 瑞士网格、理性、报告型演示 |
| `deck-tech-sharing` | 技术分享 Deck | slides | 16:9 | 技术分享、代码、终端、Q&A |
| `deck-xhs-pastel` | 马卡龙慢生活 Deck | slides | 16:9 | 小红书慢生活、柔和风格图文 |
| `deck-xhs-post` | 小红书图文 Deck | slides | 810×1080 ×9 | 9 页 3:4 小红书图文 |
| `deck-xhs-white` | 白底杂志风 Deck | slides | 16:9 / 3:4 | 白底小红书/杂志风图文 |
| `digital-eguide` | 电子指南 | article | 双页预览 | 电子指南、封面、课程页、步骤列表 |
| `doc-kami-parchment` | Kami 羊皮纸文档 | doc | A4 / Letter 长页 | 文档证据、报告截图、历史材料、政策文件 |
| `docs-page` | 技术文档页 | doc | 桌面 1440 | 三栏技术文档、API、指南 |
| `email-marketing` | 营销邮件 | email | 600 邮件宽 | 产品发布邮件、营销邮件、table fallback |
| `eng-runbook` | 工程 Runbook | doc | 长页面 | 运维 runbook、alerts、命令、事故清单 |
| `exec-briefing-memo` | 高管决策简报 | doc | 一页决策 memo | recommendation、evidence、tradeoffs，适合拍板材料 |
| `experiment-readout` | 实验复盘 | data | 产品实验报告 | A/B 实验、产品实验、指标解释和决策 |
| `finance-report` | 季度财报 | finance | 长页面 | 财务报告、KPI、收入/烧钱图、P&L、展望 |
| `flowai-team-dashboard` | FlowAI 团队管理 | dashboard | 桌面 1440 | 团队后台、成员、详情、活动日志、CSV 导出 |
| `frame-data-chart-nyt` | NYT 风数据图表帧 | video | 1920×1080 | 编辑级折线/柱状/范围带图表 |
| `frame-flowchart-sticky` | 便利贴流程图帧 | video | 1920×1080 | 便利贴流程、白板 brainstorm、逻辑链 |
| `frame-glitch-title` | 故障艺术标题帧 | video | 1920×1080 | 故障艺术、科技转场、cyberpunk hero |
| `frame-light-leak-cinema` | 胶片漏光电影帧 | video | 2.39:1 或 16:9 | 电影感开场、章节卡、氛围转场 |
| `frame-liquid-bg-hero` | 流体背景 Hero 帧 | poster | 16:9 / 9:16 | 视频片头、landing hero、封面海报 |
| `frame-logo-outro` | 品牌 Logo 收尾帧 | video | 1920×1080 | 片尾、品牌闭幕、栏目落版 |
| `frame-macos-notification` | macOS 通知横幅 | card | 1920×1080 或横幅 | 通知 banner、产品发布预告、视频 overlay |
| `gamified-app` | 游戏化 App 多屏 | mobile | 3 × iPhone | 游戏化 App、任务、XP、移动端流程 |
| `hr-onboarding` | 新员工入职页 | doc | 长页面 | 入职日程、buddy、学习路径、设备 |
| `invoice` | 可打印发票 | finance | A4 | 发票、账单、税费、付款指引 |
| `kanban-board` | 看板 / Kanban | dashboard | 桌面 1440 | 四列看板、任务状态、头像、泳道 |
| `live-dashboard` | Notion 风团队仪表板 | dashboard | 桌面长页 | KPI、sparkline、activity feed、任务表 |
| `magazine-poster` | 杂志风海报 | poster | 竖版长图 | Sunday paper、双栏正文、编号 sections |
| `meeting-notes` | 会议纪要 | doc | 长页面 | 出席、议程、决议、action items |
| `mobile-app` | iPhone App 单屏 | mobile | iPhone 15 Pro | 单屏 App 截图、手机框展示 |
| `mobile-onboarding` | App 引导多屏 | mobile | 3 × iPhone | splash、value-prop、sign-in |
| `mockup-device-3d` | iPhone × MacBook 立体展架 | poster | 1920×1080 | 设备展架、网页/App/产品截图 |
| `motion-frames` | 动效英雄帧 | video | 桌面 hero | CSS 动效、旋转环、地球仪、计时器 |
| `pm-spec` | PRD / 产品 Spec | doc | 长页面 | 产品需求、成功指标、范围、用户故事 |
| `poster-hero` | 营销海报 | poster | 1080×1920 | 竖版海报、朋友圈分享图 |
| `ppt-keynote` | Keynote 风格 PPT | slides | 16:9 | 一屏一卡，Keynote 风演示 |
| `pricing-page` | 定价页 | prototype | 桌面 1440 | 三档定价、特性对比、FAQ |
| `prototype-web` | Web 产品原型 | prototype | 1440×900 | 可点击 Web 原型、导航、hero、features |
| `resume-modern` | 极简简历 | resume | A4 | 现代极简单页简历 |
| `saas-landing` | SaaS Landing | prototype | 桌面 1440 | SaaS 落地页、social proof、pricing、CTA |
| `social-carousel` | 社交媒体三联 | card | 1080×1080 ×3 | 三张方形卡片轮播 |
| `social-media-dashboard` | 社媒创作者仪表板 | dashboard | 桌面 1440 | 平台切换、粉丝、互动、增长、热门话题 |
| `social-media-matrix` | 社媒矩阵追踪面板 | dashboard | 桌面长页 | 多平台社媒分析、区间对比、洞察 |
| `social-reddit-card` | Reddit 帖子卡 | card | 1280×720 或 800×600 | Reddit 帖子、投票、评论数 |
| `social-spotify-card` | Spotify 正在播放卡 | card | 1280×720 或 600×200 | Now Playing、进度条、播放控制 |
| `social-x-post-card` | X (Twitter) 帖子卡 | card | 1280×720 或 1080×1080 | X 推文卡、互动数据、社交引用 |
| `sprite-animation` | 像素动画解说 | poster | 竖版/横版 | 像素美术、kinetic 字体、短视频解说 |
| `team-okrs` | 团队 OKR 追踪 | dashboard | 桌面 1440 | 季度目标、KR 进度条、owner、状态 |
| `vfx-text-cursor` | VFX 文字光标 | video | 1920×1080 | 光标拖光、逐字揭示、技术叙事 |
| `video-hyperframes` | Hyperframes 视频脚本 | video | 1920×1080 | HyperFrames/Remotion 连续帧动画脚本 |
| `waitlist-page` | 等候名单页 | prototype | 桌面 1440 | 产品预发布页、邮箱捕获 |
| `web-proto-brutalist` | Brutalist 原型 | prototype | 桌面 1440 | Swiss industrial print、原型展示 |
| `web-proto-editorial` | Editorial 原型 | prototype | 桌面 1440 | Editorial minimalist、暖色画布 |
| `web-proto-soft` | Apple Soft 原型 | prototype | 桌面 1440 | Apple 调、软卡片、spring |
| `weekly-update` | 团队周报 Deck | slides | 16:9 ×8 | 周报、阻塞、指标、求助 |
| `wireframe-sketch` | 手绘线框图 | prototype | 桌面 1440 | 手绘线框、流程草图、scribble 图表 |

## html-video 完整模板场景表

| 模板 | 中文名 | 引擎 | 场景 | 支持画幅 | 适配业务场景 | 输入说明 |
| --- | --- | --- | --- | --- | --- | --- |
| `frame-bold-poster` | 大胆海报帧 | hyperframes | presentation / statement-title | 16:9, 9:16, 1:1 | 品牌宣言、文化 pitch、杂志封面式开场 | 有 schema |
| `frame-bold-signal` | 大胆信号卡帧 | hyperframes | presentation / section-title | 16:9, 9:16, 1:1 | 章节分隔、发布声明、高冲击标题 | 有 schema |
| `frame-build-minimal` | 奢华极简留白帧 | hyperframes | presentation / hero | 16:9, 1:1 | 高级产品 hero、单词概念、优雅标题卡 | 有 schema |
| `frame-creative-voltage` | 创意电压分屏帧 | hyperframes | presentation / title-card | 16:9, 1:1 | 活力品牌、活动标题、复古现代 hero | 有 schema |
| `frame-data-chart-nyt` | NYT 风数据图表帧 | hyperframes | data-viz / bar-chart | 16:9, 9:16, 1:1 | 编辑级数据图、年报、对比 reveal | 有 schema |
| `frame-data-rollup` | 数据滚动帧 | remotion | data-viz / bar-chart | 16:9, 9:16, 1:1 | 3-7 个真实数值的柱状滚动和数字计数 | 有 schema |
| `frame-decision-tree` | Decision Tree | hyperframes | explainer / flowchart | 16:9 | 决策树、流程分支、步骤图 | 有 schema |
| `frame-electric-studio` | 电光工作室分屏帧 | hyperframes | presentation / quote-card | 16:9, 1:1 | quote、testimonial、mission statement | 有 schema |
| `frame-glitch-title` | 故障艺术标题帧 | hyperframes | presentation / text-card | 16:9, 9:16, 1:1 | 科技 reveal、cyberpunk、黑客感标题 | 有 schema |
| `frame-kinetic-type` | Kinetic Type | hyperframes | presentation / text-card | 16:9 | 促销标题、强观点、punchy intro | 有 schema |
| `frame-light-leak-cinema` | 胶片漏光电影帧 | hyperframes | ambient / cinematic | 16:9, 9:16, 1:1 | 电影感开场、纪录片冷开、氛围 B-roll | 有 schema |
| `frame-liquid-bg-hero` | 流体背景 Hero 帧 | hyperframes | marketing / hero | 16:9, 9:16, 1:1 | 产品发布 hero、SaaS 视频、编辑封面 | 有 schema |
| `frame-logo-outro` | 品牌 Logo 收尾帧 | hyperframes | intro-outro / outro | 16:9, 9:16, 1:1 | 视频结尾、品牌 outro、频道 sign-off | 有 schema |
| `frame-nyt-graph` | NYT Graph | hyperframes | data-viz / editorial | 16:9 | 新闻风关键数据、时间序列、编辑级数据点 | 有 schema |
| `frame-pentagram-stat` | 瑞士网格数据帧 | hyperframes | data-viz / stat-card | 16:9, 1:1 | 单一 hero metric、benchmark、理性品牌数据页 | 有 schema |
| `frame-play-mode` | Play Mode | hyperframes | social-shorts / playful | 16:9 | 活泼社交广告、轻松 intro、趣味产品 | 有 schema |
| `frame-product-promo` | Product Promo | hyperframes | product-demo / multi-scene | 16:9 | 产品展示、多功能 reel、hero promo | 有 schema |
| `frame-product-promo-30s` | Product Promo · 30s | hyperframes | product-demo / multi-scene | 16:9 | 30 秒 SaaS/B2B 产品宣传，含音频节奏 | 有 schema |
| `frame-swiss-grid` | Swiss Grid | hyperframes | presentation / corporate | 16:9 | 公司 slide、极简报告卡、排版型标题 | 有 schema |
| `frame-takram-organic` | 东方柔和有机帧 | hyperframes | explainer / concept-diagram | 16:9, 1:1 | 系统概念、产业生态、温暖产品故事 | 有 schema |
| `frame-vignelli` | Vignelli | hyperframes | social-shorts / portrait-bold | 9:16 | 竖屏强观点、红黑标题、短视频金句 | 有 schema |
| `frame-warm-grain` | Warm Grain | hyperframes | presentation / hero | 16:9 | 产品发布、生活方式品牌、杂志感 intro | 有 schema |
| `vfx-text-cursor` | VFX 文字光标 | hyperframes | presentation / text-card | 16:9, 9:16, 1:1 | 代码 demo、技术叙事、终端感逐字揭示 | 有 schema |

## 自动适配需要的输入颗粒度

未来如果输入内容要自动适配模板，不能只给一篇文章或一段口播稿。至少需要拆到三层。

### 第一层：项目级参数

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `source_type` | 是 | `article_html`、`markdown`、`script`、`srt`、`raw_video`、`dataset`、`screenshots` |
| `target_output` | 是 | `wechat_article_html`、`xiaohongshu_cards`、`talking_head_video`、`no_human_explainer_video`、`poster`、`deck` |
| `platform` | 是 | 公众号、小红书、抖音、B站、X、微博、播客等 |
| `aspect_ratio` | 是 | 视频/图卡必须指定：`9:16`、`16:9`、`1:1`、`3:4`、长页面 |
| `duration_sec` | 视频必填 | 总时长或目标时长；若有音频，以音频时长优先 |
| `style_profile` | 建议 | 金融专业、彭博风、巫师财经、小 Lin、暖光电影、社论等 |
| `brand_profile` | 建议 | Logo、署名、口头禅、主色、禁用色、字体偏好 |
| `motion_policy` | 视频建议 | HyperFrames/GSAP/Lottie 使用边界、入场/出场、转场强度 |
| `data_policy` | 是 | 数据源优先级、是否允许示意图、是否必须真实取数、来源记录格式 |
| `asset_policy` | 是 | 图片来源、截图、用户素材、AI 生成图、是否允许网络素材 |

### 第二层：语义切片参数

每个段落、句群或视频 beat 都应转成一个 `content_part`。这是模板路由的核心颗粒度。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `segment_id` | 是 | 稳定 ID，便于回溯 |
| `start_sec` / `end_sec` | 视频必填 | 对齐口播、字幕、音频或动画时间轴 |
| `text` | 是 | 原文、口播句、标题或表格说明 |
| `content_part` | 是 | `article_title`、`opening_hook`、`overall_outline`、`chapter_divider`、`logic_chain`、`data_chart`、`financial_chart`、`data_table`、`quote`、`news_or_document`、`warning_or_risk`、`transition`、`closing_outro` 等 |
| `claim` | 建议 | 本段要表达的判断，尤其是财经分析 |
| `evidence_refs` | 数据/证据段必填 | 指向数据、截图、新闻、报告、PDF、表格的来源 ID |
| `visual_priority` | 建议 | `low`、`medium`、`high`，决定是否必须上模板 |
| `template_hint` | 可选 | 用户或 Agent 指定模板，不强制覆盖规则 |
| `avoid_templates` | 可选 | 禁止使用的模板，比如避免太花、避免社交卡 |
| `density` | 建议 | `low`、`medium`、`high`，控制文字量和图表复杂度 |
| `sync_mode` | 视频建议 | `audio_locked`、`animation_locked`、`manual_timeline` |

### 第三层：模板变量参数

不同模板需要不同变量，但可以统一成以下槽位。

| 变量族 | 常见字段 | 对应模板 |
| --- | --- | --- |
| 标题/封面 | `title`、`subtitle`、`kicker`、`date`、`author`、`tagline` | `frame-liquid-bg-hero`、`frame-glitch-title`、`poster-hero`、`article-magazine` |
| 章节/大纲 | `chapter_no`、`chapter_title`、`items[]`、`active_index` | `frame-bold-signal`、`deck-blueprint`、`weekly-update` |
| 逻辑链 | `nodes[]`、`edges[]`、`active_node`、`relationship_label` | `frame-decision-tree`、`frame-flowchart-sticky`、`wireframe-sketch` |
| 图表 | `series[]`、`x_axis`、`y_axis`、`unit`、`source`、`as_of`、`annotations[]` | `frame-data-chart-nyt`、`frame-nyt-graph`、`finance-report` |
| 数字卡 | `metric`、`value`、`unit`、`delta`、`comparison`、`source` | `frame-pentagram-stat`、`frame-data-rollup`、`data-report` |
| 表格 | `columns[]`、`rows[]`、`highlight_rows[]`、`source` | `data-report`、`finance-report`、`dashboard` |
| 文档/截图 | `image_path`、`crop_box`、`caption`、`source_url`、`highlight_regions[]` | `doc-kami-parchment`、`mockup-device-3d`、`docs-page` |
| 社交/评论 | `author`、`handle`、`avatar`、`text`、`metrics`、`platform` | `social-x-post-card`、`social-reddit-card`、`card-xiaohongshu` |
| 手机/桌面 | `device_type`、`screen_image`、`url`、`callouts[]` | `mobile-app`、`mobile-onboarding`、`mockup-device-3d` |
| 结尾/品牌 | `logo`、`brand_name`、`cta`、`disclaimer`、`next_topic` | `frame-logo-outro`、`poster-hero` |

## 最小输入与理想输入

### 最小可运行输入

```json
{
  "target_output": "no_human_explainer_video",
  "platform": "douyin",
  "aspect_ratio": "9:16",
  "source_type": "article_html",
  "source_path": "/path/to/article.html",
  "duration_sec": 180,
  "style_profile": "金融专业 / 彭博风 / 竖屏",
  "data_policy": "图表必须使用文章内真实数据或重新取数"
}
```

这种输入只能做基础切片和模板自动选择，质量取决于 Agent 对文章的理解。

### 理想生产输入

```json
{
  "target_output": "talking_head_video",
  "platform": "douyin",
  "aspect_ratio": "9:16",
  "duration_sec": 420,
  "source_type": "raw_video",
  "raw_video_path": "/path/to/talking-head.mov",
  "script_or_srt_path": "/path/to/checked.srt",
  "style_profile": {
    "reference": "巫师财经 / 小 Lin",
    "tone": "金融专业、节奏紧、证据优先",
    "visual_system": "Bloomberg dark, amber accent, compact typography"
  },
  "segments": [
    {
      "segment_id": "s01",
      "start_sec": 0,
      "end_sec": 7.5,
      "content_part": "opening_hook",
      "text": "AI 真的就一定等于美国吗？",
      "claim": "开场提出反常识问题",
      "visual_priority": "high"
    },
    {
      "segment_id": "s02",
      "start_sec": 33.2,
      "end_sec": 48.8,
      "content_part": "financial_chart",
      "text": "AI 回调时资金没有低切高，而是在高位资产内部重新定价。",
      "evidence_refs": ["chart_ai_vs_industry_rotation_20260701"],
      "visual_priority": "high"
    }
  ],
  "evidence_assets": [
    {
      "id": "chart_ai_vs_industry_rotation_20260701",
      "type": "chart_data",
      "source": "Tushare / 东方财富 / 用户文章",
      "as_of": "2026-07-01",
      "data_path": "/path/to/chart-data.json"
    }
  ]
}
```

这种输入可以稳定完成高质量适配：模板选择、时长控制、图表生成、证据绑定、字幕/口播同步都能闭环。

## 适配决策规则

1. `content_part` 决定候选模板，不允许直接让模型凭感觉选模板。
2. `target_output + platform + aspect_ratio` 决定可用模板集合；不支持 `9:16` 的 html-video 模板只能作为视觉参考。
3. `evidence_refs` 决定事实层；图表/表格/截图没有证据就不能进入数据模板。
4. 同一期视频限定一个主视觉系统，最多两个辅助模板族，避免风格乱跳。
5. 3 分钟视频通常 18-35 个视觉段足够；不是每句话都上模板。
6. 转场模板只服务节奏，不能出现模板名、slot、position、debug 标签。
7. Lottie 只做辅助动效；金融数据、财报、市场图表必须由 HTML/SVG/Canvas/Remotion 数据驱动。

## 后续落地建议

建议新增或强化 `dasheng-video-template-router`：

```text
dasheng-video-template-router/
├── SKILL.md
├── references/
│   ├── template-business-scenarios.md
│   ├── script-slot-mapping.md
│   ├── html-video-template-capabilities.md
│   └── html-anything-visual-references.md
└── scripts/
    ├── scan_template_pool.py
    ├── classify_script_segments.py
    └── build_video_template_timeline.py
```

这个 skill 不应复制外部模板源码，只做四件事：

1. 扫描外部项目当前模板池。
2. 把文章/口播切成标准 `content_part`。
3. 按平台、画幅、证据、风格选择模板。
4. 输出 `video_template_timeline.json` 或 `html_article_template_plan.json`，交给下游渲染器。
