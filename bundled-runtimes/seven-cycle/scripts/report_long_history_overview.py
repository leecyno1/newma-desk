"""
Generate a compact overview for the long-history panels (annual year-index + monthly).

Outputs
- output/long_history_overview.md
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _col_summary(df: pd.DataFrame, index_kind: str) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        s = df[c]
        non = int(s.notna().sum())
        start = None
        end = None
        if non:
            start = s.dropna().index.min()
            end = s.dropna().index.max()
        rows.append({"column": c, "non_null": non, "start": start, "end": end})
    out = pd.DataFrame(rows)
    if index_kind == "year":
        out["start"] = pd.to_numeric(out["start"], errors="coerce").astype("Int64")
        out["end"] = pd.to_numeric(out["end"], errors="coerce").astype("Int64")
    return out.sort_values(["non_null", "column"], ascending=[False, True]).reset_index(drop=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_path = root / "output" / "long_history_overview.md"

    annual_path = root / "data" / "indicator_panel_annual_long_history_year.parquet"
    annual_ext_path = root / "data" / "indicator_panel_annual_year_extended.parquet"
    monthly_path = root / "data" / "indicator_panel_monthly_long_history.parquet"

    lines: list[str] = []
    lines.append("# Long-History Panel Overview")
    lines.append("")

    if annual_path.exists():
        df = pd.read_parquet(annual_path)
        lines.append("## Annual (year index)")
        lines.append(f"- File: `{annual_path}`")
        lines.append(f"- Shape: {df.shape[0]} years × {df.shape[1]} columns")
        lines.append(f"- Year range: {int(df.index.min())}–{int(df.index.max())}")
        lines.append("")

        cols = list(df.columns)
        lines.append("### Column counts (prefix heuristics)")
        lines.append("")
        lines.append("```\n" + "\n".join(
            [
                f"total: {len(cols)}",
                f"UK BoE (A1 auto): {sum(c.startswith('UK_BOE_A1_') for c in cols)}",
                f"UK BoE (all): {sum(c.startswith('UK_BOE_') for c in cols)}",
                f"UK OECD: {sum(c.startswith('UK_OECD_') for c in cols)}",
                f"EA OECD: {sum(c.startswith('EA_OECD_') for c in cols)}",
                f"US Shiller: {sum(c.startswith('US_SHILLER_') for c in cols)}",
                f"Maddison MPD: {sum(c.startswith('MPD_') for c in cols)}",
                f"*_EXT_WB: {sum(c.endswith('_EXT_WB') for c in cols)}",
                f"*_EXT_WB_GROWTH: {sum(c.endswith('_EXT_WB_GROWTH') for c in cols)}",
                f"*_EXT_OECD: {sum(c.endswith('_EXT_OECD') for c in cols)}",
            ]
        ) + "\n```")
        lines.append("")

        summ = _col_summary(df, index_kind="year").head(40)
        lines.append("### Best-covered columns (top 40)")
        lines.append("")
        lines.append(summ.to_markdown(index=False))
        lines.append("")

    if annual_ext_path.exists():
        df = pd.read_parquet(annual_ext_path)
        lines.append("## Annual extended (year index, merged)")
        lines.append(f"- File: `{annual_ext_path}`")
        lines.append(f"- Shape: {df.shape[0]} years × {df.shape[1]} columns")
        lines.append(f"- Year range: {int(df.index.min())}–{int(df.index.max())}")
        lines.append("")

    if monthly_path.exists():
        df = pd.read_parquet(monthly_path)
        lines.append("## Monthly (month-end)")
        lines.append(f"- File: `{monthly_path}`")
        lines.append(f"- Shape: {df.shape[0]} months × {df.shape[1]} columns")
        lines.append(f"- Month range: {df.index.min().date()}–{df.index.max().date()}")
        lines.append("")
        summ = _col_summary(df, index_kind="month").head(50)
        lines.append("### Coverage (top 50)")
        lines.append("")
        lines.append(summ.to_markdown(index=False))
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("Wrote:", out_path)


if __name__ == "__main__":
    main()
