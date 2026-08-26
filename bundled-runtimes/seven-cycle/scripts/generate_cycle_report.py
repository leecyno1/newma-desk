#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a Markdown report for cycle decomposition artifacts.
"""
from __future__ import annotations

import os
import glob
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
CYCL_DIR = os.path.join(OUT_DIR, "cycles")
PLOT_DIR = os.path.join(CYCL_DIR, "plots")


def main():
    phase_files = sorted(glob.glob(os.path.join(CYCL_DIR, "phase_*.parquet")))
    lines = []
    lines.append("# Cycle Decomposition Report (1984-2024)")
    lines.append("")
    lines.append("周期：200 / 100 / 42 / 21 / 12 个月；方法：巴特沃斯带通 + Hilbert 相位；超过±35%偏离的周期点视为异常并屏蔽。")
    lines.append("")
    for pf in phase_files:
        base = os.path.basename(pf).replace("phase_", "").replace(".parquet", "")
        lines.append(f"## {base}")
        comp_img = os.path.join("cycles", "plots", f"{base}_components.png")
        phase_img = os.path.join("cycles", "plots", f"{base}_phase_heatmap.png")
        if os.path.exists(os.path.join(OUT_DIR, comp_img)):
            lines.append(f"![components]({comp_img})")
        if os.path.exists(os.path.join(OUT_DIR, phase_img)):
            lines.append(f"![phase]({phase_img})")
        lines.append("")
    md_path = os.path.join(OUT_DIR, "cycle_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()

