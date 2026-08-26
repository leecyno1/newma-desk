from __future__ import annotations

"""
Select representative indicator groups for long cycles (200m/100m) using the
annual year-index *extended* panel (1800+).

Inputs:
- output/long_cycle_bandpower_scores_year_extended.csv
- data/indicator_panel_annual_year_extended.parquet

Outputs:
- output/long_cycle_representatives_year_extended.csv
- output/long_cycle_representatives_year_extended.md
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


CYCLES: list[CycleSpec] = [
    CycleSpec(
        200,
        "库兹涅茨/地产建造长周期(≈15-25y)",
        min_points=120,  # prefer >= ~7 long cycles
        top_k=16,
        keywords=("HOUSE", "CREDIT", "MONEY", "DEBT", "GDP", "POP", "EXCHANGE", "CONSOL", "BOND", "YIELD", "房地产", "房", "信贷", "债"),
    ),
    CycleSpec(
        100,
        "朱格拉/资本开支周期(≈7-11y)",
        min_points=80,  # prefer >= ~9 cycles
        top_k=16,
        keywords=("INVEST", "CAPITAL", "TFP", "PRODUCTION", "GDP", "EXPORT", "IMPORT", "UNEMP", "RATE", "投资", "制造"),
    ),
]


def prepare_regular_series_year(s: pd.Series, *, max_missing_frac: float = 0.15, min_points: int = 60) -> pd.Series | None:
    s = s.sort_index()
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return None
    w = s.loc[first:last].copy()
    if len(w) < min_points:
        return None
    if float(w.isna().mean()) > max_missing_frac:
        return None
    return w.interpolate(method="linear").ffill().bfill()


def transform_for_corr(s: pd.Series, value_type: str) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce")
    if value_type in {"price", "price_adj", "level"}:
        if (x > 0).all():
            x = np.log(x)
        x = x.diff()
    elif value_type == "rate_level":
        x = x.diff()
    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 30:
        return None
    std = float(x.std(ddof=0))
    if std == 0.0 or np.isnan(std):
        return None
    return (x - float(x.mean())) / std


def greedy_dedup(
    candidates: pd.DataFrame,
    *,
    panel: pd.DataFrame,
    by_col: str = "column",
    corr_threshold: float = 0.92,
) -> pd.DataFrame:
    kept: list[dict[str, object]] = []
    kept_series: list[pd.Series] = []

    for row in candidates.itertuples(index=False):
        col = str(getattr(row, by_col))
        if col not in panel.columns:
            continue
        s0 = prepare_regular_series_year(panel[col])
        if s0 is None:
            continue
        x = transform_for_corr(s0, value_type=str(getattr(row, "value_type")))
        if x is None:
            continue

        ok = True
        for ks in kept_series:
            aligned = pd.concat([x, ks], axis=1).dropna()
            if aligned.shape[0] < 40:
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
    selected: pd.DataFrame,
    ranked: pd.DataFrame,
    *,
    keywords: tuple[str, ...],
    max_extra: int = 10,
) -> pd.DataFrame:
    if not keywords:
        return selected
    base = selected.copy() if not selected.empty else pd.DataFrame()
    ids = set(base["id"].astype(str).tolist()) if "id" in base.columns else set()

    pattern = "|".join([k for k in keywords if k])
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
    out_dir.mkdir(parents=True, exist_ok=True)

    scores_path = out_dir / "long_cycle_bandpower_scores_year_extended.csv"
    panel_path = data_dir / "indicator_panel_annual_year_extended.parquet"
    if not scores_path.exists():
        raise FileNotFoundError(scores_path)
    if not panel_path.exists():
        raise FileNotFoundError(panel_path)

    scores = pd.read_csv(scores_path)
    panel = pd.read_parquet(panel_path)

    scores["bandpower_ratio"] = pd.to_numeric(scores["bandpower_ratio"], errors="coerce")
    scores["n_points"] = pd.to_numeric(scores["n_points"], errors="coerce")

    # Focus on macro-style series for long-cycle research (exclude pure return series).
    scores = scores[scores["value_type"].astype(str).str.lower() != "return"].copy()

    all_selected: list[pd.DataFrame] = []
    report_lines: list[str] = []
    report_lines.append("# Long-cycle representatives (year-extended panel)")
    report_lines.append("")
    report_lines.append("Selection logic:")
    report_lines.append("- Score = Welch PSD band-power ratio around 200m/100m (annualized).")
    report_lines.append("- Exclude `value_type=return` to focus on macro-style series.")
    report_lines.append("- Greedy correlation dedup on transformed series.")
    report_lines.append("")

    for cyc in CYCLES:
        df = scores[scores["cycle_months"] == cyc.months].copy()
        df = df.dropna(subset=["bandpower_ratio"])
        df = df[df["n_points"] >= cyc.min_points]
        df = df.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False])

        top = df.head(max(cyc.top_k * 12, 120)).copy()
        dedup = greedy_dedup(top, panel=panel, corr_threshold=cyc.corr_threshold)
        if not dedup.empty:
            dedup = dedup.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False]).head(cyc.top_k)
        dedup = ensure_keywords_included(dedup, df, keywords=cyc.keywords)
        dedup["cycle_label"] = cyc.label
        all_selected.append(dedup)

        report_lines.append(f"## {cyc.months}m – {cyc.label}")
        report_lines.append(f"- Candidates scored: {int(len(df))}")
        report_lines.append(f"- Selected (after dedup + keyword补充): {int(len(dedup))}")
        report_lines.append(
            to_markdown_table(
                dedup,
                cols=["id", "name", "universe_category", "value_type", "n_points", "start_year", "end_year", "bandpower_ratio", "column"],
            )
        )
        report_lines.append("")

    out = pd.concat(all_selected, ignore_index=True) if all_selected else pd.DataFrame()
    out_path = out_dir / "long_cycle_representatives_year_extended.csv"
    out.to_csv(out_path, index=False)

    md_path = out_dir / "long_cycle_representatives_year_extended.md"
    md_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("Wrote:", out_path)
    print("Wrote:", md_path)


if __name__ == "__main__":
    main()

