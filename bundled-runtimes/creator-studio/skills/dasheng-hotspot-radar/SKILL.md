---
name: dasheng-hotspot-radar
description: Use when an agent needs a standalone no-login hotspot/news radar for Newma workflows, especially public macro/policy/geopolitics/market trend capture without running the full intake stage.
---

# dasheng-hotspot-radar

## Purpose

Run the standalone hotspot capture module used by Stage 1 intake.

Use this when another Agent needs fast public signal discovery from:

- 公开新闻：华尔街见闻、同花顺、彭博市场
- 公开热榜：HN、WSJ、知乎、头条、微博、虎扑、抖音等 no-login sources

## Command

```bash
cd ${DASHENG_PROJECT_ROOT:-.}
python3 scripts/run_hotspot_radar.py
```

Optional output directory:

```bash
python3 scripts/run_hotspot_radar.py --output-dir ~/Desktop/自媒体创作/00_热点捕捉/manual-check
```

## Output

The command writes:

- `hotspot_radar.json`
- `hotspot_radar_manifest.json`
- `raw/public_news_fallback_items.json`
- `raw/public_fallback_items.json`
- `raw/hotspot_radar.json`

`hotspot_radar.json` preserves dynamic items and adds:

- `radar.capture_role`
- `radar.source_role`
- `radar.macro_policy_score`
- `radar.kept_by`

## Rules

- Do not hard-filter news content by fixed topics.
- Keep dynamic public hotspots even when macro/policy score is low.
- Treat macro/policy/geopolitics preference as scoring metadata, not an exclusion rule.
- Use source health in `hotspot_radar_manifest.json` before trusting a missing source.
