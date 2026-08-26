from __future__ import annotations

"""Run the robust cycle-discovery and historical-interpretation pipeline."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

STEPS = (
    "discover_cycle_periods_robust.py",
    "compare_cycle_filters_robustness.py",
    "cycle_phase_timeline_long_short_hybrid.py",
    "build_robust_cycle_composites.py",
    "build_cycle_historical_event_study.py",
    "verify_cycle_research_robustness.py",
)


def main() -> None:
    for position, script_name in enumerate(STEPS, start=1):
        script_path = ROOT / "scripts" / script_name
        print(f"[{position}/{len(STEPS)}] {script_name}")
        subprocess.run([sys.executable, str(script_path)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()

