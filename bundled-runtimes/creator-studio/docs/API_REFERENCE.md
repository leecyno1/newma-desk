# API Reference

Complete API reference for the Newma Media Studio.

## Overview

The system uses a **manifest-driven architecture** where each stage produces:
1. **Manifest JSON** - Canonical state (source of truth)
2. **Gate JSON** - HITL decision point
3. **Markdown Report** - Human-readable delivery view

## Stage Interfaces

### Stage 1: Intake (内容采集)

#### Input
- None (scrapes from configured data sources)

#### Output Files
- `intake_manifest.json` - Canonical intake state
- `intake_records.json` - Raw intake records
- `entity_rankings.json` - Entity frequency analysis
- `event_clusters.json` - Event clustering results
- `channel_top10.json` - Top 10 per channel
- `brief_input.json` - Prepared input for Brief stage
- `intake_review.json` - Optional HITL gate

#### Manifest Schema
```json
{
  "run_id": "YYYY-MM-DD_HHMMSS",
  "stage": "intake",
  "status": "completed",
  "timestamp": "ISO8601",
  "sources": {
    "port_5173": { "count": 0, "valid": 0 },
    "port_18080": { "count": 0, "valid": 0 },
    "port_8001": { "count": 0, "valid": 0 },
    "external": { "count": 0, "valid": 0 }
  },
  "summary": {
    "total_items": 0,
    "valid_items": 0,
    "dedup_items": 0,
    "top_entities": []
  },
  "next_stage": "brief"
}
```

#### CLI
```bash
python3 scripts/run_stage1_intake.py
```

---

### Stage 2: Brief (选题分析)

#### Input
- `brief_input.json` (from Intake)
- `channel_top10.json` (from Intake)
- `event_clusters.json` (from Intake)

#### Output Files
- `brief_manifest.json` - Canonical brief state
- `topic_cards.json` - Structured topic cards
- `selected_topics.json` - **MANDATORY GATE** for Draft

#### Topic Card Schema
```json
{
  "topic_id": "string",
  "topic_kind": "hot_event|trend_analysis|opinion_piece",
  "mother_topic_id": "string|null",
  "angle_variant_of": "string|null",
  "core_proposition": "string",
  "conflict_axis": "string",
  "scoring": {
    "heat": 0-10,
    "sharpness": 0-10,
    "evidence": 0-10,
    "longevity": 0-10,
    "reader_value": 0-10
  },
  "proof_requirements": [
    {
      "requirement": "string",
      "current_evidence": [],
      "gap": "string"
    }
  ],
  "recommended_data_angles": [],
  "recommended_visual_angles": []
}
```

#### Gate Schema (selected_topics.json)
```json
{
  "run_id": "string",
  "status": "approved",
  "selected_topics": [
    {
      "topic_id": "string",
      "editor_note": "string",
      "priority": 1-10
    }
  ]
}
```

---

### Stage 3: Draft (初稿生成)

#### Input
- `selected_topics.json` - **MANDATORY GATE**
- `topic_cards.json` (from Brief)

#### Output Files
- `draft_manifest.json` - Canonical draft state
- `03_标准初稿_<topic>.md` - Standard draft per topic
- `03_ReasoningSheet_<topic>.md` - Reasoning structure
- `03_ReasoningSheet_<topic>.json` - Structured reasoning
- `final_structure_snapshot.json` - **MANDATORY GATE** for Material/Rewrite

#### Manifest Schema
```json
{
  "run_id": "string",
  "stage": "draft",
  "status": "completed",
  "output_dir": "string",
  "drafts": [
    {
      "topic_id": "string",
      "title": "string",
      "draft_file": "string",
      "reasoning_sheet_file": "string",
      "reasoning_sheet_json": "string",
      "word_count": 0,
      "h2_count": 0
    }
  ],
  "next_stage": "material"
}
```

#### Gate Schema (final_structure_snapshot.json)
```json
{
  "run_id": "string",
  "status": "approved",
  "topics": [
    {
      "topic_id": "string",
      "title": "string",
      "doc_file": "string",
      "final_primary_sections": ["string"],
      "h2_count": 0,
      "editor_note": "string"
    }
  ]
}
```

#### CLI
```bash
python3 scripts/build_stage3_draft.py \
  --selected-topics /path/to/selected_topics.json \
  --run-id YYYY-MM-DD_HHMMSS
```

---

### Stage 4: Material (素材收集)

#### Input
- `draft_manifest.json` (from Draft)
- `final_structure_snapshot.json` - **MANDATORY GATE**

#### Output Files
- `material_manifest.json` - Canonical material state
- `material_acceptance.json` - **MANDATORY GATE** for Rewrite
- `pack_assets/<topic>/` - Asset directories

