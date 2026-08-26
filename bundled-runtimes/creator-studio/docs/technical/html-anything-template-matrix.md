# HTML Anything 模板使用矩阵

生成时间：2026-06-13T13:10:49+08:00

用途：把文章/口播稿拆成可执行的视觉部件，自动匹配 HTML Anything 模板，再进入视频时间轴。

## 内容部件到模板

| 内容部件 | 触发场景 | 主模板 | 备选模板 | 时间轴策略 |
| --- | --- | --- | --- | --- |
| `article_title` / 标题 / 封面 | 文章标题、视频主标题、封面标题。 | `frame-liquid-bg-hero` | `vfx-text-cursor`, `frame-glitch-title`, `poster-hero`, `magazine-poster` | 3-6s，随主标题逐字或分层入场。 |
| `article_subtitle` / 副标题 / 氛围解释 | 副标题、导语、背景气氛句。 | `frame-light-leak-cinema` | `deck-guizang-editorial`, `deck-swiss-international` | 3-6s，接标题后轻过渡。 |
| `opening_hook` / 开头钩子 | 开场 3-8 秒强钩子、反常识判断、冲突句。 | `frame-glitch-title` | `frame-liquid-bg-hero`, `vfx-text-cursor`, `motion-frames`, `frame-data-chart-nyt` | 4-8s，必须卡住口播第一句冲突点。 |
| `closing_outro` / 结尾 / CTA | 结尾总结、关注提示、下期预告。 | `frame-logo-outro` | `poster-hero`, `card-twitter` | 4-7s，跟最后一句结论对齐。 |
| `chapter_divider` / 章节标题 | 一、二、三等章节切换，或口播进入下一段。 | `frame-light-leak-cinema` | `frame-glitch-title`, `deck-swiss-international`, `deck-dir-key-nav`, `deck-blueprint` | 2-4s，短，不抢正文。 |
| `overall_outline` / 文章总纲 / 大纲 | 文章总框架、目录、核心问题列表。 | `frame-flowchart-sticky` | `deck-blueprint`, `deck-swiss-international`, `deck-guizang-editorial`, `deck-course-module` | 6-10s，覆盖口播总纲，允许逐项高亮。 |
| `logic_chain` / 逻辑链路 / 推导 | 因果推导、传导路径、政策/市场/产业三段链。 | `frame-flowchart-sticky` | `deck-blueprint`, `wireframe-sketch`, `deck-graphify-dark` | 6-12s，节点跟随口播逐步点亮。 |
| `timeline` / 时间线 / 进度 | 事件先后、政策节奏、口播进度。 | `deck-blueprint` | `weekly-update`, `deck-dir-key-nav`, `frame-flowchart-sticky`, `social-spotify-card` | 5-10s，按事件顺序推进。 |
| `data_chart` / 图表 / 数据可视化 | 折线、柱状、对比、散点、范围带等真实数据。 | `frame-data-chart-nyt` | `data-report`, `finance-report`, `frame-flowchart-sticky`, `card-twitter` | 6-12s，先出现坐标/指标，再 reveal 数据结论。 |
| `financial_chart` / 金融市场图表 | 股指、债券、汇率、商品、估值、财务指标。 | `finance-report` | `frame-data-chart-nyt`, `data-report`, `dashboard`, `invoice` | 6-12s，跟关键市场数据或财务指标同步。 |
| `data_table` / 表格 / 指标清单 | 文章表格、指标清单、财务明细、横向对比。 | `data-report` | `finance-report`, `dashboard`, `invoice`, `dating-web` | 5-10s，表格只显示关键行，逐行扫光。 |
| `kpi_card` / 关键数字卡 | 单个关键数字、同比环比、概率、估值、融资额。 | `data-report` | `finance-report`, `dashboard`, `frame-data-chart-nyt`, `dating-web` | 3-6s，适合口播中单个强数字。 |
| `article_image` / 文章图片 / 资料截图 | 文章内图片、截图、资料图、报告截屏。 | `doc-kami-parchment` | `article-magazine`, `mockup-device-3d`, `frame-light-leak-cinema` | 4-8s，配合放大/裁切/标注，不要静止堆图。 |
| `quote` / 引用 / 社交观点 | 社交媒体引用、外部人物原话、短观点。 | `card-twitter` | `blog-post`, `article-magazine`, `doc-kami-parchment`, `card-xiaohongshu` | 3-6s，随引用句出现。 |
| `pull_quote` / 正文金句 | 作者金句、需要居中放大的判断句。 | `blog-post` | `article-magazine`, `card-twitter`, `deck-guizang-editorial`, `digital-eguide` | 3-6s，跟金句同步放大。 |
| `warning_or_risk` / 风险警示 | 风险、暴跌、踩踏、政策红线、反转信号。 | `deck-safety-alert` | `frame-glitch-title`, `deck-hermes-cyber`, `deck-swiss-international`, `eng-runbook` | 4-8s，适合突然转折或风险提示。 |
| `news_or_document` / 新闻 / 文档证据 | 新闻事实、官方文件、研究报告、公告。 | `doc-kami-parchment` | `article-magazine`, `docs-page`, `blog-post`, `competitive-teardown` | 5-9s，证据画面可做局部 zoom。 |
| `source_citation` / 来源引用 | 数据来源、脚注、报告出处。 | `doc-kami-parchment` | `docs-page`, `eng-runbook`, `article-magazine`, `competitive-teardown` | 2-4s，短停留，不占主节奏。 |
| `phone_mockup` / 手机框展示 | App、手机截图、微信/小红书/交易软件界面。 | `mobile-app` | `mobile-onboarding`, `mockup-device-3d`, `gamified-app`, `frame-macos-notification` | 5-9s，手机画面滑入并局部放大。 |
| `desktop_mockup` / 桌面框展示 | 网页、后台、大屏、PC 软件截图。 | `mockup-device-3d` | `web-proto-editorial`, `web-proto-soft`, `prototype-web`, `pricing-page` | 5-9s，网页/桌面画面进入再局部强调。 |
| `chat_box` / 聊天框 / 评论 | 聊天记录、评论区、问答对话。 | `social-x-post-card` | `social-reddit-card`, `frame-macos-notification`, `card-twitter`, `card-xiaohongshu` | 4-8s，按对话气泡逐条出现。 |
| `social_post` / 社交帖子 | X/Reddit/小红书/微博式帖子。 | `social-x-post-card` | `social-reddit-card`, `card-twitter`, `social-carousel`, `card-xiaohongshu` | 4-8s，按帖文标题和核心句出现。 |
| `xiaohongshu_card` / 小红书卡片 | 小红书封面、笔记页、图文轮播。 | `card-xiaohongshu` | `deck-xhs-post`, `deck-xhs-white`, `deck-xhs-pastel` | 4-8s，适合竖版轮播节奏。 |
| `dashboard_screen` / 仪表盘 | 数据后台、监控面板、组合指标。 | `dashboard` | `live-dashboard`, `social-media-dashboard`, `social-media-matrix`, `dating-web` | 6-10s，KPI 和图表分层显示。 |
| `kanban_or_process` / 流程 / 看板 | 流程拆解、任务状态、执行步骤。 | `kanban-board` | `team-okrs`, `pm-spec`, `eng-runbook` | 5-9s，步骤逐列推进。 |
| `product_or_app_ui` / 产品界面 | 产品原型、功能页、应用落地演示。 | `mobile-app` | `saas-landing`, `prototype-web`, `web-proto-soft`, `gamified-app` | 5-9s，随功能点切换。 |
| `broll_mood` / 氛围 B-roll | 无具体数据但需要视觉情绪承托的段落。 | `frame-light-leak-cinema` | `motion-frames`, `sprite-animation`, `frame-liquid-bg-hero`, `frame-data-chart-nyt` | 3-7s，作为过渡或情绪缓冲。 |
| `transition` / 转场 | 段落之间 1-3 秒节奏切换。 | `frame-glitch-title` | `vfx-text-cursor`, `frame-light-leak-cinema`, `motion-frames`, `frame-data-chart-nyt` | 1-3s，只做节奏，不放开发提示文字。 |
| `brand_mark` / 品牌落版 | 片尾署名、栏目品牌、Logo 落版。 | `frame-logo-outro` | `poster-hero`, `card-twitter` | 3-5s，片尾落版。 |
| `deck_explainer` / 连续解释 Deck | 需要多页连续解释的复杂段落。 | `video-hyperframes` | `deck-swiss-international`, `deck-guizang-editorial`, `deck-magazine-web`, `deck-blueprint` | 8-20s，拆成多页或多个子场景。 |

