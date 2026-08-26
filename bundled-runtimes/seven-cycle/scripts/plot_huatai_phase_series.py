"""
Plot 200/100/42-month cycle components and phase labels for CPI/PPI etc.

This script reads the pre-computed phase parquet files produced by
`huatai_cycle_phase_timeline.py` and generates PNG plots under `output/plots`.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import matplotlib.pyplot as plt

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


PHASE_FILES = [
    "huatai_phase_macro_cpi_yoy.parquet",
    "huatai_phase_macro_ppi_yoy.parquet",
    "huatai_phase_idx_sh_comp_ret_m.parquet",
    "huatai_phase_idx_hs300_ret_m.parquet",
]

PERIODS_TO_PLOT = [200, 100, 42]

PHASE_COLORS = {
    "Up": "tab:green",
    "High": "tab:orange",
    "Down": "tab:red",
    "Low": "tab:blue",
}


def plot_series(path: Path) -> None:
    df = pd.read_parquet(path)
    name = path.stem  # e.g. huatai_phase_macro_cpi_yoy

    out_dir = Path("output") / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}_cycles.png"

    fig, axes = plt.subplots(len(PERIODS_TO_PLOT) + 1, 1, figsize=(12, 8), sharex=True)

    # Original
    axes[0].plot(df.index, df["Original"], color="black", linewidth=1)
    axes[0].set_title(f"{name} - Original and Cycle Components")
    axes[0].grid(True, alpha=0.3)

    # Cycle components with phase-colored segments
    for ax, p in zip(axes[1:], PERIODS_TO_PLOT):
        comp_col = f"Cycle_{p}m"
        phase_col = f"PhaseLabel_{p}m"
        if comp_col not in df.columns or phase_col not in df.columns:
            ax.set_visible(False)
            continue

        comp = df[comp_col]
        phase = df[phase_col]

        # Plot line segments by phase
        for phase_name, color in PHASE_COLORS.items():
            mask = phase == phase_name
            if mask.any():
                ax.plot(df.index[mask], comp[mask], color=color, label=phase_name)

        ax.set_ylabel(f"{p}m")
        ax.grid(True, alpha=0.3)

    # Build a combined legend for the last subplot
    handles = []
    labels = []
    for phase_name, color in PHASE_COLORS.items():
        handles.append(plt.Line2D([0], [0], color=color, lw=2))
        labels.append(phase_name)
    axes[-1].legend(handles, labels, loc="upper right")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    print(f"Saved {out_path}")


def main() -> None:
    data_dir = Path("data")
    for fname in PHASE_FILES:
        path = data_dir / fname
        if not path.exists():
            print(f"Skip {fname}: file not found")
            continue
        plot_series(path)


if __name__ == "__main__":
    main()

