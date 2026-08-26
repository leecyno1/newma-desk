---
name: dasheng-html-anything-bridge
description: Use when Newma draft or transwrite needs HTML Anything templates, editable article HTML, social cards, posters, or visual HTML references.
---

# Newma HTML Anything Bridge

## Role

Use the external `html-anything` repository as the design/template reference library for Newma HTML outputs. This is a local-first visual language source, not the fact engine.

`html-anything` is an external dependency, not vendored into this repo and not version-locked. Default path: `${HTML_ANYTHING_ROOT:-vendor/reserved/render/html-anything}`; override with `HTML_ANYTHING_ROOT`.

Check or install before first use:

```bash
python3 scripts/ensure_video_external_deps.py --dep html-anything --mode check
python3 scripts/ensure_video_external_deps.py --dep html-anything --mode install --install-node-deps
```

## Best Surfaces

- WeChat/article HTML: `article-magazine`, `blog-post`, `doc-kami-parchment`
- Finance/data pages: `data-report`, `finance-report`, `dashboard`
- Long image/social distribution: `magazine-poster`, `card-xiaohongshu`, `social-carousel`
- Video frames/reference: `video-hyperframes`, `motion-frames`, `frame-data-chart-nyt`

## Source Paths

```text
${HTML_ANYTHING_ROOT:-${HTML_ANYTHING_ROOT:-vendor/reserved/render/html-anything}}/next/src/lib/templates/skills/
${HTML_ANYTHING_ROOT:-${HTML_ANYTHING_ROOT:-vendor/reserved/render/html-anything}}/nonfarm-hyperframes-10s-playable.html
${HTML_ANYTHING_ROOT:-${HTML_ANYTHING_ROOT:-vendor/reserved/render/html-anything}}/docs/cover.html
```

## Draft Usage

Draft may borrow layout discipline from HTML Anything, but final article HTML must still obey Newma Draft rules:

- Single self-contained HTML file
- Inline CSS and JS
- No CDN for Chart.js in final article HTML
- `contenteditable="true"` with edit/preview/save controls
- Real charts and images embedded before Draft completes

## Transwrite Usage

Transwrite may use HTML Anything for channel reformatting:

- WeChat polish after DNA/humanize
- Xiaohongshu/card/poster variants
- Video frame visual references for html-video
- Video scene routing: `content_part -> template_id -> timeline scene`

Do not create a second fact chain. If the HTML template wants extra numbers, send the work back to Draft/data collection.

## Video Template Routing

Before making a no-human explainer video, build the router:

```bash
python3 scripts/build_html_anything_template_router.py \
  --output configs/video/html_anything_template_router.json
```

Then expand the article storyboard:

```bash
python3 scripts/build_html_anything_video_timeline.py \
  --storyboard <explainer_storyboard.json> \
  --article-html <article.html> \
  --template-router configs/video/html_anything_template_router.json \
  --output <html_anything_video_timeline.json>
```

The router covers all scanned HTML Anything templates and maps title, subtitle, outline, logic chain, chart, table, quote, phone mockup, chat box, social post, transition, opening, and closing parts to template candidates.

Each video timeline scene must also carry `motion_policy`:

- `framework`: default `hyperframes`
- `animation`: GSAP-style animation strategy, such as `gsap_chart_reveal` or `gsap_path_draw`
- `lottie_role`: decorative motion asset role
- `lottie_keywords`: search terms for future AI/Lottie asset matching
- `fact_rule`: when data is involved, Lottie is decorative only and must not replace real charts or tables

Scene pack rendering supports:

```bash
python3 scripts/render_html_anything_timeline_pack.py \
  --timeline <html_anything_video_timeline.json> \
  --output-dir <scene_pack_dir> \
  --motion-runtime auto
```

`auto` inlines real `gsap` and `lottie-web` from external `html-video` when available. `lite` uses a small offline GSAP-compatible fallback.

## Quick Inspection

```bash
find "${HTML_ANYTHING_ROOT:-${HTML_ANYTHING_ROOT:-vendor/reserved/render/html-anything}}/next/src/lib/templates/skills" -maxdepth 2 -name SKILL.md
```

Open only the templates needed for the current surface. Avoid loading all 75 skills into context.

## Hard Rules

1. HTML Anything contributes presentation, layout, and export ergonomics.
2. Newma Draft remains the source of facts, chart data, and article body.
3. Do not copy the whole external repo into this project.
4. If using a template with CDN assumptions, adapt it to Newma's self-contained HTML rules.
5. Record chosen template names in the current stage manifest.
6. Do not vendor or pin `html-anything`; install or update the external repo when the skill needs it.
7. Prefer HyperFrames-style scene composition. Use GSAP for timing/reveal control; use Lottie only as auxiliary motion, never as the fact layer.
