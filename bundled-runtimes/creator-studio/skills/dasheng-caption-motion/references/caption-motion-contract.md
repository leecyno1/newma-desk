# Caption motion contract

Each entry in `caption_motion_plan.json` should contain:

```json
{
  "scene_id": "scene-03",
  "start": 12.4,
  "end": 15.1,
  "text": "机构持仓进一步集中",
  "emphasis": [{"text": "进一步集中", "type": "marker_sweep"}],
  "renderer": "hyperframes",
  "safe_area": "square_default",
  "evidence_ref": "claim-07",
  "fallback": "static_caption"
}
```

Use `hyperframes` for HTML/GSAP-first overlays and `remotion` for frame-native React/chart compositions. The scene plan owns final timing when subtitle timestamps conflict with an approved edit.