## 关键文章元素映射

| 文章/视频元素 | 应用规则 | 首选模板 |
| --- | --- | --- |
| 标题 | 进入视频的第一视觉锚点；主标题逐字或分层入场。 | `frame-liquid-bg-hero`, `vfx-text-cursor`, `frame-glitch-title`, `poster-hero` |
| 副标题/导语 | 承接标题，不承担复杂信息密度。 | `frame-light-leak-cinema`, `deck-guizang-editorial`, `deck-swiss-international` |
| 文章总体架构大纲 | 转成章节地图，随口播逐项高亮。 | `frame-flowchart-sticky`, `deck-blueprint`, `deck-swiss-international`, `deck-guizang-editorial` |
| 章节标题 | 短节奏卡，2-4 秒，不要长篇文字。 | `frame-light-leak-cinema`, `frame-glitch-title`, `deck-swiss-international`, `deck-dir-key-nav` |
| 逻辑链路 | 政策、市场、产业、资金之间的因果关系。 | `frame-flowchart-sticky`, `deck-blueprint`, `wireframe-sketch`, `deck-graphify-dark` |
| 真实数据图表 | 必须来自文章数据或重新取数，不能造假图。 | `frame-data-chart-nyt`, `data-report`, `finance-report`, `frame-flowchart-sticky` |
| 金融市场图表 | 资产价格、收益率、估值、财务指标。 | `finance-report`, `frame-data-chart-nyt`, `data-report`, `dashboard` |
| 表格 | 只展示关键行列，适合逐行扫光。 | `data-report`, `finance-report`, `dashboard`, `invoice` |
| 文章图片/资料图 | 复用文章图片，做裁切、放大、重点标注。 | `doc-kami-parchment`, `article-magazine`, `mockup-device-3d`, `frame-light-leak-cinema` |
| 引用/金句 | 短引用用社交卡，作者判断用 pull quote。 | `card-twitter`, `blog-post`, `article-magazine`, `doc-kami-parchment` |
| 开头钩子 | 冲突、反常识、悬念句。 | `frame-glitch-title`, `frame-liquid-bg-hero`, `vfx-text-cursor`, `motion-frames` |
| 结尾 | 结论、CTA、品牌落版。 | `frame-logo-outro`, `poster-hero`, `card-twitter` |
| 手机框展示 | 微信、小红书、交易软件、App 截图。 | `mobile-app`, `mobile-onboarding`, `mockup-device-3d`, `gamified-app` |
| 桌面框展示 | 网页、后台、大屏、PC 端材料。 | `mockup-device-3d`, `web-proto-editorial`, `web-proto-soft`, `prototype-web` |
| 聊天框/评论 | 评论区、私信、问答式内容。 | `social-x-post-card`, `social-reddit-card`, `frame-macos-notification`, `card-twitter` |

