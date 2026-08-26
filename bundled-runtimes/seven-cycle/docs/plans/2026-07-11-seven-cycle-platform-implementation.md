# Seven-Cycle Past–Present–Future Platform Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reproducible seven-cycle research platform that reconstructs historical vintages, attributes realized asset returns through transmission channels, maps current asset risk/return distributions, forecasts future cycle/channel/asset paths, and exposes traceable 2D/3D research views.

**Architecture:** Create a new Python 3.12 research package under `src/seven_cycle_platform/` and keep the verified root research scripts as compatibility wrappers and regression baselines. Every run writes immutable Parquet products plus a manifest, verifies contracts, builds a DuckDB catalog, and only then atomically advances `latest.json`; a read-only FastAPI service and the existing React shell consume those products without recalculating research logic.

**Tech Stack:** Python 3.12, NumPy, pandas, SciPy, statsmodels, scikit-learn, Matplotlib, PyArrow, DuckDB, Pydantic v2, FastAPI, Uvicorn, PyYAML, Tushare, AkShare, pytest, Ruff, React 19, TypeScript, ECharts, ECharts-GL, React Testing Library, Playwright.

---

## Execution Preconditions

1. Read the approved specification at `docs/superpowers/specs/2026-07-11-seven-cycle-platform-design.md` before implementation.
2. The workspace root is currently **not** a Git repository. Do not initialize or restructure Git automatically. Before executing this plan, the user must either provide a top-level worktree/repository or explicitly accept file-based checkpoints in `progress.md`. The nested frontend repository already has uncommitted `axios` and `echarts` dependency changes; preserve them.
3. Rotate the Tushare token previously exposed in chat. Never copy it into a file. All code must read `TUSHARE_TOKEN` from the environment and redact secret-like values from logs and manifests.
4. Preserve these regression baselines until their replacement gates pass:
   - `scripts/cycle_realtime_core.py`
   - `scripts/build_realtime_cycle_signals.py`
   - `scripts/cycle_robustness_core.py`
   - `scripts/discover_cycle_periods_robust.py`
   - `scripts/backtest_cycle_style_rotation_v3.py`
   - `scripts/verify_cycle_investment_application.py`
5. Use `products/seven_cycle/runs/<run_id>/` for immutable products, `products/seven_cycle/staging/<run_id>/` for unpublished runs, and `products/seven_cycle/latest.json` as the only mutable pointer.
6. In an approved Git worktree, make the commit shown at the end of each task. Without a top-level Git repository, record the same message as a checkpoint in `progress.md` instead.

## Milestone Gates

| Milestone | Gate before advancing |
|---|---|
| M1 Foundation | Registries validate; secrets scan passes; failed staging run cannot change `latest.json` |
| M2 Cycles | C1–C7 products exist; arbitrary cutoff rebuild is exact; dynamic-period fallback and drift limits are tested |
| M3 Attribution | 2019 Baijiu absolute/excess attribution conserves contributions and includes intervals, residual, proxy/vintage status |
| M4 Current Mapping | Every published mapping has calibrated distributions, transferability status, and a bounded weight range or an explicit unavailable reason |
| M5 Forecasting | Champion is walk-forward calibrated; Challenger cannot promote without improving all approved gates |
| M6 Product | API values trace to run/vintage/model/config; Past/Present/Future and 3D/2D synchronization pass E2E |
| M7 Production | Expanded assets pass quality gates; schedules are idempotent; failed runs preserve the prior live release |

## M1 — Foundation

