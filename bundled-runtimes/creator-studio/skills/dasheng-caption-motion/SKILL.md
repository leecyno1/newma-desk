---
name: dasheng-caption-motion
description: Use when SRT, VTT, ASR segments, or word timestamps must drive animated subtitles, keyword emphasis, kinetic typography, lower thirds, or timed chart callouts in a Newma video using HyperFrames or Remotion.
---

# Newma Caption Motion

## Role

Convert approved timed text into a motion specification consumed by the existing HyperFrames/Remotion renderers. Captions are part of the director composition, not an unrelated subtitle layer pasted on at the end.

## Inputs

- reviewed SRT/VTT or word-level transcript
- director scene plan and safe-area/aspect-ratio rules
- visual identity and typography rules
- optional evidence-linked values for chart or number callouts

## Route Selection

- Choose HyperFrames for HTML-native captions, GSAP text reveals, marker sweeps, hand-drawn emphasis, audio-reactive accents, and reusable overlay blocks.
- Choose Remotion for frame-exact React compositions, data-native charts, complex master-timeline integration, or programmatic families already emitted by `build_remotion_renderer_pack.py`.
- Choose plain FFmpeg subtitle burn-in only for compatibility exports or low-motion fallback.

Read [references/caption-motion-contract.md](references/caption-motion-contract.md) before authoring a motion plan.

## Workflow

1. Normalize and proofread timed text before animation. Preserve names, dates, numbers, and sentence meaning.
2. Group words into readable semantic phrases; never animate every token merely because timestamps exist.
3. Emit `caption_motion_plan.json` with scene, phrase, timing, emphasis, renderer, safe-area, and fallback fields.
4. Bind key claims to real evidence or data fields. Animation may emphasize a number but may not invent it.
5. Render, inspect hero frames and dense-caption moments, then run the main video QC.
6. Keep a static SRT or restrained caption preset as fallback when the selected renderer is unavailable.

## Quality Gates

- Captions must remain readable at delivery resolution and within platform safe areas.
- Do not exceed two simultaneous emphasis devices on one phrase.
- Avoid continuous bouncing, random per-word color changes, and motion that competes with evidence.
- Captions may overlap B-roll only when contrast and occlusion have been checked at representative frames.
- Store render artifacts under `~/Desktop/自媒体创作/<run_id>/`, never inside this skill.
