"""
Impute missing values for the selected "cycle representative indicator" groups.

Why?
- Decomposition / phase-labelling works best on contiguous series.
- The selected representative list is small (vs 700+ full universe), so we can
  impute conservatively and keep the process auditable.

Method (per series)
- Only impute *internal* missing values between first_valid and last_valid.
- Use time interpolation + ffill/bfill (no extrapolation beyond observed range).

Inputs
- output/cycle_representative_indicators.csv
- data/indicator_panel_monthly.parquet
- data/indicator_panel_annual.parquet

Outputs
- data/cycle_representatives_monthly_imputed.parquet
- data/cycle_representatives_annual_imputed.parquet
- output/cycle_representatives_imputation_report.csv
- output/cycle_representatives_imputation_report.md
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _impute_internal_time(s: pd.Series) -> tuple[pd.Series, dict[str, object]]:
    s = s.sort_index()
    first = s.first_valid_index()
    last = s.last_valid_index()

    meta: dict[str, object] = {
        "first_valid": first,
        "last_valid": last,
        "n_total": int(len(s)),
        "n_non_null": int(s.notna().sum()),
        "n_missing": int(s.isna().sum()),
        "n_filled": 0,
    }

    if first is None or last is None or first >= last:
        return s, meta

    w = s.loc[first:last].copy()
    missing_before = int(w.isna().sum())
    if missing_before == 0:
        meta.update({"n_filled": 0, "missing_window_before": 0, "missing_window_after": 0})
        return s, meta

    w2 = w.interpolate(method="time").ffill().bfill()
    missing_after = int(w2.isna().sum())
    filled = max(0, missing_before - missing_after)

    out = s.copy()
    out.loc[first:last] = w2
    meta.update(
        {
            "missing_window_before": missing_before,
            "missing_window_after": missing_after,
            "n_filled": filled,
        }
    )
    return out, meta


def _report_to_md(df: pd.DataFrame) -> str:
    if df.empty:
        return "(empty)"
    cols = [
        "freq",
        "column",
        "missing_window_before",
        "missing_window_after",
        "n_filled",
        "first_valid",
        "last_valid",
    ]
    show = df[cols].copy()
    show = show.sort_values(["n_filled", "missing_window_before"], ascending=[False, False])
    return "\n".join(
        [
            "# Cycle Representatives – Imputation Report",
            "",
            "Rule: only fill missing values within [first_valid, last_valid] using time interpolation.",
            "",
            "## Filled rows (top)",
            "",
            show.head(50).to_markdown(index=False),
            "",
        ]
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    data_dir = root / "data"

    selected = pd.read_csv(out_dir / "cycle_representative_indicators.csv")
    monthly = pd.read_parquet(data_dir / "indicator_panel_monthly.parquet")
    annual = pd.read_parquet(data_dir / "indicator_panel_annual.parquet")

    # Unique columns by freq (some ids appear in multiple cycles)
    sel_m = selected[selected["cycle_freq_used"] == "M"].copy()
    sel_a = selected[selected["cycle_freq_used"] == "A"].copy()
    cols_m = sorted(set(sel_m["panel_main_column"].astype(str).tolist()))
    cols_a = sorted(set(sel_a["panel_main_column"].astype(str).tolist()))

    panel_m = monthly[[c for c in cols_m if c in monthly.columns]].copy()
    panel_a = annual[[c for c in cols_a if c in annual.columns]].copy()

    report_rows: list[dict[str, object]] = []

    # Monthly
    for c in panel_m.columns:
        s, meta = _impute_internal_time(panel_m[c])
        panel_m[c] = s
        report_rows.append({"freq": "M", "column": c, **meta})

    # Annual
    for c in panel_a.columns:
        s, meta = _impute_internal_time(panel_a[c])
        panel_a[c] = s
        report_rows.append({"freq": "A", "column": c, **meta})

    # Save panels
    panel_m.to_parquet(data_dir / "cycle_representatives_monthly_imputed.parquet")
    panel_a.to_parquet(data_dir / "cycle_representatives_annual_imputed.parquet")

    # Save reports
    rep = pd.DataFrame(report_rows)
    rep["n_filled"] = pd.to_numeric(rep.get("n_filled"), errors="coerce").fillna(0).astype(int)
    rep["missing_window_before"] = pd.to_numeric(rep.get("missing_window_before"), errors="coerce").fillna(0).astype(int)
    rep["missing_window_after"] = pd.to_numeric(rep.get("missing_window_after"), errors="coerce").fillna(0).astype(int)

    rep_path = out_dir / "cycle_representatives_imputation_report.csv"
    rep.to_csv(rep_path, index=False)

    md_path = out_dir / "cycle_representatives_imputation_report.md"
    md_path.write_text(_report_to_md(rep), encoding="utf-8")

    print("Wrote:", data_dir / "cycle_representatives_monthly_imputed.parquet")
    print("Wrote:", data_dir / "cycle_representatives_annual_imputed.parquet")
    print("Wrote:", rep_path)
    print("Wrote:", md_path)


if __name__ == "__main__":
    main()

