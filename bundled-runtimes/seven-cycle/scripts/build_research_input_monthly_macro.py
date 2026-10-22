"""Compatibility entry point for the packaged monthly panel builder."""

from pathlib import Path
import sys


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    root = _project_root()
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from seven_cycle_platform.legacy.monthly_research_panel import build_panel

    result = build_panel(input_root=root, output_root=root)
    for key in ("panel", "selection", "report"):
        print("Wrote:", result[key])


if __name__ == "__main__":
    main()
