from __future__ import annotations

"""
Select representative indicator groups for short cycles (42m/20m)
from the *short* monthly panel (post-2000), restricted to macro-style indicators.

Motivation:
- The 700+ universe is dominated by FF factor/portfolio returns (value_type=return).
- For macro-cycle research, we prefer macro/credit/rates/inflation/FX/equity indices,
  and we avoid cumulative (ACCU) series where possible.

Inputs:
- output/cycle_bandpower_scores_monthly.csv
- output/research_input_monthly_macro_selection.csv
- data/research_input_monthly_macro.parquet

Outputs:
- output/cycle_representative_indicators_short_macro.csv
- output/cycle_representative_indicators_short_macro.md
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CycleSpec:
    months: int
    label: str
    min_points: int
    top_k: int
    corr_threshold: float = 0.92
    keywords: tuple[str, ...] = ()


KEEP_CATEGORIES = {
    "宏观增长类（Macro Growth）",
    "通胀与价格类（Inflation & Prices）",
    "货币与信用类（Money & Credit）",
    "利率与债券类（Rates & Bonds）",
    "汇率与外部部门（FX & External）",
    "股票市场与估值（Equity Market & Valuation）",
}


CYCLES: list[CycleSpec] = [
    CycleSpec(42, "库存/基钦周期(≈3-5y, 42m)", min_points=180, top_k=20, keywords=("产成品库存", "原材料库存", "库存")),
    CycleSpec(20, "流动性/政策短周期(≈1-2y, 20m)", min_points=180, top_k=22, keywords=("信用", "社融", "贷款", "M1", "M2", "利率", "SHIBOR", "HIBOR")),
]


def prepare_regular_series(s: pd.Series, max_missing_frac: float = 0.1) -> pd.Series | None:
    s = s.sort_index()
    # Normalize to one observation per calendar month before gap checks.
    s = s.groupby(s.index.to_period("M")).last()
    s.index = s.index.to_timestamp("M")
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return None
    full_index = pd.date_range(first, last, freq="ME")
    w = s.reindex(full_index).copy()
    if len(w) < 60:
        return None
    if float(w.isna().mean()) > max_missing_frac:
        return None
    return w.interpolate(method="time").ffill().bfill()


def transform_for_corr(s: pd.Series, value_type: str) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce")
    if value_type in {"price", "price_adj", "level"}:
        if (x > 0).all():
            x = np.log(x)
        x = x.diff()
    elif value_type == "rate_level":
        x = x.diff()
    # return / rate_yoy / rate_mom: keep as-is

    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 60:
        return None
    std = float(x.std(ddof=0))
    if std == 0.0 or np.isnan(std):
        return None
    return (x - float(x.mean())) / std


def greedy_dedup(
    candidates: pd.DataFrame,
    panel: pd.DataFrame,
    *,
    by_col: str = "panel_main_column",
    corr_threshold: float = 0.92,
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
        x = transform_for_corr(s0, value_type=str(getattr(row, "value_type")))
        if x is None:
            continue

        ok = True
        for ks in kept_series:
            aligned = pd.concat([x, ks], axis=1).dropna()
            if aligned.shape[0] < 72:
                continue
            corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
            if np.isfinite(corr) and abs(corr) >= corr_threshold:
                ok = False
                break
        if ok:
            kept.append(row._asdict())
            kept_series.append(x)

    if not kept:
        return candidates.head(0).copy()
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


def to_markdown_table(df: pd.DataFrame, cols: list[str], max_rows: int = 40) -> str:
    if df.empty:
        return "(empty)"
    show = df[cols].head(max_rows).copy()
    return "```\n" + show.to_string(index=False) + "\n```"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "output"
    data_dir = root / "data"

    scores_path = out_dir / "cycle_bandpower_scores_monthly.csv"
    panel_path = data_dir / "research_input_monthly_macro.parquet"
    selection_path = out_dir / "research_input_monthly_macro_selection.csv"

    scores = pd.read_csv(scores_path)
    panel = pd.read_parquet(panel_path)
    selection = pd.read_csv(selection_path)
    selected_cols = set(selection.loc[selection["status"] == "selected", "panel_main_column"].astype(str))

    # NOTE: cycle_bandpower_scores_monthly.csv already contains the metadata columns we need
    # (name/category/value_type/panel_main_column/start/end). We filter on it directly to
    # avoid merge-suffix issues (panel_main_column_x/_y).
    scores = scores[scores.get("freq", "M") == "M"].copy()
    scores = scores[scores["universe_category"].isin(KEEP_CATEGORIES)].copy()
    scores = scores[scores["value_type"] != "return"].copy()
    scores = scores[~scores["panel_main_column"].astype(str).str.contains("ACCU", case=False, na=False)].copy()
    scores = scores[scores["panel_main_column"].astype(str).isin(selected_cols)].copy()

    all_selected: list[pd.DataFrame] = []
    report_lines: list[str] = []
    report_lines.append("# Short-cycle representatives (macro-only, monthly panel)")
    report_lines.append("")
    report_lines.append("Filters:")
    report_lines.append(f"- Keep categories: {', '.join(sorted(KEEP_CATEGORIES))}")
    report_lines.append("- Exclude value_type=return (FF portfolios/factors).")
    report_lines.append("- Exclude ACCU cumulative series.")
    report_lines.append(f"- Restrict to selected research input columns from `{selection_path.relative_to(root)}`.")
    report_lines.append("")

    for cyc in CYCLES:
        df = scores[scores["cycle_months"] == cyc.months].copy()
        if df.empty:
            continue

        df["bandpower_ratio"] = pd.to_numeric(df["bandpower_ratio"], errors="coerce")
        df["n_points"] = pd.to_numeric(df["n_points"], errors="coerce")
        df = df.dropna(subset=["bandpower_ratio", "n_points"])
        df = df[df["n_points"] >= cyc.min_points]
        df = df.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False])

        top = df.head(max(cyc.top_k * 12, 120)).copy()
        dedup = greedy_dedup(top, panel=panel, corr_threshold=cyc.corr_threshold)
        if dedup.empty:
            report_lines.append(f"## {cyc.months}m – {cyc.label}")
            report_lines.append(f"- Candidates: {int(len(df))}")
            report_lines.append("- Selected: 0")
            report_lines.append("- Note: no candidates passed the de-duplication / transform checks on the research input panel.")
            report_lines.append("")
            continue
        dedup = dedup.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False]).head(cyc.top_k)
        dedup = ensure_keywords_included(dedup, df, keywords=cyc.keywords)
        dedup["cycle_months"] = cyc.months
        dedup["cycle_label"] = cyc.label
        all_selected.append(dedup)

        report_lines.append(f"## {cyc.months}m – {cyc.label}")
        report_lines.append(f"- Candidates: {int(len(df))}")
        report_lines.append(f"- Selected: {int(len(dedup))}")
        report_lines.append(
            to_markdown_table(
                dedup,
                cols=[
                    "id",
                    "name",
                    "universe_category",
                    "primary_source",
                    "value_type",
                    "panel_main_column",
                    "n_points",
                    "start",
                    "end",
                    "bandpower_ratio",
                ],
                max_rows=60,
            )
        )
        report_lines.append("")

    out = pd.concat(all_selected, ignore_index=True) if all_selected else pd.DataFrame()
    out_path = out_dir / "cycle_representative_indicators_short_macro.csv"
    out.to_csv(out_path, index=False)

    md_path = out_dir / "cycle_representative_indicators_short_macro.md"
    md_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("Wrote:", out_path)
    print("Wrote:", md_path)


if __name__ == "__main__":
    main()
