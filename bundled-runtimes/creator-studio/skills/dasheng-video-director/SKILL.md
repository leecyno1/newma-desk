---
name: dasheng-video-director
description: Use after roughcut/intake and before asset generation when converting article scripts, ASR, captions, or draft HTML into detailed video shot plans, scene plans, template choices, composition states, transitions, audio policies, and review gates.
---

# Newma Video Director

## Role

You are the director layer. Your job is to turn content into a reviewable video plan, not to render final media.

This skill sits between roughcut/script intake and material generation:

```text
brief/script -> director scene_plan -> claim/evidence ledger -> storyboard review -> asset build/render
```

Use this skill for six registered lanes. Read `configs/video/director_registry.json` first and use the matching director profile:

- 真人出镜口播：speaker is the trust anchor; evidence, PIP, B-roll, charts, documents, and transitions carry pace.
- VOX 调查解释：one central question, evidence map, counterargument, qualified conclusion, Shotcraft/Remotion and generated explanatory shots.
- 无真人 HTML 科普：voiceover is the timeline; animated HTML scenes carry narration, proof, rhythm, and structure.
- AI 数字人：single presenter or dual interview; each presenter source is generated independently and composed by active-speaker turns.
- 电影短剧：planning only by default; produce screenplay, character/continuity bible and storyboard, but do not call paid external video APIs.
- 广告宣传片：one objective, one CTA, early product reveal, real product/proof assets, brand memory and multi-aspect safe areas.

All six lanes follow:

```text
素材接收 -> 编剧/口播重写 -> 导演分镜 -> 素材生成 -> 剪辑合成 -> 渲染 -> QC/交付
```

## Required Reading

Before producing a director plan, read:

- `docs/technical/video-pipeline-governance.md`
- `docs/technical/video-editing-driving-mechanism.md`
- `configs/video/video_editing_driver_rules.json`
- `configs/video/director_feedback_memory.json`
- `configs/video/tool_registry.json`
- `configs/video/director_registry.json`
- `configs/external/reserved_projects.json`
- `configs/video/reference_video_dna_registry.json`
- `~/Desktop/自媒体创作/00_范式学习/视频训练/每日博主自学习/knowledge/index.md` when the daily self-learning knowledge base exists
- The relevant pipeline manifest:
  - `configs/video/pipelines/talking_head.yaml`
  - `configs/video/pipelines/vox_explainer.yaml`
  - `configs/video/pipelines/explainer_html.yaml`
  - `configs/video/pipelines/digital_human.yaml`
  - `configs/video/pipelines/cinematic_short_drama.yaml`
  - `configs/video/pipelines/commercial_promo.yaml`

## Inputs

Accept any combination of:

- `project_run_manifest.json`
- `brief.json`
- `script.json`
- `roughcut_gate_report.json`
- `roughcut_edl.json` or equivalent keep-segment edit decisions when captions were generated before roughcut
- `agent_proofread.srt`
- `captions_full.json`
- `article.html`
- `commercial_brief.json` for `commercial_promo_video`
- `explainer_storyboard.json`
- draft article charts, images, tables, and data references
- optional style profile under `~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/style_profile.json`
- optional curated style profile selected from `configs/video/reference_video_dna_registry.json`
- optional creator self-learning candidate notes under `~/Desktop/自媒体创作/00_范式学习/视频训练/每日博主自学习/`

Self-learning notes are advisory. Read the creator rolling profile, director
playbook, aesthetic playbook, and technical-stack mapping only when their scope
matches the current lane. Prefer rules with explicit evidence and higher
confidence. Never let an automatic candidate override an approved historical
profile, the current article evidence, or user feedback recorded in this skill.

Do not select a reference by creator name alone. Select by production scope:

- classic Xiaolin-like finance explanation for dense talking-head finance;
- latest Xiaolin interview reference only for conversation and product-demo grammar;
- latest Wizard reference for no-human full-screen visual documentary grammar;
- approved XHS real-estate reference for professional maps, tables, plans, and metric-led talking-head explanation.

## Output Contract

Always produce a `scene_plan` before material generation:

