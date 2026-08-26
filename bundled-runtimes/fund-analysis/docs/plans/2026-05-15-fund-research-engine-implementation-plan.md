# Fund Research Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the current fund-analysis project from a fund screening and AI report app into a trustworthy fund research investment analysis engine.

**Architecture:** FastAPI becomes the authoritative research-computation backend. Next.js acts as UI and BFF. PostgreSQL stores structured entities, data lineage, metric snapshots, research workflow state, and portfolio objects. Vector search is standardized before strengthening RAG reports.

**Tech Stack:** Next.js App Router, TypeScript, FastAPI, Python, PostgreSQL, Prisma, Wind/Tushare integrations, OpenAI embeddings, Anthropic/OpenAI-compatible LLM APIs, optional Redis task queue.

---

## Phase 0: Alignment and Safety

### Task 0.1: Create Architecture Decision Record

**Files:**
- Create: `docs/plans/2026-05-15-fund-research-engine-adr.md`

**Steps:**
1. Document the decision that FastAPI is the authoritative research backend.
2. Document that Next.js API Routes should only act as BFF/proxy/page aggregation.
3. Document the temporary coexistence strategy for current duplicated APIs.
4. Document migration risks and rollback strategy.
5. Review with project owner before implementation.

**Acceptance Criteria:**
- The ADR clearly states backend responsibility boundaries.
- The ADR lists which modules stay in Next.js and which move to FastAPI.

### Task 0.2: Inventory Existing API Responsibilities

**Files:**
- Create: `docs/plans/api-inventory.md`

**Steps:**
1. List all files under `app/api`.
2. List all files under `backend/routes`.
3. Create a table with endpoint, owner, responsibility, duplicate risk, migration target.
4. Mark P0 endpoints: funds, managers, scoring, screening, reports, research reports.
5. Mark endpoints that should remain as BFF.

**Acceptance Criteria:**
- Every current API route has a target owner.
- Duplicate scoring/report/screening responsibilities are explicitly identified.

---

## Phase 1: Data Lineage Foundation

### Task 1.1: Add Data Source Snapshot Model

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `backend/repositories/data_snapshot_repo.py`
- Test: `backend/tests/data_snapshot_repo_smoke.py`

**Steps:**
1. Add `DataSourceSnapshot` model to Prisma.
2. Include fields: `id`, `source`, `dataset`, `status`, `startedAt`, `finishedAt`, `coverageStart`, `coverageEnd`, `recordCount`, `errorMessage`, `metadata`, `createdAt`.
3. Add indexes on `source`, `dataset`, `status`, and `startedAt`.
4. Create Python repository functions to create, update success, and update failure.
5. Add smoke test for snapshot lifecycle.
6. Run targeted backend test.

**Acceptance Criteria:**
- Sync tasks can create a lineage record.
- Failed tasks can persist failure reason.
- Data snapshot records can be queried by dataset.

### Task 1.2: Add Metric Snapshot Model

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `backend/repositories/metric_snapshot_repo.py`
- Test: `backend/tests/metric_snapshot_repo_smoke.py`

**Steps:**
1. Add `MetricSnapshot` model.
2. Include `targetType`, `targetId`, `asOfDate`, `metricName`, `metricValue`, `metricUnit`, `window`, `benchmarkCode`, `peerGroupKey`, `sourceSnapshotId`, `details`.
3. Add unique key on target/date/metric/window/benchmark/peer group.
4. Add upsert repository method.
5. Add query method for a target metric panel.
6. Add smoke test for upsert behavior.

**Acceptance Criteria:**
- Metric values are versioned by as-of date.
- Recalculation can update the same metric key idempotently.

### Task 1.3: Add Data Health Endpoint

**Files:**
- Create: `backend/routes/data_health.py`
- Modify: `backend/main.py`
- Test: `backend/tests/data_health_smoke.py`

**Steps:**
1. Create `/api/data-health/summary` endpoint.
2. Return latest snapshot by dataset.
3. Return failed snapshot count for recent runs.
4. Return stale dataset list based on configurable threshold.
5. Register router in `backend/main.py`.
6. Add smoke test.

**Acceptance Criteria:**
- Frontend can show whether fund, NAV, holding, report, and metric data are fresh.

---

## Phase 2: Metric Factory

### Task 2.1: Create Metric Calculation Service Skeleton

**Files:**
- Create: `backend/services/metric_factory.py`
- Create: `backend/tests/metric_factory_smoke.py`

**Steps:**
1. Define service class `MetricFactory`.
2. Add method `calculate_return_metrics(nav_series)`.
3. Add method `calculate_risk_metrics(nav_series)`.
4. Add method `calculate_relative_metrics(nav_series, benchmark_series)`.
5. Return plain dictionaries with metric names and values.
6. Add tests using small deterministic NAV arrays.

**Acceptance Criteria:**
- Return and risk metrics are computed in one backend service.
- Tests verify annualized return, volatility, max drawdown, and Sharpe for sample data.

### Task 2.2: Persist Metric Snapshots

