"""Checkout-safe entry point for generic and M2 acceptance verification."""

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
    arguments = sys.argv[1:] if argv is None else argv
    return _load_package_main()(["verify", *arguments])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
