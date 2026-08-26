# HTML Anything Video Template Routing

Date: 2026-06-13

本文件记录无真人视频链路的模板路由层。这个层解决的问题是：文章内容不能直接变成一堆自绘卡片，必须先拆成内容部件，再匹配 HTML Anything 的模板。

## Core Flow

```text
article.html
  -> explainer_storyboard.json
  -> content_part classification
  -> HTML Anything template router
  -> html_anything_video_timeline.json
  -> motion_policy (HyperFrames + GSAP + optional Lottie)
  -> renderer / html-video / ffmpeg compose
```

## Required Commands

```bash
python3 scripts/build_html_anything_template_router.py \
  --output configs/video/html_anything_template_router.json

python3 scripts/video_explainer_storyboard.py \
  --html <article.html> \
  --template-router configs/video/html_anything_template_router.json \
  --output <explainer_storyboard.json> \
  --preview-html <storyboard_preview.html>

python3 scripts/build_html_anything_video_timeline.py \
  --storyboard <explainer_storyboard.json> \
  --article-html <article.html> \
  --template-router configs/video/html_anything_template_router.json \
  --output <html_anything_video_timeline.json>

python3 scripts/render_html_anything_timeline_pack.py \
  --timeline <html_anything_video_timeline.json> \
  --output-dir <scene_pack_dir> \
  --motion-runtime auto
```

## Content Part Mapping

| Content Part | Primary Template | Typical Use |
| --- | --- | --- |
| `article_title` | `frame-liquid-bg-hero` | 标题、封面、视觉锚点 |
| `opening_hook` | `frame-glitch-title` | 开头钩子、冲击性入场 |
| `overall_outline` | `frame-flowchart-sticky` | 总纲、章节地图、观点框架 |
| `chapter_divider` | `frame-light-leak-cinema` | 章节卡、段落切换 |
| `logic_chain` | `frame-flowchart-sticky` | 因果链、推导链、传导路径 |
| `data_chart` | `frame-data-chart-nyt` | 折线、柱状、范围带、数据 reveal |
| `financial_chart` | `finance-report` | 市场、宏观、财务、资产价格 |
| `data_table` | `data-report` | 表格、指标清单、财务明细 |
| `quote` | `card-twitter` | 金句、短观点、社交引用 |
| `pull_quote` | `blog-post` | 正文强调句、放大引语 |
| `warning_or_risk` | `deck-safety-alert` | 风险、暴跌、政策红线、警示 |
| `news_or_document` | `doc-kami-parchment` | 新闻截图、文档、来源材料 |
| `source_citation` | `doc-kami-parchment` | 来源说明、报告引用 |
| `phone_mockup` | `mobile-app` | 手机框、App 截图 |
| `desktop_mockup` | `mockup-device-3d` | 桌面产品、网页、大屏截图 |
| `chat_box` | `social-x-post-card` | 聊天框、评论、社交对话 |
| `social_post` | `social-x-post-card` | 推文、Reddit、小红书社交内容 |
| `xiaohongshu_card` | `card-xiaohongshu` | 小红书图文卡、轮播 |
| `dashboard_screen` | `dashboard` | 仪表盘、后台、控制台 |
| `kanban_or_process` | `kanban-board` | 流程、协作看板、任务板 |
| `product_or_app_ui` | `mobile-app` | 产品界面、App 原型 |
| `broll_mood` | `frame-light-leak-cinema` | 氛围 B-roll、视觉隐喻 |
| `transition` | `frame-glitch-title` | 转场、故障、闪白、光标揭示 |
| `brand_mark` | `frame-logo-outro` | 署名、品牌、结尾落版 |
| `closing_outro` | `frame-logo-outro` | 结尾和 CTA |

## Example: `国家不让你炒美股2.html`

当前文章被拆成 44 个 HTML Anything 时间轴部件，约 227 秒：

| Template | Count |
| --- | ---: |
| `frame-glitch-title` | 9 |
| `frame-light-leak-cinema` | 8 |
| `finance-report` | 8 |
| `frame-flowchart-sticky` | 5 |
| `data-report` | 4 |
| `frame-data-chart-nyt` | 4 |
| `deck-safety-alert` | 3 |
| `frame-logo-outro` | 2 |
| `frame-liquid-bg-hero` | 1 |

This is the baseline expected shape: title, hook, outline, chapter cards, logic-chain frames, finance-data frames, table frames, transitions, and outro are separate timeline units.

## Motion Policy

每个 `html_anything_video_timeline.json` 场景必须带 `motion_policy`。

| Field | Use |
| --- | --- |
| `framework` | 默认 `hyperframes`，表示按 HTML/CSS/JS 可编程视频帧组织 |
| `animation` | GSAP 风格时间轴策略，例如 `gsap_chart_reveal`、`gsap_path_draw`、`gsap_table_scan` |
| `lottie_role` | 可选 Lottie 动效角色，例如 `risk_alarm`、`market_ticker_accent`、`document_scan` |
| `lottie_keywords` | 后续由 Agent 搜索或生成 Lottie 素材的关键词 |
| `fact_rule` | 数据相关场景必须声明：Lottie 只能装饰，真实数据仍来自文章 |

执行边界：

- HyperFrames 是主框架，负责把 scene 变成可渲染 HTML 视频帧。
- GSAP 负责入场、出场、错峰 reveal、图表绘制、路径高亮、表格扫描。
- Lottie 只做辅助动效和氛围层，不替代图表、表格、截图、来源证据。
- 如果没有合适 Lottie，场景必须仍然能靠 HTML/SVG/GSAP 独立成立。

Runtime modes:

- `--motion-runtime auto`: 从外部 `html-video` 的 `node_modules` 读取并内联真实 `gsap` 与 `lottie-web`，同时为每个 scene 生成轻量 Lottie JSON。
- `--motion-runtime lite`: 不内联真实库，只使用离线 GSAP-compatible 小运行时，适合快速调试。

依赖检查：

```bash
python3 scripts/ensure_video_external_deps.py \
  --dep html-video \
  --mode check
```

`html-video` 需要包含 `gsap` 和 `lottie-web`。安装/补齐时运行：

```bash
python3 scripts/ensure_video_external_deps.py \
  --dep html-video \
  --mode install \
  --install-node-deps
```