- `scene_plan.json`
- `tool_routing_plan.json`，为每个制作阶段和每个分镜登记主工具、后备工具、受阻工具及依赖原因
- `scene_plan_quality_gate.json`
- `claim_spec.json` with roughly 8-12 core claims for a normal 4-6 minute finance video
- `claim_evidence_ledger.json`
- `claim_evidence_gate.json`
- `claim_evidence_review.html`
- `spoken_revision_sheet.json` and `spoken_revision_sheet.html` when original narration must be cut, replaced, overdubbed, or re-recorded
- `scene_plan.claim_bound.json`
- `storyboard_template_review.html` or equivalent review page
- `storyboard_review_decision.json` after user approval
- `storyboard_review_gate.json`
- optional `director_checkpoint.json`
- `timeline_alignment` inside the final scene plan
- `evidence_binding` on every bound evidence scene
- `renderer_contract_gate.json` before render

The scene plan must satisfy `configs/video/artifact_schemas/scene_plan.schema.json` and pass `scripts/video_scene_plan_quality_gate.py` before material generation or render.
The director must route every scene through `scripts/video_director_tool_router.py`. Each scene must carry `tool_routing.required_capabilities`, `primary_stack`, `fallback_stack`, and unresolved capability warnings. A project or Skill marked `reference_only`, missing an API key/login/model, or missing its runtime cannot become a primary route.
The claim ledger must satisfy `configs/video/artifact_schemas/claim_evidence_ledger.schema.json`. A failing claim/evidence gate blocks asset generation, not only final render.

Default executable entry:

```bash
python3 scripts/dasheng_video_director.py \
  --lane explainer_html_video \
  --article-html <article.html> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/video_director
```

For talking-head footage:

```bash
python3 scripts/dasheng_video_director.py \
  --lane talking_head_video \
  --srt <agent_proofread.srt> \
  --source-video <roughcut.mp4> \
  --roughcut-gate <roughcut_gate_report.json> \
  --roughcut-edl <roughcut_edl.json> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/video_director
```

If captions were generated from the final roughcut itself, omit `--roughcut-edl`. Never compress a pre-cut timeline with a global scale factor.

For a digital-human presenter or dual interview, use the same director entry with `--lane digital_human_video`; the input captions must already identify speaker turns, and the presenter package must use `presenter_source.mode=single_presenter|dual_interview`.

For a commercial promo:

```bash
python3 scripts/dasheng_video_director.py \
  --lane commercial_promo_video \
  --commercial-brief <commercial_brief.json> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/commercial_promo_director
```

The cinematic lane remains planning-only. Build its screenplay/storyboard package through `dasheng-stage-transwrite` / `scripts/build_stage4_transwrite.py`; do not use the renderer or external provider route while `execution_enabled=false`.

If the current production has a `project_run_manifest.json`, register every output with:

```bash
python3 scripts/project_run_manifest.py add-artifact <project_run_manifest.json> \
  --stage scene_plan \
  --type scene_plan \
  --path <scene_plan.json>
```

Run the director quality gate before any render:

```bash
python3 scripts/video_scene_plan_quality_gate.py <scene_plan.json> \
  --output <scene_plan_quality_gate.json>
```

For 真人口播, a failing `scene_plan_quality_gate.json` blocks render. Revise the storyboard first.

After the micro-scene timing is locked, group scenes into core claims and audit evidence:

```bash
python3 scripts/video_claim_evidence_ledger.py \
  --scene-plan <scene_plan.real_evidence.json> \
  --claim-spec <claim_spec.json> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/claim_evidence
```

Do not auto-treat every spoken sentence as a separate fact. Each micro-scene must belong to exactly one core claim. Facts, comparisons, causal claims, and historical claims require direct, locatable evidence. Rumors, forecasts, opinions, and scenarios require an explicit on-screen disclosure.

Changing a claim from `fact` to `opinion` must not hide an incorrect original sentence. If the audio contains a contradicted number, undefined percentage, unsupported causal statement, or false certainty, add `spoken_revision_requirements`. The gate remains closed until the scene has a real `narration_override`, cut/exclude decision, approved overdub, or re-record.

## Director Decision Model

Do not map every sentence to a random sticker. Drive scenes with:

```text
semantic beat -> evidence need -> attention debt -> trust debt -> cognitive load -> composition -> template/material -> motion -> transition -> audio
```

Every scene must answer:

- What is the viewer supposed to understand now?
- What evidence or visual metaphor supports it?
- Why this composition instead of the previous one?
- What motion happens inside the scene?
- How does this scene enter and exit?
- What can go wrong: collision, clutter, fake data, subtitle drift, repetition?

## Conceptual Illustration Routing