### Task 1: Scaffold the research package and test environment

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/seven_cycle_platform/__init__.py`
- Create: `src/seven_cycle_platform/types.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_package_smoke.py`

**Steps:**
1. Create `pyproject.toml` with Python `>=3.12`, runtime dependencies listed in the plan header (including `matplotlib`, `tushare`, and `akshare` for legacy/core data compatibility), and a `dev` group containing `pytest`, `pytest-cov`, `httpx`, and `ruff`.
2. Write a failing smoke test:

   ```python
   from seven_cycle_platform.types import ReleaseStatus

   def test_release_status_contract() -> None:
       assert ReleaseStatus.LIVE.value == "live"
       assert ReleaseStatus.BLOCKED.value == "blocked"
   ```

3. Run `uv sync --group dev` and then `uv run pytest tests/unit/test_package_smoke.py -v`; expect failure because `ReleaseStatus` is absent.
4. Implement `ReleaseStatus`, `MappingStatus`, `EvidenceLevel`, and `VintageKind` as string enums in `src/seven_cycle_platform/types.py`.
5. Run `uv run pytest tests/unit/test_package_smoke.py -v` and `uv run ruff check src tests`; expect both to pass.
6. Commit/checkpoint: `chore: scaffold seven-cycle research package`.

### Task 2: Define validated cycle, indicator, channel, and asset registries

**Files:**
- Create: `config/seven_cycle/cycles.yaml`
- Create: `config/seven_cycle/indicators.yaml`
- Create: `config/seven_cycle/channels.yaml`
- Create: `config/seven_cycle/assets.yaml`
- Create: `src/seven_cycle_platform/registry/models.py`
- Create: `src/seven_cycle_platform/registry/loader.py`
- Create: `tests/unit/registry/test_registry_loader.py`

**Steps:**
1. Write tests asserting that the registry loads exactly `C1`–`C7`, cycle search bands equal the approved ranges, asset proxy chains have effective dates, and channel definitions contain eligible indicator concepts but no asset whitelist.
2. Run `uv run pytest tests/unit/registry/test_registry_loader.py -v`; expect import/validation failures.
3. Implement Pydantic models with `extra="forbid"` and these minimum fields:

   ```python
   class CycleSpec(BaseModel):
       cycle_id: Literal["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
       name_zh: str
       economic_role: str
       frequency: Literal["A", "M"]
       search_min: float
       search_max: float
       initial_center: float | None
       max_quarterly_drift: float
       horizons: list[int]
       default_usage: MappingStatus
   ```

4. Seed `cycles.yaml` from the approved C1–C7 table; seed `channels.yaml` with growth, inflation, real-rate, liquidity/credit, earnings, risk-premium/crowding, FX/external-demand, and supply/inventory/geopolitics.
5. Seed the core asset tier with HS300, CSI500, CSI1000, Baijiu, China government bonds, gold, copper, crude oil, USD/CNY, S&P 500, and cash. Set Baijiu preferred source to index `399997.SZ`; set CITIC Food & Beverage `CI005019.CI` as an explicit dated proxy, never as an invisible splice.
6. Run the registry tests and `uv run ruff check src tests`; expect pass.
7. Commit/checkpoint: `feat: add governed seven-cycle registries`.

### Task 3: Add the vintage observation contract and legacy-panel adapters

**Files:**
- Create: `src/seven_cycle_platform/data/observations.py`
- Create: `src/seven_cycle_platform/data/legacy_adapters.py`
- Create: `src/seven_cycle_platform/contracts/arrow.py`
- Create: `tests/unit/data/test_observation_contract.py`
- Create: `tests/unit/data/test_legacy_adapters.py`

**Steps:**
1. Write tests for the required fields `entity_id`, `observation_date`, `release_date`, `vintage_date`, `value`, `unit`, `source`, `retrieval_time`, `revision_number`, and `quality_status`.
2. Add a test that converts `data/research_input_monthly_macro.parquet` to observations and requires `vintage_kind="pseudo_vintage"` when no real release history exists.
3. Run the tests and verify they fail.
4. Implement an immutable `Observation` Pydantic model plus Arrow schemas for raw observations and quality findings.
5. Implement adapters for the current monthly/annual research panels. They must accept an explicit release-rule registry, never infer strict historical availability silently, and emit a caveat when using pseudo vintages.
6. Run `uv run pytest tests/unit/data -v`; expect pass.
7. Commit/checkpoint: `feat: add vintage observation contracts`.

### Task 4: Implement run manifests and atomic publication

**Files:**
- Create: `src/seven_cycle_platform/storage/run_context.py`
- Create: `src/seven_cycle_platform/storage/manifest.py`
- Create: `src/seven_cycle_platform/storage/publisher.py`
- Create: `tests/unit/storage/test_run_context.py`
- Create: `tests/unit/storage/test_atomic_publisher.py`

**Steps:**
1. Write tests requiring the same inputs/config/model to produce the same `config_hash` and a unique `run_id` that includes `as_of` plus the hash.
2. Write a failure test that creates an existing `latest.json`, raises during staging validation, and asserts the pointer is unchanged.
3. Run the tests; expect failures.
4. Implement `RunContext` with `run_id`, `as_of`, `data_vintage`, `model_version`, `config_hash`, `created_at`, input checksums, quality summary, and product checksums.
5. Implement publication as: write staging directory → fsync files → verify manifest and contracts → atomic directory rename → atomic replacement of `latest.json`.
6. Run `uv run pytest tests/unit/storage -v`; expect pass.
7. Commit/checkpoint: `feat: add immutable run publication`.

### Task 5: Remove credential fallbacks and add log redaction

**Files:**
- Modify: `scripts/update_citic_l1_valuations.py:11`
- Modify: `scripts/update_citic_l1_valuations.py:139`
- Modify: `cycle_forecast_system/cycle_forecast_system/settings.py:219`
- Create: `src/seven_cycle_platform/security/redaction.py`
- Create: `tests/unit/security/test_secret_handling.py`

**Steps:**
1. Write a test that scans source/config files for non-empty token literals and fails on the existing fallback.
2. Write redaction tests for query parameters, headers, URLs, and exception strings containing token-like values.
3. Run `uv run pytest tests/unit/security -v`; expect failure.
4. Delete the non-empty `TOKEN_FALLBACK`, require `TUSHARE_TOKEN` at call time, and change Django settings to `os.getenv("TUSHARE_TOKEN")` without logging it.
5. Implement `redact_secrets(text: str) -> str` and use it in new pipeline logging and manifest error serialization.
6. Re-run the security tests plus `rg -n "TOKEN_FALLBACK|TUSHARE_TOKEN\\s*=\\s*['\\\"][^'\\\"]+" . --glob '!**/venv/**' --glob '!.superpowers/**'`; expect no persisted secret.
7. Commit/checkpoint: `fix: enforce environment-only credentials`.

### Task 6: Create the CLI and legacy regression harness

**Files:**
- Create: `src/seven_cycle_platform/cli.py`
- Create: `scripts/run_seven_cycle_pipeline.py`
- Create: `scripts/verify_seven_cycle_platform.py`
- Create: `tests/integration/test_legacy_regressions.py`
- Modify: `pyproject.toml`

**Steps:**
1. Add a failing test for `seven-cycle validate-config`, `seven-cycle build --as-of`, and `seven-cycle verify --run-id` command parsing.
2. Implement an `argparse` CLI and expose it as the `seven-cycle` project script.
3. Make `scripts/run_seven_cycle_pipeline.py` a thin compatibility entry point calling the package CLI.
4. Add a regression test invoking `scripts/verify_cycle_research_robustness.py` and `scripts/verify_cycle_investment_application.py` in subprocesses; mark it `integration` and keep it separate from fast unit tests.
5. Run `uv run pytest tests/unit tests/integration/test_legacy_regressions.py -v`; expect current legacy verification to remain green.
6. Commit/checkpoint: `test: preserve legacy cycle regressions`.

## M2 — Seven-Cycle Historical and Real-Time State

### Task 7: Extract causal preprocessing and the harmonic state kernel

**Files:**
- Create: `src/seven_cycle_platform/cycles/preprocess.py`
- Create: `src/seven_cycle_platform/cycles/state_space.py`
- Create: `tests/unit/cycles/test_preprocess.py`
- Create: `tests/unit/cycles/test_state_space.py`
- Modify: `scripts/cycle_realtime_core.py:55`
- Modify: `scripts/cycle_realtime_core.py:153`

**Steps:**
1. Port tests for month-end regularization, causal transforms, lagged expanding standardization, and missing-observation propagation.
2. Add a cutoff test: append future observations to a series and assert all filtered outputs through the cutoff are byte-equivalent.
3. Add a sinusoid test asserting the filter returns latent level, quadrature state, slope, acceleration, amplitude, angle in `[0, 360)`, and uncertainty.
4. Implement the package kernel by extracting and extending `regularize_panel`, `causal_transform`, `expanding_standardize`, and `harmonic_state_filter` from `scripts/cycle_realtime_core.py`.
5. Keep legacy functions as thin imports/wrappers so old verification continues to pass.
6. Run new cycle tests and the legacy investment verification.
7. Commit/checkpoint: `refactor: extract causal cycle kernel`.

### Task 8: Build the C1–C7 state engine

**Files:**
- Create: `src/seven_cycle_platform/cycles/engine.py`
- Create: `src/seven_cycle_platform/cycles/aggregation.py`
- Create: `src/seven_cycle_platform/cycles/phase.py`
- Create: `tests/unit/cycles/test_seven_cycle_engine.py`

**Steps:**
1. Write a synthetic panel test with annual and monthly categories that expects exactly seven cycle rows per `as_of` date.
2. Require each row to contain `angle`, `phase`, `level`, `slope`, `acceleration`, `amplitude`, causal `innovation`, `uncertainty`, `center_period`, `bandwidth`, `confidence`, `evidence_level`, and `usage_status`.
3. Implement category-balanced aggregation using past-only sign alignment, preserving the approach at `scripts/cycle_realtime_core.py:316` while removing hard-coded period lists at lines 30–43.
4. Derive UI phases from continuous level/slope while retaining the continuous angle as the authoritative internal state.
5. Force C1/C2 to low confidence when effective cycles are insufficient and C7 to `conditional` until its validation gate passes.
6. Run `uv run pytest tests/unit/cycles/test_seven_cycle_engine.py -v`.
7. Commit/checkpoint: `feat: compute governed C1-C7 states`.

### Task 9: Implement quarterly dynamic period recalibration

**Files:**
- Create: `src/seven_cycle_platform/cycles/discovery.py`
- Create: `src/seven_cycle_platform/cycles/recalibration.py`
- Create: `src/seven_cycle_platform/cycles/model_version.py`
- Create: `tests/unit/cycles/test_recalibration.py`
- Modify: `scripts/cycle_robustness_core.py:20`
- Modify: `scripts/discover_cycle_periods_robust.py:134`

**Steps:**
1. Write tests for AR(1) red-noise scores, bootstrap intervals, category support, method agreement, and deterministic random seeds.
2. Add acceptance/rejection fixtures: a strong candidate inside the search band is accepted; a weak candidate retains the prior center and lowers confidence.
3. Add a drift test asserting `abs(new_center - old_center)` cannot exceed `max_quarterly_drift` unless an explicit manual model-version override is present.
4. Extract reusable discovery functions from the two legacy scripts into the package.
5. Persist every decision as a `CycleModelVersion` containing old/new bands, evidence metrics, rejection reason, and effective date.
6. Run the new tests plus `scripts/verify_cycle_research_robustness.py`.
7. Commit/checkpoint: `feat: add governed cycle recalibration`.

### Task 10: Build exact vintage reconstruction and `cycle_phase_vintage`

**Files:**
- Create: `src/seven_cycle_platform/cycles/vintage.py`
- Create: `src/seven_cycle_platform/products/cycle_phase.py`
- Create: `tests/integration/test_cycle_cutoff_reconstruction.py`
- Create: `tests/contract/test_cycle_phase_product.py`

**Steps:**
1. Write an integration test that builds a full history and a truncated history for at least one annual and one monthly cutoff and compares all realtime fields at `<= cutoff` with tolerance `1e-10` and identical missingness.
2. Add a contract test for the approved `date × cycle_id × vintage` product and common provenance columns.
3. Implement a vintage reader that filters observations by `release_date <= as_of` and refuses pseudo-vintage rows when strict mode is requested.
4. Build and write `cycle_phase_vintage.parquet` under the current run directory.
5. Store latest-historical and realtime-vintage interpretations separately; never overwrite one with the other.
6. Run both tests and inspect the produced manifest checksums.
7. Commit/checkpoint: `feat: publish exact cycle vintages`.

### Task 11: Add the M2 pipeline and acceptance verifier

**Files:**
- Create: `src/seven_cycle_platform/pipeline/cycles.py`
- Create: `src/seven_cycle_platform/verification/cycles.py`
- Modify: `src/seven_cycle_platform/cli.py`
- Modify: `scripts/verify_seven_cycle_platform.py`
- Create: `tests/integration/test_m2_cycle_pipeline.py`

**Steps:**
1. Add a failing integration test that runs an M2 build in a temporary product root and expects registries, model versions, cycle products, quality findings, and manifest files.
2. Implement pipeline stages `load_vintage → recalibrate_if_due → estimate_states → verify → publish`.
3. Fail the run with status `blocked` when cutoff reconstruction, schema, or no-lookahead verification fails.
4. Add CLI command `seven-cycle build-cycles --as-of YYYY-MM-DD --strict-vintage`.
5. Run the integration test, legacy verification scripts, and `uv run ruff check src tests`.
6. Commit/checkpoint: `feat: complete M2 cycle pipeline`.

## M3 — Quantitative Attribution

### Task 12: Build the core asset return panel and explicit proxy chain

**Files:**
- Create: `src/seven_cycle_platform/assets/sources.py`
- Create: `src/seven_cycle_platform/assets/panel.py`
- Create: `src/seven_cycle_platform/assets/proxies.py`
- Create: `tests/unit/assets/test_proxy_chain.py`
- Create: `tests/integration/test_core_asset_panel.py`
- Reference: `output/monthly_returns_20y.parquet`

**Steps:**
1. Write tests requiring source, symbol, currency, calendar, proxy status, effective dates, overlap calibration, and confidence discount for every asset series.
2. Add a Baijiu fixture: preferred index `399997.SZ`; fallback `CI005019.CI` must remain a separate proxy segment and be labeled `proxy`, not silently concatenated.
3. Implement Tushare and AkShare adapters that read credentials only through the environment and normalize prices to month-end total/price returns with source metadata.
4. Implement a converter for the existing MultiIndex columns in `output/monthly_returns_20y.parquet` so legacy assets can seed the core panel.
5. Build a core panel containing the approved M3 subset and explicit benchmarks.
6. Run the asset unit and integration tests.
7. Commit/checkpoint: `feat: build governed core asset panel`.

### Task 13: Build transmission-channel states and innovations

**Files:**
- Create: `src/seven_cycle_platform/channels/engine.py`
- Create: `src/seven_cycle_platform/channels/innovations.py`
- Create: `src/seven_cycle_platform/products/channel_state.py`
- Create: `tests/unit/channels/test_channel_engine.py`

**Steps:**
1. Write tests that load eligible indicator concepts from `channels.yaml`, estimate weights from past-only data, and reject a channel with insufficient breadth.
2. Require channel output fields `state`, `innovation`, `uncertainty`, `member_count`, `revision_risk`, `vintage_kind`, and `confidence`.
3. Implement category-balanced channel composites with dynamic reliability weights based on walk-forward fit, data quality, revision size, and breadth.
4. Estimate innovations as one-step-ahead residuals from a causal state model; do not use two-sided residuals.
5. Publish `channel_state.parquet` with provenance.
6. Run `uv run pytest tests/unit/channels -v`.
7. Commit/checkpoint: `feat: estimate causal transmission channels`.

### Task 14: Estimate cycle-to-channel path coefficients

**Files:**
- Create: `src/seven_cycle_platform/attribution/stage1.py`
- Create: `src/seven_cycle_platform/attribution/walk_forward.py`
- Create: `tests/unit/attribution/test_cycle_to_channel.py`

**Steps:**
1. Generate synthetic correlated C1–C7 innovations with known channel coefficients and write a recovery test.
2. Add a no-lookahead test that perturbs future channel values and asserts prior coefficients/contributions are unchanged.
3. Implement expanding/rolling ridge with nested past-only alpha selection and optional recursive coefficient updating.
4. Return coefficient means, covariance, predicted channel innovation, cycle-specific channel contributions, and channel residual for every date.
5. Add condition-number diagnostics and mark a coefficient set `not_identifiable` when approved thresholds are exceeded.
6. Run `uv run pytest tests/unit/attribution/test_cycle_to_channel.py -v`.
7. Commit/checkpoint: `feat: estimate cycle-to-channel attribution`.

### Task 15: Estimate hierarchical time-varying channel-to-asset sensitivities

**Files:**
- Create: `src/seven_cycle_platform/attribution/stage2.py`
- Create: `src/seven_cycle_platform/attribution/hierarchy.py`
- Create: `tests/unit/attribution/test_channel_to_asset.py`

**Steps:**
1. Write a fixture with asset-class, industry, and asset-level coefficients where short-history assets must shrink toward their parent.
2. Test that long-history assets use more own-history information, while a short-history proxy receives lower confidence and stronger parent shrinkage.
3. Implement an interpretable hierarchical TVP ridge: parent posterior as prior mean, forgetting factor/rolling window for drift, and covariance propagation.
4. Include benchmark component, stable validated interactions, asset controls, event shocks, and residual as separate terms.
5. Assert coefficients use only training data ending before the attributed return.
6. Run `uv run pytest tests/unit/attribution/test_channel_to_asset.py -v`.
7. Commit/checkpoint: `feat: estimate dynamic asset channel exposures`.

### Task 16: Compose path contributions and identifiability allocation

**Files:**
- Create: `src/seven_cycle_platform/attribution/contributions.py`
- Create: `src/seven_cycle_platform/attribution/identifiability.py`
- Create: `tests/unit/attribution/test_contribution_conservation.py`
- Create: `tests/unit/attribution/test_identifiability.py`

**Steps:**
1. Write a conservation test requiring `benchmark + Σcycle paths + channel residual paths + controls + events + asset residual == target return` within `1e-10`.
2. Write a correlated-cycle test that triggers conditional Shapley/LMG allocation or a merged-cycle/not-identifiable status instead of unstable point attribution.
3. Implement path multiplication `cycle innovation × stage1 coefficient × stage2 coefficient`, summed across channels for each C1–C7 contribution.
4. Preserve negative contributions and contribution shares above 100%; do not normalize them to a pie chart.
5. Emit a direct-cycle residual only when it adds stable out-of-sample value and label it `unobserved_channel_residual`.
6. Run both attribution test modules.
7. Commit/checkpoint: `feat: conserve cycle attribution paths`.

### Task 17: Add uncertainty intervals and the `asset_attribution` product

**Files:**
- Create: `src/seven_cycle_platform/attribution/uncertainty.py`
- Create: `src/seven_cycle_platform/products/asset_attribution.py`
- Create: `tests/unit/attribution/test_intervals.py`
- Create: `tests/contract/test_asset_attribution_product.py`

**Steps:**
1. Write deterministic tests for seeded residual block bootstrap/posterior draws and nested 50%/80% intervals.
2. Require product dimensions `asset × period × horizon × component` and fields for point contribution, lower/upper bounds, component type/ID, significance, explained/residual, absolute/excess, status, and evidence level.
3. Combine coefficient covariance, channel uncertainty, cycle-state uncertainty, and residual sampling without double counting.
4. Mark intervals unavailable rather than fabricating them when effective samples are insufficient.
5. Write the product and product-level conservation diagnostics to the run directory.
6. Run interval and contract tests.
7. Commit/checkpoint: `feat: publish attribution distributions`.

### Task 18: Implement the 2019 Baijiu acceptance case

**Files:**
- Create: `src/seven_cycle_platform/reports/baijiu_2019.py`
- Create: `tests/integration/test_baijiu_2019_acceptance.py`
- Create: `docs/runbooks/baijiu-2019-attribution.md`
- Modify: `src/seven_cycle_platform/cli.py`

**Steps:**
1. Write an integration test that attributes Baijiu calendar-year 2019 absolute return and excess return versus HS300.
2. Require C1–C7, growth, real-rate, liquidity, earnings, risk-premium, foreign-flow/funding, valuation/event, and residual rows; unavailable channels must have an explicit reason. If the preferred Baijiu history is too short, publish its strongly shrunk low-confidence result alongside the explicit Food & Beverage proxy result rather than silently replacing it.
3. Assert both absolute and excess decompositions conserve to the model target and include 50%/80% intervals, evidence level, proxy status, realtime vintage, and latest-historical interpretation.
4. Implement `seven-cycle report-baijiu-2019 --run-id ...`; all numeric output must come from `asset_attribution.parquet` and related manifests.
5. Generate `products/.../reports/baijiu_2019.md` and a machine-readable JSON companion.
6. Run the acceptance test and manually inspect that no model-free number is inserted by the report template.
7. Commit/checkpoint: `feat: add 2019 Baijiu attribution gate`.

## M4 — Current Asset Mapping

### Task 19: Build the point-in-time current feature snapshot

**Files:**
- Create: `src/seven_cycle_platform/mapping/features.py`
- Create: `tests/unit/mapping/test_feature_snapshot.py`

**Steps:**
1. Write a test that requests an `as_of` date and rejects any cycle, channel, valuation, earnings, positioning, liquidity, or event observation released afterward.
2. Implement `CurrentFeatureSnapshot` containing C1–C7 states, channel states, asset controls, event scenarios, historical posterior, and provenance.
3. Add freshness and structural-drift flags per feature.
4. Run the test with true and pseudo vintage fixtures.
5. Commit/checkpoint: `feat: build point-in-time mapping features`.

### Task 20: Generate current return and risk distributions

**Files:**
- Create: `src/seven_cycle_platform/mapping/distribution.py`
- Create: `src/seven_cycle_platform/mapping/risk.py`
- Create: `tests/unit/mapping/test_current_distribution.py`

**Steps:**
1. Write tests for up/neutral/down probabilities summing to one, ordered return quantiles, non-negative volatility, coherent VaR/CVaR, and drawdown intervals.
2. Generate 3/6/12-month absolute and benchmark-relative draws from the stage-2 posterior plus current cycle/channel forecasts and residual bootstrap.
3. Use horizon-specific aggregation rather than multiplying one-month point estimates.
4. Implement probability calibration hooks and record calibration version.
5. Run mapping distribution tests.
6. Commit/checkpoint: `feat: estimate current asset distributions`.

### Task 21: Score transferability and publish usage status

**Files:**
- Create: `src/seven_cycle_platform/mapping/transferability.py`
- Create: `tests/unit/mapping/test_transferability.py`

**Steps:**
1. Write table-driven tests covering `formal`, `conditional`, `retrospective_only`, and `unavailable`.
2. Score sign/magnitude stability, historical-neighbor similarity, constituent/business-model drift, valuation/positioning distance, structural breaks, cycle/channel confidence, proxy discount, and out-of-sample increment.
3. Make `formal` impossible when the future model fails the simple-baseline gate even if retrospective attribution is strong.
4. Persist each subscore and reason code; never return only an opaque aggregate.
5. Run transferability tests.
6. Commit/checkpoint: `feat: govern mapping transferability`.

### Task 22: Convert distributions into bounded suggested weight ranges

**Files:**
- Create: `src/seven_cycle_platform/mapping/weights.py`
- Create: `tests/unit/mapping/test_weight_ranges.py`

**Steps:**
1. Write tests requiring a neutral benchmark range, max active tilt, risk-budget cap, confidence shrinkage, and no output for low-confidence/unavailable assets.
2. Implement a deterministic range rule based on expected excess return, downside risk, transferability, and model disagreement; return `[min_weight, max_weight]`, never a single optimized weight.
3. Ensure all asset ranges can coexist without claiming they form a fully optimized executable portfolio.
4. Add caveats for leverage, liquidity, currency, and proxy assets.
5. Run weight-range tests.
6. Commit/checkpoint: `feat: add confidence-aware weight ranges`.

### Task 23: Publish and verify `asset_mapping_current`

**Files:**
- Create: `src/seven_cycle_platform/products/asset_mapping_current.py`
- Create: `src/seven_cycle_platform/verification/current_mapping.py`
- Create: `tests/contract/test_asset_mapping_current.py`
- Create: `tests/integration/test_m4_current_mapping.py`

**Steps:**
1. Write the approved product contract with provenance and all direction, return, risk, influence, range, transferability, status, and caveat fields.
2. Add verification that every published weight range is supported by a non-retrospective status and non-stale data.
3. Integrate M4 after M3 in the pipeline; fail only affected assets as `partial` when the platform can safely publish the remainder.
4. Run contract and integration tests.
5. Commit/checkpoint: `feat: complete current asset mapping`.

## M5 — Probabilistic Forecasting

### Task 24: Forecast cycle phases with the Champion model

**Files:**
- Create: `src/seven_cycle_platform/forecast/cycles.py`
- Create: `tests/unit/forecast/test_cycle_champion.py`

**Steps:**
1. Write tests for horizon-specific forecasts, four-phase probabilities summing to one, ordered angle quantiles, and turning-window output.
2. Propagate the causal harmonic latent state and covariance using phase velocity, acceleration, duration, and approved leading indicators.
3. Use C1–C7 horizon sets from the registry and preserve wider uncertainty for long horizons/C1/C2.
4. Calibrate phase probabilities by walk-forward isotonic or logistic calibration fitted only on prior folds.
5. Run cycle forecast tests.
6. Commit/checkpoint: `feat: add cycle forecast champion`.

### Task 25: Forecast transmission channels

**Files:**
- Create: `src/seven_cycle_platform/forecast/channels.py`
- Create: `tests/unit/forecast/test_channel_champion.py`

**Steps:**
1. Write a walk-forward test comparing a regularized ARX/channel-state model to historical-mean and persistence baselines.
2. Use predicted cycle paths plus point-in-time exogenous features; apply embargo where publication/revision overlap can leak outcomes.
3. Return channel distributions and covariance needed by asset forecasts.
4. Record baseline and Champion losses by fold/horizon.
5. Run channel forecast tests.
6. Commit/checkpoint: `feat: forecast transmission channels`.

### Task 26: Generate future asset distributions and scenarios

**Files:**
- Create: `config/seven_cycle/scenarios.yaml`
- Create: `src/seven_cycle_platform/forecast/assets.py`
- Create: `src/seven_cycle_platform/forecast/scenarios.py`
- Create: `tests/unit/forecast/test_asset_scenarios.py`

**Steps:**
1. Define baseline, easing, tightening, growth, inflation, and geopolitical/supply scenarios as explicit channel shocks with dates and units.
2. Write tests ensuring historical actuals and future forecasts cannot appear in the same record/view mode.
3. Combine cycle, channel, dynamic exposure, valuation, positioning, and event draws into asset median, 50%/80% return intervals, volatility, CVaR, drawdown, and channel contributions.
4. Preserve scenario provenance and prevent scenario shocks from being counted as cycle contributions.
5. Run scenario tests.
6. Commit/checkpoint: `feat: generate future asset scenarios`.

### Task 27: Define the Challenger interface and promotion gates

**Files:**
- Create: `src/seven_cycle_platform/forecast/protocol.py`
- Create: `src/seven_cycle_platform/forecast/evaluation.py`
- Create: `tests/unit/forecast/test_challenger_promotion.py`

**Steps:**
1. Define a `ForecastModel` protocol with `fit(train_vintage)`, `predict(as_of, horizons)`, `model_card()`, and `feature_audit()`.
2. Write promotion tests requiring Challenger improvement in Brier score, LogLoss, interval coverage, and downstream asset out-of-sample loss with no no-lookahead violation.
3. Require nested walk-forward folds, embargo, deterministic seeds, and fold-level artifacts.
4. Keep Champion live when any mandatory gate fails; store Challenger as `experimental` with failure reasons.
5. Run promotion tests.
6. Commit/checkpoint: `feat: govern forecast challengers`.

### Task 28: Publish `cycle_forecast` and `asset_mapping_future`

**Files:**
- Create: `src/seven_cycle_platform/products/cycle_forecast.py`
- Create: `src/seven_cycle_platform/products/asset_mapping_future.py`
- Create: `src/seven_cycle_platform/verification/forecast.py`
- Create: `tests/contract/test_forecast_products.py`
- Create: `tests/integration/test_m5_forecast_pipeline.py`

**Steps:**
1. Encode the approved dimensions and fields for both products.
2. Verify probability sums, quantile ordering, interval coverage metadata, Champion/Challenger labels, scenario separation, and transferability status.
3. Integrate M5 after current mapping without allowing retrospective contribution shares to become future weights.
4. Run contract/integration tests and compare against simple baselines.
5. Commit/checkpoint: `feat: complete probabilistic forecast products`.

## M6 — Query Service and 2D/3D Workbench

### Task 29: Build the DuckDB product catalog

**Files:**
- Create: `src/seven_cycle_platform/catalog/duckdb.py`
- Create: `src/seven_cycle_platform/catalog/views.sql`
- Create: `tests/integration/test_duckdb_catalog.py`

**Steps:**
1. Write tests that build a temporary catalog from one published run and query every core product through stable views.
2. Create views for runs, cycle current/history/forecast, assets, attribution, current/future mapping, analogs, scenarios, and quality findings.
3. Store only paths/metadata in DuckDB; keep Parquet as the immutable data source.
4. Verify catalog rebuild is idempotent and does not mutate product files.
5. Run catalog tests.
6. Commit/checkpoint: `feat: add DuckDB product catalog`.

### Task 30: Implement the read-only FastAPI service

**Files:**
- Create: `src/seven_cycle_platform/api/app.py`
- Create: `src/seven_cycle_platform/api/dependencies.py`
- Create: `src/seven_cycle_platform/api/schemas.py`
- Create: `src/seven_cycle_platform/api/repository.py`
- Create: `src/seven_cycle_platform/api/routes/runs.py`
- Create: `src/seven_cycle_platform/api/routes/cycles.py`
- Create: `src/seven_cycle_platform/api/routes/assets.py`
- Create: `src/seven_cycle_platform/api/routes/analogs.py`
- Create: `src/seven_cycle_platform/api/routes/scenarios.py`
- Create: `tests/api/test_api_smoke.py`

**Steps:**
1. Write failing API tests for all approved `/v1` endpoints and query parameters.
2. Implement Pydantic response envelopes containing `data`, `provenance`, `freshness`, `usage_status`, and `caveats`.
3. Read `latest.json` once per request context and query only its immutable catalog/run; never mix runs in one response.
4. Add pagination, validation, bounded query sizes, ETag/checksum headers, and stale/partial/blocked status propagation.
5. Expose `seven-cycle serve --host 127.0.0.1 --port 8008`.
6. Commit/checkpoint: `feat: expose read-only research API`.

### Task 31: Add API contract and atomic-release tests

**Files:**
- Create: `tests/api/test_runs_api.py`
- Create: `tests/api/test_cycles_api.py`
- Create: `tests/api/test_assets_api.py`
- Create: `tests/api/test_release_degradation.py`

**Steps:**
1. Assert each endpoint returns only requested run/vintage/model/horizon/scenario rows and traceable provenance.
2. Simulate a failed new staging run and assert API continues serving the prior live run with `stale` state.
3. Simulate partial asset failure and assert valid assets remain available while failed ones carry explicit reasons.
4. Run `uv run pytest tests/api -v` and generate the OpenAPI snapshot.
5. Commit/checkpoint: `test: lock API and degradation contracts`.

### Task 32: Establish the React application shell and URL state

**Files:**
- Modify: `cycle_forecast_system_frontend/package.json:5`
- Modify: `cycle_forecast_system_frontend/src/App.tsx:1`
- Modify: `cycle_forecast_system_frontend/src/App.css:1`
- Modify: `cycle_forecast_system_frontend/src/App.test.tsx:1`
- Modify: `cycle_forecast_system_frontend/src/index.css:1`
- Create: `cycle_forecast_system_frontend/src/api/client.ts`
- Create: `cycle_forecast_system_frontend/src/api/types.ts`
- Create: `cycle_forecast_system_frontend/src/state/urlState.ts`
- Create: `cycle_forecast_system_frontend/src/layout/AppShell.tsx`

**Steps:**
1. Preserve existing uncommitted `axios` and `echarts` additions; add `echarts-gl`, `react-router-dom`, and Playwright dev dependencies.
2. Replace the CRA placeholder test with a failing shell test for navigation: Overview, Past, Present, Future, 3D Lab, Data & Models.
3. Implement a typed API client and URL-backed global filters for date/vintage, model version, asset tier/asset, horizon, scenario, and benchmark.
4. Add loading, stale, partial, blocked, and error banners with non-technical copy.
5. Run `npm test -- --watchAll=false` and `npm run build` from `cycle_forecast_system_frontend/`.
6. Commit in the nested frontend repo: `feat: add seven-cycle workbench shell`.

### Task 33: Build the Past research page

**Files:**
- Create: `cycle_forecast_system_frontend/src/pages/PastPage.tsx`
- Create: `cycle_forecast_system_frontend/src/components/cycles/CyclePhaseBands.tsx`
- Create: `cycle_forecast_system_frontend/src/components/assets/ReturnRiskHeatmap.tsx`
- Create: `cycle_forecast_system_frontend/src/components/attribution/AttributionWaterfall.tsx`
- Create: `cycle_forecast_system_frontend/src/components/analogs/AnalogTimeline.tsx`
- Create: `cycle_forecast_system_frontend/src/pages/PastPage.test.tsx`

**Steps:**
1. Write component tests for realtime-vintage versus latest-historical toggle, exact numbers in the table, residual visibility, and proxy/evidence labels.
2. Implement seven phase bands, asset heatmap, attribution waterfall, analog/event replay, and model-explained/residual panels.
3. Make chart clicks update the selected date in URL state and all sibling panels.
4. Ensure tooltips show return, phase angle, contribution, interval, vintage, and proxy status.
5. Run the page tests and frontend build.
6. Commit: `feat: add historical attribution workbench`.

### Task 34: Build the Present research page

**Files:**
- Create: `cycle_forecast_system_frontend/src/pages/PresentPage.tsx`
- Create: `cycle_forecast_system_frontend/src/components/cycles/CurrentCycleStrip.tsx`
- Create: `cycle_forecast_system_frontend/src/components/assets/RiskReturnMatrix.tsx`
- Create: `cycle_forecast_system_frontend/src/components/mapping/MappingEvidencePanel.tsx`
- Create: `cycle_forecast_system_frontend/src/components/mapping/WeightRangeTable.tsx`
- Create: `cycle_forecast_system_frontend/src/pages/PresentPage.test.tsx`

**Steps:**
1. Test direction probabilities, return/risk ranges, transferability subscores, usage statuses, and absence of exact automatic weights.
2. Implement current cycle strip, cross-asset risk/return matrix, channel/contribution rank, probability intervals, weight ranges, and evidence audit.
3. Disable weight-range display when the API status is retrospective-only/unavailable.
4. Run tests and build.
5. Commit: `feat: add current mapping workbench`.

### Task 35: Build the Future research page

**Files:**
- Create: `cycle_forecast_system_frontend/src/pages/FuturePage.tsx`
- Create: `cycle_forecast_system_frontend/src/components/forecast/CycleFanChart.tsx`
- Create: `cycle_forecast_system_frontend/src/components/forecast/TurningWindow.tsx`
- Create: `cycle_forecast_system_frontend/src/components/forecast/ScenarioDistribution.tsx`
- Create: `cycle_forecast_system_frontend/src/components/forecast/ModelDisagreement.tsx`
- Create: `cycle_forecast_system_frontend/src/pages/FuturePage.test.tsx`

**Steps:**
1. Test probability fans, turning windows, scenario separation, Champion/Challenger disagreement, and transferability changes.
2. Prevent historical actual and future forecast series from being rendered in one mode.
3. Implement synchronized horizon/scenario/asset filters and exact companion tables.
4. Run tests and build.
5. Commit: `feat: add probabilistic forecast workbench`.

### Task 36: Implement the synchronized 3D laboratory

**Files:**
- Create: `cycle_forecast_system_frontend/src/pages/Lab3DPage.tsx`
- Create: `cycle_forecast_system_frontend/src/components/three/CycleTrajectory3D.tsx`
- Create: `cycle_forecast_system_frontend/src/components/three/CrossAssetTerrain3D.tsx`
- Create: `cycle_forecast_system_frontend/src/components/three/ContributionCube3D.tsx`
- Create: `cycle_forecast_system_frontend/src/components/three/StaticFallback.tsx`
- Create: `cycle_forecast_system_frontend/src/components/three/renderer.ts`
- Create: `cycle_forecast_system_frontend/src/pages/Lab3DPage.test.tsx`

**Steps:**
1. Write tests for the three approved modes, single WebGL instance, URL-persisted camera, and 2D/static fallback.
2. Implement ECharts-GL behind a renderer adapter so a future Three.js renderer does not change page contracts.
3. Default the trajectory view to cycle contribution, with total-performance mode explicit and separately labeled.
4. On point click, write date/asset/cycle into URL state and synchronize Past/Present exact 2D tables.
5. Detect WebGL/context loss, reduced motion, mobile portrait, and low capability; fall back to 2D small multiples.
6. Run tests and build.
7. Commit: `feat: add synchronized 3D research lab`.

### Task 37: Add frontend E2E, accessibility, visual, and performance gates

**Files:**
- Create: `cycle_forecast_system_frontend/playwright.config.ts`
- Create: `cycle_forecast_system_frontend/e2e/past-present-future.spec.ts`
- Create: `cycle_forecast_system_frontend/e2e/url-history.spec.ts`
- Create: `cycle_forecast_system_frontend/e2e/three-sync.spec.ts`
- Create: `cycle_forecast_system_frontend/e2e/accessibility.spec.ts`

**Steps:**
1. Mock/stub a fixed API run for deterministic browser tests.
2. Test browser back/forward, shared URLs, table/chart numeric equality, 3D click synchronization, export, keyboard focus, color-safe legends, and reduced animation.
3. Assert only one WebGL canvas exists and that the static fallback appears when WebGL is disabled.
4. Add practical performance budgets for initial data payload, interaction response, and lazy-loaded 3D bundle.
5. Run `npx playwright test`, `npm test -- --watchAll=false`, and `npm run build`.
6. Commit: `test: verify workbench interaction and accessibility`.

### Task 38: Complete the M6 end-to-end release gate

**Files:**
- Create: `src/seven_cycle_platform/verification/end_to_end.py`
- Create: `tests/e2e/test_product_api_consistency.py`
- Modify: `scripts/verify_seven_cycle_platform.py`
- Create: `docs/runbooks/local-platform.md`

**Steps:**
1. Build a complete local run, catalog it, start FastAPI, and compare selected API values back to Parquet by run/vintage/model/config keys.
2. Verify the 2019 Baijiu report, current mapping, cycle forecast, and one 3D dataset all originate from the same published run.
3. Fail publication if product/API consistency, contribution conservation, cutoff reconstruction, or frontend contract snapshots fail.
4. Document local start/stop, product locations, stale fallback, and troubleshooting without exposing credentials.
5. Run the full Python and frontend gate.
6. Commit/checkpoint: `feat: complete traceable M6 release`.

## M7 — Expansion and Productionization

### Task 39: Expand governed asset coverage

**Files:**
- Modify: `config/seven_cycle/assets.yaml`
- Create: `src/seven_cycle_platform/assets/expansion.py`
- Create: `tests/integration/test_expanded_asset_quality.py`

**Steps:**
1. Add A-share style indices, all 31 Shenwan level-one industries, China/US bonds, global equities, precious/energy/base metals, FX, cash, and qualified small metals.
2. Enforce minimum history, liquidity, missingness, proxy, overlap, and effective-date gates before an asset can leave observation tier.
3. Do not create pre-inception Shenwan histories; use coarse historical parents or unavailable status.
4. Run attribution/mapping stability by asset tier and publish only passing assets.
5. Commit/checkpoint: `feat: expand governed asset universe`.

### Task 40: Implement the Transformer Challenger only after Champion gates pass

**Files:**
- Create: `src/seven_cycle_platform/forecast/challengers/transformer.py`
- Create: `src/seven_cycle_platform/forecast/challengers/dataset.py`
- Create: `tests/forecast/test_transformer_challenger.py`
- Modify: `pyproject.toml`

**Steps:**
1. Add the sequence-model dependency only in an optional `ml` group so the base platform stays lightweight.
2. Build strictly vintage-aware windows with masks, publication lags, nested walk-forward folds, and embargo.
3. Restrict targets to cycle state or transmission channels; never let the model directly emit portfolio weights.
4. Compare against the frozen Champion using all promotion gates from Task 27.
5. Keep the model experimental unless every mandatory metric improves and the downstream asset mapping remains interpretable.
6. Commit/checkpoint: `feat: add governed Transformer challenger`.

### Task 41: Add idempotent daily, monthly, and quarterly orchestration

**Files:**
- Create: `src/seven_cycle_platform/orchestration/jobs.py`
- Create: `src/seven_cycle_platform/orchestration/scheduler.py`
- Create: `src/seven_cycle_platform/monitoring/health.py`
- Create: `src/seven_cycle_platform/monitoring/alerts.py`
- Create: `tests/integration/test_scheduled_jobs.py`
- Create: `docs/runbooks/scheduling.md`

**Steps:**
1. Define daily ingest/quality refresh, monthly official state/attribution/mapping release, and quarterly recalibration/model comparison.
2. Write tests for idempotency, retry, lock ownership, partial failure, and unchanged `latest.json` on blocked runs.
3. Add health outputs for freshness, missing sources, model drift, publication status, and next scheduled run.
4. Keep notification transport configurable and free of secrets in payload/logs.
5. Document cron/launchd deployment examples without embedding schedules into research logic.
6. Commit/checkpoint: `feat: schedule governed platform runs`.

### Task 42: Run final acceptance and write the production handoff

**Files:**
- Create: `docs/runbooks/production-acceptance.md`
- Create: `output/SEVEN_CYCLE_PLATFORM_ACCEPTANCE.md`
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `findings.md`

**Steps:**
1. Run all fast Python tests, integration/contract/API tests, legacy regressions, frontend unit/build/E2E, and end-to-end release verification.
2. Record the eight approved core gates: exact cutoff, governed recalibration, Baijiu conservation, future-baseline increment/status, full provenance, 3D/2D synchronization, atomic fallback, and environment-only secrets.
3. Record limitations for C1/C2 sample size, C7 evidence, pseudo vintages, short-history industries, proxies, and any Challenger that did not promote.
4. Update project planning files only after all mandatory gates pass; do not call the platform production-ready while any gate is blocked.
5. Commit/checkpoint: `docs: record seven-cycle platform acceptance`.

## Required Verification Commands

Run these from `/Volumes/PSSD/Projects/1周期模块` unless a task says otherwise:

```bash
uv sync --group dev
uv run ruff check src tests
uv run pytest tests/unit -v
uv run pytest tests/contract tests/api -v
uv run pytest tests/integration -v
uv run python scripts/verify_cycle_research_robustness.py
uv run python scripts/verify_cycle_investment_application.py
uv run python scripts/verify_seven_cycle_platform.py
```

Run these from `/Volumes/PSSD/Projects/1周期模块/cycle_forecast_system_frontend`:

```bash
npm test -- --watchAll=false
npm run build
npx playwright test
```

## Stop Conditions

- Stop and mark the run `blocked` if cutoff reconstruction, no-lookahead, product contract, contribution conservation, or atomic publication fails.
- Stop future Mapping promotion if it does not improve a simple baseline; publish `retrospective_only` instead of tuning until it passes.
- Stop Baijiu formal reporting if only the Food & Beverage proxy is available without explicit proxy disclosure or if attribution does not conserve.
- Stop 3D release if synchronized exact 2D values are unavailable.
- Stop all data acquisition if `TUSHARE_TOKEN` is missing; never fall back to a persisted token.
