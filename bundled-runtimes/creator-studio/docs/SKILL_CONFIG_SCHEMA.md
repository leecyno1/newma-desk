# Skill Config Schema - Unified Standard

This document defines the unified `config.json` schema for all OpenClaw/Hermes skills in the Newma Media Studio.

## Schema Version

**Current Version**: 2.0.0

## Standard Schema

```json
{
  "name": "string (required)",
  "version": "string (required, semver format)",
  "description": "string (required)",
  "stage": "string (optional, for stage-based skills)",
  "stage_number": "number (optional, 1-7)",
  "runner": "string (optional, 'node' or 'python', default: 'python')",
  "entry": "string (optional, entry point file)",
  "upstream_gate": "string (optional, required gate file from previous stage)",
  "output_gate": "string (optional, gate file produced by this stage)",
  "hitl": "boolean (optional, human-in-the-loop required)",
  "trigger": "string or object (optional)",
  "deprecated": "boolean (optional, default: false)",
  "replacement": "string (optional, replacement skill name)",
  "aliases": "array of strings (optional)",
  "dependencies": "object (optional)",
  "inputs": "object (optional)",
  "outputs": "object (optional)",
  "quality_requirements": "object (optional)",
  "metadata": "object (optional, skill-specific configuration)"
}
```

## Field Definitions

### Core Fields (Required)

#### name
- **Type**: string
- **Required**: Yes
- **Description**: Unique skill identifier
- **Format**: `dasheng-{category}-{function}` or `dasheng-stage-{stage_name}`
- **Examples**: `dasheng-daily-intake`, `dasheng-stage-draft`, `dasheng-media-sop`

#### version
- **Type**: string
- **Required**: Yes
- **Description**: Semantic version number
- **Format**: `MAJOR.MINOR.PATCH`
- **Examples**: `1.0.0`, `3.1.0`, `4.0.0-beta`

#### description
- **Type**: string
- **Required**: Yes
- **Description**: Brief description of skill purpose
- **Max Length**: 200 characters
- **Language**: Chinese or English

### Stage Fields (For Stage-Based Skills)

#### stage
- **Type**: string
- **Required**: For stage-based skills
- **Description**: Stage name in workflow
- **Valid Values**: `intake`, `brief`, `draft`, `material`, `rewrite`, `publish`, `postmortem`

#### stage_number
- **Type**: number
- **Required**: For stage-based skills
- **Description**: Stage position in workflow (1-7)
- **Valid Values**: 1, 2, 3, 4, 5, 6, 7

#### upstream_gate
- **Type**: string
- **Required**: For stages 2-7
- **Description**: Required gate file from previous stage
- **Examples**: `selected_topics.json`, `final_structure_snapshot.json`, `material_acceptance.json`

#### output_gate
- **Type**: string
- **Required**: For stages 1-6
- **Description**: Gate file produced by this stage
- **Examples**: `intake_review.json`, `selected_topics.json`, `final_structure_snapshot.json`

#### hitl
- **Type**: boolean
- **Required**: For stage-based skills
- **Description**: Whether human-in-the-loop approval is required
- **Default**: false

### Execution Fields

#### runner
- **Type**: string
- **Required**: No
- **Description**: Execution runtime
- **Valid Values**: `node`, `python`
- **Default**: `python`

#### entry
- **Type**: string
- **Required**: If runner is `node`
- **Description**: Entry point file
- **Examples**: `index.js`, `main.py`

#### trigger
- **Type**: string or object
- **Required**: No
- **Description**: Skill invocation trigger
- **Formats**:
  - String: `"manual"`, `"auto"`
  - Object: `{ "keyword": "string", "cron": "string", "previous_step": "string" }`

### Deprecation Fields

#### deprecated
- **Type**: boolean
- **Required**: No
- **Description**: Whether skill is deprecated
- **Default**: false

#### replacement
- **Type**: string
- **Required**: If deprecated is true
- **Description**: Name of replacement skill
- **Example**: `dasheng-media-sop`

### Discovery Fields

#### aliases
- **Type**: array of strings
- **Required**: No
- **Description**: Alternative names for skill invocation
- **Example**: `["intake", "caiji", "第一环节"]`

### Dependency Fields

#### dependencies
- **Type**: object
- **Required**: No
- **Description**: External dependencies
- **Schema**:
```json
{
  "python": ">=3.10",
  "node": ">=18.0.0",
  "anthropic": ">=0.18.0",
  "packages": ["requests", "pandas"]
}
```

### Input/Output Fields

#### inputs
- **Type**: object
- **Required**: No
- **Description**: Input file requirements
- **Schema**:
```json
{
  "required": ["file1.json", "file2.json"],
  "optional": ["file3.json"]
}
```