`dasheng-lemon-illustrations` is the default cartoon system for future口播精简 when a beat needs a metaphor, workflow, emotional reset, abstract mechanism, or chapter bridge. The recurring character is柠檬人, not the upstream character.

- Read Draft `illustration_intents` before inventing new visual metaphors. If the source explicitly says “比如/例如/举个例子/就像/好比/仿佛/如同” or uses a physical financial metaphor, preserve its core meaning and route it through the lemon skill.
- Use `setup -> character action -> result` for examples and metaphors. Simple metaphors normally need 4-7 seconds; example micro-stories normally need 7-12 seconds.
- Route real numbers, charts, tables, source pages, documents, maps, and product UI to evidence renderers first.
- Route only conceptual beats to lemon illustrations and mark them `evidence_authenticity=schematic`.
- Set `illustration_system=dasheng-lemon-illustrations`, `illustration_mode=full_canvas|transparent_overlay`, and a concrete `concept_action` in the scene plan.
- Do not assign a cartoon to every sentence. Avoid more than two consecutive lemon-illustration micro-shots without a speaker return, real evidence, or a different material family.
- For talking-head scenes, use transparent lemon assets as one compositing layer. For no-human scenes, use full-canvas illustrations only when they advance the argument.
- The generated raster image is not the final animation. Plan separate motion for the character, prop, path, annotation, mask, or PIP transition; static zoom/pan fails QC.

## 真人口播 Rules

Default state machine:

```text
speaker_anchor -> claim_closeup -> evidence_fullscreen -> broll_with_pip -> document_zoom/chart_card -> speaker_return
```

Required fields per scene:

- `speaker_state`: `full`, `half_left`, `half_right`, `circle_pip`, `rounded_rect_pip`, `vertical_strip`, or `hidden`
- `material_state`: `none`, `transparent_overlay`, `evidence_fullscreen`, `document_fullscreen`, `chart_fullscreen`, `broll_fullscreen`, or `split_screen`
- `pip_shape`: `none`, `circle`, `rounded_rect`, `square`, `phone_mockup`, or `nested_card`
- `html_animation_behavior`: concrete behavior such as `line_draw_axis_then_series`, `table_scan_highlight_rows`, `document_zoom_marker_circle`, `pip_circle_morph_to_rect`
- `collision_policy`: face, torso, subtitle, and key data safe zones

Hard rules:

- Roughcut gate must be approved before final render planning.
- Discrete deletions must use `scripts/video_timeline_edl.py` or final-roughcut ASR. `global_scale` / uniform `timeScale` after roughcut is forbidden.
- Do not keep the speaker mechanically in the same corner.
- Do not use static image zoom/pan as animation.
- Evidence-heavy sections may hide the speaker, but must return to the speaker after the evidence run.
- No more than two consecutive scenes should share the same `speaker_state + material_state + pip_shape`.
- Speaker should usually return within 8-20 seconds unless the segment is a dense evidence run.
- Do not stop at chapter/paragraph-level scenes. A 4-5 minute talking-head video should normally expand into about 70-100 micro-shots, or at least pass the hard floor of 14 effective visual changes per minute.
- Median visual segment should stay under 4.5 seconds; the preferred Xiaolin-like target is 1.4-4.0 seconds.
- Any scene longer than 8 seconds must include a `micro_shots` array that specifies internal cuts, PIP morphs, evidence swaps, chart reveals, B-roll inserts, or speaker returns.
- Evidence scenes must carry `evidence_authenticity`: `real_data`, `source_screenshot`, `user_claim_card`, or `schematic`. Use `schematic` only for clearly marked concept animations.
- Conceptual cartoon scenes must use `dasheng-lemon-illustrations`; do not generate the upstream recurring character or substitute a generic cute mascot.
- Bound `real_data` and `source_screenshot` scenes must include `evidence_binding.claim_id`, `relation=direct`, and a concrete `source_locator`. Company homepages and correlated price charts are context, not direct proof.
- `evidence_binding.claim_id` must be the core claim ID after Ledger approval. Preserve the original micro-scene claim ID as `micro_claim_id` for traceability.
- A composite claim is proven only when all explicitly required evidence items are satisfied. One valid screenshot cannot prove the other unsupported parts of the same sentence block.
- Evidence completeness and spoken correctness are separate gates. Zero missing-evidence claims is insufficient when `spoken_revision_sheet.pending_count > 0`.
- The renderer must pass `scripts/video_renderer_contract_gate.py`; template names that collapse to one generic component do not count as template diversity.
- A scene plan that relies mostly on one self-made card system is not acceptable, even if the template names differ. Mix real/source-like evidence: market chart, webpage/news/doc, company/product UI, table, B-roll, logic diagram, and speaker return.

