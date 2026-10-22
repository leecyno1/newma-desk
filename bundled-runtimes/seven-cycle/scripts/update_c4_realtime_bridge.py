"""Compatibility entry point for the packaged C4 research implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"


def __getattr__(name: str):
    src = str(PROJECT_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from seven_cycle_platform.legacy import c4_realtime_bridge

    return getattr(c4_realtime_bridge, name)


def main() -> None:
    build_bridge = __getattr__("build_bridge")
    fetch_c4_features = __getattr__("fetch_c4_features")
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--through")
    args = parser.parse_args()
    realtime_payload = json.loads(args.input.read_text(encoding="utf-8"))
    payload = build_bridge(
        realtime_payload,
        fetch_c4_features(),
        through=args.through,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "latest": payload["latest"],
                "output": str(args.output),
                "validation": payload["bridge_validation"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
