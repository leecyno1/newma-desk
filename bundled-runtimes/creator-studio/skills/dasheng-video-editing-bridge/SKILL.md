---
name: dasheng-video-editing-bridge
description: Use when a request asks for end-to-end video editing and Newma must choose between its internal director pipeline, chengfeng-videocut, video-use, Jianying, or another reviewed provider without losing review gates.
---

# Newma Video Editing Bridge

## Role

Select and supervise a full-editing route. This bridge keeps one project manifest, one reviewed timeline, and one final QC contract even when an external editing agent performs part of the work.

## Routing

| Route | Choose when | Status |
| --- | --- | --- |
| internal Newma pipeline | evidence-heavy finance video, director-level control, custom animation, repeatable review | default |
| Jianying production path | fast talking-head cleanup, beauty/audio polish, cloud-draft handoff | production fallback |
| chengfeng-videocut | local-first agent editing experiment with a reviewed project boundary | optional provider |
| video-use | conversational folder-to-final experiment where its dependency model is acceptable | optional provider |

Detailed constraints are in [references/provider-matrix.md](references/provider-matrix.md).

## Workflow

1. Inventory source media, script, subtitles, evidence, output ratio, target duration, and publishing channel.
2. Select the smallest route that satisfies the creative and audit requirements.
3. Write the selected provider, version/commit if known, input boundary, output boundary, and fallback into the run manifest.
4. Keep roughcut, director plan, asset generation, compositing, render, and QC as separately reviewable stages even if one provider can run them all.
5. Import external output as a work copy. Probe it and run Newma render/QC gates before calling it final.
6. If the external route fails, preserve manifests and fall back to the internal or Jianying path instead of restarting from raw media.

## Hard Rules

- Do not vendor external repositories into `skills/`.
- Do not allow a one-shot editor to bypass evidence review, subtitle proofreading, final-frame inspection, or publish confirmation.
- External provider output is not automatically the final master.
- Credentials, browser state, caches, and generated media remain outside the repository.
- Store production outputs under `~/Desktop/自媒体创作/<run_id>/`.
