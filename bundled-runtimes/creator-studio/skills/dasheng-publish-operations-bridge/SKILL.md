---
name: dasheng-publish-operations-bridge
description: Use when a Newma Publish channel pack needs account-launch, cold-start, matrix-role, cadence, hook, keyword, series, CTA, or post-publish metric advice before platform execution. Normalizes the external agent-skills-launch-pack into a small machine-readable Publish advisory without uploading or publishing.
---

# Newma Publish Operations Bridge

## Role

This is the account-operations advisory layer inside `publish`.

It consumes `account_operations_request.json`, consults the matching external
`agent-skills-launch-pack` skill, and writes normalized advice beside the
channel pack. It never logs in, uploads media, edits cookies, schedules posts,
or clicks a final publish button.

The publish executor remains responsible for platform delivery. This bridge
only improves the decision around positioning, hook, keywords, series,
cadence, interaction, experiment design, and post-publish review.

## External Upstream

- Repository: `https://github.com/chenjin-cmd/agent-skills-launch-pack_`
- Root env: `AGENT_SKILLS_LAUNCH_PACK_ROOT`
- Default root: `${AGENT_SKILLS_LAUNCH_PACK_ROOT:-vendor/reserved/publish/agent-skills-launch-pack}`
- Registry: `configs/publish/upstream_repos.json`

Do not vendor the upstream skills into this repository or install them into
global Codex skills. Read them from the external checkout so upstream updates
remain easy to inspect and sync.

Platform mapping:

| Publish channel | Upstream skill |
| --- | --- |
| `wechat_article` | `wechat-account-launch-expert` |
| `xiaohongshu_video` | `xiaohongshu-account-launch-expert` |
| `douyin_video` | `douyin-account-launch-expert` |
| `x_post` | `x-twitter-cold-start-expert` |
| future `wechat_channels_video` | `channels-account-launch-expert` |

## Input

Required:

- `account_operations_request.json`
- The referenced `channel_pack.json`
- The referenced upstream `SKILL.md`

Useful account context:

- `account_stage`: `new`, `cold_start`, `active`, `low_performance`,
  `dormant`, `risk_review`, or `matrix_experiment`
- `account_goal`
- `account_slot`
- `matrix_role`
- `target_audience`
- `conversion_goal`
- `weekly_capacity`
- prior post metrics or review notes

Missing context must not cause a long interview. Produce a conservative
hypothesis-based advisory and list only the missing fields that materially
change the recommendation.

## Workflow

1. Validate that the request and channel pack belong to the same topic and
   channel.
2. Resolve the external root from `AGENT_SKILLS_LAUNCH_PACK_ROOT`, falling back
   to `${AGENT_SKILLS_LAUNCH_PACK_ROOT:-vendor/reserved/publish/agent-skills-launch-pack}`.
3. Read only the mapped upstream `SKILL.md`. Read its `references/` playbook
   only when the request asks for a full launch plan, account audit, content
   calendar, or matrix experiment.
4. Treat upstream platform claims as advisory. Current platform rules, API
   behavior, AI labels, advertising, finance/investment wording, and account
   penalties require separate official-rule verification.
5. Keep the approved article/video facts and core thesis frozen. Recommend
   metadata, packaging, cadence, series placement, interaction, and experiment
   changes; do not silently rewrite or regenerate production assets.
6. Write both normalized JSON and a short human review page in the channel pack
   directory.

## Output Contract

Write:

- `account_operations_advice.json`
- `account_operations_advice.md`

Minimum JSON shape:

```json
{
  "schema_version": "dasheng.publish.operations_advice.v1",
  "status": "completed",
  "topic_id": "topic-id",
  "channel": "wechat_article",
  "platform": "wechat",
  "account_stage": "cold_start",
  "upstream_skill": "wechat-account-launch-expert",
  "recommendations": {
    "positioning_check": [],
    "title_or_hook": [],
    "keywords_or_tags": [],
    "series_or_collection": [],
    "cadence": [],
    "interaction_or_cta": [],
    "risk_checks": []
  },
  "experiment": {
    "hypothesis": "",
    "success_signals": [],
    "stop_or_adjust_conditions": []
  },
  "post_publish_metrics": [],
  "missing_context": [],
  "source": {
    "repo": "https://github.com/chenjin-cmd/agent-skills-launch-pack_",
    "skill_file": "",
    "local_head": ""
  }
}
```

`recommendations` must be a JSON object. `status`, `channel`, `platform`, and
`upstream_skill` must match the request. A malformed or mismatched advice file
does not satisfy a required operations review.

## Publish Gate

- `new`, `cold_start`, `low_performance`, `dormant`, `risk_review`, and
  `matrix_experiment` default to `required_before_execution`.
- `active` and `unspecified` default to non-blocking advisory mode.
- The publish pack may still be built while review is pending, but guarded
  execution must remain blocked until a valid advice JSON exists and the pack
  is rebuilt.

## Safety

- Never promise followers, views, revenue, or viral results.
- Never recommend fake engagement, bulk account abuse, hidden contact details,
  review bypass, plagiarism, or copyright evasion.
- For finance and investment content, add a platform-expression risk check and
  preserve the article/video disclaimer.
- Keep all runtime request/advice files under
  `~/Desktop/自媒体创作/<run_id>/05_发布/...`; never write them into
  `skills/` or the project root.

## Upstream Check

Before changing this bridge against a newer upstream version:

```bash
python3 scripts/check_publish_upstreams.py \
  --name agent-skills-launch-pack \
  --remote
```

Review the upstream diff and rerun its validator/tests before changing the
normalized output contract.
