---
name: dasheng-video-explainer-html
description: Use when turning a Newma HTML article into a no-human finance explainer video with voiceover, storyboard scenes, HTML animation, real charts, music, and final MP4.
---

# Newma Video Explainer HTML

正式无真人财经视频默认横版 16:9，并遵循 `docs/technical/no-human-square-video-production-standard.md`；1:1 与 9:16 是适配规格。

## Role

Build the无真人出镜科普 production line. The article is the fact source; the storyboard is the first-class artifact; html-video renders the animated scenes.

## Required First Artifact

Build the template router, extract the article into a storyboard, then expand it into an HTML Anything video timeline:

```bash
.venv/bin/python scripts/build_html_anything_template_router.py \
  --output configs/video/html_anything_template_router.json

.venv/bin/python scripts/video_explainer_storyboard.py \
  --html <article.html> \
  --template-router configs/video/html_anything_template_router.json \
  --output <explainer_storyboard.json> \
  --preview-html <storyboard_preview.html>

.venv/bin/python scripts/build_storyboard_template_review_table.py \
  --storyboard <explainer_storyboard.json> \
  --output <storyboard_template_review.html>

.venv/bin/python scripts/extract_template_preview_frames.py \
  --template-data <template_showcase_data.json> \
  --video <template_showcase_silent.mp4> \
  --output-dir <template_previews_dir>

.venv/bin/python scripts/build_html_anything_video_timeline.py \
  --storyboard <explainer_storyboard.json> \
  --article-html <article.html> \
  --template-router configs/video/html_anything_template_router.json \
  --output <html_anything_video_timeline.json>
```

Optional style asset:

```text
~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/style_profile.json
```

Use it to tune template preferences, scene length, transitions, color palette, title/opening/outro rhythm, Lottie/GSAP density, and evidence-scene spacing. Do not train on sample videos inside this production step; use `dasheng-video-style-trainer` first.

When available, the director may also read candidate learning notes from:

```text
~/Desktop/自媒体创作/00_范式学习/视频训练/每日博主自学习/knowledge/
```

Use them as scene-design hypotheses only. They must not replace approved DNA,
article evidence, core-scene integrity rules, or the user's latest review.

## Director Mechanism

Read `docs/technical/video-editing-driving-mechanism.md`, `docs/technical/video-script-template-routing-guide.md`, and `configs/video/video_editing_driver_rules.json` before rendering.

No-human explainer is not PPT pagination. Drive scene choice with:

`voiceover beat -> evidence_need -> cognitive_load -> template -> intra-scene motion -> transition -> music/SFX`

Default state machine:

`hook_card -> question_setup -> chapter_card -> evidence_scene -> logic_animation -> cinematic_bridge -> evidence_scene -> recap_card -> outro`

## Production Rules

