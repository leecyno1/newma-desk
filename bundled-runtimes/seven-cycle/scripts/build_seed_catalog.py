"""Build the local DuckDB catalog for the bundled read-only seed run."""

from __future__ import annotations

import json
from pathlib import Path

from seven_cycle_platform.catalog import CatalogError, build_catalog, open_catalog
from seven_cycle_platform.storage.manifest import load_manifest, verify_manifest


def ensure_seed_catalog(project_root: Path) -> tuple[str, str]:
    product_root = project_root / "products" / "circle"
    run_id = json.loads(
        (product_root / "latest.json").read_text(encoding="utf-8")
    )["run_id"]
    run_dir = product_root / "runs" / run_id
    manifest = verify_manifest(run_dir, expected=load_manifest(run_dir))
    catalog_path = product_root / "catalogs" / f"{run_id}.duckdb"

    try:
        connection = open_catalog(
            catalog_path,
            run_dir=run_dir,
            expected_manifest=manifest,
        )
    except (CatalogError, OSError):
        build_catalog(run_dir, catalog_path, expected_manifest=manifest)
        return "rebuilt", run_id

    connection.close()
    return "verified", run_id


if __name__ == "__main__":
    action, run_id = ensure_seed_catalog(Path(__file__).resolve().parents[1])
    print(f"Seven Cycle catalog {action}: {run_id}")
