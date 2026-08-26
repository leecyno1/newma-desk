# Project Instructions

## Overview

Newma is a manifest-driven Chinese self-media workflow. The canonical six-stage chain is:

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

Optional paradigm learning, video style training, and video self-learning produce reusable assets but are not formal gates.

## Canonical entry points

- Orchestrator CLI: `scripts/run_mainline_stage.py`
- Orchestrator Skill: `skills/dasheng-media-sop/SKILL.md`
- Workflow contracts: `skills/dasheng-media-sop/references/`
- Module registry: `configs/workflow/module_registry.json`
- Skill registry: `skills/SKILL_ALIASES.md`
- External project registry: `configs/external/reserved_projects.json`
- Upstream patches: `configs/external/upstream_patches.json`
- Diagnostics: `scripts/workflow_doctor.py` and `scripts/verify_installation.py`

Legacy `dasheng-*` paths are runtime locators only. New user-facing names, schemas, events and artifacts use the `newma` namespace.

## Critical invariants

- Do not restore the retired seven-stage layout. Material is part of Draft; rewrite production is Transwrite.
- Do not skip stages or bypass gates with a hand-written “latest directory” path.
- Every stage writes a human-readable deliverable and a canonical Manifest JSON.
- Keep every topic isolated in its own directory.
- Draft structure is inherited by Transwrite; do not impose a fixed three-part outline.
- Paradigm Profile controls structure; Style DNA controls voice. Keep them separate.
- Reference samples are not evidence. Claims require source records or evidence-ledger entries.
- Runtime outputs must stay outside `skills/`, source configs, and external dependency checkouts.

## Video direction rules

- Treat the source article as the narration base; never say “the article mentions…” unless the content itself requires that viewpoint.
- Prefer real, topic-matched footage for openings and evidence-heavy scenes. Combine footage, titles, animated charts and motion graphics within one composition.
- News anchors and interview subjects are primary or picture-in-picture material, not low-opacity full-screen backgrounds.
- Background footage should favor locations, crowds, social situations, factories, landscapes or contextual interviews.
- Preserve complete charts and source images; never crop away labels, legends or key values.
- Avoid end-of-sentence flashes and scene-gap blank frames. Render QC must check every transition.
- Narration timing should sound conversational, with semantic pauses rather than uniform sentence gaps.

## Publish rules

- Default route: Qianfan local API; async Qianfan queue is the batch candidate; Social Auto Upload CLI is fallback.
- Store cookies, profiles, OTPs, credentials and receipts outside Git.
- Visible publish browsers must be small, never maximized, prefer the secondary display, and restore the previous foreground app when possible.
- Normal in-flow dialogs may be handled automatically. Never log OTP values or session material.
- A successful click is not a verified publish; require platform receipt, draft ID or public URL.

## External projects

Third-party source is ignored under `vendor/`. Reproduce it with:

```bash
python scripts/sync_reserved_projects.py --mode clone
python scripts/apply_upstream_patches.py --mode apply
```

Do not commit nested `.git`, `node_modules`, virtual environments, models or generated media. Do not update a dirty external checkout; export local changes as a registered patch first.

## Project map

- `core/`: shared orchestration, AI, DNA and path logic
- `scripts/`: executable builders, routers, checks and generators
- `skills/`: project-local agent skills
- `configs/`: machine-readable contracts and registries
- `templates/`: reusable video and content templates
- `tests/`: pytest contract, regression and hygiene tests
- `docs/`: onboarding, architecture, research and generated catalog
- `patches/upstreams/`: reproducible third-party compatibility patches

## Development conventions

- Python: 3.10+, type hints, `pathlib`, JSON/YAML contracts, explicit error messages.
- Prefer repository-relative paths and environment overrides; never add personal absolute paths.
- Add or update tests when changing a contract, registry, generator, gate or route.
- Generated docs must have a `--check` mode and a single machine-readable source of truth.
- Preserve unrelated working-tree changes. Never reset or overwrite user work.
- Use Conventional Commits for public changes.

## Verification

```bash
source .venv/bin/activate
python -m pytest tests -q
python scripts/verify_installation.py
python scripts/build_project_catalog.py --check
python scripts/apply_upstream_patches.py --mode check
git diff --check
```

See `docs/ONBOARDING.md` for architecture and common tasks, and `docs/PROJECT_CATALOG.md` for the complete module, Skill, dependency and reserve list.
