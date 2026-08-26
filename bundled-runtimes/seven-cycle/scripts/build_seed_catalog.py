"""Build the local DuckDB catalog for the bundled read-only seed run."""

from __future__ import annotations

import json
from pathlib import Path

from seven_cycle_platform.catalog import build_catalog
from seven_cycle_platform.storage.manifest import load_manifest


project_root = Path(__file__).resolve().parents[1]
product_root = project_root / "products" / "circle"
run_id = json.loads((product_root / "latest.json").read_text(encoding="utf-8"))["run_id"]
run_dir = product_root / "runs" / run_id
result = build_catalog(
    run_dir,
    product_root / "catalogs" / f"{run_id}.duckdb",
    expected_manifest=load_manifest(run_dir),
)
print(f"Seven Cycle catalog ready: {result.run_id} ({result.product_count} products)")
