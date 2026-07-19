# vibe-visualization MVP Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the approved vibe-visualization MVP as four independently testable plans and finish with matching GitHub and Gitee repositories.

**Architecture:** Build contracts and the registry-driven HTML Shell first, then add the Agent/Data Gateway, then the structured market module, and only then connect upstream projects and publish. Each phase has a hard completion gate so later layers never compensate for an unstable lower layer.

**Tech Stack:** React 19, TypeScript, Vite, Zod, ECharts, FastAPI, Pydantic, SQLite, SSE, Nginx, Docker Compose, Vitest, Pytest, Playwright

---

## Execution Order

- [ ] **Phase 1: Foundation** — Execute every task in `docs/superpowers/plans/2026-07-19-vibe-visualization-foundation.md` and satisfy its completion gate.
- [ ] **Phase 2: Agent and Data Gateway** — Execute every task in `docs/superpowers/plans/2026-07-19-vibe-visualization-gateway.md` and satisfy its completion gate.
- [ ] **Phase 3: Structured Renderer and Market Module** — Execute every task in `docs/superpowers/plans/2026-07-19-vibe-visualization-market-module.md` and satisfy its completion gate.
- [ ] **Phase 4: Upstream Integrations and Release** — Execute every task in `docs/superpowers/plans/2026-07-19-vibe-visualization-integrations-release.md` and satisfy its release gate.

Do not reorder the phases. The later plans reference types, APIs, and package names defined by earlier plans.

## Spec Coverage

| Approved requirement | Implementation location |
|---|---|
| Independent repository and tooling | Foundation Task 1; Release Task 8 |
| Dynamic sidebar and registry | Foundation Tasks 4–6 |
| Standalone and embedded HTML modules | Foundation Tasks 6–8; Market Task 6 |
| Draft, preview, publish, disable, rollback | Foundation Tasks 4–6 |
| Import, export, and private sharing | Foundation Task 9 |
| Versioned Manifest and events | Foundation Task 2 |
| Sandbox and origin validation | Foundation Tasks 7–8; Release Task 7 |
| Agent-neutral Gateway | Gateway Tasks 1–5 |
| Data Service Registry | Gateway Task 6 |
| Module actions and permissions | Gateway Task 7 |
| Module browser SDK | Foundation Task 7; Gateway Task 8 |
| Structured View Schema and Renderer | Market Tasks 1–2 |
| Persistent snapshots and schedules | Market Tasks 3 and 5 |
| Daily market demonstration module | Market Tasks 4, 6–8 |
| Vibe-Research URL modules | Release Task 2 |
| Vibe-Trading URL modules | Release Task 3 |
| Failure isolation and health | Release Tasks 4 and 7 |
| Local and production deployment | Release Task 5 |
| CI and upstream compatibility checks | Release Task 6 |
| GitHub and Gitee publication | Release Task 8 |

## Final Verification

After all four phase gates pass, run exactly:

```bash
scripts/verify.sh
git status --short
git log --oneline --decorate -12
git ls-remote github refs/heads/main
git ls-remote gitee refs/heads/main
```

Expected:

- `scripts/verify.sh` exits 0.
- `git status --short` prints nothing.
- The latest commits show small, phase-aligned changes.
- GitHub and Gitee report the same `main` commit SHA.