#### Manifest Schema
```json
{
  "run_id": "string",
  "stage": "material",
  "status": "completed",
  "topics": [
    {
      "topic_id": "string",
      "assets": [
        {
          "asset_id": "string",
          "asset_type": "chart|image|video|infographic",
          "claim_id": "string",
          "section_id": "string",
          "file_path": "string",
          "usage_type": "evidence|illustration|cover",
          "relevance_score": 0.0-1.0,
          "editor_status": "pending|approved|rejected"
        }
      ]
    }
  ],
  "next_stage": "rewrite"
}
```

#### Gate Schema (material_acceptance.json)
```json
{
  "run_id": "string",
  "status": "approved",
  "topics": [
    {
      "topic_id": "string",
      "assets_count": 0,
      "editor_review": {
        "charts_approved": 0,
        "images_approved": 0,
        "videos_approved": 0,
        "total_approved": 0
      }
    }
  ]
}
```

#### CLI
```bash
python3 scripts/material_execute_pack.py \
  --draft-manifest /path/to/draft_manifest.json
```

---

### Stage 5: Rewrite (改写)

#### Input
- `draft_manifest.json` (from Draft)
- `final_structure_snapshot.json` - **MANDATORY GATE**
- `material_manifest.json` (optional, for asset integration)

#### Output Files
- `rewrite_manifest.json` - Canonical rewrite state
- `<topic>__rewrite_bundle.md` - All versions bundled
- `<topic>__wechat_luxun_hot.md` - WeChat hot version
- `<topic>__wechat_lemon_normal.md` - WeChat normal version
- `<topic>__xhs_video_luxun_hot.md` - Xiaohongshu hot version
- `<topic>__xhs_video_lemon_normal.md` - Xiaohongshu normal version
- `meta.json` - Version metadata

#### Manifest Schema
```json
{
  "run_id": "string",
  "stage": "rewrite",
  "status": "completed",
  "topics": {
    "topic-001": {
      "wechat_hot": {
        "status": "completed",
        "content": "string",
        "quality_score": 8.0-10.0,
        "quality_status": "excellent|good|acceptable",
        "anchor_preserved_rate": 0-100,
        "word_count": 0,
        "target_word_count": 0,
        "attempt": 1-3
      }
    }
  },
  "summary": {
    "total_topics": 0,
    "completed_versions": 0,
    "failed_topics": 0,
    "versions": []
  },
  "next_stage": "transwrite"
}
```

#### Version Schema
```json
{
  "wechat_hot": {
    "platform": "wechat",
    "tone": "hot",
    "word_count": {
      "target": 1300,
      "min": 1105,
      "max": 1495
    },
    "primary_audience": "知识精英、投资者"
  },
  "wechat_normal": {
    "platform": "wechat",
    "tone": "normal",
    "word_count": {
      "target": 1000,
      "min": 850,
      "max": 1150
    }
  },
  "xiaohongshu_hot": {
    "platform": "xiaohongshu",
    "tone": "hot",
    "word_count": {
      "target": 900,
      "min": 765,
      "max": 1035
    }
  },
  "xiaohongshu_normal": {
    "platform": "xiaohongshu",
    "tone": "normal",
    "word_count": {
      "target": 650,
      "min": 553,
      "max": 748
    }
  }
}
```

#### Quality Requirements
- **Quality Score**: ≥8.0/10
- **Word Count Deviation**: ±15%
- **Anchor Preservation Rate**: ≥80%
- **Auto-retry**: Up to 3 attempts

#### CLI
```bash
python3 scripts/rewrite_execute_stage5.py \
  --draft-manifest /path/to/draft_manifest.json \
  --versions wechat_hot,wechat_normal,xiaohongshu_hot,xiaohongshu_normal \
  --json-output
```

---

### Stage 6: Publish (发布执行)

#### Input
- `transwrite_manifest.json` (from Transwrite)
- `publish_decision.json` - **MANDATORY GATE**