## 无真人科普 Rules

Default state machine:

```text
hook_card -> question_setup -> chapter_card -> evidence_scene -> logic_animation -> cinematic_bridge -> evidence_scene -> recap_card -> outro
```

Required fields per scene:

- `template_id`
- `content_part`
- `beat_class`
- `evidence_refs`
- `motion` or `html_animation_behavior`
- `transition_to_next`
- `audio`
- `risk_notes`

Hard rules:

- The article HTML is the fact source. Do not create a second fact chain.
- Inventory every source chart, table, image, and document before scene planning. Every source chart must be represented by a reconstruction record, documentary screenshot scene, or `excluded_with_reason`; silent loss is a blocking failure.
- Audit source raster images at their intrinsic dimensions before composition. Download the original image asset, record width, height, aspect ratio, source URL, and completeness, and never treat a long-page screenshot as the chart source when the original image URL exists.
- A source chart shown as documentary evidence must enter with a complete `contain` reading state before any local magnification, camera move, or detail crop. `object-fit: cover`, crop-before-audit, and a detail crop used as the only chart view are blocking defects. A detail view is a secondary micro-shot and must preserve a traceable return to the full chart.
- Preserve exact enumeration cardinality. If the source says there are `N` reasons, risks, steps, gates, or checklist items, the narration, storyboard, renderer, recap, and review page must all show exactly `N`; silently compressing five points into four is a blocking content-loss failure.
- Rebuild source charts as data-driven HTML/GSAP/Remotion animation and show the reconstruction directly. Do not repeat the original chart screenshot when the animated chart already preserves the data, labels, units, and source. Use the screenshot only when it is itself documentary evidence or the reconstruction is incomplete.
- Write explainer narration as the creator speaking directly from their own material. Prefer direct claims and selective first-person judgment. Third-party rewrite framing such as `原文提到`, `文章指出`, `文章认为`, `作者表示`, and `根据原文章` is a blocking script defect.
- Route real topical B-roll as a normal director option when a claim has a real-world process, place, industry, machine, or human activity that benefits from documentary context. Use `media-downloader` to search and download an actual clip before marking the route executable; a storyboard-only placeholder does not count as a working B-roll route.
- For real-world topics, make the opening a layered documentary composite by default: `real video base -> animated title -> outline/question map -> interactive data or rule layer -> captions`. Avoid opening a publishable 4-6 minute explainer with only a static title card when relevant footage is available.
- Build a footage pool before final storyboard approval. For a typical 4-6 minute explainer, target 10-18 downloaded candidates, 6-12 locally usable clips, at least four visual categories, and at least two publishers/sources when rights and availability allow. Record a documented exception when the target cannot be met.
- Target roughly 20-35% of final visual runtime and 6-12 shot windows using real video as a base layer, background, full-screen scene, split panel, mask, or cinematic bridge. This is a relevance target, not a quota that permits unrelated or repetitive footage.
- Use a coherent footage family across the hook, chapter bridges, mechanism explanations, calculations, and recap to create continuity. Reuse different source time ranges, crops, focus states, speeds, masks, and overlay grammars; do not replay the same exact shot treatment mechanically.
- Record B-roll provenance: source title, channel/publisher, URL, source time range, download date, local path, intended scene, and rights-review status. Real B-roll may share one scene with HTML Video, Remotion data layers, captions, and annotations.
- News anchors, interview subjects, presenter-led reports, and footage with a prominent human PIP must never become a dimmed chart background. A centrally framed anchor or host defaults to an independent PIP from the first visible frame; do not force a 4-5 second full-screen pre-roll. Use full-screen first only when the original statement, lower-third, document, or on-site context is itself the evidence that viewers must read.
- For PIP-first presenter footage, use a restrained `0.45-0.6s PIP enter -> stable independent panel -> no-black exit` grammar while the HTML/Remotion evidence canvas remains full-size. Place the presenter at right or right-bottom, keep title/data/caption safe zones clear, and give the presenter and animation different narrative responsibilities.
- Prefer factory floors, production processes, markets, social environments, public spaces, landscapes, crowds, interview environments without a dominant face, servers, machinery, or other spatial footage as the full-canvas dynamic background. The background must remain visibly alive; tune source exposure case by case, normally keeping video brightness around `0.68-0.76`, avoiding broad black washes above roughly `0.82`, and reducing vignette/shadow until motion is perceptible without sacrificing text readability.
- New high-salience techniques are selective accents, not a global skin. In a normal explainer, reserve spotlight PIP, depth-layer motion, shared-element transitions, or GSAP staged timelines for the hook, a chapter turn, or one to two core data scenes. Repeating the same conspicuous effect throughout the video is a director defect.
- Treat `animation_top_left + person_bottom_right`, `chart_left + interview_right`, and `document_left + anchor_right` as explicit script-language composition states. Each side must have a distinct narrative responsibility rather than duplicating the same claim.
- Subtitle plates must remain continuous across adjacent cues whose gap is no more than 0.45 seconds. Replace text inside the stable plate; do not spring the whole subtitle in and fade it out at every sentence end.
- Ordinary scene changes use a clean hard cut or visible-object transform. A universal dark curtain, white flash, or whole-canvas fade at every scene head/tail is forbidden.
- Every frame must retain at least one fully visible base layer. Background-video crossfades must overlap safely; never author an opacity schedule in which every video can be transparent at once.
- Spoken narration must be rewritten for breath and emphasis before TTS: 80-140ms within one semantic phrase, 150-220ms after a comma-level breath, 280-380ms at a sentence end, 450-650ms for questions/conclusions/number landings, and 500-700ms at scene tails. For MiniMax financial narration, start from speed 1.08-1.12 and tune by listening rather than using one global fast setting.
- Merge isolated ordinals, connectors, nouns, units, and punctuation tails into neighboring subtitle phrases. Do not publish cue cards such as `第一，`, `最后，`, `科技，`, `估值，`, or a trailing `亿。` as standalone subtitles.
- Treat topical B-roll as contextual footage unless the visible frames directly prove the claim. Semiconductor-fab footage can establish manufacturing context, but it cannot directly prove a company's allocation amount, valuation, lock-up rule, or fund return. Bind those claims to article/official evidence separately.
- Allocate time by information load, not by a fixed cut interval: simple chapter/kinetic cards may take 2-4 seconds; one-claim cards 4-7 seconds; dense charts/tables normally need 8-15 seconds with internal micro-shots and a final reading hold.
- Do not repeatedly enter and exit the same layout for adjacent clauses. Keep one semantic scene active until its evidence has been read, and use internal focus changes instead of seven-in/seven-out card cycling.
- Protect core-scene integrity. Once a chart, table, document, causal map, or other core evidence scene is active, do not interrupt it with full-screen keyword cards, title curtains, or detached summary inserts from the same topic. Keep the core canvas visible and advance with local labels, row highlights, line reveals, node states, or camera-safe reframing.
- Create a new scene boundary only when the topic, evidence object, explanatory objective, or composition grammar genuinely changes. A new sentence, number, or rhetorical emphasis is not enough reason to cut.
- Full-screen title cards are reserved for real theme changes. If a chapter card contains only a repeated title or one keyword, merge its narration into the next substantive scene or keep it as a non-narrated transition under 2.5 seconds.
- Visual-change targets are a guardrail, not an optimization objective. Never increase cut density by covering an active core scene with short full-canvas focus cards. Over-editing that damages reading continuity is a blocking director defect even when numeric density gates pass.
- The overall outline appears once at the opening. After entering a chapter, never cut back and forth between the overall outline and its sub-outline; reveal sub-points progressively inside the active chapter and keep previously revealed context stable.
- Preserve every outline item. A renderer that silently truncates a seven-item outline to five items is a blocking content-loss failure.
- Different business meanings require different visual grammars: use a flywheel for closed-loop economics, a funnel for concentrated customers, a waterfall for valuation arithmetic, a ladder for proof requirements, and gates for investment conditions. Do not route all logic into the same sticky-note or card component.
- For a normal 4-6 minute evidence-driven explainer, target roughly 12-20 real renderer components. Excluding mandatory repeated article-chart reconstruction, one semantic component should normally appear no more than twice.
- Official website screenshots must show the organization/site identity and carry a source URL plus capture date. Treat them only as direct evidence for what is visibly stated on that page, not for unrelated causal claims.
- Template diversity must be real at renderer/component level, not title-only switching.
- Data scenes must use real article data or verified data; decorative fake charts are forbidden.
- Conceptual cartoon scenes use the lemon-person system, but article charts, tables, screenshots, and sourced evidence remain mandatory and cannot be replaced by illustration.
- Final/review renders must use live HTML/GSAP/Lottie animation recording, not PNG stitching or FFmpeg zoompan.
- Evidence scenes should appear every 20-35 seconds.
- A scene longer than 8 seconds needs intra-scene motion.
- Before render, produce a storyboard review page with one row per scene and wait for approval.
- Before delivery, scan the complete render for single-frame luminance pulses, then separately inspect every subtitle end and scene boundary within a roughly seven-frame window. A detected one-frame black/white dropout blocks delivery until repaired or re-rendered and the same scan returns zero failures.