**Files:**
- Modify: `backend/services/metric_factory.py`
- Modify: `backend/repositories/metric_snapshot_repo.py`
- Test: `backend/tests/metric_snapshot_persist_smoke.py`

**Steps:**
1. Add method `calculate_and_save_fund_metrics(fund_code, as_of_date)`.
2. Load NAV data through existing repositories or data service.
3. Calculate metrics.
4. Save each metric through `MetricSnapshotRepository`.
5. Return saved metric summary.
6. Add smoke test with mocked NAV data.

**Acceptance Criteria:**
- A fund metric panel can be recomputed and stored idempotently.

### Task 2.3: Add Metric API

**Files:**
- Create: `backend/routes/metrics.py`
- Modify: `backend/main.py`
- Test: `backend/tests/metrics_route_smoke.py`

**Steps:**
1. Create `/api/metrics/fund/{fund_code}` endpoint.
2. Return latest metric snapshot panel.
3. Create `/api/metrics/fund/{fund_code}/recalculate` endpoint.
4. Register router.
5. Add smoke tests.

**Acceptance Criteria:**
- Fund detail page can retrieve a stable metric panel from backend.

---

## Phase 3: Scoring Engine Upgrade

### Task 3.1: Define Scoring Output Contract

**Files:**
- Create: `backend/services/scoring_contract.py`
- Test: `backend/tests/scoring_contract_smoke.py`

**Steps:**
1. Define output structure with total score, grade, dimensions, positive factors, negative factors, missing data, as-of date, source snapshot ids.
2. Add helper to validate grade boundaries.
3. Add helper to serialize decimals and dates safely.
4. Add tests for grade mapping.

**Acceptance Criteria:**
- Scoring output is stable and frontend-friendly.

### Task 3.2: Refactor Backend Scoring to Use Metric Snapshots

**Files:**
- Modify: `backend/services/scoring_engine.py`
- Test: `backend/tests/scoring_engine_metrics_smoke.py`

**Steps:**
1. Load fund metric snapshots instead of recomputing all fields inline.
2. Keep current scoring weights as baseline.
3. Add missing-data penalties.
4. Add positive and negative explanation items.
5. Keep existing API compatible where possible.
6. Add tests for scoring with full and partial metric data.

**Acceptance Criteria:**
- Score result explains why it got the score.
- Missing inputs are visible instead of silently ignored.

### Task 3.3: Add Peer and Benchmark Fields to Score Details

**Files:**
- Modify: `backend/services/scoring_engine.py`
- Modify: `backend/routes/scoring.py`
- Test: `backend/tests/scoring_peer_context_smoke.py`

**Steps:**
1. Add optional benchmark code and peer group key to score request.
2. Store them in score detail output.
3. If peer metrics are unavailable, return explicit `peerDataStatus`.
4. Add smoke test.

**Acceptance Criteria:**
- Score can distinguish absolute-only result from relative-context result.

---

## Phase 4: Evidence-Based RAG Reports

### Task 4.1: Standardize Vector Store Choice

**Files:**
- Create: `docs/plans/vector-store-decision.md`
- Modify as needed: `backend/services/vector_db_service.py`
- Modify as needed: `backend/services/search_service.py`

**Steps:**
1. Inspect current vector service and search service usage.
2. Choose pgvector or Qdrant as primary store.
3. Document migration and fallback.
4. Remove ambiguous runtime branching where safe.
5. Keep backward compatibility for existing data during transition.

**Acceptance Criteria:**
- There is one primary vector store strategy.
- Search service behavior is predictable.

### Task 4.2: Add Report Chunk Model

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `backend/repositories/report_chunk_repo.py`
- Test: `backend/tests/report_chunk_repo_smoke.py`

**Steps:**
1. Add `ResearchReportChunk` model.
2. Include `reportId`, `chunkIndex`, `content`, `tokenCount`, `embeddingId`, `entities`, `metadata`.
3. Add unique key on `reportId` and `chunkIndex`.
4. Add repository methods for replace-all chunks and search metadata lookup.
5. Add smoke test.

**Acceptance Criteria:**
- Reports can be cited at chunk level.

### Task 4.3: Enforce AI Report Evidence Contract

**Files:**
- Modify: `backend/services/ai_report.py`
- Modify: `backend/routes/reports.py`
- Test: `backend/tests/ai_report_evidence_smoke.py`

**Steps:**
1. Add required evidence block to AI report prompt.
2. Require generated result to include conclusion, evidence list, risks, data gaps, follow-up triggers.
3. Persist evidence references in `dataSources` or a structured JSON field.
4. Add validation fallback when model output is incomplete.
5. Add smoke test with mocked LLM response.

**Acceptance Criteria:**
- AI report cannot be saved without data sources and evidence metadata.

---

## Phase 5: Fund Pool Workflow

### Task 5.1: Add Fund Pool Models

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `backend/repositories/fund_pool_repo.py`
- Test: `backend/tests/fund_pool_repo_smoke.py`

