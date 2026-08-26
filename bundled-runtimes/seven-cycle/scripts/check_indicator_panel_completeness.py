"""
Check completeness of the monthly/annual indicator panels.

Panels:
- data/indicator_panel_monthly.parquet
- data/indicator_panel_annual.parquet

Completeness definition (defaults):
- Monthly: all months from 2000-01 to 2024-12 (month-end) are present with non-null values.
- Annual: all year-ends from 1960 to 2024 are present with non-null values.

Outputs:
- output/indicator_panel_completeness.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class WindowSpec:
    start: str
    end: str
    freq: str  # "M" or "A"


MONTHLY_WINDOW = WindowSpec(start="2000-01-31", end="2024-12-31", freq="M")
ANNUAL_WINDOW = WindowSpec(start="1960-12-31", end="2024-12-31", freq="A")


def expected_index(window: WindowSpec) -> pd.DatetimeIndex:
    start = pd.Timestamp(window.start)
    end = pd.Timestamp(window.end)
    if window.freq == "M":
        return pd.date_range(start=start, end=end, freq="ME")
    if window.freq == "A":
        return pd.date_range(start=start, end=end, freq="YE-DEC")
    raise ValueError(f"Unsupported freq: {window.freq}")


def _max_consecutive_missing(mask_missing: pd.Series) -> int:
    max_run = 0
    run = 0
    for v in mask_missing.astype(bool).values:
        if v:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return int(max_run)


def column_stats(df: pd.DataFrame, window: WindowSpec) -> pd.DataFrame:
    idx = expected_index(window)
    dfw = df.reindex(idx)

    records = []
    for col in dfw.columns:
        s = dfw[col]
        missing = s.isna()
        non_na = s.dropna()
        records.append(
            {
                "column": col,
                "expected_points": int(len(idx)),
                "available_points": int(non_na.shape[0]),
                "missing_points": int(missing.sum()),
                "coverage": float(non_na.shape[0] / len(idx)) if len(idx) else 0.0,
                "first_non_null": non_na.index.min() if not non_na.empty else pd.NaT,
                "last_non_null": non_na.index.max() if not non_na.empty else pd.NaT,
                "max_consecutive_missing": _max_consecutive_missing(missing),
                "is_complete": bool(missing.sum() == 0),
            }
        )

    out = (
        pd.DataFrame.from_records(records)
        .set_index("column")
        .sort_values(["is_complete", "coverage", "missing_points"], ascending=[False, False, True])
    )
    return out


def _load_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run scripts/build_indicator_panel_multi_source.py first.")
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df.sort_index()


def build_report() -> str:
    monthly_path = Path("data") / "indicator_panel_monthly.parquet"
    annual_path = Path("data") / "indicator_panel_annual.parquet"

    df_m = _load_panel(monthly_path)
    df_a = _load_panel(annual_path)

    stats_m = column_stats(df_m, MONTHLY_WINDOW)
    stats_a = column_stats(df_a, ANNUAL_WINDOW)

    complete_m = stats_m[stats_m["is_complete"]]
    complete_a = stats_a[stats_a["is_complete"]]

    lines: list[str] = []
    lines.append("# Indicator Panel Completeness Report")
    lines.append("")
    lines.append("## Windows")
    lines.append("")
    lines.append(
        f"- Monthly window: {MONTHLY_WINDOW.start} ~ {MONTHLY_WINDOW.end} (month-end, expected {len(expected_index(MONTHLY_WINDOW))} points)"
    )
    lines.append(
        f"- Annual window:  {ANNUAL_WINDOW.start} ~ {ANNUAL_WINDOW.end} (year-end, expected {len(expected_index(ANNUAL_WINDOW))} points)"
    )
    lines.append("")

    lines.append("## Monthly Panel Summary")
    lines.append("")
    lines.append(f"- Panel path: `{monthly_path}`")
    lines.append(f"- Panel index range: {df_m.index.min().date()} ~ {df_m.index.max().date()}")
    lines.append(f"- Columns: {df_m.shape[1]}")
    lines.append(f"- Complete columns (no missing within window): {complete_m.shape[0]}")
    lines.append("")
    if not complete_m.empty:
        lines.append("### Monthly Complete Columns")
        lines.append("")
        lines.append(
            complete_m.reset_index()[["column", "coverage", "first_non_null", "last_non_null"]].to_markdown(index=False)
        )
        lines.append("")
    lines.append("### Monthly Coverage Table (top 50 by completeness/coverage)")
    lines.append("")
    lines.append(stats_m.reset_index().head(50).to_markdown(index=False))
    lines.append("")

    lines.append("## Annual Panel Summary")
    lines.append("")
    lines.append(f"- Panel path: `{annual_path}`")
    lines.append(f"- Panel index range: {df_a.index.min().date()} ~ {df_a.index.max().date()}")
    lines.append(f"- Columns: {df_a.shape[1]}")
    lines.append(f"- Complete columns (no missing within window): {complete_a.shape[0]}")
    lines.append("")
    if not complete_a.empty:
        lines.append("### Annual Complete Columns")
        lines.append("")
        lines.append(
            complete_a.reset_index()[["column", "coverage", "first_non_null", "last_non_null"]].to_markdown(index=False)
        )
        lines.append("")
    lines.append("### Annual Coverage Table (top 50 by completeness/coverage)")
    lines.append("")
    lines.append(stats_a.reset_index().head(50).to_markdown(index=False))
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "indicator_panel_completeness.md"
    out_path.write_text(build_report(), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
