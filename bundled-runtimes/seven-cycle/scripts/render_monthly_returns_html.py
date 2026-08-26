#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render monthly_returns_20y.parquet to an HTML page of tables (per category).
Saves to output/monthly_returns_20y.html
"""
from __future__ import annotations

import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")

def main():
    src = os.path.join(OUT_DIR, "monthly_returns_20y.parquet")
    if not os.path.exists(src):
        raise SystemExit("missing monthly_returns_20y.parquet, run scripts/compute_monthly_returns_20y.py first")
    df = pd.read_parquet(src)
    parts = []
    # basic CSS
    head = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>20年间月度回报（复权/指数增长率）</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; margin: 24px; }
    h2 { margin-top: 28px; }
    table { border-collapse: collapse; width: 100%; margin: 12px 0 28px; font-size: 13px; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: right; }
    th:first-child, td:first-child { text-align: left; white-space: nowrap; }
    thead th { background: #f6f8fa; position: sticky; top: 0; }
    tr:nth-child(even) { background: #fafafa; }
  </style>
</head>
<body>
  <h1>20年间月度回报（复权/指数增长率）</h1>
  <p>口径：A股优先ETF累计净值，海外优先OpenBB yfinance(含分红)；其余为指数点位。</p>
"""
    parts.append(head)
    for cat in df.columns.get_level_values(0).unique():
        sub = df[cat].copy()
        tail = (sub.tail(24) * 100.0).round(2)
        # 行: 指数（资产），列: 时间
        tail.index = [d.strftime("%Y-%m") for d in tail.index]
        tail = tail.T  # transpose: rows=assets, cols=months
        tail.columns = [str(c) for c in tail.columns]
        tail.index.name = "资产"
        html_table = tail.to_html(border=0, escape=False)
        parts.append(f"<h2>{cat}（最近24个月, %）</h2>\n{html_table}")
    parts.append("</body></html>")
    out_path = os.path.join(OUT_DIR, "monthly_returns_20y.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
