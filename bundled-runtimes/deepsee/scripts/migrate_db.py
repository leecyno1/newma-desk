#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import engine
from app.migrations import MIGRATIONS, applied_versions, pending_migrations, run_schema_migrations


def main() -> int:
    parser = argparse.ArgumentParser(description="Deepsee database migration helper")
    parser.add_argument("command", choices=["status", "apply", "plan"], nargs="?", default="status")
    args = parser.parse_args()

    if args.command == "plan":
        print(
            json.dumps(
                [{"version": item.version, "description": item.description} for item in MIGRATIONS],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "status":
        applied = applied_versions(engine)
        pending = pending_migrations(engine)
        print(
            json.dumps(
                {
                    "database": str(engine.url).replace(str(engine.url.password or ""), "***")
                    if getattr(engine.url, "password", None)
                    else str(engine.url),
                    "applied": sorted(applied),
                    "pending": [{"version": item.version, "description": item.description} for item in pending],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if not pending else 2

    executed = run_schema_migrations(engine)
    print(json.dumps({"applied_now": executed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
