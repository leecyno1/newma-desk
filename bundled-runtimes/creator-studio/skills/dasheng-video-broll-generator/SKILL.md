---
name: dasheng-video-broll-generator
description: Use when a Newma video needs B-roll, editorial collage inserts, animated stickers, visual metaphors, or generated cutaways. Routes each shot to sourced footage, local motion/illustration tools, or allowlisted first-party video models without replacing factual evidence.
---

# Newma Video B-roll Generator

## Role

Turn a reviewed scene plan into a B-roll manifest. This is a routing and quality-gate skill: it does not vendor upstream generators and it never treats generated imagery as proof of a factual claim.

## Inputs

- reviewed `scene_plan.json` or director storyboard
- narration/subtitle timing
- visual identity (`DESIGN.md`, style profile, or explicit art direction)
- evidence ledger and existing media inventory

## Provider Routing

1. Use real charts, filings, screenshots, source video, or licensed stock when the shot carries evidence.
2. Use internal HTML/Remotion/HyperFrames motion for data-native diagrams, text, UI, and repeatable graphic systems.
3. For the VOX lane, Codex built-in `imagegen` makes each approved flat paper-collage object map, then `dasheng-video-omni-browser` uses the signed-in Chrome Gemini session only to generate one 10-second video clip per shot.
4. Use internal HTML/Remotion/HyperFrames for exact text, charts, UI, repeatable systems and final compositing.
5. Use `seedance2-skill` only as a shot-level reserve when no factual identity, exact product state, or real event must be preserved.
6. Use `dasheng-lemon-illustrations` for conceptual metaphors that should match the channel IP.

Read [references/provider-routing.md](references/provider-routing.md) before selecting an external provider.

## Workflow

1. Classify every requested insert as `evidence`, `context`, `metaphor`, `transition`, or `decoration`.
2. Reuse approved local assets before generating new media.
3. Write one manifest row per shot with `scene_id`, `start`, `duration`, `purpose`, `provider`, `prompt_or_source`, `evidence_status`, `license_status`, and `fallback`.
4. Generate only reviewed rows. Store outputs under `~/Desktop/自媒体创作/<run_id>/assets/broll/`.
5. Probe every clip, normalize its dimensions/frame rate, and pass it to the main compositor; do not concatenate a second independent video timeline.
6. Review the combined cut for repetition, visual-semantic mismatch, false realism, discontinuity, and excessive decorative motion.

## Hard Rules

- Generated B-roll may illustrate a concept but must not impersonate evidence, a real person, a real interface state, or a historical event.
- Never copy generated media, model caches, credentials, or external repositories into `skills/`.
- Do not create a new visual for every sentence. Preserve continuity and let important shots breathe.
- A provider failure must fall back to an internal composition, licensed source, or explicit placeholder; it must not block the entire edit.
- The director timeline remains the source of truth for timing, crop, transitions, and compositing.