## Review Page Requirements

The review page should show:

- scene id and time range
- micro-shot count and visual-change density estimate
- voiceover/caption text
- core meaning
- evidence refs
- evidence authenticity level
- template id and template screenshot or explicit missing-preview placeholder
- composition state
- motion behavior
- transition in/out
- subtitle/safe-zone notes
- risk notes
- review decision

## Quality Gate

Reject the scene plan if any of these appear:

- core article/script meaning is lost
- fake data chart or unsourced number
- static image zoom/pan presented as animation
- repeated fixed layout for more than two consecutive scenes
- fewer than 14 effective visual changes per minute for 真人口播
- median scene duration above 4.5 seconds for 真人口播
- scene longer than 8 seconds without `micro_shots`
- evidence scene without `evidence_authenticity`
- global time scaling after discrete roughcut edits
- strong evidence without a direct claim relation and source locator
- one asset reused as direct support for more than four distinct claims
- missing or failing `claim_evidence_ledger` before asset generation
- a factual core claim marked complete when only part of its evidence requirements are satisfied
- contradicted or undefined original narration with a pending spoken revision
- renderer missing template implementations or ignoring director fields
- missing review table before render
- subtitles not planned from full voiceover/audio timing
- media output path points into `skills/` or project root
- outline items are truncated or silently omitted by the renderer
- source raster charts are taken from cropped page screenshots when original image assets exist
- a source chart has no complete `contain` reading state before detail magnification
- an enumerated source list changes cardinality between article, narration, storyboard, renderer, and recap
- a scene claims to use real topical B-roll but no downloaded local asset and provenance record exist
- a real-world explainer uses a static title-only opening despite having relevant downloaded footage and no documented editorial reason
- a 4-6 minute real-world explainer has only isolated token B-roll inserts, without a footage-pool plan, continuity use, or documented availability/rights exception
- contextual B-roll is labeled as direct evidence for a financial, regulatory, valuation, or return claim
- distinct business mechanisms are collapsed into one repeated card/flowchart template
- a core chart/table/document is repeatedly covered by short title or keyword curtains from the same topic
- visual-change density is achieved through full-screen interruptions rather than meaningful topic/evidence changes or local scene motion
- subtitle plates re-enter or disappear at every sentence end instead of remaining continuous across short gaps
- a scene transition uses a universal dark/white curtain or any frame where all visual layers are transparent
- human news/interview footage is used as an obscured chart background when it could be a full-screen or independent split/PIP evidence shot
- full-render pulse QC finds any single-frame black/white dropout at a subtitle end, scene boundary, or elsewhere in the timeline

## Related Commands

Validate the pipeline:

```bash
python3 scripts/video_pipeline_governance.py validate-pipeline talking_head
python3 scripts/video_pipeline_governance.py validate-pipeline explainer_html
python3 scripts/video_pipeline_governance.py validate-pipeline vox_explainer
python3 scripts/video_pipeline_governance.py validate-pipeline digital_human
python3 scripts/video_pipeline_governance.py validate-pipeline commercial_promo
python3 scripts/video_pipeline_governance.py validate-pipeline cinematic_short_drama
```

Create a checkpoint:

```bash
python3 scripts/video_pipeline_governance.py checkpoint <pipeline> scene_plan \
  --artifact script=<script.json> \
  --artifact scene_plan=<scene_plan.json> \
  --status pending_review \
  --output <director_checkpoint.json>
```

Validate a scene plan:

```bash
python3 scripts/video_pipeline_governance.py validate-artifact scene_plan <scene_plan.json>
```

Validate a Claim/Evidence Ledger:

```bash
python3 scripts/video_pipeline_governance.py validate-artifact claim_evidence_ledger <claim_evidence_ledger.json>
```
