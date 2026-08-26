# HTML Anything Workflow

## Role

Use `${HTML_ANYTHING_ROOT:-vendor/reserved/render/html-anything}` as a local template and visual reference library.

Good references:

- `article-magazine` / `blog-post`: article layout
- `data-report` / `finance-report`: data-heavy article sections
- `magazine-poster` / `card-xiaohongshu`: social derivative assets
- `video-hyperframes` / `motion-frames`: video frame language

## Constraint

HTML Anything templates can contain CDN assumptions. Newma final article HTML cannot. When adapting templates into Draft HTML:

- Inline CSS/JS.
- Inline Chart.js UMD v4.4.4 if charts are used.
- Embed images as compressed base64.
- Keep `contenteditable="true"`.

## Manifest

When a template influences an output, record the template id or file path in that lane's manifest under `template_references`.
