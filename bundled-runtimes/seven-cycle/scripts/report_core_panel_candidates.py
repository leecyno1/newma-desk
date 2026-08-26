"""
Generate core panel candidate lists with window-specific coverage.

Outputs:
- output/core_panel_candidates.csv
- output/core_panel_candidates.md
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd


def _category(col: str) -> str:
    if col.startswith("MPD_"):
        return "MPD"
    if col.startswith("WB_"):
        return "WorldBank"
    if col.startswith("UK_BOE_"):
        return "BoE"
    if col.startswith("UK_OECD_") or col.startswith("EA_OECD_") or col.endswith("_OECD"):
        return "OECD"
    if col.startswith("US_SHILLER_"):
        return "Shiller"
    if col.startswith("CN_"):
        return "China"
    if col.startswith("IDX_") or col.startswith("ETF_"):
        return "China/Market"
    if col.startswith("US_FF"):
        return "US/FF"
    if col.startswith("US_") or col.startswith("EU_") or col.startswith("JP_"):
        return "Global"
    return "Other"


def _window_stats(s: pd.Series, start: int, end: int) -> tuple[float, int]:
    sub = s.loc[(s.index >= start) & (s.index <= end)]
    total = int(len(sub))
    non_null = int(sub.notna().sum())
    missing_pct = float((1 - non_null / total) * 100) if total else 100.0
    return missing_pct, total


def main() -> None:
    panel_path = Path("data/indicator_panel_annual_very_long_history_year.parquet")
    out_csv = Path("output/core_panel_candidates.csv")
    out_md = Path("output/core_panel_candidates.md")

    df = pd.read_parquet(panel_path)
    if df.index.name != "year":
        df.index = pd.Index(df.index.astype(int), name="year")

    rows = []
    for col in df.columns:
        s = df[col]
        non_null = int(s.notna().sum())
        total = int(len(s))
        start = int(s.dropna().index.min()) if non_null else None
        end = int(s.dropna().index.max()) if non_null else None
        missing_full = float((1 - non_null / total) * 100) if total else 100.0

        miss_1900, total_1900 = _window_stats(s, 1900, 2024)
        miss_1960, total_1960 = _window_stats(s, 1960, 2024)

        rows.append(
            {
                "column": col,
                "category": _category(col),
                "start_year": start,
                "end_year": end,
                "missing_pct_full": missing_full,
                "missing_pct_1900_2024": miss_1900,
                "missing_pct_1960_2024": miss_1960,
                "total_full": total,
                "total_1900_2024": total_1900,
                "total_1960_2024": total_1960,
            }
        )

    stats = pd.DataFrame(rows)

    # Tier definitions
    stats["tier_long"] = (stats["start_year"].fillna(9999) <= 1900) & (stats["missing_pct_full"] <= 10)
    stats["tier_modern"] = (stats["missing_pct_1960_2024"] <= 10)
    stats["tier_modern_relaxed"] = (stats["missing_pct_1960_2024"] <= 20)

    stats = stats.sort_values(["tier_long", "tier_modern", "missing_pct_full", "column"], ascending=[False, False, True, True])

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(out_csv, index=False)

    # Summary counts
    def _count_table(flag: str) -> pd.DataFrame:
        return (
            stats[stats[flag]]
            .groupby("category", as_index=False)
            .size()
            .sort_values("size", ascending=False)
        )

    long_tbl = _count_table("tier_long")
    modern_tbl = _count_table("tier_modern")
    modern_relaxed_tbl = _count_table("tier_modern_relaxed")

    lines = [
        "# Core panel candidates (annual)",
        "",
        f"- Input: `{panel_path}`",
        f"- Output (csv): `{out_csv}`",
        "",
        "## Tier definitions",
        "",
        "- tier_long: start_year <= 1900 AND missing_pct_full <= 10",
        "- tier_modern: missing_pct_1960_2024 <= 10",
        "- tier_modern_relaxed: missing_pct_1960_2024 <= 20",
        "",
        "## Counts by category",
        "",
        "### tier_long",
        "",
        long_tbl.to_markdown(index=False),
        "",
        "### tier_modern",
        "",
        modern_tbl.to_markdown(index=False),
        "",
        "### tier_modern_relaxed",
        "",
        modern_relaxed_tbl.to_markdown(index=False),
        "",
        "## Top 50 tier_long",
        "",
        stats[stats["tier_long"]].head(50).to_markdown(index=False),
        "",
        "## Top 50 tier_modern",
        "",
        stats[stats["tier_modern"]].head(50).to_markdown(index=False),
        "",
        "## Top 50 tier_modern_relaxed",
        "",
        stats[stats["tier_modern_relaxed"]].head(50).to_markdown(index=False),
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
