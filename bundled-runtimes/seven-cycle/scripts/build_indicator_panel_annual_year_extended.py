"""
Build an *extended* annual panel with an integer year index.

This merges:
- data/indicator_panel_annual.parquet (1951+; DatetimeIndex year-end)
- data/indicator_panel_annual_long_history_year.parquet (1600+; year index)

Output:
- data/indicator_panel_annual_year_extended.parquet
- output/annual_year_extended_summary.md
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        s = df[c]
        non_null = int(s.notna().sum())
        start = int(s.dropna().index.min()) if non_null else None
        end = int(s.dropna().index.max()) if non_null else None
        rows.append(
            {
                "column": c,
                "non_null": non_null,
                "start_year": start,
                "end_year": end,
                "missing_pct": float((1 - non_null / len(s)) * 100) if len(s) else 100.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["missing_pct", "column"]).reset_index(drop=True)


def main(
    *,
    annual_path: Path = Path("data/indicator_panel_annual.parquet"),
    long_path: Path = Path("data/indicator_panel_annual_long_history_year.parquet"),
    out_path: Path = Path("data/indicator_panel_annual_year_extended.parquet"),
    summary_path: Path = Path("output/annual_year_extended_summary.md"),
) -> None:
    if not annual_path.exists():
        raise FileNotFoundError(annual_path)
    if not long_path.exists():
        raise FileNotFoundError(long_path)

    annual = pd.read_parquet(annual_path)
    if not isinstance(annual.index, pd.DatetimeIndex):
        raise TypeError(f"Expected DatetimeIndex in {annual_path}, got {type(annual.index)}")
    annual_year = annual.copy()
    annual_year.index = pd.Index(annual_year.index.year.astype(int), name="year")
    annual_year = annual_year.groupby(level=0).last().sort_index()

    long_df = pd.read_parquet(long_path)
    if long_df.index.name != "year":
        long_df.index = pd.Index(long_df.index.astype(int), name="year")
    long_df = long_df.sort_index()

    merged = long_df.join(annual_year, how="outer").sort_index()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(out_path)

    summ = _summary(merged)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Annual year-index panel (extended)",
        "",
        f"- Output: `{out_path}`",
        f"- Source annual panel: `{annual_path}`",
        f"- Source long-history panel: `{long_path}`",
        f"- Shape: {merged.shape[0]} years × {merged.shape[1]} columns",
        f"- Year range: {int(merged.index.min())}–{int(merged.index.max())}",
        "",
        "## Coverage summary",
        "",
        summ.to_markdown(index=False),
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

