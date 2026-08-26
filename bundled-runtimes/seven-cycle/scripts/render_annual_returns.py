#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse output/annual_returns_2014_2024.md and generate per-category line charts.
Saves figures to output/annual_returns_plots/<category>_lines.png
"""
from __future__ import annotations

import os
import re
from typing import List, Tuple, Dict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_PATH = os.path.join(ROOT, "output", "annual_returns_2014_2024.md")
OUT_DIR = os.path.join(ROOT, "output", "annual_returns_plots")
os.makedirs(OUT_DIR, exist_ok=True)


def sanitize(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.\\-\\u4e00-\\u9fa5]+", "_", name)


def parse_md_tables(md_path: str) -> List[Tuple[str, pd.DataFrame]]:
    with open(md_path, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f.readlines()]
    out: List[Tuple[str, pd.DataFrame]] = []
    i = 0
    current_category = None
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("### "):  # category header
            current_category = ln[4:].strip()
            i += 1
            continue
        # find markdown table start
        if current_category and ln.startswith("| 资产 |"):
            # collect table lines until blank line
            table_lines = []
            while i < len(lines) and lines[i].strip():
                table_lines.append(lines[i].strip())
                i += 1
            # parse table
            if len(table_lines) >= 2:
                headers = [h.strip() for h in table_lines[0].strip("|").split("|")]
                # skip separator line table_lines[1]
                rows = []
                for tl in table_lines[2:]:
                    toks = [t.strip() for t in tl.strip("|").split("|")]
                    if len(toks) != len(headers):
                        continue
                    rows.append(toks)
                df = pd.DataFrame(rows, columns=headers)
                # convert year columns
                year_cols = [c for c in df.columns if c not in ("资产",)]
                for c in year_cols:
                    # strip % and convert
                    df[c] = df[c].astype(str).str.replace("%", "", regex=False).replace({"": np.nan})
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                df = df.set_index("资产")
                out.append((current_category, df))
            continue
        i += 1
    return out


def plot_category(category: str, df: pd.DataFrame):
    sns.set(style="whitegrid")
    fig, ax = plt.subplots(figsize=(12, 6))
    # years sorted
    years = sorted([int(c) for c in df.columns])
    for asset, row in df.iterrows():
        y = row.astype(float).values
        ax.plot(years, y, lw=1.2, label=str(asset))
    ax.set_title(f"{category} 年度回报（%）")
    ax.set_xlabel("Year")
    ax.set_ylabel("Return (%)")
    ax.axhline(0, color="k", lw=0.8, alpha=0.6)
    # legend outside
    n = len(df)
    if n <= 12:
        ax.legend(loc="best", fontsize=9)
    else:
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=7, ncol=1)
        fig.subplots_adjust(right=0.78)
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, f"{sanitize(category)}_lines.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main():
    cats = parse_md_tables(MD_PATH)
    saved = []
    for cat, df in cats:
        p = plot_category(cat, df)
        saved.append((cat, p))
    print("Saved plots:")
    for cat, p in saved:
        print(cat, "->", p)


if __name__ == "__main__":
    main()

