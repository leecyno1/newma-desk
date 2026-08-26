#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render monthly_returns_480m.parquet to a single HTML page of tables (per category),
rows=month, cols=assets, full 480 months.
"""
from __future__ import annotations

import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")

def main():
    src = os.path.join(OUT_DIR, "monthly_returns_480m.parquet")
    if not os.path.exists(src):
        raise SystemExit("missing monthly_returns_480m.parquet, run scripts/compute_monthly_returns_480m.py first")
    df = pd.read_parquet(src)
    parts = []
    head = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>480个月月度回报（复权/指数增长率）</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; margin: 24px; }
    h2 { margin-top: 28px; }
    table { border-collapse: collapse; width: 100%; margin: 12px 0 28px; font-size: 12px; }
    th, td { border: 1px solid #ddd; padding: 4px 6px; text-align: right; }
    th:first-child, td:first-child { text-align: left; white-space: nowrap; position: sticky; left: 0; background: #fff; }
    thead th { background: #f6f8fa; position: sticky; top: 0; }
    tr:nth-child(even) { background: #fafafa; }
    .wrap { overflow: auto; max-height: 80vh; border: 1px solid #eee; }
  </style>
</head>
<body>
  <h1>480个月月度回报（复权/指数增长率）</h1>
  <p>注：数值为百分比；A股优先ETF累计净值，海外优先OpenBB yfinance(含分红)。</p>
"""
    parts.append(head)
    for cat in df.columns.get_level_values(0).unique():
        sub = df[cat].copy() * 100.0
        sub = sub.round(2)
        # 行: 指数（资产），列: 时间
        sub.index = [d.strftime("%Y-%m") for d in sub.index]
        sub = sub.T
        sub.columns = [str(c) for c in sub.columns]
        sub.index.name = "资产"
        html_table = sub.to_html(border=0, escape=False)
        parts.append(f"<h2>{cat}（全480个月, %）</h2>\n<div class='wrap'>{html_table}</div>")
    parts.append("</body></html>")
    out_path = os.path.join(OUT_DIR, "monthly_returns_480m.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
