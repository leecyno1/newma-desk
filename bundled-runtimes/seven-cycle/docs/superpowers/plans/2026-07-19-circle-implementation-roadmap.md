# Circle Implementation Roadmap

> **For agentic workers:** Each phase has its own detailed implementation plan. Complete phases in order because every later phase consumes governed products from earlier phases.

**Goal:** Deliver the approved seven-cycle research and cross-asset research system as independently testable vertical slices.

**Architecture:** Keep Python research computation and immutable product publication in `src/seven_cycle_platform`. Add a new React/TypeScript frontend after the research contracts are corrected. Every frontend view reads versioned API products and never estimates cycles in the browser.

**Tech Stack:** Python 3.12, Pandas, NumPy, SciPy, Statsmodels, scikit-learn, PyArrow, DuckDB, FastAPI, React, TypeScript, Vite, ECharts, React Three Fiber, Vitest, Playwright.

---

## Phase A: Research Foundation and Publication Gates

Detailed plan: `docs/superpowers/plans/2026-07-19-circle-phase-a-research-foundation.md`

Delivers:

- corrected C1–C7 definitions and fixed priors;
- data identity and freshness contracts;
- cycle evidence and calibration products;
- formal, limited, and blocked publication gates;
- governed import of the approved C1/C4/C5 research prototypes;
- audit API endpoints.

Acceptance: the API can explain why C4 historical state is publishable, why C4 realtime is pseudo-realtime, why C4 forecast is stale, and why C2/C3/C5/C7 are blocked.

## Phase B: Homepage Market Surface and Seven-Cycle 2D Views

Planned file: `docs/superpowers/plans/2026-07-19-circle-phase-b-visual-research-workbench.md`

Delivers:

- new `web/` React application;
- homepage X=time, Y=seven-cycle reconstructed change, Z=track surface;
- default ten tracks and expandable full track registry;
- C1–C7 evidence cards and historical 2D phase views;
- 3D-to-2D linked interaction;
- explicit original-value, transformed-value and provenance tooltips.

Acceptance: the browser renders real C4 history, C1 long-history context, blocked weak cycles, correct axes, clickable tracks and no fixed sine-wave placeholders.

## Phase C: Realtime State and Forecast Extension

Planned file: `docs/superpowers/plans/2026-07-19-circle-phase-c-realtime-forecast.md`

Delivers:

- C4 historical-final versus one-sided pseudo-realtime comparison;
- vintage-aware revision statistics;
- candidate model registry;
- rolling 3/6/12-month forecast evaluation;
- qualified dashed extensions and uncertainty bands;
- stale-data publication blocking;
- optional TimesFM challenger adapter without mandatory dependency.

Acceptance: only qualified and fresh forecasts produce dashed lines; TimesFM absence is visible and never fabricated.

## Phase D: Asset Statistics, Attribution and Risk-Return Forecasts

Planned file: `docs/superpowers/plans/2026-07-19-circle-phase-d-assets.md`

Delivers:

- governed 94-asset registry and 91 observed-asset release;
- C4 four-phase return/risk statistics;
- HAC association contribution and expanding OOS R²;
- 2019 food-and-beverage falsification example;
- explicit unavailable handling for gold, copper and crude oil until sources land;
- conditional 3/6/12-month asset risk-return distributions;
- joint C1–C7 attribution only after additional cycles pass evidence gates.

Acceptance: asset pages never infer mapping from industry names and never force residual returns into cycles.

## Phase E: Scheduling, Version Archive and End-to-End Release

Planned file: `docs/superpowers/plans/2026-07-19-circle-phase-e-operations.md`

Delivers:

- daily, monthly, quarterly and annual schedules;
- immutable run manifests and atomic latest pointers;
- data freshness monitoring and degradation rules;
- research version archive and prior design links;
- end-to-end browser and API acceptance suite;
- operating runbook for new data, calibration changes and model rollback.

Acceptance: a scheduled run either publishes a fully auditable version or leaves the prior version untouched with a visible failure reason.

## Dependency Order

```text
Phase A → Phase B
Phase A → Phase C
Phase A + Phase C → Phase D
Phase A + Phase B + Phase C + Phase D → Phase E
```

## Repository Rules

- `main` remains releasable;
- each task uses TDD and a focused commit;
- generated data, local databases, secrets and large source documents remain ignored;
- both `github` and `gitee` remotes receive every completed phase;
- old `cycle_forecast_system_frontend/` remains local reference only and is not reused as the new frontend.
