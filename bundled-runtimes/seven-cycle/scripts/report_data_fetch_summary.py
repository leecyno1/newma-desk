from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class WindowSpec:
    name: str
    start: str
    end: str
    expected_points: int


MONTHLY_WINDOW = WindowSpec("monthly_2000_2024", "2000-01-31", "2024-12-31", 300)
ANNUAL_WINDOW = WindowSpec("annual_1960_2024", "1960-12-31", "2024-12-31", 65)


def _pct(x: float) -> str:
    if pd.isna(x):
        return "NA"
    return f"{x * 100:.1f}%"


def _fmt_dt(x) -> str:
    if pd.isna(x):
        return "NA"
    try:
        return pd.Timestamp(x).strftime("%Y-%m-%d")
    except Exception:
        return str(x)


def _coverage_stats(values: pd.Series) -> dict[str, float]:
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return {"count": 0}
    return {
        "count": float(len(s)),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "p10": float(s.quantile(0.10)),
        "p25": float(s.quantile(0.25)),
        "p75": float(s.quantile(0.75)),
        "p90": float(s.quantile(0.90)),
        "min": float(s.min()),
        "max": float(s.max()),
    }


def _write_panel_column_coverage(
    panel: pd.DataFrame, window: WindowSpec, out_csv: Path, out_top_missing_csv: Path, top_n: int = 80
) -> dict[str, object]:
    w = panel.loc[pd.Timestamp(window.start) : pd.Timestamp(window.end)]
    expected = window.expected_points
    if len(w) != expected:
        # Still compute, but record what we actually got.
        expected = len(w)

    coverage = w.notna().mean().rename("coverage")
    missing = (1.0 - coverage).rename("missing")
    first_non_null = w.apply(lambda s: s.first_valid_index()).rename("first_non_null")
    last_non_null = w.apply(lambda s: s.last_valid_index()).rename("last_non_null")

    out = pd.concat([coverage, missing, first_non_null, last_non_null], axis=1)
    out.index.name = "column"
    out = out.reset_index()
    out.to_csv(out_csv, index=False)

    top_missing = out.sort_values(["missing", "column"], ascending=[False, True]).head(top_n)
    top_missing.to_csv(out_top_missing_csv, index=False)

    stats = _coverage_stats(coverage)
    stats.update(
        {
            "panel_points_in_window": int(len(w)),
            "panel_columns": int(panel.shape[1]),
            "complete_columns": int((coverage == 1.0).sum()),
            "any_data_columns": int((coverage > 0.0).sum()),
            "window_expected_points_used": int(expected),
        }
    )
    return stats


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    data_dir = root / "data"

    mapping_csv = out_dir / "indicator_universe_latest_mapped.csv"
    monthly_panel_path = data_dir / "indicator_panel_monthly.parquet"
    annual_panel_path = data_dir / "indicator_panel_annual.parquet"

    if not mapping_csv.exists():
        raise FileNotFoundError(f"Missing mapping file: {mapping_csv}")
    if not monthly_panel_path.exists():
        raise FileNotFoundError(f"Missing monthly panel: {monthly_panel_path}")
    if not annual_panel_path.exists():
        raise FileNotFoundError(f"Missing annual panel: {annual_panel_path}")

    df = pd.read_csv(mapping_csv)
    monthly = pd.read_parquet(monthly_panel_path)
    annual = pd.read_parquet(annual_panel_path)

    # Basic indicator registry totals (sanity)
    try:
        from cycle_analysis_system.indicators.indicator_registry import INDICATORS  # noqa: WPS433

        registry_count = len(INDICATORS)
    except Exception:
        registry_count = int(len(df))

    # Panel column type split (rough; suffix-based)
    def col_bucket(c: str) -> str:
        if c.endswith("_RET"):
            return "RET"
        if c.endswith("_LEVEL"):
            return "LEVEL"
        if c.endswith("_YOY"):
            return "YOY"
        if c.endswith("_MOM"):
            return "MOM"
        return "OTHER"

    monthly_bucket = pd.Series([col_bucket(c) for c in monthly.columns]).value_counts()
    annual_bucket = pd.Series([col_bucket(c) for c in annual.columns]).value_counts()

    # Indicator-level coverage stats (from mapped CSV)
    monthly_cov = pd.to_numeric(df.get("monthly_coverage_2000_2024", np.nan), errors="coerce")
    annual_cov = pd.to_numeric(df.get("annual_coverage_1960_2024", np.nan), errors="coerce")
    monthly_cov_stats = _coverage_stats(monthly_cov)
    annual_cov_stats = _coverage_stats(annual_cov)

    # Column-level coverage stats (from actual panels)
    monthly_cov_csv = out_dir / "monthly_panel_column_coverage_2000_2024.csv"
    monthly_top_missing_csv = out_dir / "monthly_panel_top_missing_2000_2024.csv"
    annual_cov_csv = out_dir / "annual_panel_column_coverage_1960_2024.csv"
    annual_top_missing_csv = out_dir / "annual_panel_top_missing_1960_2024.csv"

    monthly_panel_stats = _write_panel_column_coverage(monthly, MONTHLY_WINDOW, monthly_cov_csv, monthly_top_missing_csv)
    annual_panel_stats = _write_panel_column_coverage(annual, ANNUAL_WINDOW, annual_cov_csv, annual_top_missing_csv)

    # Group summaries
    def group_counts(col: str) -> pd.DataFrame:
        if col not in df.columns:
            return pd.DataFrame(columns=[col, "count"])
        g = df.groupby(col, dropna=False).size().rename("count").reset_index()
        g[col] = g[col].fillna("NA")
        return g.sort_values(["count", col], ascending=[False, True])

    by_universe = group_counts("universe_category")
    by_source = group_counts("primary_source")
    by_backend = group_counts("backend").head(25)
    by_base_freq = group_counts("base_freq")
    by_value_type = group_counts("value_type")

    def group_coverage(universe_category: str, cov_col: str) -> pd.DataFrame:
        if universe_category not in df.columns or cov_col not in df.columns:
            return pd.DataFrame()
        tmp = df[[universe_category, cov_col]].copy()
        tmp[cov_col] = pd.to_numeric(tmp[cov_col], errors="coerce")
        g = (
            tmp.groupby(universe_category, dropna=False)[cov_col]
            .agg(["count", "mean", "median", "min", "max"])
            .reset_index()
            .sort_values(["mean", "count"], ascending=[False, False])
        )
        return g

    cov_by_cat_monthly = group_coverage("universe_category", "monthly_coverage_2000_2024")
    cov_by_cat_annual = group_coverage("universe_category", "annual_coverage_1960_2024")

    # Range stats from mapping (indicator main columns)
    monthly_present = df.get("monthly_present", False)
    annual_present = df.get("annual_present", False)
    monthly_first = pd.to_datetime(df.get("monthly_first", pd.NaT), errors="coerce")
    monthly_last = pd.to_datetime(df.get("monthly_last", pd.NaT), errors="coerce")
    annual_first = pd.to_datetime(df.get("annual_first", pd.NaT), errors="coerce")
    annual_last = pd.to_datetime(df.get("annual_last", pd.NaT), errors="coerce")

    monthly_min = monthly_first[monthly_present == True].min()  # noqa: E712
    monthly_max = monthly_last[monthly_present == True].max()  # noqa: E712
    annual_min = annual_first[annual_present == True].min()  # noqa: E712
    annual_max = annual_last[annual_present == True].max()  # noqa: E712

    # Output markdown
    report_path = out_dir / "data_fetch_summary.md"
    lines: list[str] = []
    lines.append("# Data Fetch Summary")
    lines.append("")
    lines.append(f"- Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## Key Outputs")
    lines.append(f"- Indicator mapping (per-indicator details): `{mapping_csv.relative_to(root)}`")
    lines.append(f"- Monthly panel: `{monthly_panel_path.relative_to(root)}`")
    lines.append(f"- Annual panel: `{annual_panel_path.relative_to(root)}`")
    lines.append(f"- Window completeness report: `output/indicator_panel_completeness.md`")
    lines.append(f"- Monthly column coverage CSV: `{monthly_cov_csv.relative_to(root)}`")
    lines.append(f"- Annual column coverage CSV: `{annual_cov_csv.relative_to(root)}`")
    lines.append("")

    lines.append("## Panels")
    lines.append(f"- Indicators (registry): {registry_count}")
    lines.append(f"- Monthly panel shape: {monthly.shape[0]} rows × {monthly.shape[1]} cols; index {monthly.index.min().date()} ~ {monthly.index.max().date()}")
    lines.append(f"- Annual panel shape: {annual.shape[0]} rows × {annual.shape[1]} cols; index {annual.index.min().date()} ~ {annual.index.max().date()}")
    lines.append("")
    lines.append("### Panel Column Types (suffix-based)")
    lines.append(f"- Monthly: {', '.join([f'{k}={int(v)}' for k,v in monthly_bucket.items()])}")
    lines.append(f"- Annual: {', '.join([f'{k}={int(v)}' for k,v in annual_bucket.items()])}")
    lines.append("")

    lines.append("## Indicator Universe (main columns)")
    lines.append(f"- Monthly main-column date range (any data): {_fmt_dt(monthly_min)} ~ {_fmt_dt(monthly_max)}")
    lines.append(f"- Annual main-column date range (any data): {_fmt_dt(annual_min)} ~ {_fmt_dt(annual_max)}")
    lines.append("")

    def _md_table(frame: pd.DataFrame, max_rows: int = 30) -> list[str]:
        if frame.empty:
            return ["(empty)"]
        f = frame.head(max_rows).copy()
        return ["```", f.to_string(index=False), "```"]

    lines.append("### Counts by Universe Category")
    lines += _md_table(by_universe, max_rows=50)
    lines.append("")

    lines.append("### Counts by Data Source")
    lines += _md_table(by_source, max_rows=20)
    lines.append("")

    lines.append("### Counts by Base Frequency (raw)")
    lines += _md_table(by_base_freq, max_rows=20)
    lines.append("")

    lines.append("### Counts by Value Type")
    lines += _md_table(by_value_type, max_rows=30)
    lines.append("")

    lines.append("### Top Backends (by indicator count)")
    lines += _md_table(by_backend, max_rows=25)
    lines.append("")

    lines.append("## Coverage & Missingness")
    lines.append(f"- Window (monthly): {MONTHLY_WINDOW.start} ~ {MONTHLY_WINDOW.end} (expected {MONTHLY_WINDOW.expected_points} points)")
    lines.append(f"- Window (annual):  {ANNUAL_WINDOW.start} ~ {ANNUAL_WINDOW.end} (expected {ANNUAL_WINDOW.expected_points} points)")
    lines.append("")

    lines.append("### Indicator-level Coverage (main columns; from mapping CSV)")
    if monthly_cov_stats.get("count", 0) == 0:
        lines.append("- Monthly: NA")
    else:
        lines.append(
            "- Monthly: "
            + f"mean={_pct(monthly_cov_stats['mean'])}, median={_pct(monthly_cov_stats['median'])}, "
            + f"p10={_pct(monthly_cov_stats['p10'])}, p90={_pct(monthly_cov_stats['p90'])}, "
            + f"min={_pct(monthly_cov_stats['min'])}, max={_pct(monthly_cov_stats['max'])}"
        )
    if annual_cov_stats.get("count", 0) == 0:
        lines.append("- Annual: NA")
    else:
        lines.append(
            "- Annual: "
            + f"mean={_pct(annual_cov_stats['mean'])}, median={_pct(annual_cov_stats['median'])}, "
            + f"p10={_pct(annual_cov_stats['p10'])}, p90={_pct(annual_cov_stats['p90'])}, "
            + f"min={_pct(annual_cov_stats['min'])}, max={_pct(annual_cov_stats['max'])}"
        )
    lines.append("")

    lines.append("### Column-level Coverage (all panel columns; computed from panels)")
    lines.append(
        "- Monthly: "
        + f"complete={monthly_panel_stats['complete_columns']}/{monthly_panel_stats['panel_columns']}, "
        + f"mean={_pct(monthly_panel_stats.get('mean', np.nan))}, "
        + f"p10={_pct(monthly_panel_stats.get('p10', np.nan))}, "
        + f"min={_pct(monthly_panel_stats.get('min', np.nan))}"
    )
    lines.append(
        "- Annual:  "
        + f"complete={annual_panel_stats['complete_columns']}/{annual_panel_stats['panel_columns']}, "
        + f"mean={_pct(annual_panel_stats.get('mean', np.nan))}, "
        + f"p10={_pct(annual_panel_stats.get('p10', np.nan))}, "
        + f"min={_pct(annual_panel_stats.get('min', np.nan))}"
    )
    lines.append("")
    lines.append(f"- Top missing (monthly columns): `{monthly_top_missing_csv.relative_to(root)}`")
    lines.append(f"- Top missing (annual columns): `{annual_top_missing_csv.relative_to(root)}`")
    lines.append("")

    if not cov_by_cat_monthly.empty:
        lines.append("### Monthly Coverage by Universe Category (mean/median)")
        lines += _md_table(cov_by_cat_monthly, max_rows=50)
        lines.append("")
    if not cov_by_cat_annual.empty:
        lines.append("### Annual Coverage by Universe Category (mean/median)")
        lines += _md_table(cov_by_cat_annual, max_rows=50)
        lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {report_path.relative_to(root)}")


if __name__ == "__main__":
    main()

