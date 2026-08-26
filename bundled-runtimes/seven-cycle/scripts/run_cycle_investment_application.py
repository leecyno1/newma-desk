from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


PIPELINE = (
    "build_realtime_cycle_signals.py",
    "backtest_cycle_style_rotation_v3.py",
    "build_cycle_investment_report_v3.py",
    "verify_cycle_investment_application.py",
)


def main() -> None:
    for script_name in PIPELINE:
        script_path = ROOT / "scripts" / script_name
        print(f"Running {script_path}")
        subprocess.run([sys.executable, str(script_path)], cwd=ROOT, check=True)
    print("Cycle investment application pipeline completed")


if __name__ == "__main__":
    main()
