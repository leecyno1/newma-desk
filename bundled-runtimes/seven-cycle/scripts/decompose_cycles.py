#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decompose each indicator into target cycle components:
periods = [200, 100, 42, 21, 12] months
- Band-pass filter around each period
- Hilbert transform to get phase
- Flag abnormal cycles with large period deviations
Outputs:
- output/cycles/components_<name>.parquet (components per period)
- output/cycles/phase_<name>.parquet (phase per period)
- output/cycles/inst_period_<name>.parquet (instant period per period)
- output/cycles/plots/<name>_<period>.png (plots)
"""
from __future__ import annotations

import os
import re
from typing import Dict, List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from cycle_utils import (
    bandpass_component,
    analytic_phase,
    instantaneous_period,
    flag_outliers,
    ensure_dir,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
OUTPUT_DIR = os.path.join(ROOT, "output", "cycles")
PLOT_DIR = os.path.join(OUTPUT_DIR, "plots")
ensure_dir(OUTPUT_DIR)
ensure_dir(PLOT_DIR)

TARGET_PERIODS = [200, 100, 42, 21, 12]


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def plot_components(name: str, ts: pd.Series, comp: pd.DataFrame, phases: pd.DataFrame):
    fig, axes = plt.subplots(len(comp.columns) + 1, 1, figsize=(12, 2.4 * (len(comp.columns) + 1)), sharex=True)
    ts.plot(ax=axes[0], color="black", lw=1.0, label="Series (MoM)")
    axes[0].legend(loc="upper left")
    for i, col in enumerate(comp.columns, start=1):
        comp[col].plot(ax=axes[i], lw=1.0, label=f"Band {col}m")
        axes[i].legend(loc="upper left")
    fig.tight_layout()
    fpath = os.path.join(PLOT_DIR, f"{sanitize(name)}_components.png")
    fig.savefig(fpath, dpi=150)
    plt.close(fig)

    # Phase heatmap
    fig, ax = plt.subplots(figsize=(12, 2.6))
    ph_deg = phases.apply(np.degrees)
    sns.heatmap(ph_deg.transpose(), cmap="twilight", cbar_kws={"label": "phase (deg)"}, ax=ax)
    ax.set_title(f"Phase heatmap: {name}")
    fig.tight_layout()
    fpath2 = os.path.join(PLOT_DIR, f"{sanitize(name)}_phase_heatmap.png")
    fig.savefig(fpath2, dpi=150)
    plt.close(fig)


def main():
    df = pd.read_parquet(os.path.join(DATA_DIR, "cycle_dataset_mom.parquet"))
    # Iterate series
    for col in df.columns:
        ts = df[col].copy()
        # Require enough data
        if ts.dropna().shape[0] < 60:
            continue
        comps = {}
        phases = {}
        instTs = {}
        for P in TARGET_PERIODS:
            y = bandpass_component(ts, P, bandwidth=0.25, order=4)
            comps[P] = y
            ph = analytic_phase(y.fillna(0.0))
            phases[P] = ph
            instT = instantaneous_period(ph)
            # mask outliers
            ok = flag_outliers(instT, P, tol=0.35)
            y_masked = y.where(ok)
            comps[P] = y_masked
            instTs[P] = instT
        comp_df = pd.DataFrame(comps)
        ph_df = pd.DataFrame(phases)
        inst_df = pd.DataFrame(instTs)
        base = sanitize(col)
        comp_df.to_parquet(os.path.join(OUTPUT_DIR, f"components_{base}.parquet"))
        ph_df.to_parquet(os.path.join(OUTPUT_DIR, f"phase_{base}.parquet"))
        inst_df.to_parquet(os.path.join(OUTPUT_DIR, f"inst_period_{base}.parquet"))
        # Plots
        plot_components(col, ts, comp_df, ph_df)
    print(f"Decomposition done. Artifacts in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