#### Output Files
- `publish_manifest.json` - Canonical publish state
- `channel_packs/<topic_id>/<channel>/channel_pack.json` - Per-channel execution pack
- `channel_packs/<topic_id>/<channel>/execution_request.json` - Safe execution plan
- `channel_packs/<topic_id>/<channel>/verification_request.json` - Verification plan
- `channel_packs/<topic_id>/<channel>/platform_form_validation.json` - Platform-specific preflight validation
- `channel_packs/<topic_id>/<channel>/publish_payload.json` - Executor payload
- `channel_packs/<topic_id>/<channel>/publish_result.json` - Recorded executor/manual result
- `channel_packs/<topic_id>/<channel>/<task_id>/channel_pack.json` - Independent matrix task pack
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_result_history.json` - Append-only retry history
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_results/attempt-XXXX.json` - Per-attempt receipt
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_retry_request.json` - Classified, confirmation-gated retry plan
- `channel_execution_manifest.json` - Execution routing and result state
- `publish_verification_report.json` - Post-publish verification
- `publish_guard_report.json` - Batch verification report
- `publish_guard_report.md` - Human-readable batch verification report

#### Manifest Schema
```json
{
  "run_id": "string",
  "stage": "publish",
  "status": "pending_execution|partially_recorded|failed|needs_manual_verification|all_drafted|all_published|completed_with_mixed_status",
  "channel_packs": [
    {
      "task_id": "string|null",
      "batch_id": "string|null",
      "topic_id": "string",
      "variant_id": "string",
      "title": "string",
      "channel": "wechat_article|xiaohongshu_video|douyin_video|bilibili_video|x_post|weibo_post|podcast",
      "account_slot": "slot-1",
      "platform": "string",
      "status": "ready_for_execution|blocked_or_waiting",
      "pack_manifest": "path"
    }
  ],
  "publish_results": [],
  "publish_summary": {
    "total_channels": 0,
    "recorded_count": 0,
    "pending_count": 0,
    "failed_count": 0,
    "draft_count": 0,
    "published_count": 0,
    "verified_count": 0,
    "needs_manual_verification_count": 0,
    "pending_channels": []
  },
  "publish_guard": {
    "status": "missing|pending_execution|failed|passed",
    "passed": false,
    "checked_at": "ISO8601|null",
    "report_json": "path|null",
    "report_markdown": "path|null",
    "will_not_publish": true
  },
  "next_stage": "postmortem"
}
```

For batch publishing, define `publish_matrix.json` with content variants and target account slots, then run `scripts/expand_publish_matrix.py`. When `publish_decision.tasks` exists, Stage Publish creates one independent pack per `task_id`; legacy decisions without tasks retain the old directory shape and `(topic_id, channel)` identity. Metadata precedence is matrix defaults, matrix channel defaults, registry channel presets, content variant, registry account presets, then target override.

Account presets are non-secret configuration only. Sensitive-looking fields such as passwords, cookies, tokens, API keys, secrets, or proxy passwords are stripped and block matrix approval.

#### Gate Schema (publish_decision.json)
```json
{
  "run_id": "string",
  "status": "approved",
  "topics": [
    {
      "topic_id": "string",
      "channels": ["wechat_article", "xiaohongshu_video"],
      "scheduled_time": "ISO8601|null",
      "notes": "string"
    }
  ]
}
```

#### CLI
```bash
python3 scripts/build_stage5_publish.py \
  --transwrite-manifest /path/to/transwrite_manifest.json \
  --publish-decision /path/to/publish_decision.json
```

Result writeback:

```bash
python3 scripts/record_publish_result.py \
  --channel-pack /path/to/channel_pack.json \
  --success true \
  --status draft \
  --draft-id <draft_id> \
  --verification-status verified
```

Publish Guard:

```bash
python3 scripts/publish_guard.py \
  --publish-manifest /path/to/publish_manifest.json
```

Strict/CI gate:

```bash
python3 scripts/publish_guard.py \
  --publish-manifest /path/to/publish_manifest.json \
  --fail-on-error
