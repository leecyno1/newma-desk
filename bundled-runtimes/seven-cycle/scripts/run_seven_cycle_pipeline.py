"""Compatibility entry point for the seven-cycle package CLI."""

from collections.abc import Callable, Sequence
from pathlib import Path
import sys


def _load_package_main() -> Callable[[Sequence[str] | None], int]:
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    from seven_cycle_platform.cli import main

    return main


def main(argv: Sequence[str] | None = None) -> int:
    return _load_package_main()(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
