---
name: dasheng-video-talking-head
description: Use when producing or improving Newma真人出镜口播视频 from raw speaker footage, subtitles, rough cuts, B-roll, data charts, or HTML sticker overlays.
---

# Newma Video Talking Head

## Role

Build the真人出镜口播 production line. The real presenter is the trust anchor; evidence screens, charts, documents, B-roll, subtitles, camera motion, and music carry the pace.

This Skill owns `talking_head_video`, which accepts one governed presenter source:

- `human_video`: imported real-person footage and its approved human audio.

If the user supplies only a portrait or asks for 数字人、类真人、照片说话、单人或双人 AI 访谈, route the task to `digital_human_video` and `dasheng-digital-human-talking-head`. That Lane may reuse this Skill's Remotion compositor, but it is not a真人任务。

## Presenter Source Contract

Before director planning, require `presenter_source_manifest.json` or derive the equivalent fields:

- `kind`: `human_video`.
- `engine`: `camera`.
- `video`: approved real-person roughcut.
- `master_audio`: the only audible voice track.
- `consent.status`: confirmed for a real likeness.
- `ai_disclosure_required`: false for ordinary真人素材。

## Required First Artifact

Create a director timeline before rendering:

```bash
python3 scripts/video_director_timeline.py \
  --srt <agent_proofread.srt> \
  --source-video <speaker.mp4> \
  --roughcut-edl <roughcut_edl.json> \
  --title "<title>" \
  --output <talking_head_timeline.json>
```

Use `--captions-json` instead of `--srt` when the rough-cut review page produced captions JSON.
Omit `--roughcut-edl` only when captions were generated directly from the final consolidated roughcut video.

Optional style asset:

```text
~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/style_profile.json
```

Use it to tune pacing, evidence interval, overlay density, transition signature, B-roll rhythm, and speaker-return cadence. Do not train on sample videos inside this production step; use `dasheng-video-style-trainer` first.

After creating or editing the director timeline/scene plan, run the production quality gate:

```bash
python3 scripts/video_scene_plan_quality_gate.py <scene_plan.json> \
  --output <scene_plan_quality_gate.json>
```

If this gate fails, do not render. Produce a revised storyboard/review page instead.

Before any asset generation, build and approve the core Claim/Evidence Ledger:

```bash
python3 scripts/video_claim_evidence_ledger.py \
  --scene-plan <scene_plan.real_evidence.json> \
  --claim-spec <claim_spec.json> \
  --output-dir <run_dir>/claim_evidence
```

The ledger separates 70-100 editing micro-shots from roughly 8-12 factual or interpretive claims. A failing `claim_evidence_gate.json` blocks asset generation and full rendering. Review `spoken_revision_sheet.html`; every pending original-audio correction must be cut, replaced, overdubbed, or re-recorded before render.

## Director Mechanism

Read `docs/technical/video-editing-driving-mechanism.md` and `configs/video/video_editing_driver_rules.json` before planning final shots.

Do not map every sentence to a sticker. Drive editing with:

`evidence_need -> attention_debt -> trust_debt -> cognitive_load -> shot -> template/material -> transition -> audio`

Default state machine:

`speaker_anchor -> claim_closeup -> evidence_fullscreen -> broll_with_pip -> document_zoom/chart_card -> speaker_return`

Director timelines must include composition fields, not only template names:

- `roughcut_gate`: path/status of the approved rough-cut report. If missing or blocked, produce review artifacts only and do not render final video.
- `speaker_state`: `full`, `half_left`, `half_right`, `circle_pip`, `rounded_rect_pip`, `vertical_strip`, `hidden`.
- `material_state`: `none`, `transparent_overlay`, `evidence_fullscreen`, `document_fullscreen`, `chart_fullscreen`, `broll_fullscreen`, `split_screen`.
- `pip_shape`: `none`, `circle`, `rounded_rect`, `square`, `phone_mockup`, `nested_card`.
- `transition_in` / `transition_out`: semantic transitions such as `hard_cut`, `push_zoom`, `circle_morph`, `pip_pop`, `wipe_card`, `data_reveal`, `chapter_hit`, `speaker_return_cut`.
- `html_animation_behavior`: concrete motion description, for example `line_draw_axis_then_series`, `table_scan_highlight_rows`, `flow_arrow_step_reveal`, `document_zoom_marker_circle`.
- `collision_policy`: face, torso, subtitles, and key data safe-area constraints.

## Production Rules