**Steps:**
1. Add `FundPool` model.
2. Add `PoolMember` model.
3. Support statuses: `candidate`, `watch`, `core`, `rejected`, `archived`.
4. Store reason, evidence, nextReviewDate, createdBy, updatedBy.
5. Add repository CRUD and state transition methods.
6. Add smoke tests.

**Acceptance Criteria:**
- A fund can be added to a pool with reason and evidence.
- A pool member can transition between statuses.

### Task 5.2: Add Fund Pool API

**Files:**
- Create: `backend/routes/fund_pools.py`
- Modify: `backend/main.py`
- Test: `backend/tests/fund_pools_route_smoke.py`

**Steps:**
1. Add endpoints to list pools.
2. Add endpoint to create pool.
3. Add endpoint to add fund to pool.
4. Add endpoint to update member status.
5. Add endpoint to list members by status.
6. Register router.
7. Add smoke tests.

**Acceptance Criteria:**
- Screening results can be converted into research workflow objects.

### Task 5.3: Add Frontend Fund Pool Page

**Files:**
- Create: `app/(dashboard)/pools/page.tsx`
- Modify: `app/(dashboard)/layout.tsx`
- Optional Modify: navigation component if present

**Steps:**
1. Add pool list page.
2. Show tabs for candidate, watch, core, rejected.
3. Show fund name, score, reason, next review date, latest alert count.
4. Add status transition buttons.
5. Add loading and error states.

**Acceptance Criteria:**
- User can view and manage fund research workflow from UI.

---

## Phase 6: Alerts and Review Loop

### Task 6.1: Add Alert Models

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `backend/repositories/alert_repo.py`
- Test: `backend/tests/alert_repo_smoke.py`

**Steps:**
1. Add `AlertRule` model.
2. Add `AlertEvent` model.
3. Support alert types: drawdown, score_drop, style_drift, manager_change, scale_change, report_negative_signal.
4. Add repository methods to create rules and events.
5. Add smoke tests.

**Acceptance Criteria:**
- Research workflow can persist triggered risk events.

### Task 6.2: Add Alert Scan Service

**Files:**
- Create: `backend/services/alert_scan.py`
- Test: `backend/tests/alert_scan_smoke.py`

**Steps:**
1. Load active pool members.
2. Load latest metrics and scores.
3. Evaluate simple threshold rules.
4. Create alert events for triggered conditions.
5. Avoid duplicate unresolved alerts.
6. Add smoke tests.

**Acceptance Criteria:**
- Core and watch pool funds can be monitored automatically.

---

## Phase 7: Portfolio and Backtest Foundation

### Task 7.1: Add Portfolio Models

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `backend/repositories/portfolio_repo.py`
- Test: `backend/tests/portfolio_repo_smoke.py`

**Steps:**
1. Add `Portfolio` model.
2. Add `PortfolioHolding` model.
3. Store fund id, target weight, actual weight, start date, end date.
4. Add repository CRUD.
5. Add smoke tests.

**Acceptance Criteria:**
- System can represent a model or real fund portfolio.

### Task 7.2: Add Portfolio Diagnostics Service

**Files:**
- Create: `backend/services/portfolio_diagnostics.py`
- Test: `backend/tests/portfolio_diagnostics_smoke.py`

**Steps:**
1. Calculate portfolio weighted score.
2. Calculate manager and company concentration.
3. Calculate weighted factor exposures if available.
4. Calculate correlation matrix if NAV data is available.
5. Return top risk contributors.
6. Add deterministic tests with sample holdings.

**Acceptance Criteria:**
- Portfolio page can explain major concentration and style risks.

### Task 7.3: Add Strategy Backtest Skeleton

**Files:**
- Modify: `prisma/schema.prisma`
- Create: `backend/services/backtest_engine.py`
- Create: `backend/routes/backtests.py`
- Test: `backend/tests/backtest_engine_smoke.py`

**Steps:**
1. Add `BacktestRun` model.
2. Implement simple screening-template backtest skeleton.
3. Store params, date range, result summary, createdAt.
4. Add endpoint to start and fetch backtest result.
5. Add smoke test with mocked screening results.

**Acceptance Criteria:**
- Screening templates can become testable strategies.

---

## Validation Strategy

Run tests progressively:

1. Repository smoke tests after each schema-facing change.
2. Service-level deterministic tests for metrics, scoring, alerts, portfolio diagnostics.
3. Route smoke tests for new FastAPI endpoints.
4. Frontend typecheck after UI changes.
5. Full backend smoke test suite before merging major phases.

Suggested commands:

```bash
cd backend
pytest tests/<target_test>.py -q
```

```bash
npm run lint
npm run build
```

## Rollout Strategy

1. Add new models without removing existing behavior.
2. Populate new snapshots in parallel with old API behavior.
3. Switch read paths once snapshots are stable.
4. Keep old fields for compatibility until frontend migration is complete.
5. Remove duplicate logic only after route inventory confirms no active consumers.

## Non-Goals for Initial Implementation

- Do not build a full trading system.
- Do not automate buy/sell decisions without human approval.
- Do not add broker integration.
- Do not over-optimize factor models before data quality is stable.
- Do not rewrite the full frontend before backend contracts stabilize.