#### outputs
- **Type**: object
- **Required**: No
- **Description**: Output file specifications
- **Schema**:
```json
{
  "documents": ["file1.md", "file2.md"],
  "manifests": ["manifest.json"],
  "gates": ["gate.json"]
}
```

### Quality Fields

#### quality_requirements
- **Type**: object
- **Required**: No
- **Description**: Quality thresholds and constraints
- **Schema**:
```json
{
  "min_quality_score": 8.0,
  "word_count_deviation": "±15%",
  "anchor_preservation_rate": "≥80%",
  "structure_limit": "3-4 top-level sections maximum"
}
```

### Metadata Fields

#### metadata
- **Type**: object
- **Required**: No
- **Description**: Skill-specific configuration
- **Examples**: `material`, `brief`, `scoring`, `output`, `feishu`, `layer5`

## Standard Templates

### Stage-Based Skill Template

```json
{
  "name": "dasheng-stage-{stage_name}",
  "version": "1.0.0",
  "description": "Stage {N} {Stage Name} - {Purpose}",
  "stage": "{stage_name}",
  "stage_number": 0,
  "runner": "node",
  "entry": "index.js",
  "upstream_gate": "{previous_gate}.json",
  "output_gate": "{current_gate}.json",
  "hitl": true,
  "trigger": "manual",
  "dependencies": {
    "python": ">=3.10",
    "node": ">=18.0.0"
  },
  "inputs": {
    "required": ["{upstream_gate}.json"],
    "optional": []
  },
  "outputs": {
    "documents": [],
    "manifests": [],
    "gates": []
  },
  "quality_requirements": {}
}
```

### Daily Workflow Skill Template

```json
{
  "name": "dasheng-daily-{function}",
  "version": "1.0.0",
  "description": "{Function description}",
  "trigger": {
    "keyword": "{keyword}",
    "previous_step": "{previous_skill}"
  },
  "aliases": [],
  "runner": {
    "script": "${OPENCLAW_WORKSPACE}/scripts/{script_name}.py",
    "stage_root": "${OPENCLAW_WORKSPACE}/产物/{stage_dir}",
    "manifest": "{manifest_name}.json"
  },
  "output": {
    "stage_dir": "${OPENCLAW_WORKSPACE}/产物/{stage_dir}/{run_id}",
    "report": "notes/{report_name}.md",
    "manifest": "{manifest_name}.json"
  }
}
```

### Deprecated Skill Template

```json
{
  "name": "dasheng-{old-name}",
  "version": "3.0.0",
  "description": "{Legacy description}",
  "deprecated": true,
  "replacement": "dasheng-{new-name}",
  "trigger": {
    "keyword": "{keyword}",
    "previous_step": null
  }
}
```

## Migration Guide

### From Legacy Format to Standard Format

**Step 1**: Add required fields if missing
```json
{
  "name": "existing-skill",
  "version": "1.0.0",  // ADD if missing
  "description": "..."  // ADD if missing
}
```

**Step 2**: Standardize stage fields (for stage-based skills)
```json
{
  "stage": "draft",           // ADD
  "stage_number": 3,          // ADD
  "upstream_gate": "...",     // ADD
  "output_gate": "...",       // ADD
  "hitl": true                // ADD
}
```

**Step 3**: Unify runner configuration
```json
{
  "runner": "node",           // CHANGE from nested object
  "entry": "index.js"         // EXTRACT from runner object
}
```

**Step 4**: Standardize dependencies
```json
{
  "dependencies": {           // RENAME from requirements
    "python": ">=3.10",
    "node": ">=18.0.0"
  }
}
```

**Step 5**: Move skill-specific config to metadata
```json
{
  "metadata": {               // WRAP skill-specific fields
    "material": {...},
    "layer5": {...}
  }
}
```

## Validation Rules

1. **Required Fields**: `name`, `version`, `description` must be present
2. **Version Format**: Must follow semver (MAJOR.MINOR.PATCH)
3. **Stage Consistency**: If `stage` is present, `stage_number` must match
4. **Gate Chain**: `upstream_gate` must match previous stage's `output_gate`
5. **Deprecation**: If `deprecated: true`, `replacement` must be specified
6. **Runner Entry**: If `runner: "node"`, `entry` must be specified
7. **HITL Gates**: If `hitl: true`, `output_gate` must be specified

## Examples

See individual skill `config.json` files for complete examples:
- Stage-based: `skills/dasheng-stage-draft/config.json`
- Daily workflow: `skills/dasheng-daily-intake/config.json`
- Deprecated: `skills/dasheng-daily-brief/config.json`

## Version History

- **2.0.0** (2026-04-17): Unified standard schema with stage fields
- **1.0.0** (2025-12-01): Initial schema with basic fields