- Approved human audio/video is the master timeline.
- Mount the audible human voice exactly once at the Remotion composition root. Scene changes may remount muted visual copies of the speaker, but must never trim, fade, hide, restart, or sequence the master voice track.
- Keep BGM on a separate continuous root track. Scene transitions may change BGM ducking and visual composition only; they must not create gaps in the voice track.
- Non-overlapping scene sequences must never fade both the outgoing and incoming scene to the canvas background. Use a hard cut or keep the incoming scene visually opaque; use a real dissolve only when the two visual layers overlap.
- Quantize shared scene boundaries once. In Remotion, derive a scene's frame duration from `next_scene_start_frame - current_scene_start_frame`; never round `start_sec` and `duration_sec` independently, because that can create one-frame white/blank flashes.
- Never align a discrete roughcut by multiplying every scene time by one `timeScale`. Regenerate ASR on the final roughcut or apply the keep-segment EDL.
- Do not plan only paragraph-level scenes. For a 4-5 minute Xiaolin-like finance talking-head video, expand the roughcut into roughly 70-100 micro-shots, or at minimum pass 14 effective visual changes per minute.
- Median visual segment must be below 4.5 seconds before final render. Longer explanation blocks must be broken with internal evidence swaps, PIP morphs, speaker punch-ins, hard cuts, or B-roll.
- Any scene longer than 8 seconds must include `micro_shots`; otherwise it is treated as static even if it has one animation label.
- Evidence scenes must mark `evidence_authenticity`: `real_data`, `source_screenshot`, `user_claim_card`, or `schematic`.
- Strong evidence must bind one specific claim to an exact data series, page, selector, paragraph, table row, or screenshot region. A real source used for the wrong claim fails QC.
- One direct asset does not prove a composite claim unless every required evidence item is satisfied. Price charts cannot prove valuation, buybacks, revenue growth, model rankings, product features, or management intent.
- Do not bypass a false spoken sentence by relabeling its core claim as an opinion. Contradicted facts, undefined percentages, and unsupported “already finished / already bottomed” language require a concrete spoken revision and remain render blockers.
- Subtitles are optional by production lane. If the user says subtitles will be handled later, do not render subtitles in the director edit; only keep transcript artifacts for review.
- Use external `html-video` through `dasheng-html-video-bridge` only for evidence overlays, chart cards, title cards, or non-transparent visual layers; install on demand with `scripts/ensure_video_external_deps.py`.
- Every chart/table must come from article data or verified data collection. Fake placeholders are forbidden.
- Production rendering requires `renderer_asset_gate.json` to pass. Placeholder document skeletons, synthetic B-roll fallbacks, empty chart series, missing valuation metrics, and empty evidence tables are allowed only in an explicitly marked showcase render.
- Keep review and production renders separate. A review render may carry a failed Claim/Evidence gate for visual approval, but production rendering must remain blocked until every pending spoken revision is cut, replaced, overdubbed, or re-recorded.
- `html_animation_behavior` must drive semantic timing stages directly. Hashing the behavior string into random delays does not count as consuming the director instruction.
- Important evidence scenes should distribute motion across structure, evidence, annotation, and conclusion stages instead of completing all motion during the first second.
- Static image zoom/pan is not animation. Native images and charts may appear as evidence, but they need HTML/Remotion motion: fade/fly/scan/reveal/highlight/axis draw/marker circle/path draw. A still image with only scale change fails QC.
- Use `dasheng-lemon-illustrations` as the default conceptual-cartoon lane for metaphors, workflows, emotional beats, and short transitions. Use transparent柠檬人 assets, not the upstream recurring character or a generic cute mascot.
- Source metaphors and examples take priority over invented decorative ideas. Consume `illustration_intents.json` and preserve the original meaning; stage each as setup, lemon action, result, then return to the speaker or evidence.
- A lemon illustration is `schematic`, not evidence. Never let it replace a real chart, source screenshot, table, document, map, product UI, or speaker trust shot.
- Composite lemon art as layers: character, prop, path/arrow, annotation, and result may animate independently. A flattened lemon image with zoom/pan alone fails QC.
- Do not leave the lemon character permanently in a corner. Alternate transparent overlay, centered/full-screen conceptual insert, PIP morph, and speaker return according to the beat.
- Do not use a mechanical fixed layout like “HTML page at upper-left + speaker at bottom-right” for long sections. Use composition changes: full speaker, full evidence no speaker, circle PIP, rounded-rect PIP, split screen, phone mockup, nested card, and speaker return.
- Evidence/document/chart scenes must occupy the main visual field. Do not place the animated material as a small upper-left card with large empty center space. For dense material, use centered/full-screen evidence and keep the speaker as a lower-right PIP only when it does not cover key data.
- Do not add global decorative scan lines, yellow sweep lines, moving highlight bars, or repeated scan-light transitions. If a user rejects this visual language, remove it from both component code and baked asset cards. Prefer hard cuts, subtle fades, card scale/opacity settles, PIP morphs, and semantic push-ins.
- Dense evidence sections may hide the speaker completely for a short interval; return to the speaker after the evidence run.
- When this compositor is reused by `digital_human_video`, the digital person remains a presenter layer rather than factual evidence and must follow that Lane's consent, short-sample, identity, lip-sync and disclosure gates.
- For transparent stickers and reusable motion accents, optional `text-to-lottie` assets may be generated through `dasheng-html-video-bridge`: lower thirds, term cards, warning icons, document scan cues, data-flow arrows, ticker accents, and chapter/outro marks. These must be verified as Lottie JSON and composited as live motion, not exported as static PNGs.
- Learned video style controls form only. It must not introduce new facts, charts, market claims, or copied sample-video scripts.
- Keep developer labels out of final video.
- The renderer must consume template, composition, PIP, transition, motion, and audio fields. Run `video_renderer_contract_gate.py` before render.
- Remotion is the master talking-head timeline and compositor. Use `scripts/build_remotion_renderer_pack.py` for the production renderer families; HTML Video, HyperFrames, GSAP, and Lottie are scene-animation workers or imported assets, not competing master timelines.
- The initial production renderer pack contains ten distinct families: speaker anchor, data-native line chart, valuation comparison, exact document crop, evidence table, logic flow, product UI, full-screen B-roll, split comparison, and recap/outro. Do not expand template count until these families pass real render review.
- Run `video_render_qc.py` after render. Repeated dark-entry pulses, flat transition frames, insufficient strong visual changes, timeline duration drift, or voice loudness outside `-16 LUFS +/- 1.5 LU` block delivery.
- Target vertical mobile output: `9:16`, speaker crop safe, subtitle near the source-video bottom edge.
- If `trust_debt` exceeds 16 seconds, return to the speaker unless the current sequence is a dense evidence run.
- If a beat contains numbers, source documents, policies, companies, or market data, force an evidence shot before another decorative overlay.

