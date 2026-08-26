# Sprint A Fund Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver Sprint A of the fund selection evaluation system by adding fund-pool workflow, alert center, and page-level data trust panels.

**Architecture:** Build on the existing FastAPI authority path, PostgreSQL tables, DataSourceSnapshot/MetricSnapshot, scoring contract, and market browser. Keep FastAPI as the system of record for workflow state and monitoring logic. Use Next.js pages and API as presentation/BFF only where needed.

**Tech Stack:** Next.js App Router, TypeScript, FastAPI, Python, PostgreSQL, Prisma, existing repository/service pattern, existing metrics/scoring foundation.

---

## Scope of Sprint A

Sprint A covers three feature groups only:

1. Fund pool workflow
2. Alert center
3. Page-level trust and data-quality display

It intentionally does **not** include:

- fund comparison workspace
- peer percentile engine
- Research Insight
- portfolio diagnostics
- backtesting

---

## Task 0: Stabilize Preconditions

### Task 0.1: Fix local database assumptions for new repository work

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/repositories/nav_repo.py`
- Test: `backend/tests/metric_snapshot_repo_smoke.py`
- Test: `backend/tests/report_chunk_repo_smoke.py`

**Steps:**
1. Review current `fund_nav` table definition in `backend/database.py`.
2. Compare it with `backend/repositories/nav_repo.py` fields.
3. Resolve the schema/repository mismatch so metric persistence can rely on NAV reads.
4. Re-run repository smoke tests in a DB-enabled environment.

**Acceptance Criteria:**
- `NavRepo.get_nav_series()` works against the actual table schema.
- Metric-related repository tests no longer fail for schema mismatch.

---

## Task Group A1: Fund Pool Workflow

### Task 1.1: Add FundPool and PoolMember models

**Files:**
- Modify: `prisma/schema.prisma`
- Modify: `backend/database.py`
- Test: `backend/tests/fund_pool_repo_smoke.py`

**Steps:**
1. Add `FundPool` model with fields: `id`, `name`, `description`, `createdBy`, `isDefault`, `createdAt`, `updatedAt`.
2. Add `PoolMember` model with fields: `id`, `poolId`, `fundId`, `status`, `reason`, `latestConclusion`, `evidence`, `riskNotes`, `nextReviewDate`, `createdBy`, `updatedBy`, `createdAt`, `updatedAt`.
3. Add indexes on `poolId`, `fundId`, `status`, and `nextReviewDate`.
4. Add SQL table creation and indexes in `backend/database.py`.
5. Write a smoke test that proves create/list/update lifecycle.

**Acceptance Criteria:**
- Pool and member records can be created and queried.
- Member status is stored as workflow state.

### Task 1.2: Implement fund pool repository

**Files:**
- Create: `backend/repositories/fund_pool_repo.py`
- Modify: `backend/repositories/__init__.py`
- Test: `backend/tests/fund_pool_repo_smoke.py`

**Steps:**
1. Implement repository methods:
   - `create_pool(...)`
   - `list_pools()`
   - `add_fund_to_pool(...)`
   - `update_member_status(...)`
   - `list_members(pool_id, status=None)`
2. Prevent duplicate active member rows for the same fund in the same pool.
3. Return frontend-safe dictionaries.
4. Verify test red/green cycle.

**Acceptance Criteria:**
- Pool members can move through `candidate`, `watch`, `core`, `rejected`.
- Re-adding the same fund to the same pool behaves predictably.

### Task 1.3: Add fund pool API

**Files:**
- Create: `backend/routes/fund_pools.py`
- Modify: `backend/main.py`
- Test: `backend/tests/fund_pools_route_import_smoke.py`

**Steps:**
1. Add route `GET /api/fund-pools`.
2. Add route `POST /api/fund-pools`.
3. Add route `GET /api/fund-pools/{pool_id}/members`.
4. Add route `POST /api/fund-pools/{pool_id}/members`.
5. Add route `PATCH /api/fund-pools/members/{member_id}`.
6. Register router in `backend/main.py`.
7. Add import/contract smoke test.

**Acceptance Criteria:**
- API contract is stable and importable.
- Pool CRUD and member transitions are exposed through FastAPI.

### Task 1.4: Add fund pool page

**Files:**
- Create: `app/(dashboard)/pools/page.tsx`
- Modify: `app/(dashboard)/layout.tsx`

**Steps:**
1. Create page for pool list and member tabs.
2. Show tabs for `candidate`, `watch`, `core`, `rejected`.
3. Render fields: fund name, score, reason, latest conclusion, next review date.
4. Add basic status action buttons.
5. Add loading and empty states.

**Acceptance Criteria:**
- User can open `/pools` and browse workflow states.
- Workflow feels like a real candidate-management page, not raw JSON output.

### Task 1.5: Add “加入候选池” entry from market browser

**Files:**
- Modify: `app/(dashboard)/market/page.tsx`
- Optional Modify: `app/api/funds/route.ts` only if needed for helper behavior

**Steps:**
1. Add action button per row: `加入候选池`.
2. Add a lightweight dialog or inline form for reason input.
3. Submit to fund-pool API.
4. Show success/failure state.

**Acceptance Criteria:**
- User can add a market-browser fund into candidate pool without leaving the page.

---

## Task Group A2: Alert Center

### Task 2.1: Add AlertRule and AlertEvent models

**Files:**
- Modify: `prisma/schema.prisma`
- Modify: `backend/database.py`
- Test: `backend/tests/alert_repo_smoke.py`

**Steps:**
1. Add `AlertRule` model with fields: `id`, `name`, `ruleType`, `scopeType`, `scopeId`, `threshold`, `enabled`, `createdBy`, `createdAt`, `updatedAt`.
2. Add `AlertEvent` model with fields: `id`, `ruleId`, `fundId`, `poolMemberId`, `eventType`, `severity`, `title`, `message`, `status`, `triggeredAt`, `resolvedAt`, `details`, `createdAt`.
3. Add SQL table definitions and indexes.
4. Write lifecycle smoke test.

**Acceptance Criteria:**
- Rule and event rows persist and can be queried by state.

### Task 2.2: Implement alert repository

**Files:**
- Create: `backend/repositories/alert_repo.py`
- Modify: `backend/repositories/__init__.py`
- Test: `backend/tests/alert_repo_smoke.py`

**Steps:**
1. Implement methods:
   - `create_rule(...)`
   - `list_rules(...)`
   - `create_event(...)`
   - `list_events(status=None, severity=None)`
   - `update_event_status(...)`
2. Add dedup logic for unresolved repeated events where practical.
3. Keep output frontend-safe.

**Acceptance Criteria:**
- Event status can transition through `new`, `acknowledged`, `ignored`, `resolved`.

### Task 2.3: Implement basic alert scan service

**Files:**
- Create: `backend/services/alert_scan.py`
- Test: `backend/tests/alert_scan_smoke.py`

**Steps:**
1. Load active pool members.
2. Load latest metrics and scoring for each member.
3. Evaluate first rule set:
   - drawdown threshold
   - score drop threshold
   - missing-data health issue
4. Persist alert events.
5. Return summary counts.

**Acceptance Criteria:**
- Running the service can produce alert events from sample inputs.
- The logic is deterministic in tests.

### Task 2.4: Add alert API

**Files:**
- Create: `backend/routes/alerts.py`
- Modify: `backend/main.py`
- Test: `backend/tests/alerts_route_import_smoke.py`

**Steps:**
1. Add `GET /api/alerts`.
2. Add `POST /api/alerts/rules`.
3. Add `PATCH /api/alerts/events/{event_id}`.
4. Add `POST /api/alerts/scan`.
5. Register router.

**Acceptance Criteria:**
- Alert center can list, create, and update alert state.

### Task 2.5: Add alert center page

**Files:**
- Create: `app/(dashboard)/alerts/page.tsx`
- Modify: `app/(dashboard)/layout.tsx`

**Steps:**
1. Build alert table with filters for status and severity.
2. Show event title, fund, rule, triggered time, status.
3. Add actions for acknowledge/ignore/resolve.
4. Add empty, loading, and error states.

**Acceptance Criteria:**
- User can manage alert workflow from the UI.

---

## Task Group A3: Page-Level Trust and Data Quality

### Task 3.1: Add trust contract helper

**Files:**
- Create: `backend/services/trust_contract.py`
- Test: `backend/tests/trust_contract_smoke.py`

**Steps:**
1. Define helper that formats trust information:
   - `data_as_of`
   - `synced_at`
   - `metric_as_of`
   - `scoring_time`
   - `missing_data`
   - `source_snapshot_ids`
   - `data_quality_status`
2. Make output safe for frontend rendering.
3. Add small deterministic test.

**Acceptance Criteria:**
- Trust panel payload has a stable shape.

### Task 3.2: Extend scoring route with trust metadata

**Files:**
- Modify: `backend/routes/scoring.py`
- Modify: `backend/services/scoring_engine.py`
- Test: `backend/tests/scoring_contract_smoke.py`

**Steps:**
1. Add trust metadata to `GET /api/scoring/fund/{wind_code}`.
2. Surface `source_snapshot_ids`, `as_of_date`, `missing_data`, and `data_quality` from current scoring output.
3. Keep legacy fallback behavior intact.

**Acceptance Criteria:**
- Scoring response includes trust-facing metadata.

### Task 3.3: Extend fund detail response with data recency metadata

**Files:**
- Modify: `app/api/funds/[id]/route.ts`
- Optional Modify: `backend/routes/funds.py` if a FastAPI detail endpoint becomes the source

**Steps:**
1. Add `updatedAt`, `navDate`, and relevant metric/scoring timestamps to fund detail payload.
2. Add a lightweight trust section if practical.
3. Keep existing detail rendering compatible.

**Acceptance Criteria:**
- Fund detail page can show when core data was last updated.

### Task 3.4: Add trust panel to fund detail page

**Files:**
- Modify: `app/(dashboard)/funds/[id]/page.tsx`
- Optional Create: `components/TrustPanel.tsx`

**Steps:**
1. Add a “数据可信度” card.
2. Show data-as-of, score-as-of, missing-data count, and source snapshot count.
3. Display score positives and negatives if available.

**Acceptance Criteria:**
- Trust information is visible without reading raw JSON.

### Task 3.5: Add trust cues to AI report area

**Files:**
- Modify: `app/(dashboard)/analysis/[id]/page.tsx`
- Optional Modify: related analysis detail components

**Steps:**
1. Reserve space for evidence count and report source count.
2. If current data is unavailable, show placeholder labels.
3. Keep design aligned with future RAG evidence rollout.

**Acceptance Criteria:**
- Analysis pages visually prepare for evidence-based reporting.

---

## Validation Plan

### Offline validations

Run after each task where possible:

```bash
.venv/bin/python -m py_compile backend/**/*.py
```

Run import/contract smoke tests:

```bash
.venv/bin/python backend/tests/fund_pools_route_import_smoke.py
.venv/bin/python backend/tests/alerts_route_import_smoke.py
.venv/bin/python backend/tests/trust_contract_smoke.py
```

### DB-enabled validations

When PostgreSQL is running:

```bash
DATABASE_URL=postgresql://postgres:fundanalysis2024@localhost:5432/fund_analysis .venv/bin/python backend/tests/fund_pool_repo_smoke.py
DATABASE_URL=postgresql://postgres:fundanalysis2024@localhost:5432/fund_analysis .venv/bin/python backend/tests/alert_repo_smoke.py
DATABASE_URL=postgresql://postgres:fundanalysis2024@localhost:5432/fund_analysis .venv/bin/python backend/tests/alert_scan_smoke.py
```

### Frontend validations

Run targeted checks where possible. Note that the repo currently has unrelated `tsc` issues in existing Next route typings and in the separate `frontend/` subtree, so prefer page/file-level checks first.

---

## Delivery Criteria for Sprint A

Sprint A is complete when all of the following are true:

1. User can add a fund from `/market` into a candidate pool.
2. User can browse candidate/watch/core/rejected states in `/pools`.
3. Alert events can be generated and managed in `/alerts`.
4. Fund detail and scoring responses expose trust-facing metadata.
5. Fund detail page visibly shows trust information.
6. The new backend modules have deterministic smoke coverage.
7. DB-enabled repository tests pass in a running local PostgreSQL environment.