- Do not create a second fact chain. Reuse the article's real tables, charts, images, and sourced claims.
- Build a source-asset inventory before writing the storyboard. Every article chart must remain traceable through its data, labels, units, source, and reconstruction record; traceability does not require showing the original screenshot in the final video.
- For each source image, download the original image asset and record intrinsic width, height, aspect ratio, source URL, and download completeness. Do not use a cropped article-page screenshot when an original chart/image URL is available.
- When a source chart is shown as documentary evidence, begin with a full-frame `contain` reading state. Local zooms and detail crops are allowed only as later micro-shots; they cannot replace the complete chart, crop axes/legends, or use `object-fit: cover`.
- Preserve exact source cardinality. If the article opens with five risks, the script, overview, five detailed scenes, recap, and renderer must all retain five. Template capacity is never a reason to drop an item.
- When an article chart is faithfully rebuilt as a data-driven animation, show the dynamic chart directly: `axis/context -> one-time data reveal -> key annotation -> completed-chart reading hold`. Do not also display the original chart image in the same or adjacent scene. Show the source screenshot only when the screenshot itself is evidence, the chart cannot be fully reconstructed, or provenance comparison is explicitly required.
- Scene duration must follow cognitive load. Default guidance: 2-4 seconds for a simple transition, 4-7 seconds for a single claim, and 8-15 seconds for a dense chart/table. Long evidence scenes should gain internal micro-shots rather than being fragmented into unreadable short scenes.
- Adjacent sentences that share one visual argument should remain in the same scene. Repeatedly cutting back to the same card or making one layout enter/exit multiple times is a director failure.
- Show the overall outline once. Chapter scenes may use a persistent progress marker, but must not alternate between the full outline and enlarged sub-outline cards.
- Verify rendered outline cardinality against the director plan. All planned items must appear, even when the default template was originally designed for fewer nodes.
- Route semantics to purpose-built motion: business flywheel, customer funnel, valuation waterfall, commercialization ladder, value-chain profit map, recurring-revenue network, investment gates, and direction-versus-price balance. Repeated generic cards are not an acceptable substitute.
- Use official webpage evidence as a browser/document scene with visible source identity, URL, capture date, and a claim-scoped annotation. Never show an official page as decorative background or imply that it proves more than its visible content.
- Learned video style controls presentation only. It must not invent facts, replace article charts, or copy sample-video scripts/frames.
- Real topical B-roll is a standard production route, not an optional decoration. Use `media-downloader` to search, download, trim, and locally register usable clips for real industries, facilities, machinery, places, and human processes mentioned in the narration.
- Default the opening of a real-world explainer to a composite documentary shot: real video as the moving base, with animated title, outline or question map, interactive chart/rule layer, and captions. Use a static title-only opening only when no relevant publishable footage is available or the editorial concept explicitly requires it.
- Before final storyboard approval, build a deeper footage pool for a typical 4-6 minute production: target 10-18 downloaded candidates, 6-12 usable local clips, at least four visual categories, and at least two publishers/sources when practical. Log search failures and rights limitations instead of silently accepting a three-clip pool.
- Aim for real video to occupy roughly 20-35% of final visual runtime across 6-12 windows when the topic supports it. Count full-screen footage, background video, split-screen, masked panels, and video-under-data composites; do not count a still frame extracted from video.
- Reuse a coherent footage family as visual connective tissue across the hook, chapter transitions, process explanations, calculation scenes, and recap. Change the selected time range, crop, motion, mask, color treatment, and overlay logic so continuity does not become obvious repetition.
- A real-B-roll scene must carry source title, publisher/channel, URL, source time range, download date, local path, scene usage, rights-review status, and `evidence_role=context` unless the footage visibly proves the exact claim.
- Combine tools inside a shot when it improves explanation: real video may be the moving base layer while HTML Video or Remotion supplies numbers, rule diagrams, timelines, chart annotations, and captions. Do not force one shot to use only one tool.
- For formal delivery, keep the authored HTML scene, frame-exact Remotion overlays/charts/captions, and audio master as separate layers until the final render. Do not flatten the HTML scene to a still before Remotion.
- A real-video window counts toward footage share only when moving footage remains visibly present in the final composite; footage hidden behind a fully opaque panel does not count.
- Generate narration with MiniMax CLI (`mmx`). For review/final videos, prefer per-scene TTS or provider timestamps so each scene duration comes from real audio duration. A single continuous TTS file with text-length timing is only acceptable for rough preview.
- Default no-human narration is `tianxin_xiaoling` at `1.2x` speed. If narration feels slow, compress the visual timeline by the same ratio as the voice; do not speed up voice alone and leave visuals drifting.
- Treat the supplied article as the creator's own source draft. Narration is an authorial first-person/direct voice, not a rewrite report. State the argument directly and use `我认为/我的判断` only where ownership matters; do not repeatedly say `原文提到`, `文章认为`, `作者表示`, `根据原文章`, or similar third-party framing.
- Keep display copy and TTS copy separate. Screen text may use Arabic numerals, but `narration_tts` must use natural Mandarin: years are read digit by digit (`1985 年` -> `一九八五年`), numbered headings are ordinals (`01` -> `第一`), and dates, percentages, quantities, money, and model numbers must be pronunciation-checked before synthesis. Never let a heading be read as `零一`.
- Do not pad scene audio with multi-second silence to preserve a planned visual duration. Derive duration from real speech plus a semantic tail: about `0.35s` for logic, `0.45s` for evidence, `0.50s` for chapter resets, and `0.60s` for recap/outro. If a chart needs more reading time, reveal it earlier under narration or continue the next spoken beat over the completed chart. Reject unexplained inter-scene voice gaps above `0.8s`.
- Preserve the active core canvas. Do not cut from a chart, table, document, or logic map into a full-screen card that only repeats one title, number, or keyword from the same topic. Use local annotations and progressive states while the evidence remains readable.
- Only switch full scenes when entering a new content theme, changing the evidence object, or changing the explanatory grammar. Pure chapter titles should be merged into the next substantive scene unless they provide new information.
- For evidence-driven explainers, target a semantic rhythm range rather than maximum cut density. A typical core-scene-integrity target is roughly 4-8 strong visual changes per minute, with dense charts allowed to hold longer. More changes are not automatically better.
- Use MiniMax CLI for production narration, background music, AI image assets, and generated口播音频. Do not call MiniMax APIs directly from ad-hoc scripts unless the CLI cannot express the operation.
- Use `dasheng-lemon-illustrations` as the default conceptual-cartoon lane for abstract mechanisms, workflows, emotional beats, and transitions. The recurring character is柠檬人; do not request the upstream recurring character.
- Consume Draft `illustration_intents.json` before inventing new metaphors. Explicit examples and analogies become setup-action-result scenes; simple metaphors normally run 4-7 seconds and example micro-stories 7-12 seconds.
- Lemon illustrations are schematic visual metaphors. They must not replace article charts, tables, source screenshots, documents, maps, or verified data.
- A generated lemon image is source material. Build live scene motion with separately timed character/prop/path/annotation layers; a flattened illustration with zoom/pan alone is not a production animation.
- Use external `html-video` as the default scene renderer via `dasheng-html-video-bridge`; Remotion remains the master timeline.
- Use external `html-anything` only as visual/template reference via `dasheng-html-anything-bridge`; install on demand with `scripts/ensure_video_external_deps.py`.
- No generic framework diagrams when article data can support a concrete chart/table.
- Charts, tables, and line graphs must be backed by article data, source images, or verified data pulls. Never draw decorative or fake lines for a data scene.
- Template diversity must be real at the renderer/component level, not just a template title label.
- Reserve safe zones before rendering: keep core charts/tables away from top chrome and bottom captions; no card/table overlap, no element collision, no developer-facing labels in final MP4.
- Each finance/data scene must answer “what does this prove?” on screen. Avoid visually busy but content-light template demos.
- Final captions must cover the full voiceover, not just scene summaries. Captions should be generated as timed JSON/SRT cues, displayed in sync with the active spoken sentence, and included as delivery artifacts.
- Caption display text must normalize years, percentages, quantities, and counts to Arabic numerals where readability is better, e.g. `2022-2025`, `50%`, `3个月`, `5句话`.
- Subtitle timing must be audio-driven. Use per-scene audio durations, provider alignment metadata, or ASR/forced-alignment backfill. If subtitles are generated only by proportional text length, label the render as preview and do not deliver it as final.
- When only a continuous TTS file exists, run `scripts/align_video_subtitles_to_asr.py --project-dir <remotion_project> --asr-json <whisper_json> --speed 1.2 --write`, then re-render. This keeps script text but uses ASR timestamps.
- No CDN-dependent final assets; preview HTML may be simple, final MP4 must be rendered locally.
- Prefer HyperFrames as the scene composition model.
- Use GSAP-style timelines for entrance, exit, chart reveal, path draw, table scan, and title kinetics.
- Lottie is allowed only as decorative/auxiliary motion. It must never replace real article charts, tables, screenshots, or evidence.
- When a scene needs a reusable vector motion accent, route it through `dasheng-html-video-bridge` and optional external `text-to-lottie`: warning icon, document scan, data flow, market ticker, path trace, lower-third, chapter symbol, or outro mark. Generated Lottie JSON must be verified in the Skia Skottie player and recorded under the task output folder before final render.
- Final/review videos must be rendered by live HTML animation recording. Static screenshot, PNG stitching, or FFmpeg `zoompan` is forbidden for production because it destroys GSAP/Lottie/template motion.
- If the HTML scene already owns its motion language, disable generic ambient sweep/scan-line injection during recording; do not add a global effect that was absent from the approved storyboard.
- Do not render from raw storyboard directly unless debugging. Final video planning must route content parts to HTML Anything templates first.
- Before TTS, material generation, or video render, produce `storyboard_template_review.html` and ask for user approval. This page must show one row per scene with time, voiceover, core meaning, evidence refs, template id, template screenshot/placeholder, motion plan, risk notes, and review decision controls.
- Require the user/exported `storyboard_review_decision.json` before production. Validate it with `scripts/validate_storyboard_review_gate.py --storyboard <storyboard.json> --decision <storyboard_review_decision.json> --output <storyboard_review_gate.json>`.
- Do not proceed if the gate report has `status != approved` or `render_allowed != true`.
- After storyboard approval, build `claim_evidence_ledger.json` and require `claim_evidence_gate.status=pass` before TTS, B-roll generation, chart rendering, or final composition.
- The final delivery must include `final_delivery_manifest.json`; its video path, duration, dimensions, FPS, and SHA-256 must describe the exact file checked by `video_render_qc.py`.
- If a template has no screenshot, show a visible “暂无模板截图” placeholder and the required preview path. Do not fake a screenshot or hide the missing preview.
- Prefer real template screenshots from `scripts/extract_template_preview_frames.py`, template `preview.png`, or a renderer still. Do not substitute unrelated scene frames as template screenshots unless the table explicitly labels them as scene previews.
- macOS `say` is only a smoke-test fallback; it is not acceptable for final voiceover unless explicitly requested.
- Evidence scenes must appear every 20-35 seconds. Chapter or structure reset must appear every 45-90 seconds.
- A scene longer than 8 seconds needs explicit intra-scene motion: data reveal, document zoom, path highlight, focus shift, or exit motion.