## 模板到使用场景

| 模板 | 中文名 | 类别 | 适合内容 | 推荐触发 | 填充要求 |
| --- | --- | --- | --- | --- | --- |
| `article-magazine` | 杂志文章 | article | 文章图片 / 资料截图、引用 / 社交观点、正文金句、新闻 / 文档证据、来源引用 | 文章内图片、截图、资料图、报告截屏。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `blog-post` | 博客长文 | article | 引用 / 社交观点、正文金句、新闻 / 文档证据 | 社交媒体引用、外部人物原话、短观点。 | 必须填入原文句子、评论、引用或口播金句；避免泛泛文案。 |
| `card-twitter` | Twitter 分享卡 | card | 结尾 / CTA、引用 / 社交观点、正文金句、聊天框 / 评论、社交帖子、品牌落版 | 结尾总结、关注提示、下期预告。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `card-xiaohongshu` | 小红书图文卡片 | card | 小红书卡片、引用 / 社交观点、社交帖子、聊天框 / 评论 | 小红书封面、笔记页、图文轮播。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `competitive-teardown` | 竞品拆解 | doc | 新闻 / 文档证据、来源引用 | 新闻事实、官方文件、研究报告、公告。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `dashboard` | 管理后台仪表板 | dashboard | 金融市场图表、表格 / 指标清单、关键数字卡、仪表盘 | 股指、债券、汇率、商品、估值、财务指标。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `data-report` | 数据可视化报告 | data | 图表 / 数据可视化、金融市场图表、表格 / 指标清单、关键数字卡 | 折线、柱状、对比、散点、范围带等真实数据。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `dating-web` | 社区 / 配对数据墙 | dashboard | 仪表盘、表格 / 指标清单、关键数字卡、图表 / 数据可视化 | 数据后台、监控面板、组合指标。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `deck-blueprint` | 蓝图架构 Deck | slides | 文章总纲 / 大纲、逻辑链路 / 推导、时间线 / 进度、章节标题、连续解释 Deck | 文章总框架、目录、核心问题列表。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-course-module` | 课程 / 培训 Deck | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-dir-key-nav` | 极简方向键 Keynote | slides | 章节标题、时间线 / 进度、文章总纲 / 大纲、连续解释 Deck、表格 / 指标清单 | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-graphify-dark` | 暗底图谱 Deck | slides | 逻辑链路 / 推导、章节标题、文章总纲 / 大纲、连续解释 Deck | 因果推导、传导路径、政策/市场/产业三段链。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-guizang-editorial` | 贵赞编辑墨水 Deck | slides | 副标题 / 氛围解释、文章总纲 / 大纲、正文金句、连续解释 Deck、章节标题 | 副标题、导语、背景气氛句。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-hermes-cyber` | Cyber Terminal Deck | slides | 风险警示、章节标题、文章总纲 / 大纲、连续解释 Deck | 风险、暴跌、踩踏、政策红线、反转信号。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-magazine-web` | 杂志风网页 PPT | slides | 连续解释 Deck、章节标题、文章总纲 / 大纲 | 需要多页连续解释的复杂段落。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-obsidian-claude` | GitHub Dark 紫渐变 Deck | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-open-slide-canvas` | 1920 画布自由 Deck | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-pitch` | 投资人 Pitch Deck | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-presenter-mode` | 演讲者模式 Deck | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-product-launch` | 产品发布 Keynote | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-replit` | Replit Slides 风 Deck | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-safety-alert` | 安全 / 风险红色 Deck | slides | 风险警示、章节标题、文章总纲 / 大纲、连续解释 Deck | 风险、暴跌、踩踏、政策红线、反转信号。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-simple` | 通用 Simple Deck | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-swiss-international` | 瑞士国际主义 Deck | slides | 副标题 / 氛围解释、章节标题、文章总纲 / 大纲、连续解释 Deck、风险警示 | 副标题、导语、背景气氛句。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-tech-sharing` | 技术分享 Deck | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `deck-xhs-pastel` | 马卡龙慢生活 Deck | slides | 小红书卡片、章节标题、文章总纲 / 大纲、连续解释 Deck | 小红书封面、笔记页、图文轮播。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-xhs-post` | 小红书图文 Deck | slides | 小红书卡片、章节标题、文章总纲 / 大纲、连续解释 Deck | 小红书封面、笔记页、图文轮播。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `deck-xhs-white` | 白底杂志风 Deck | slides | 小红书卡片、章节标题、文章总纲 / 大纲、连续解释 Deck | 小红书封面、笔记页、图文轮播。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `digital-eguide` | 电子指南 | article | 新闻 / 文档证据、正文金句、表格 / 指标清单、引用 / 社交观点 | 新闻事实、官方文件、研究报告、公告。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `doc-kami-parchment` | Kami 羊皮纸文档 | doc | 文章图片 / 资料截图、引用 / 社交观点、新闻 / 文档证据、来源引用 | 文章内图片、截图、资料图、报告截屏。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `docs-page` | 技术文档页 | doc | 新闻 / 文档证据、来源引用 | 新闻事实、官方文件、研究报告、公告。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `email-marketing` | 营销邮件 | email | 新闻 / 文档证据、表格 / 指标清单 | 新闻事实、官方文件、研究报告、公告。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `eng-runbook` | 工程 Runbook | doc | 来源引用、流程 / 看板、新闻 / 文档证据、表格 / 指标清单、风险警示 | 数据来源、脚注、报告出处。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `exec-briefing-memo` | 高管决策简报 | doc | 新闻 / 文档证据、来源引用 | 新闻事实、官方文件、研究报告、公告。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `experiment-readout` | 实验复盘 | data | 图表 / 数据可视化、表格 / 指标清单 | 折线、柱状、对比、散点、范围带等真实数据。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `finance-report` | 季度财报 | finance | 图表 / 数据可视化、金融市场图表、表格 / 指标清单、关键数字卡 | 折线、柱状、对比、散点、范围带等真实数据。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `flowai-team-dashboard` | FlowAI 团队管理 | dashboard | 仪表盘、表格 / 指标清单、关键数字卡、图表 / 数据可视化 | 数据后台、监控面板、组合指标。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `frame-data-chart-nyt` | NYT 风数据图表帧 | video | 图表 / 数据可视化、金融市场图表、关键数字卡、转场、开头钩子、氛围 B-roll | 折线、柱状、对比、散点、范围带等真实数据。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `frame-flowchart-sticky` | 便利贴流程图帧 | video | 文章总纲 / 大纲、逻辑链路 / 推导、时间线 / 进度、图表 / 数据可视化、转场、开头钩子 | 文章总框架、目录、核心问题列表。 | 可承载数据，但只有在文章提供真实数据时使用。 |
| `frame-glitch-title` | 故障艺术标题帧 | video | 标题 / 封面、开头钩子、章节标题、风险警示、转场、氛围 B-roll | 文章标题、视频主标题、封面标题。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `frame-light-leak-cinema` | 胶片漏光电影帧 | video | 副标题 / 氛围解释、章节标题、文章图片 / 资料截图、氛围 B-roll、转场、开头钩子 | 副标题、导语、背景气氛句。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `frame-liquid-bg-hero` | 流体背景 Hero 帧 | poster | 标题 / 封面、开头钩子、氛围 B-roll、引用 / 社交观点、转场 | 文章标题、视频主标题、封面标题。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `frame-logo-outro` | 品牌 Logo 收尾帧 | video | 结尾 / CTA、品牌落版、转场、开头钩子、氛围 B-roll | 结尾总结、关注提示、下期预告。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `frame-macos-notification` | macOS 通知横幅 | card | 聊天框 / 评论、引用 / 社交观点、社交帖子、手机框展示、转场 | 聊天记录、评论区、问答对话。 | 必须填入原文句子、评论、引用或口播金句；避免泛泛文案。 |
| `gamified-app` | 游戏化 App 多屏 | mobile | 手机框展示、产品界面 | App、手机截图、微信/小红书/交易软件界面。 | 填入真实界面截图或文章中提到的平台画面。 |
| `hr-onboarding` | 新员工入职页 | doc | 新闻 / 文档证据、来源引用 | 新闻事实、官方文件、研究报告、公告。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `invoice` | 可打印发票 | finance | 表格 / 指标清单、金融市场图表、关键数字卡 | 文章表格、指标清单、财务明细、横向对比。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `kanban-board` | 看板 / Kanban | dashboard | 流程 / 看板、仪表盘、表格 / 指标清单、关键数字卡 | 流程拆解、任务状态、执行步骤。 | 可承载数据，但只有在文章提供真实数据时使用。 |
| `live-dashboard` | Notion 风团队仪表板 | dashboard | 仪表盘、表格 / 指标清单、关键数字卡 | 数据后台、监控面板、组合指标。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `magazine-poster` | 杂志风海报 | poster | 标题 / 封面、氛围 B-roll | 文章标题、视频主标题、封面标题。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `meeting-notes` | 会议纪要 | doc | 新闻 / 文档证据、来源引用 | 新闻事实、官方文件、研究报告、公告。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `mobile-app` | iPhone App 单屏 | mobile | 手机框展示、产品界面 | App、手机截图、微信/小红书/交易软件界面。 | 填入真实界面截图或文章中提到的平台画面。 |
| `mobile-onboarding` | App 引导多屏 | mobile | 手机框展示、产品界面 | App、手机截图、微信/小红书/交易软件界面。 | 填入真实界面截图或文章中提到的平台画面。 |
| `mockup-device-3d` | iPhone × MacBook 立体展架 | poster | 文章图片 / 资料截图、手机框展示、桌面框展示、标题 / 封面、氛围 B-roll | 文章内图片、截图、资料图、报告截屏。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `motion-frames` | 动效英雄帧 | video | 开头钩子、氛围 B-roll、转场 | 开场 3-8 秒强钩子、反常识判断、冲突句。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `pm-spec` | PRD / 产品 Spec | doc | 流程 / 看板、新闻 / 文档证据、来源引用 | 流程拆解、任务状态、执行步骤。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `poster-hero` | 营销海报 | poster | 标题 / 封面、结尾 / CTA、品牌落版、氛围 B-roll | 文章标题、视频主标题、封面标题。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `ppt-keynote` | Keynote 风格 PPT | slides | 章节标题、文章总纲 / 大纲、连续解释 Deck | 一、二、三等章节切换，或口播进入下一段。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `pricing-page` | 定价页 | prototype | 桌面框展示、产品界面、表格 / 指标清单 | 网页、后台、大屏、PC 软件截图。 | 填入真实界面截图或文章中提到的平台画面。 |
| `prototype-web` | Web 产品原型 | prototype | 桌面框展示、产品界面 | 网页、后台、大屏、PC 软件截图。 | 填入真实界面截图或文章中提到的平台画面。 |
| `resume-modern` | 极简简历 | resume | 新闻 / 文档证据 | 新闻事实、官方文件、研究报告、公告。 | 必须复用文章图片、截图、报告或来源材料；需要局部标注。 |
| `saas-landing` | SaaS Landing | prototype | 产品界面、桌面框展示 | 产品原型、功能页、应用落地演示。 | 填入真实界面截图或文章中提到的平台画面。 |
| `social-carousel` | 社交媒体三联 | card | 社交帖子、引用 / 社交观点、聊天框 / 评论 | X/Reddit/小红书/微博式帖子。 | 必须填入原文句子、评论、引用或口播金句；避免泛泛文案。 |
| `social-media-dashboard` | 社媒创作者仪表板 | dashboard | 仪表盘、表格 / 指标清单、关键数字卡 | 数据后台、监控面板、组合指标。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `social-media-matrix` | 社媒矩阵追踪面板 | dashboard | 仪表盘、表格 / 指标清单、关键数字卡 | 数据后台、监控面板、组合指标。 | 必须使用文章已验证数据、表格或图表；禁止虚构指标。 |
| `social-reddit-card` | Reddit 帖子卡 | card | 聊天框 / 评论、社交帖子、引用 / 社交观点 | 聊天记录、评论区、问答对话。 | 必须填入原文句子、评论、引用或口播金句；避免泛泛文案。 |
| `social-spotify-card` | Spotify 正在播放卡 | card | 引用 / 社交观点、社交帖子、聊天框 / 评论、时间线 / 进度 | 社交媒体引用、外部人物原话、短观点。 | 必须填入原文句子、评论、引用或口播金句；避免泛泛文案。 |
| `social-x-post-card` | X (Twitter) 帖子卡 | card | 聊天框 / 评论、社交帖子、引用 / 社交观点、图表 / 数据可视化 | 聊天记录、评论区、问答对话。 | 必须填入原文句子、评论、引用或口播金句；避免泛泛文案。 |
| `sprite-animation` | 像素动画解说 | poster | 氛围 B-roll、标题 / 封面 | 无具体数据但需要视觉情绪承托的段落。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `team-okrs` | 团队 OKR 追踪 | dashboard | 流程 / 看板、仪表盘、表格 / 指标清单、关键数字卡、时间线 / 进度 | 流程拆解、任务状态、执行步骤。 | 可承载数据，但只有在文章提供真实数据时使用。 |
| `vfx-text-cursor` | VFX 文字光标 | video | 标题 / 封面、开头钩子、转场、氛围 B-roll、引用 / 社交观点 | 文章标题、视频主标题、封面标题。 | 填入标题、章节名、结论或转场词；画面只服务节奏。 |
| `video-hyperframes` | Hyperframes 视频脚本 | video | 连续解释 Deck、转场、开头钩子、氛围 B-roll | 需要多页连续解释的复杂段落。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `waitlist-page` | 等候名单页 | prototype | 桌面框展示、产品界面 | 网页、后台、大屏、PC 软件截图。 | 填入真实界面截图或文章中提到的平台画面。 |
| `web-proto-brutalist` | Brutalist 原型 | prototype | 桌面框展示、产品界面 | 网页、后台、大屏、PC 软件截图。 | 填入真实界面截图或文章中提到的平台画面。 |
| `web-proto-editorial` | Editorial 原型 | prototype | 桌面框展示、产品界面 | 网页、后台、大屏、PC 软件截图。 | 填入真实界面截图或文章中提到的平台画面。 |
| `web-proto-soft` | Apple Soft 原型 | prototype | 桌面框展示、产品界面、手机框展示 | 网页、后台、大屏、PC 软件截图。 | 填入真实界面截图或文章中提到的平台画面。 |
| `weekly-update` | 团队周报 Deck | slides | 时间线 / 进度、章节标题、文章总纲 / 大纲、连续解释 Deck | 事件先后、政策节奏、口播进度。 | 按内容部件填入标题、短句、要点或画面素材。 |
| `wireframe-sketch` | 手绘线框图 | prototype | 逻辑链路 / 推导、桌面框展示、产品界面、图表 / 数据可视化、表格 / 指标清单、转场 | 因果推导、传导路径、政策/市场/产业三段链。 | 可承载数据，但只有在文章提供真实数据时使用。 |

## 时间轴原则

- 先由口播稿或文章段落估算语速，再把视觉部件贴到对应句群。
- 一个内容部件只解决一个视觉任务：标题、总纲、图表、表格、引用、证据、转场不要混在一张卡里。
- 图表、表格、金融数据必须复用 Draft 文章里的真实数据；没有数据就回到 Draft/取数环节补，不允许生成假图。
- 转场和章节卡要短；数据图、逻辑链、证据画面可以稍长，但必须跟口播语义同步 reveal。
- 最终视频不显示开发标签、模板名、调试进度条。
