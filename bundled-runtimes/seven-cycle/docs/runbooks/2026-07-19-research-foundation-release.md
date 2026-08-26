# Research Foundation Release

Run all commands from the repository root. This release is fixed to the approved
`2026-07-19` research foundation and publishes immutable products under
`products/circle`.

## Build

`uv run seven-cycle build-foundation --as-of 2026-07-19 --product-root products/circle`

The command defaults `--project-root` to the current directory and uses only
these approved source paths:

- `config/seven_cycle/assets.yaml`
- `config/seven_cycle/channels.yaml`
- `config/seven_cycle/cycles.yaml`
- `config/seven_cycle/indicators.yaml`
- `config/seven_cycle/evidence_baseline.yaml`
- `output/c4_c5_phase_display_prototype_2026-07-19.json`
- `output/c4_pseudo_realtime_prototype_2026-07-19.json`
- `output/c4_forecast_prototype_2026-07-19.json`
- `output/c4_asset_statistics_prototype_2026-07-19.json`

The pipeline pins every source by exact repository path, filename, file type and
approved SHA-256 checksum. It rejects missing files, symlinks, renamed or copied
inputs, checksum drift, invalid schemas and changed files observed during the
build. Do not edit, replace or regenerate an approved input in place. A source
change requires a separately reviewed foundation release with updated pins.

A successful build prints one compact JSON object with `run_id`, immutable run
`path`, matching `catalog`, `catalog_products` and `status: live`. It advances
`products/circle/latest.json` only after the full run is staged, validated and
atomically published. Re-running the same approved build verifies and reuses the
immutable run, then safely rebuilds its matching catalog.

## Verify

`RUN_ID=$(python -c 'import json; print(json.load(open("products/circle/latest.json"))["run_id"])')`

`uv run seven-cycle verify --run-id "$RUN_ID" --product-root products/circle`

The immutable run directory must contain `manifest.json` and these five governed
products:

- `cycle_evidence.parquet` — approved C1-C7 evidence status, priors and reasons.
- `cycle_phase_vintage.parquet` — C4 historical phase rows with vintage caveat.
- `data_identity.parquet` — source, vintage, retrieval and freshness identity.
- `publication_gate.parquet` — cycle-by-layer release decisions and reasons.
- `calibration_log.parquet` — approved calibration versions and status history.

The CLI now builds the verified DuckDB catalog automatically. For manual
recovery, the equivalent catalog command is:

```bash
uv run python - "$RUN_ID" <<'PY'
import json
import sys
from pathlib import Path

from seven_cycle_platform.catalog import build_catalog
from seven_cycle_platform.storage.manifest import load_manifest

product_root = Path("products/circle")
run_id = sys.argv[1]
run_dir = product_root / "runs" / run_id
result = build_catalog(
    run_dir,
    product_root / "catalogs" / f"{run_id}.duckdb",
    expected_manifest=load_manifest(run_dir),
)
print(json.dumps({
    "catalog": str(result.path),
    "products": result.product_count,
    "run_id": result.run_id,
    "views": list(result.view_names),
}, sort_keys=True))
PY
```

Check that the catalog exposes `cycle_evidence`, `data_identity`,
`publication_gates` and `calibration_log`, and that all rows carry the selected
`RUN_ID`. Start the local read-only API with:

`uv run seven-cycle serve --product-root products/circle --catalog-root products/circle/catalogs`

Then check the governed endpoints:

- `GET http://127.0.0.1:8008/v1/governance/evidence`
- `GET http://127.0.0.1:8008/v1/governance/publication`
- `GET http://127.0.0.1:8008/v1/governance/data-identity`
- `GET http://127.0.0.1:8008/v1/governance/calibrations`

Responses must identify the same run and catalog checksums. The API reads stable
DuckDB views only; it must never read prototype JSON or recalculate research at
request time.

## Interpretation

- C4 historical: formal.
- C4 asset statistics: formal for C4 only.
- C4 realtime: limited because the source is pseudo-vintage.
- C4 forecast: limited because the model passed but input data are stale.
- C1: scenario only.
- C2/C3/C5/C7: blocked.
- C6: calendar only.

`formal` means the specific layer passed the approved evidence, identity and
publication gates and may be presented as a governed result. `limited` means the
layer is available only with its published caveat and must not be described as
formal. `blocked` means no result may be fabricated, inferred or promoted for
that cycle and layer. `scenario_only` means C1 is a long-horizon conditional
scenario, not a measured current phase. `calendar_only` means C6 represents
calendar-defined seasonal timing and amplitude, not a free-running empirical
cycle.

Gate status is layer-specific. C4 historical formality does not make C4 realtime
or forecast formal, and C4 asset statistics must not be used to fill blocked
layers for other cycles. Preserve the separation among historical, realtime,
forecast and asset-statistics products. Do not relabel pseudo-vintage data as
true realtime, stale data as fresh, scenarios as observations, or calendar
structure as an estimated cycle.

## Failure Rule

If any input checksum, schema, provenance or publication test fails, the prior `latest.json` remains unchanged.

Failed builds are safe to rerun after restoring the exact approved inputs; the
staging run is cleaned and no partial run becomes live. Published run directories
are immutable. If the same deterministic run already exists, verify and reuse it
rather than deleting or overwriting it.

Rollback changes only the live pointer, never published files. Before selecting
an earlier run, verify its manifest and ensure its matching catalog exists. Then
atomically replace `products/circle/latest.json` with `{"run_id":"<verified-run-id>"}`.
Re-run the CLI verification and all four API checks after rollback. Never edit a
manifest, Parquet product or catalog to force a rollback to pass.