## MiniMax CLI Defaults

Check authentication and quota before production rendering:

```bash
mmx auth status --no-color
mmx quota --no-color
```

Default render command shape:

```bash
.venv/bin/python scripts/render_html_anything_scene_pack_animated.py \
  --manifest <scene_pack_manifest.json> \
  --output-dir <render_output_dir> \
  --with-voice \
  --voice-provider mmx \
  --voice "tianxin_xiaoling" \
  --mmx-model speech-2.8-hd \
  --mmx-speed 1.2
```

Default narration command shape used by the renderer:

```bash
mmx speech synthesize \
  --text-file <full_voiceover_script.txt> \
  --out <voiceover_single.wav> \
  --model speech-2.8-hd \
  --voice "tianxin_xiaoling" \
  --speed 1.2 \
  --format wav \
  --sample-rate 44100 \
  --channels 1 \
  --language Chinese
```

Default background music command shape:

```bash
mmx music generate \
  --prompt "light technology explainer, data reveal, restrained financial documentary, no vocals" \
  --instrumental \
  --out <bgm.mp3>
```

Default AI image command shape:

```bash
mmx image generate \
  --prompt "<article-specific visual prompt>" \
  --aspect-ratio 16:9 \
  --out <image.jpg>
```

## Style Targets

- Horizontal `16:9` finance/documentary style is the default master. Generate `1:1` or `9:16` as separate publish adaptations when required.
- Default voice: MiniMax `tianxin_xiaoling`, speed `1.2`, warm investor-chat delivery. Keep rhetorical pauses in the script but avoid slow TTS pacing.
- Default BGM: light technology explainer / data reveal. Keep BGM low under the voice and use chapter risers sparingly.
- BGM must not remain at one flat level for the whole video. Keep the narration body restrained, allow a small lift during chapter bridges, and use a controlled recap/outro lift without masking speech.
- Average scene: 5-7s; median: 4-5s.
- Evidence screen every 20-35s.
- Chapter card every 45-90s.
- Prefer document zoom, data reveal, chart animation, terminal/Bloomberg-like information rhythm.
- Add Lottie-style accent motion for warning, market ticker, data flow, document scan, and outro only when it supports the spoken beat.
- For AI-generated Lottie assets, prefer prompts grounded in real article variables: exact label text, numeric value, direction of movement, target duration/FPS, transparent background, and where it will sit in the scene. Avoid vague prompts like “make it professional”.

