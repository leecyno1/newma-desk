"""
Fetch broad World Bank indicators in batches to avoid long runtimes or API failures.

Usage examples:
  python scripts/build_worldbank_wide_panel_batches.py --batch-index 0 --batch-count 3
  python scripts/build_worldbank_wide_panel_batches.py --countries GBR,USA,WLD
  python scripts/build_worldbank_wide_panel_batches.py --indicators NY.GDP.MKTP.KD,FP.CPI.TOTL.ZG

Outputs:
- data/indicator_panel_annual_worldbank_wide_year.parquet
- output/worldbank_wide_panel_summary.md
- output/worldbank_wide_panel_fetch_log.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from build_annual_long_history_panel import (
    WB_COUNTRY_CODES,
    WB_CORE_INDICATORS,
    WB_GOVERNANCE_INDICATORS,
    _fetch_worldbank_series,
    _to_year_index,
)


def _summary_table(df: pd.DataFrame) -> pd.DataFrame:
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
                "total_years": int(len(df)),
                "start_year": start,
                "end_year": end,
                "missing_pct": float((1 - non_null / len(df)) * 100) if len(df) else 100.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["missing_pct", "column"]).reset_index(drop=True)


def _parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-index", type=int, default=None)
    parser.add_argument("--batch-count", type=int, default=None)
    parser.add_argument("--countries", type=str, default=None)
    parser.add_argument("--indicators", type=str, default=None)
    parser.add_argument("--min-year", type=int, default=1270)
    parser.add_argument("--max-year", type=int, default=2024)
    args = parser.parse_args()

    countries = _parse_csv_list(args.countries) or WB_COUNTRY_CODES

    indicator_specs = WB_CORE_INDICATORS + WB_GOVERNANCE_INDICATORS
    if args.indicators:
        allowed = set(_parse_csv_list(args.indicators))
        indicator_specs = [x for x in indicator_specs if x[0] in allowed]

    # Partition by indicator for batch runs.
    if args.batch_index is not None or args.batch_count is not None:
        if args.batch_index is None or args.batch_count is None:
            raise SystemExit("Provide both --batch-index and --batch-count")
        total = len(indicator_specs)
        size = (total + args.batch_count - 1) // args.batch_count
        start = args.batch_index * size
        end = min(total, start + size)
        indicator_specs = indicator_specs[start:end]

    out_path = Path("data/indicator_panel_annual_worldbank_wide_year.parquet")
    log_path = Path("output/worldbank_wide_panel_fetch_log.csv")
    summary_path = Path("output/worldbank_wide_panel_summary.md")

    existing = pd.DataFrame()
    if out_path.exists():
        existing = pd.read_parquet(out_path)

    series: dict[str, pd.Series] = {}
    log_rows: list[dict[str, object]] = []
    existing_log = pd.DataFrame()
    if log_path.exists():
        try:
            existing_log = pd.read_csv(log_path)
        except Exception:
            existing_log = pd.DataFrame()

    for cc in countries:
        for indicator, suffix in indicator_specs:
            col_name = f"WB_{cc}_{suffix}"
            if not existing.empty and col_name in existing.columns:
                continue
            wb = _fetch_worldbank_series(indicator, country=cc.lower())
            if wb.dropna().empty:
                log_rows.append(
                    {
                        "country": cc,
                        "indicator": indicator,
                        "column": col_name,
                        "status": "empty",
                    }
                )
                continue
            s = _to_year_index(wb)
            series[col_name] = s
            log_rows.append(
                {
                    "country": cc,
                    "indicator": indicator,
                    "column": col_name,
                    "status": "ok",
                    "start_year": int(s.dropna().index.min()),
                    "end_year": int(s.dropna().index.max()),
                    "non_null": int(s.notna().sum()),
                }
            )

        # checkpoint after each country
        if series:
            df_new = pd.DataFrame(series)
            df_new = df_new.reindex(pd.Index(range(args.min_year, args.max_year + 1), name="year"))
            if not existing.empty:
                merged = existing.join(df_new, how="outer")
            else:
                merged = df_new
            out_path.parent.mkdir(parents=True, exist_ok=True)
            merged.to_parquet(out_path)
            existing = merged
            series.clear()

            if log_rows:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                new_log = pd.DataFrame(log_rows)
                if not existing_log.empty:
                    combined = pd.concat([existing_log, new_log], ignore_index=True)
                    combined = combined.drop_duplicates(subset=["country", "indicator", "column"], keep="last")
                    combined.to_csv(log_path, index=False)
                    existing_log = combined
                else:
                    new_log.to_csv(log_path, index=False)
                    existing_log = new_log

    if out_path.exists():
        final_df = pd.read_parquet(out_path)
        summ = _summary_table(final_df)
        lines = [
            "# World Bank wide annual panel (year index)",
            "",
            f"- Output: `{out_path}`",
            f"- Year range: {args.min_year}–{args.max_year}",
            f"- Shape: {final_df.shape[0]} years × {final_df.shape[1]} columns",
            "",
            "## Coverage summary",
            "",
            summ.to_markdown(index=False),
            "",
        ]
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
