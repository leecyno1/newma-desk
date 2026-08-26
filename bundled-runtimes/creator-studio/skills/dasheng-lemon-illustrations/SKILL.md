---
name: dasheng-lemon-illustrations
description: Use when a talking-head or no-human video needs a conceptual cartoon insert, visual metaphor, process illustration, emotional beat, or transition asset. Generates the Newma lemon-person illustration system derived from helloianneo/ian-xiaohei-illustrations while preserving real charts, screenshots, tables, and evidence.
---

# Newma Lemon Illustrations

## Role

This is the default conceptual-cartoon lane for future口播精简. It adapts the MIT-licensed [helloianneo/ian-xiaohei-illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations) visual grammar without vendoring or modifying the upstream repository.

The recurring character is `柠檬人` (brand alias: `柠檬博士`): a serious, deadpan, anthropomorphic lemon systems operator. It performs the conceptual action; it is not a cute mascot or corner sticker.

## Required Reading

- `references/lemon-ip.md` for character identity and action rules.
- `references/metaphor-routing.md` when the source contains a metaphor, example, analogy, personification, or abstract mechanism.
- `references/prompt-template.md` for full-canvas and transparent-overlay prompts.
- `references/qa-checklist.md` before accepting an image.

## Routing

Use this skill for:

- abstract systems, causal chains, workflows, bottlenecks, emotions, transitions, chapter bridges, and memorable metaphors;
- full-screen 16:9 illustrations in no-human explainers;
- transparent character/prop overlays in talking-head edits;
- a short visual reset when real evidence is not the right visual language.

Do not use it to replace:

- real market charts, article charts, tables, official pages, documents, product UI, maps, source screenshots, or the speaker;
- a missing source or unsupported factual claim;
- every sentence with a random sticker.

Any scene using this system is `evidence_authenticity=schematic` unless separately paired with direct evidence.

## Workflow

1. Read the current narration beat and state the single idea the image must explain.
2. Scan for metaphor/example triggers and create or consume `illustration_intents.json`; keyword matches require Agent semantic review.
3. Choose a story grammar from `references/metaphor-routing.md`, then choose `full_canvas` or `transparent_overlay` from `references/prompt-template.md`.
4. Define one core action for柠檬人. If removing the character leaves the metaphor unchanged, redesign it.
5. Generate one image per prompt. Production generation uses MiniMax CLI; design exploration may use built-in `image_gen`.
6. For transparent overlays, generate on solid `#ff00ff`, remove chroma locally, and validate alpha edges.
7. Save all generated media under `~/Desktop/自媒体创作/`; never write media into this skill or the project root.
8. Composite the result as a layer in HTML/Remotion. Animate props, arrows, annotations, masks, or paths separately. A flattened image with zoom/pan alone is not a production animation.
9. Record the intent id, source paragraph, prompt, provider, output path, scene id, channel placement, and QA result in the task asset manifest.

## Output Contract

- Draft: `03_IllustrationIntents_<topic>.json` plus resolved `illustration_specs` embedded in Draft HTML.
- WeChat: `illustration_intents.json`, generated files under `wechat_article/lemon_illustrations/`, and placement immediately after the matching paragraph.
- Video: the same intent id appears in the director scene plan, asset manifest, and final scene metadata.

## Production Defaults

- Character master: `~/Desktop/自媒体创作/00_品牌资产/柠檬卡通人/lemon-person-master-reference-v2.jpg`
- Action sheet: `~/Desktop/自媒体创作/00_品牌资产/柠檬卡通人/lemon-person-reference-sheet-v1.jpg`
- Runtime output: `~/Desktop/自媒体创作/<run_id>/assets/lemon_illustrations/`
- Full illustration: 16:9, pure white background, sparse hand-drawn black lines, at least 35% blank space.
- Transparent overlay: isolated subject, flat `#ff00ff` source, alpha PNG delivery.
- Color accents: lemon yellow and dark green for character; restrained orange/red/blue annotations.
- Text: no title; at most 5 short Chinese annotations on a full illustration; normally no text on a transparent overlay.

## Motion Contract

Generated raster art is source material, not the finished scene. At least one semantic motion layer is required:

- character enters while a separate path is drawn;
- prop moves independently from the character;
- evidence marker, warning, or result appears after the action;
- mask reveal exposes the system state;
- talking-head PIP morphs while the illustration takes the main field;
- full-canvas illustration holds long enough to read before a speaker return or evidence cut.

Never loop the same entrance repeatedly. Never reuse one pose for unrelated concepts merely to fill the timeline.

## Attribution And Sync

- Upstream: `https://github.com/helloianneo/ian-xiaohei-illustrations`
- Local external checkout: `${IAN_XIAOHEI_ILLUSTRATIONS_ROOT:-${IAN_XIAOHEI_ILLUSTRATIONS_ROOT:-vendor/reserved/video/ian-xiaohei-illustrations}}`
- License: MIT
- Sync with `git pull --ff-only` in the external checkout, then review upstream prompt/style changes before updating this adapter.