## Review Feedback Guardrails

- If a reviewer flags “line charts are sloppy,” first check whether numeric columns were parsed incorrectly as dates; fix data extraction before visual styling.
- If a reviewer flags “穿模/遮盖,” reduce component density and regenerate midpoint contact sheets before final render.
- If narration is too slow, target `1.2x` voice speed and rebuild scene duration allocation from the actual audio duration.
- If a template review video looks repetitive, reject title-only template switching and require one unique renderer behavior per template.
- If source charts are unaccounted for, reject the render even when technical QC passes. A chart is accounted for when it is either faithfully reconstructed with source metadata, shown as documentary evidence, or explicitly excluded with reason. Do not require duplicate screenshot display after successful reconstruction.
- If a reviewer flags a cropped or unreadable source chart, return to the original downloaded asset, verify intrinsic dimensions, show the full `contain` state first, and only then add secondary detail views.
- If a storyboard calls for real B-roll but the local file or provenance manifest is missing, keep the review gate closed; do not replace it with a generic static image or a text-only placeholder.
- If a real-world explainer opens on a static title card while suitable downloaded footage exists, redesign the opening as a real-video composite before approval.
- If the real-video share is only a few isolated inserts, expand the search pool and distribute footage across hook, body, bridges, and recap. When expansion is impossible, record the semantic, availability, or rights constraint in the storyboard review.
- If viewers cannot finish reading a chart before the next cut, extend its completed-state hold; do not solve the problem by replaying the chart entrance.
- If the concatenated video differs from the director duration because of frame rounding, auto-pad/trim the visual track before muxing. Do not deliver a manual duration-drift failure.
- If captions are missing content or lag voice, reject the render: rebuild timed subtitle cues from the full voiceover plus real audio timing, then re-render a contact-sheet/video sample.

## Output Contract

- `explainer_storyboard.json`
- `html_anything_video_timeline.json`
- `storyboard_preview.html`
- `storyboard_template_review.html`
- `storyboard_review_decision.json`
- `storyboard_review_gate.json`
- `voiceover.wav` or provider-specific audio file
- `captions_full.json`
- `captions_full.srt`
- `final_explainer_vertical.mp4`
- `video_qc_report.json`
- `qa_contact_sheet.jpg`