```

Verification semantics:

- `published_links` only contains `status=published` results with verified formal `platform_url`.
- `draft_records` only contains `status=draft|scheduled` results with verified `draft_id`.
- `draft_url` is separate from `platform_url`; draft links must not be reported as published links.
- `record_publish_result.py` does not auto-verify based on URL or draft ID; callers must explicitly pass `--verification-status verified` when the platform has been checked.
- `build_stage5_publish.py` writes an initial `publish_summary`; before any result is recorded, `recorded_count=0` and `pending_count=total_channels`.
- `publish_guard.py` writes `publish_guard_report.json`, `publish_guard_report.md`, and `publish_manifest.publish_guard`.
- `publish_guard.py` requires the sibling `publish_verification_report.json`; a manifest-only batch must not pass guard verification.
- `publish_manifest.publish_results` must match `publish_verification_report.records`, and both `publish_summary` objects must match the recomputed state.
- Every recorded publish result must reference an existing `publish_result.json` via `result_file`, and the file's core publish fields must match the recorded result.
- Every retry appends a numbered attempt receipt and updates only that task's latest result. Results with `task_id` are never deduplicated by channel alone.
- Failed attempts are classified and produce `publish_retry_request.json`. Backoff never authorizes publishing: every retry request keeps `automatic_execution=false` and requires current-session confirmation.
- Default Publish Guard writes reports and exits 0 even when the batch is not passed; `--fail-on-error` exits non-zero when `passed=false`.
- No current-session confirmation means no real platform publishing.

---

### Stage 7: Postmortem (分析复盘)

#### Input
- `publish_manifest.json` (from Publish)
- Optional strict gate: `publish_manifest.publish_guard.passed=true`

#### Output Files
- `postmortem_manifest.json` - Canonical postmortem state
- `08_复盘报告.md` - Postmortem report
- `08_L1回写建议.md` - L1 knowledge base update suggestions

#### Manifest Schema
```json
{
  "run_id": "string",
  "stage": "postmortem",
  "status": "completed",
  "publish_guard": {
    "present": true,
    "status": "passed",
    "passed": true,
    "report_json": "path|null",
    "report_markdown": "path|null",
    "checked_at": "ISO8601|null"
  },
  "topics": [
    {
      "topic_id": "string",
      "topic_name": "string",
      "published": true,
      "drafted": false,
      "selected_channels": [],
      "publish_results": [],
      "performance": {}
    }
  ],
  "writeback": {
    "topic_pattern_library": {},
    "evidence_pattern_library": {},
    "visual_pattern_library": {},
    "channel_pattern_library": {}
  }
}
```

Postmortem groups by `topic_id`, not channel pack count. A topic is counted as published only when at least one publish result is `status=published`, `verification_status=verified`, and has a formal `platform_url`.

Strict Postmortem:

```bash
python3 scripts/postmortem_writeback.py \
  --publish-manifest /path/to/publish_manifest.json \
  --require-publish-guard
```

Default Postmortem may continue when Publish Guard is missing, but strict Postmortem must fail before writing outputs unless `publish_manifest.publish_guard.status=passed`, `passed=true`, and both Guard report files exist.

---

## Common Patterns

### Manifest File Naming
- Format: `<stage>_manifest.json`
- Location: `~/Desktop/自媒体创作/<stage_number>_<stage_name>/<run_id>/`
- Example: `~/Desktop/自媒体创作/00_改写/2026-04-17_120000/rewrite_manifest.json`

### Gate File Naming
- Format: `<gate_name>.json`
- Location: Same as manifest
- Examples:
  - `selected_topics.json` (Brief → Draft gate)
  - `final_structure_snapshot.json` (Draft → Material/Rewrite gate)
  - `material_acceptance.json` (Material → Rewrite gate)
  - `publish_decision.json` (Transwrite → Publish gate)

### Run ID Format
- Format: `YYYY-MM-DD_HHMMSS`
- Example: `2026-04-17_120000`
- Generated: `datetime.now().strftime("%Y-%m-%d_%H%M%S")`

### Status Values
- `pending` - Not started
- `in_progress` - Currently executing
- `completed` - Successfully finished
- `failed` - Execution failed
- `blocked` - Waiting for gate approval
- `approved` - Gate approved (for gate files)

---

## Error Handling

### Standard Error Response
```json
{
  "success": false,
  "error": "string",
  "error_code": "string",
  "stage": "string",
  "run_id": "string"
}
```

### Common Error Codes
- `GATE_NOT_FOUND` - Required gate file missing
- `GATE_NOT_APPROVED` - Gate status not approved
- `MANIFEST_INVALID` - Manifest JSON invalid
- `QUALITY_THRESHOLD_NOT_MET` - Quality score below threshold
- `WORD_COUNT_OUT_OF_RANGE` - Word count deviation too large
- `ANCHOR_PRESERVATION_LOW` - Anchor preservation rate too low

---

## Skill Invocation

### Skill Invoker Interface
```python
from skill_invoker import SkillInvoker

invoker = SkillInvoker()
result = invoker.invoke(skill_name, payload, context)
```

### Standard Skill Response
```json
{
  "success": true|false,
  "data": {},
  "error": "string|null",
  "metadata": {
    "skill_name": "string",
    "execution_time_ms": 0,
    "model_used": "string"
  }
}
```

---

## Validation Rules

### Word Count Validation
```python
def validate_word_count(actual, target, tolerance=0.15):
    min_allowed = target * (1 - tolerance)
    max_allowed = target * (1 + tolerance)
    return min_allowed <= actual <= max_allowed
```

### Quality Score Validation
```python
def validate_quality_score(score, threshold=8.0):
    return score >= threshold
```

### Anchor Preservation Validation
```python
def validate_anchor_preservation(rate, threshold=80):
    return rate >= threshold
```

---

## Next Steps

- See [INSTALLATION.md](INSTALLATION.md) for installation guide
- See [CONFIGURATION.md](CONFIGURATION.md) for configuration options
- See [CLAUDE.md](../CLAUDE.md) for development guidelines
