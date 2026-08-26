# Real M3 Attribution + M4 Current Mapping Release — 2026-07-16

## Published Artifacts

- Atomic research run: `products/seven_cycle_research/runs/2025-12-31-980d8e01f750-d5b6b32ccbc8`
- Verified catalog: `catalogs/seven_cycle_research/2025-12-31-980d8e01f750-d5b6b32ccbc8.duckdb`
- Past attribution: `http://localhost:50515/past?asset=沪深300&horizon=6m`
- Present risk/return Mapping: `http://localhost:50515/present?asset=沪深300&horizon=6m`

## Scope

- Five governed assets: 沪深300、中证500、中证1000、中国国债、标普500.
- Horizons: 3, 6, and 12 months.
- Six objective macro categories are retained in the research channel universe.
- Five channels are active through 2025-10-31: growth, prices, liquidity/credit, external demand, and risk premium/crowding.
- `real_rate_discount` is explicitly unavailable in the current attribution window because its source observations stop before 2025-10; it is not filled, backdated, or replaced.
- Current Mapping publishes five governed assets × 3/6/12 months as retrospective research distributions. It does not publish executable weights or formal future forecasts.

## Method

- C1-C7 innovations use causal first differences of published cycle levels.
- Each of the 27 monthly indicators is expanding-standardized using only prior observations, then equal-weighted inside its governed category.
- Channel innovations use a one-sided local-level filter.
- Asset hierarchy is derived only from governed registry `asset_class` and `region` metadata.
- The stage-two benchmark is the same-month equal-weight return of the other four governed assets.
- Published attribution follows the governed chain: cycle-to-channel, channel-to-asset, conserved contributions, uncertainty intervals, and stable asset-attribution products.
- Current risk/return distributions use `retrospective_cycle_analog_knn_v1`: equal-weight circular C1–C7 phase distance, 24 historical states with strictly prior complete 12-month paths, and one shared analog origin per draw across all assets.
- Absolute and leave-one-out benchmark-relative monthly returns are wealth-linked into 3/6/12-month paths. Direction probabilities, q10/q25/q50/q75/q90, expected return, volatility, VaR/CVaR, and drawdown are reconstructed from retained paths.
- Valuation, earnings, positioning, liquidity, and event controls are explicitly marked unavailable. Transferability remains `retrospective_only`, and suggested weight ranges remain unavailable.

## Evidence Status

- `asset_attribution.parquet`: 300 rows.
- `asset_attribution_conservation.parquet`: 15 rows; all point conservation checks pass.
- `m3_influence.parquet`: 195 rows, covering five assets × three horizons × thirteen cycle/channel entries.
- `asset_mapping_current.parquet`: 15 rows, covering five assets × three horizons with available absolute/excess distributions and `retrospective_only` usage status.
- `retrospective_analogs.parquet`: 24 retained shared historical analog origins with distance and path-end audit fields.
- `research_channel_state_audit.json` retains the six research-channel histories as an audit sidecar.
- Governed `channel_state.parquet` is intentionally not published because the 27 retrospective research entities do not match the governed indicator registry.
- Release status is `partial` because one channel is unavailable and some 12-month component intervals remain unavailable.
- All evidence remains `pseudo_vintage` and `retrospective_only`; no future forecast is published.

## Validation

- Full backend verification: 1262 tests passed; 18 existing numerical warnings remain in the governed M5 channel forecast tests.
- Focused release/catalog/API verification: 118 tests passed.
- Present page: 66 tests passed; production frontend build completed successfully.
- Live API `/v1/assets/compare?horizon=6&limit=500` returns run `2025-12-31-980d8e01f750-d5b6b32ccbc8`, five assets, and `retrospective_only` usage.
- The in-app Browser plugin remained blocked by `Cannot redefine property: process`; no browser screenshot claim is made for this checkpoint.
- Past page now resolves Chinese asset labels, defaults to the explicitly labeled pseudo-vintage cycle mode, and renders C1-C7 history plus the quantitative attribution waterfall.

## Remaining Work

- M5 cycle and asset forecasts remain unavailable until a real walk-forward forecast chain passes governance and calibration gates.
- True realtime vintage history still requires source-level release archives.
