"""
Merge the very-long history panel with the World Bank wide panel.

Outputs:
- data/indicator_panel_annual_very_long_history_year.parquet
- output/annual_very_long_history_summary.md
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd


def _summary_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        s = df[c]
        non_null = int(s.notna().sum())
        total = int(len(df))
        start = int(s.dropna().index.min()) if non_null else None
        end = int(s.dropna().index.max()) if non_null else None
        rows.append(
            {
                "column": c,
                "non_null": non_null,
                "total_years": total,
                "start_year": start,
                "end_year": end,
                "missing_pct": float((1 - non_null / total) * 100) if total else 100.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["missing_pct", "column"]).reset_index(drop=True)


def main() -> None:
    base_path = Path("data/indicator_panel_annual_very_long_history_year.parquet")
    wb_path = Path("data/indicator_panel_annual_worldbank_wide_year.parquet")
    out_path = Path("data/indicator_panel_annual_very_long_history_year.parquet")
    summary_path = Path("output/annual_very_long_history_summary.md")

    if not base_path.exists():
        raise FileNotFoundError(base_path)
    if not wb_path.exists():
        raise FileNotFoundError(wb_path)

    base = pd.read_parquet(base_path)
    wb = pd.read_parquet(wb_path)

    if base.index.name != "year":
        base.index = pd.Index(base.index.astype(int), name="year")
    if wb.index.name != "year":
        wb.index = pd.Index(wb.index.astype(int), name="year")

    overlap = base.columns.intersection(wb.columns)
    wb_new = wb.drop(columns=overlap, errors="ignore")
    merged = base.join(wb_new, how="outer").sort_index()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(out_path)

    summ = _summary_table(merged)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Annual long-history panel (year index)",
        "",
        f"- Output: `{out_path}`",
        f"- Year range requested: {int(merged.index.min())}–{int(merged.index.max())}",
        f"- Panel shape: {merged.shape[0]} years × {merged.shape[1]} columns",
        "- Note: year index is integer (pre-1677 timestamps are out-of-bounds for pandas)",
        "",
        "## Coverage summary",
        "",
        summ.to_markdown(index=False),
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
