from __future__ import annotations

import json
from pathlib import Path

from seven_cycle_platform.catalog import build_catalog, open_catalog
from seven_cycle_platform.storage.manifest import load_manifest


PRODUCT_ROOT = Path("/Volumes/PSSD/Projects/1周期模块/products/circle")
CATALOG_ROOT = Path("/app/output/server-catalogs")


def main() -> None:
    pointer = json.loads((PRODUCT_ROOT / "latest.json").read_text(encoding="utf-8"))
    run_id = pointer["run_id"]
    run_dir = PRODUCT_ROOT / "runs" / run_id
    catalog_path = CATALOG_ROOT / f"{run_id}.duckdb"
    manifest = load_manifest(run_dir)

    CATALOG_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        connection = open_catalog(
            catalog_path,
            run_dir=run_dir,
            expected_manifest=manifest,
        )
    except Exception:
        catalog_path.unlink(missing_ok=True)
        result = build_catalog(
            run_dir,
            catalog_path,
            expected_manifest=manifest,
        )
        print(f"seven-cycle server catalog built: {result.run_id}", flush=True)
    else:
        connection.close()
        print(f"seven-cycle server catalog verified: {run_id}", flush=True)


if __name__ == "__main__":
    main()
