# Formal Research Rerun — 2026-07-15

## Published Runs

- Governed C1-C7 source run: `products/seven_cycle/runs/2025-12-31-99d674f1937d-91de47bbda23`
- Research surface release: `products/seven_cycle_research/runs/2025-12-31-126162704afe-d3d43520c686`
- Live catalog: `catalogs/seven_cycle_research/2025-12-31-126162704afe-d3d43520c686.duckdb`
- Browser entry: `http://127.0.0.1:50515/lab-3d?asset=沪深300&horizon=6m&scenario=baseline&surfaceX=C3&surfaceY=C5&surfaceWindow=60`

## Data Status

- C1-C7 history contains 60 monthly dates from 2020-11-30 through 2025-10-31 and exactly seven cycle rows per date.
- All observations are explicitly marked `pseudo_vintage`; the legacy panels do not contain true historical release vintages.
- The release uses 29 annual and 27 monthly category-balanced research members.
- The asset surface release uses five governed legacy assets: 沪深300、中证500、中证1000、中国国债、标普500.
- It publishes 945 surface records: five assets × three horizons × three windows × 21 distinct cycle pairs.
- The governed history windows are 48, 60, and 120 months. A window may contain fewer effective observations when the published C1-C7 history is shorter than the requested lookback.

## Evidence Coverage

- Available surfaces: 48.
- Not identifiable: 897.
- By window, the evidence gate publishes 12 of 315 surfaces at 48 months, 18 of 315 at 60 months, and 18 of 315 at 120 months.
- Identifiable combinations are concentrated in A-share equity at six- and twelve-month horizons.
- The default demonstration uses 沪深300, six months, C3 × C5. The 60- and 120-month requests have 55 effective observations and a positive purged leave-one-out score; the 48-month request has 43 observations and remains not identifiable after purged validation.
- Non-identifiable combinations retain historical observations but publish no fitted grid.
- The 3D view plots the current C1-C7 phase pair on the Z-axis floor when the return surface is not identifiable, and labels the return as unavailable rather than fabricating a value.

## Method Correction

- Multi-month forward returns overlap through time. Ordinary leave-one-out validation materially overstated response-surface evidence.
- The estimator is now `circular-kernel-purged-loocv-v2`.
- Each validation fold removes every observation whose forward-return window overlaps the held-out window.
- The product publishes a surface only when the purged out-of-sample score remains positive.
- Historical surfaces are scenario-independent. Requests for a governed non-baseline scenario fall back to the published baseline historical surface while preserving the selected scenario for future products.
- A scenario fallback returns `requested_scenario_id` and `scenario_fallback=true`, removes any baseline future path, and the UI explicitly separates the baseline historical surface from the selected future scenario.
- API envelope usage states are restricted to the documented contract; a `not_identifiable` surface is summarized as `partial` instead of leaking a product-specific status into the top-level envelope.
- When multiple vintages exist for the same cycle and date, both scheduled publication and API-derived fallback use the catalog priority `realtime` > `latest_historical` > `pseudo_vintage`. Current snapshots then select the latest date per cycle.

## Remaining Gaps

- `asset_attribution`, `asset_mapping_current`, `cycle_forecast`, and `asset_mapping_future` are not yet published from real data.
- The 3D page therefore shows real historical response surfaces and current cycle position, but does not fabricate future paths or risk-return forecasts.
- True point-in-time vintages require source-level historical release archives rather than legacy panel release assumptions.
- The next critical path is the real M3 attribution pipeline, followed by M4/M5 current and future distributions under one atomic release context.