## Quality Targets

- Median visual segment: 2.5-4s.
- Hard floor: at least 14 effective visual changes per minute; target 17-25 changes per minute when matching 小林说.
- Evidence/B-roll ratio: 45%-65%.
- Speaker returns at least every 8-20s.
- Human voice target: about -16 LUFS, no mid-video silent gaps.
- Subtitle: 1-2 lines, about 24 Chinese chars per line, no overlap.
- Composition variety: no more than 2 consecutive scenes may use the same `speaker_state + material_state + pip_shape`.
- Main evidence card area: target at least 60%-75% of frame width in horizontal talking-head review renders, unless the speaker is intentionally full-screen.
- A high cut count is not sufficient. Reject mechanical alternation such as `speaker -> cream flowchart -> speaker` when it repeats more than twice without a new evidence type or composition state.
- For Xiaohongshu, default to a 9:16 or 3:4 mobile variant between roughly 150-240 seconds. A 16:9 long version requires explicit mobile-readability review and should normally be paired with a shorter platform cut.
- The core claim should appear within 5 seconds. Opening greetings, filler sounds, false starts, and duplicated syllables are rough-cut failures, not stylistic authenticity.
- Self-made framework cards must be labeled as analysis. For factual evidence runs, at least 60% of evidence shots should use real data, source screenshots, documents, real product footage, maps, or sourced B-roll.
- Source-video intake should prefer a near-front camera angle, eyes near the upper third, and limited empty background. Persistent side-profile footage cannot be fully repaired by director overlays.

Hard failure:

- A rendered video can no longer pass QC only because audio/video exists and forbidden yellow sweep lines are absent. `scene_plan_quality_gate.json` must pass first.
- A plan with only 10-20 large scenes for a 4-5 minute talking-head video fails, even if each large scene has a different template name.
- A self-made card-only evidence system fails when the content needs real or source-like evidence.

## Output Contract

- `talking_head_timeline.json`
- `scene_plan_quality_gate.json`
- `claim_spec.json`
- `claim_evidence_ledger.json`
- `claim_evidence_gate.json`
- `claim_evidence_review.html`
- `spoken_revision_sheet.json`
- `spoken_revision_sheet.html`
- `roughcut_gate_report.json`
- `storyboard_review.html`
- `agent_proofread.srt`
- `final_talking_head.mp4`
- `video_qc_report.json`
- `renderer_contract_gate.json`
- `renderer_asset_gate.json`
- `render_qc_report.json`
- `qa_contact_sheet.jpg`
- `presenter_source_manifest.json`
