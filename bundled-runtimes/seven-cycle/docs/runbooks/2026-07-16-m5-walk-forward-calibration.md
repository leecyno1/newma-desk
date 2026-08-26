# M5 Walk-Forward Analog Calibration — 2026-07-16

## Evidence

- Method: `expanding_purged_cycle_analog_walk_forward_v1`.
- Every validation origin uses only historical paths whose complete outcome window ends strictly before that origin.
- Forecast: median return of nearest C1–C7 circular-state neighbors.
- Baseline: median return of every fully realized prior path.
- Horizons: 3, 6, and 12 months.
- Parameter stress: 8, 12, and 16 nearest neighbors with at least 24 prior training paths.

## Result

- Six of fifteen asset × horizon combinations pass under all three neighbor settings:
  - 中证1000: 3 and 6 months.
  - 中证500: 6 and 12 months.
  - 沪深300: 6 and 12 months.
- Chinese government bonds fail all horizons because analog MAE is consistently worse than the unconditional baseline.
- S&P 500 fails all horizons; short- and medium-horizon MAE and direction accuracy are materially weaker than the baseline.
- 中证1000 12 months, 中证500 3 months, and 沪深300 3 months are parameter-sensitive or fail the MAE/direction joint gate.

## Governance Decision

- Do not publish a universal formal `asset_mapping_future` from the current analog model.
- Retain the six stable combinations as research candidates for Challenger comparison.
- Keep all results `pseudo_vintage / retrospective_only` until cycle forecasts, channel transmission, and asset forecasts pass the same point-in-time walk-forward archive and calibration gates.
- Do not relabel M4 historical analog distributions as M5 Champion forecasts.

## Artifacts

- `output/m5_walk_forward_calibration_2026-07-16/asset_analog_folds.parquet`
- `output/m5_walk_forward_calibration_2026-07-16/asset_analog_summary.parquet`
- `output/m5_walk_forward_calibration_2026-07-16/parameter_sensitivity.parquet`
- `output/m5_walk_forward_calibration_2026-07-16/parameter_stability.parquet`
- `output/m5_walk_forward_calibration_2026-07-16/summary.json`
- `output/m5_walk_forward_calibration_2026-07-16/parameter_stability.json`
