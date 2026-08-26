# HTML Video Workflow

## Default Path

For `explainer_html_video`, `vox_explainer_video`, `talking_head_video`, `digital_human_video`, and `commercial_promo_video`, use `${HTML_VIDEO_ROOT:-vendor/reserved/render/html-video}` as the scene renderer. Remotion remains the master timeline. The deferred cinematic lane only registers this compositor and does not execute it.

The stage builder writes:

- `video_storyboard.json`
- `voiceover_script.md` or `talking_head_script.md`
- `html_overlay.html`
- `render_plan.json`
- `html_video_project_vars.json`
- `html_video_project_plan.json`

Run the bridge:

```bash
.venv/bin/python scripts/transwrite_html_video_bridge.py \
  --video-manifest <video_lane_manifest.json>
```

Only execute rendering when explicitly needed:

```bash
.venv/bin/python scripts/transwrite_html_video_bridge.py \
  --video-manifest <video_lane_manifest.json> \
  --execute render
```

## Mode Selection

- No human media: 16:9 synthetic voice + html-video visual scenes + Remotion master timeline.
- Commercial promo: 9:16 by default, with official product/brand assets, live HTML/HyperFrames scenes, Proof and CTA on the Remotion master timeline.
- Human audio/video: transcribe first, then align visuals to the human timeline.

## Quality Bar

- One frame, one idea.
- Use charts, contrast, maps, timelines, quotes, and market metaphors.
- Avoid turning the article outline into a generic framework diagram.
- If TTS is not configured, mark audio as blocked or preview-only.
