# Feishu Stage Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the dasheng workflow so stages 1-5 produce a unified Feishu sync contract covering folders, docs, messages, uploads, and rewrite refill actions.

**Architecture:** Keep the existing runtime entrypoints, but replace the docs-only bridge contract with a generic action plan built from `stage_review_contract.json`, local stage artifacts, and manifest metadata. Persist prepare/apply/finalize JSON artifacts per run so manual or automated Feishu executors can consume the same contract.

**Tech Stack:** Node.js runtime scripts, JSON manifest contracts, local markdown artifacts, Feishu config loader.

---

### Task 1: Expand token/config helpers

**Files:**
- Modify: `${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/doc-registry.js`
- Modify: `${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/feishu-plan.js`

**Step 1:** Add folder token extraction and stage review config loading.
**Step 2:** Add file discovery helpers that resolve stage markdown/report/material asset paths from both runtime-data and `产物/` outputs.
**Step 3:** Return normalized folder/doc refs for downstream bridge steps.

### Task 2: Replace docs-only plan with action model

**Files:**
- Modify: `${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/feishu-plan.js`

**Step 1:** Build date folder + stage folder plan from the Feishu config.
**Step 2:** Build stage docs plan for intake/brief/draft/rewrite/material with local file bindings.
**Step 3:** Build message, upload, and rewrite-refill actions.
**Step 4:** Emit a single `actions` array plus grouped summaries for prepare/finalize consumers.

### Task 3: Update prepare/apply/finalize scripts

**Files:**
- Modify: `${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/feishu-bridge.js`
- Modify: `${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/feishu-create-run.js`
- Modify: `${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/feishu-exec.js`
- Modify: `${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/runner.js`

**Step 1:** Persist pending actions instead of pending docs.
**Step 2:** Accept externally created resource maps and apply them back onto action requests.
**Step 3:** Finalize docs into manifests/object refs while retaining message/upload/refill execution status.
**Step 4:** Make the runner expose the richer Feishu bridge contract.

### Task 4: Verify with representative runs

**Files:**
- Use run fixtures under `${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime-data/runs`
- Use outputs under `~/Desktop/自媒体创作`

**Step 1:** Run `node feishu-plan.js` against a material-only run and a full content run.
**Step 2:** Run `node feishu-exec.js --prepare` and bridge/materialize helpers.
**Step 3:** Run syntax checks with `node --check` on touched runtime scripts.
