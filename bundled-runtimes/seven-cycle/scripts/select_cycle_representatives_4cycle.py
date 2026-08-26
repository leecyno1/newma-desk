from __future__ import annotations

"""
Select representative indicator groups for the 4-cycle framework:
200 / 100 / 42 / 20 months.

Inputs:
- output/cycle_bandpower_scores_monthly.csv
- output/cycle_bandpower_scores_annual.csv
- output/indicator_universe_latest_mapped.csv
- data/indicator_panel_monthly.parquet
- data/indicator_panel_annual.parquet

Outputs:
- output/cycle_representative_indicators_4cycle.csv
- output/cycle_representative_indicators_4cycle.md
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CycleSpec:
    months: int
    label: str
    freq: str  # 'M' or 'A'
    min_points: int
    top_k: int
    corr_threshold: float = 0.95
    keywords: tuple[str, ...] = ()


# NOTE:
# - 200m/100m use annual scoring (1960-2024 window) for statistical robustness.
# - 42m/20m use monthly scoring (2000-2024 window) for higher-resolution cycles.
CYCLES: list[CycleSpec] = [
    CycleSpec(200, "库兹涅茨/长周期(≈15-25y, center≈200m)", "A", min_points=40, top_k=18, keywords=("地产", "房地产", "房", "基建", "投资", "credit", "rate")),
    CycleSpec(100, "朱格拉/中周期(≈7-11y, center≈100m)", "A", min_points=40, top_k=18, keywords=("投资", "资本", "制造", "equipment", "capex")),
    # Keep keywords focused, otherwise generic "PMI/PPI" will crowd out true inventory-series in the extra include list.
    CycleSpec(42, "库存/基钦周期(≈3-5y, center≈42m)", "M", min_points=180, top_k=24, keywords=("产成品库存", "原材料库存", "库存", "inventory")),
    CycleSpec(20, "流动性/政策短周期(≈1-2y, center≈20m)", "M", min_points=180, top_k=24, keywords=("信用", "社融", "贷款", "M1", "M2", "shibor", "hibor", "policy", "liquidity")),
]


def prepare_regular_series(s: pd.Series, max_missing_frac: float = 0.1) -> pd.Series | None:
    s = s.sort_index()
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return None
    w = s.loc[first:last].copy()
    if len(w) < 24:
        return None
    if float(w.isna().mean()) > max_missing_frac:
        return None
    w = w.interpolate(method="time").ffill().bfill()
    return w


def transform_for_corr(s: pd.Series, value_type: str) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce")
    if value_type in {"price", "price_adj", "level"}:
        if (x > 0).all():
            x = np.log(x)
        x = x.diff()
    elif value_type == "rate_level":
        x = x.diff()
    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 24:
        return None
    std = float(x.std(ddof=0))
    if std == 0.0 or np.isnan(std):
        return None
    x = (x - float(x.mean())) / std
    return x


def greedy_dedup(
    candidates: pd.DataFrame,
    panel: pd.DataFrame,
    by_col: str = "panel_main_column",
    corr_threshold: float = 0.95,
) -> pd.DataFrame:
    kept: list[dict[str, object]] = []
    kept_series: list[pd.Series] = []

    for row in candidates.itertuples(index=False):
        col = getattr(row, by_col)
        if col not in panel.columns:
            continue
        s0 = prepare_regular_series(panel[col])
        if s0 is None:
            continue
        x = transform_for_corr(s0, value_type=getattr(row, "value_type"))
        if x is None:
            continue

        ok = True
        for ks in kept_series:
            aligned = pd.concat([x, ks], axis=1).dropna()
            if aligned.shape[0] < 36:
                continue
            corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
            if np.isfinite(corr) and abs(corr) >= corr_threshold:
                ok = False
                break
        if ok:
            kept.append(row._asdict())
            kept_series.append(x)

    return pd.DataFrame(kept)


def ensure_keywords_included(
    selected: pd.DataFrame, ranked: pd.DataFrame, keywords: tuple[str, ...], max_extra: int = 10
) -> pd.DataFrame:
    if not keywords:
        return selected
    base = selected.copy() if not selected.empty else pd.DataFrame()
    ids = set(base["id"].astype(str).tolist()) if "id" in base.columns else set()

    pattern = "|".join([k for k in keywords if k])
    if not pattern:
        return base
    hit = ranked[ranked["name"].astype(str).str.contains(pattern, case=False, regex=True, na=False)].copy()
    hit = hit[~hit["id"].astype(str).isin(ids)].head(max_extra)
    if hit.empty:
        return base
    return pd.concat([base, hit], ignore_index=True)


def to_markdown_table(df: pd.DataFrame, cols: list[str], max_rows: int = 30) -> str:
    if df.empty:
        return "(empty)"
    show = df[cols].head(max_rows).copy()
    return "```\n" + show.to_string(index=False) + "\n```"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    scores_m = pd.read_csv(out_dir / "cycle_bandpower_scores_monthly.csv")
    scores_a = pd.read_csv(out_dir / "cycle_bandpower_scores_annual.csv")
    mapping = pd.read_csv(out_dir / "indicator_universe_latest_mapped.csv")

    monthly = pd.read_parquet(root / "data" / "indicator_panel_monthly.parquet")
    annual = pd.read_parquet(root / "data" / "indicator_panel_annual.parquet")

    # Join scores with mapping for any missing text fields (defensive)
    map_cols = [
        "id",
        "name",
        "universe_category",
        "primary_source",
        "backend",
        "base_freq",
        "value_type",
        "panel_main_column",
    ]
    mapping_small = mapping[map_cols].drop_duplicates(subset=["id"])

    all_selected: list[pd.DataFrame] = []
    report_lines: list[str] = []
    report_lines.append("# Cycle Representative Indicators (4-cycle)")
    report_lines.append("")
    report_lines.append("Selection logic:")
    report_lines.append("- Score = band-power ratio around target cycle via Welch PSD on transformed series (log-diff / diff / returns).")
    report_lines.append("- Dedup within each cycle via greedy correlation filter.")
    report_lines.append("- 200m/100m use annual scoring (1960-2024 window); 42m/20m use monthly scoring (2000-2024 window).")
    report_lines.append("")

    for cyc in CYCLES:
        scores = scores_m if cyc.freq == "M" else scores_a
        panel = monthly if cyc.freq == "M" else annual

        df = scores[scores["cycle_months"] == cyc.months].copy()
        if df.empty:
            continue
        df = df.merge(mapping_small, on="id", how="left", suffixes=("", "_m"))
        # Defensive: if score CSV already had these columns and merge produced suffixed variants.
        for col in ["name", "universe_category", "primary_source", "backend", "base_freq", "value_type", "panel_main_column"]:
            if col not in df.columns and f"{col}_m" in df.columns:
                df[col] = df[f"{col}_m"]
            elif col in df.columns and f"{col}_m" in df.columns:
                df[col] = df[col].fillna(df[f"{col}_m"])

        df["bandpower_ratio"] = pd.to_numeric(df["bandpower_ratio"], errors="coerce")
        df = df.dropna(subset=["bandpower_ratio"])
        df = df[df["n_points"] >= cyc.min_points]
        df = df.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False])

        # Preselect top for dedup
        top = df.head(max(cyc.top_k * 10, 120)).copy()
        dedup = greedy_dedup(top, panel=panel, corr_threshold=cyc.corr_threshold)
        dedup = dedup.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False]).head(cyc.top_k)
        dedup = ensure_keywords_included(dedup, df, keywords=cyc.keywords)
        dedup["cycle_months"] = cyc.months
        dedup["cycle_label"] = cyc.label
        dedup["cycle_freq_used"] = cyc.freq
        all_selected.append(dedup)

        report_lines.append(f"## {cyc.months}m – {cyc.label} ({'monthly' if cyc.freq=='M' else 'annual'})")
        report_lines.append(f"- Candidates scored: {int(len(df))}")
        report_lines.append(f"- Selected (after dedup + keyword补充): {int(len(dedup))}")
        report_lines.append(
            to_markdown_table(
                dedup,
                cols=[
                    "id",
                    "name",
                    "universe_category",
                    "value_type",
                    "panel_main_column",
                    "n_points",
                    "start",
                    "end",
                    "bandpower_ratio",
                ],
                max_rows=50,
            )
        )
        report_lines.append("")

    out = pd.concat(all_selected, ignore_index=True) if all_selected else pd.DataFrame()
    out_path = out_dir / "cycle_representative_indicators_4cycle.csv"
    out.to_csv(out_path, index=False)

    md_path = out_dir / "cycle_representative_indicators_4cycle.md"
    md_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("Wrote:", out_path)
    print("Wrote:", md_path)


if __name__ == "__main__":
    main()
