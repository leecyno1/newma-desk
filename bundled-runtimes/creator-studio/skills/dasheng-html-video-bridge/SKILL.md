---
name: dasheng-html-video-bridge
description: Use when Newma transwrite needs no-human or human-material talking-head videos rendered through the local html-video project.
---

# Newma HTML Video Bridge

正式无真人财经视频默认横版 16:9，并遵循 `docs/technical/no-human-square-video-production-standard.md`；1:1 与 9:16 是独立适配规格。

## Role

Use the external `html-video` repository as the scene renderer for Newma video transwrite. Remotion owns the master timeline; this skill does not research facts or rewrite the article thesis.

`html-video` is an external dependency, not vendored into this repo and not version-locked. Default path: `${HTML_VIDEO_ROOT:-vendor/reserved/render/html-video}`; override with `HTML_VIDEO_ROOT`.

Check or install before first use:

```bash
.venv/bin/python scripts/ensure_video_external_deps.py --dep html-video --mode check
.venv/bin/python scripts/ensure_video_external_deps.py --dep html-video --mode install --install-node-deps
```

For Newma no-human explainer scenes, external `html-video` must also provide `gsap` and `lottie-web`; `ensure_video_external_deps.py --install-node-deps` checks and installs them in the external repo.

Optional Lottie authoring uses external `diffusionstudio/lottie` (`text-to-lottie`) as a verified Skia Skottie player and scene workspace. It is an external dependency, not vendored or version-locked:

```bash
.venv/bin/python scripts/ensure_video_external_deps.py --dep text-to-lottie --mode check
.venv/bin/python scripts/ensure_video_external_deps.py --dep text-to-lottie --mode install --install-node-deps
```

## Inputs

- `explainer_html_video_manifest.json` or `talking_head_video_manifest.json`
- `video_storyboard.json`
- `talking_head_script.md`
- `storyboard_template_review.html` or equivalent approved pre-render scene/template contact table
- `storyboard_review_decision.json` plus a passing `storyboard_review_gate.json`
- Optional human media: real video, real audio, or subtitle/SRT files

## Default Renderer

Resolve the root from `HTML_VIDEO_ROOT` or `${HTML_VIDEO_ROOT:-vendor/reserved/render/html-video}`, then run:

```bash
HTML_VIDEO_ROOT="${HTML_VIDEO_ROOT:-${HTML_VIDEO_ROOT:-vendor/reserved/render/html-video}}"
node "$HTML_VIDEO_ROOT/packages/cli/dist/bin.js" doctor --cwd "$HTML_VIDEO_ROOT"
node "$HTML_VIDEO_ROOT/packages/cli/dist/bin.js" search-templates --intent "<intent>" --aspect 16:9 --top 5 --cwd "$HTML_VIDEO_ROOT"
```

Prefer these templates for market commentary:

- `frame-liquid-bg-hero`: hook/title/opening atmosphere
- `frame-data-chart-nyt`: one clear data comparison
- `frame-electric-studio`: quote or conflict frame
- `frame-light-leak-cinema`: cinematic transition
- `frame-logo-outro`: ending card

## Bridge Command

Generate a project plan without mutating html-video:

```bash
.venv/bin/python scripts/transwrite_html_video_bridge.py \
  --video-manifest <video_lane_manifest.json>
```

Create and preview a real html-video project only when the user asks to render:

```bash
.venv/bin/python scripts/transwrite_html_video_bridge.py \
  --video-manifest <video_lane_manifest.json> \
  --execute create
```

Render MP4:

```bash
.venv/bin/python scripts/transwrite_html_video_bridge.py \
  --video-manifest <video_lane_manifest.json> \
  --execute render
```

## Two Production Modes

### No Human Material

Flow:

`draft -> short script -> storyboard beats -> TTS audio -> html-video template vars -> preview -> MP4`

Rules:

- Do not use macOS `say` for production voice unless explicitly accepted as a rough preview.
- Use MiniMax CLI (`mmx`) as the default production provider for final narration, generated口播音频, background music, and AI image/video assets.
- Default synthetic narration voice is MiniMax `tianxin_xiaoling` at `1.2x`. After voice speed changes, rebuild or compress the visual timeline to keep audio and scene cuts aligned.
- For final/review videos, drive the timeline from real audio timing: per-scene TTS durations, provider alignment metadata, or ASR/forced-alignment backfill. Continuous TTS plus text-length estimation is preview-only.
- If a continuous TTS file has already been generated, backfill subtitle timing with `scripts/align_video_subtitles_to_asr.py` before final render, so display text remains the approved script while timing follows the real voice.
- Coze or direct MiniMax API calls are fallback paths only when the CLI cannot express the required operation.
- Visuals must contain market/data metaphors, charts, and scene motion; do not render only enlarged outline bullets.
- Motion stack: HyperFrames scene composition + GSAP timing + optional Lottie accents. Lottie cannot replace real data charts or evidence.
- Final/review renders must record live HTML animation. Do not use screenshot PNG, static scene stitching, or FFmpeg `zoompan` as a production renderer.
- Real-data scenes must render actual article/verified data. Do not use fake line paths, generic charts, or template-name-only visual switching.
- Do not create materials or render final video until the pre-render scene/template contact table has been reviewed and exported to `storyboard_review_decision.json`.
- Validate the exported decision JSON with `scripts/validate_storyboard_review_gate.py`; if any scene is pending, changed, edited, or deleted, return to storyboard revision instead of rendering.
- The table must include template screenshots or explicit missing-preview placeholders for every scene.
- When a TemplateShowcase MP4 exists, use `scripts/extract_template_preview_frames.py` to build a `template_previews/` directory and pass it into the review table generator.
- Final captions must be full timed subtitles, not shortened scene prompts. Generate JSON/SRT cues from the full narration, keep them synchronized to the voice timeline from real audio timing, and normalize years/quantities to Arabic numerals in display text.
- For formal delivery, use live HTML Video as the authored scene layer and Remotion as the frame-exact chart/caption/master-timeline layer. Remotion must contribute visible output; it cannot be an empty wrapper around a pre-rendered MP4.
- When scene-authored motion is already present, disable generic ambient sweep, scan-line, and light-sweep injection. Production motion must come from the approved scene design.
- If MiniMax CLI shows a request URL containing `/v1/v1/`, remove `/v1` from `MINIMAX_BASE_URL` or `base_url`; the CLI appends the API version path itself.

Default voice render entry:

```bash
.venv/bin/python scripts/render_html_anything_scene_pack_animated.py \
  --manifest <scene_pack_manifest.json> \
  --output-dir <render_dir> \
  --with-voice \
  --voice-provider mmx \
  --voice "tianxin_xiaoling" \
  --mmx-model speech-2.8-hd \
  --mmx-speed 1.2
```

### Human Material Present

Flow:

`human audio/video -> Whisper/SRT -> beat alignment -> transparent/non-transparent HTML visual layer -> FFmpeg/html-video compose`

Rules:

- Existing human audio is the master timeline.
- Visual frames follow the audio; do not force the speaker to follow animation timing.
- If only real video exists, extract audio first, then transcribe.

## Text-to-Lottie Motion Layer

Use `text-to-lottie` when a scene needs reusable vector motion that is hard to author cleanly by hand in HTML/CSS:

- lower-third/name tag/term card accents
- warning badges, status feedback, market alert icons
- document scan, data flow, ticker, arrow/path motion accents
- chapter/outro symbols and compact social-video stickers
- transparent overlays for talking-head scenes

Do not use Lottie as the fact layer. Real charts, tables, screenshots, article images, and sourced data must still come from Draft/article assets or verified data. Lottie can decorate or direct attention to those facts.

Generation contract:

- Store generated Lottie JSON under the current task output folder, e.g. `~/Desktop/自媒体创作/<task>/lottie_assets/<scene_id>/lottie.json`.
- Record each asset in the video manifest with `source_tool: text-to-lottie`, `background: transparent|full_frame`, `duration_frames`, `fps`, `intended_scene_ids`, and `fact_role: decorative|attention_cue`.
- Verify in the upstream Skia Skottie player before using it in a render. At minimum inspect frame `0`, midpoint, and `op - 1`.
- Import into html-video/Remotion with `lottie-web` or `@remotion/lottie`; do not rasterize it into a static PNG for production.
- If verification fails, fall back to HTML/SVG/GSAP hand-authored motion, not static zoompan.

## Output Contract

The bridge writes:

- `html_video_project_vars.json`
- `html_video_project_plan.json`
- `storyboard_template_review.html`
- `storyboard_review_decision.json`
- `storyboard_review_gate.json`
- `html_video_commands.sh`
- Optional `html_video_execution.json` when executed

`talking_head_video_manifest.json` must point to `html_video_project_plan.json`.

## Hard Rules

1. Draft owns facts, charts, and source claims.
2. This skill owns video structure, visual metaphor, timing, and renderer handoff.
3. Plans are not final videos; only mark `rendered` after an MP4 exists.
4. Keep output folders shallow: manifest, storyboard, script, vars, plan, renders.
5. Never hardcode API keys or write credentials into manifests.
6. Do not vendor or pin `html-video`; install or update the external repo when the skill needs it.
