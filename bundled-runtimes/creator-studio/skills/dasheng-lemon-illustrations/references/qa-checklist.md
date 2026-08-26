# QA Checklist

## Image Gate

- The same柠檬人 identity is recognizable across scenes.
- The character is serious/deadpan, not cute, smiling, childish, or commercially polished.
- The character performs the core action; it is not a corner decoration.
- One image contains one conceptual action.
- Full-canvas mode is 16:9, white, sparse, and keeps at least 35% blank space.
- Transparent mode has an alpha channel, transparent corners, no magenta fringe, and no cast shadow.
- No invented fact, fake chart, unsupported number, source logo, or fake document appears.
- No top-left type title, dense labels, PPT grid, realistic UI, gradient, shadow, or paper texture appears.

## Video Gate

- The image is not used as a flattened full scene with zoom/pan only.
- Character, prop, path, annotation, mask, or PIP has semantic motion.
- The scene holds long enough to understand the metaphor.
- It does not cover the speaker's face, subtitles, or evidence.
- The same pose/layout is not reused for unrelated consecutive beats.
- A factual beat returns to real evidence instead of continuing decorative cartoon inserts.

## Retry Rules

- Too cute: remove the mouth, reduce leaf size, require deadpan eyes and awkward work posture.
- Too generic: make柠檬人 operate the actual metaphor, not stand beside it.
- Too dense: delete nodes and labels until one action remains.
- Too static: split the scene into character, prop, path, and result layers and animate them separately.
- Bad chroma edge: retry removal with `--edge-contract 1`; reject if magenta remains.
