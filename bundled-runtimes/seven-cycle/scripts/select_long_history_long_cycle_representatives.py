from __future__ import annotations

"""
Select representative indicator groups for long cycles (200m/100m)
using the long-history annual panel (1800-2024, year index).

Inputs:
- output/cycle_bandpower_scores_annual_long_history_long.csv
- data/indicator_panel_annual_long_history_year.parquet

Outputs:
- output/cycle_representative_indicators_long_history_long.csv
- output/cycle_representative_indicators_long_history_long.md
"""

from dataclasses import dataclass
from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm


warnings.filterwarnings("ignore")


@dataclass(frozen=True)
class CycleSpec:
    months: int
    label: str
    min_points: int
    top_k: int
    corr_threshold: float = 0.9
    keywords: tuple[str, ...] = ()


CYCLES = [
    CycleSpec(200, "长周期(≈16-18y, 200m)", min_points=140, top_k=20, keywords=("GDP", "GDPPC", "CPI", "HOUSE", "SHARE", "YIELD", "CREDIT")),
    CycleSpec(100, "中长周期(≈7-9y, 100m)", min_points=120, top_k=20, keywords=("GDP", "CPI", "UNEMP", "RATE", "YIELD", "SHARE")),
]


def _slug(s: str, max_len: int = 80) -> str:
    s = str(s).strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "NA"
    return s[:max_len]


def prepare_regular_series(s: pd.Series, *, min_points: int = 80, max_missing_frac: float = 0.2) -> pd.Series | None:
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


def _zscore(x: pd.Series) -> pd.Series | None:
    x = pd.to_numeric(x, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 60:
        return None
    sd = float(x.std(ddof=0))
    if sd == 0.0 or np.isnan(sd):
        return None
    return (x - float(x.mean())) / sd


def infer_value_type(col: str) -> str:
    c = col.upper()
    if "RET" in c:
        return "return"
    if "YOY" in c:
        return "rate_yoy"
    if "UNEMPLOY" in c:
        return "level"
    if c.endswith("_PCT") or "YIELD" in c or "IR_LONG" in c or "IR_SHORT" in c or "BANK_RATE" in c:
        return "rate_level"
    return "level"


def transform_for_corr(s: pd.Series, value_type: str, *, hp_lamb: float = 100.0) -> pd.Series | None:
    x = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if x.shape[0] < 80:
        return None
    y = x.astype("float64")
    if value_type in {"level", "price", "price_adj"}:
        if (y > 0).all():
            y = np.log(y)
    try:
        cycle, _trend = sm.tsa.filters.hpfilter(y.values, lamb=hp_lamb)
        y = pd.Series(cycle, index=y.index)
    except Exception:
        y = y - y.rolling(10, min_periods=1).mean()
    return _zscore(y)


def greedy_dedup(
    candidates: pd.DataFrame,
    panel: pd.DataFrame,
    *,
    by_col: str = "column",
    corr_threshold: float = 0.9,
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
        vt = getattr(row, "value_type", None) or infer_value_type(col)
        x = transform_for_corr(s0, value_type=str(vt))
        if x is None:
            continue

        ok = True
        for ks in kept_series:
            aligned = pd.concat([x, ks], axis=1).dropna()
            if aligned.shape[0] < 60:
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
    ids = set(base["column"].astype(str).tolist()) if "column" in base.columns else set()

    pattern = "|".join([k for k in keywords if k])
    if not pattern:
        return base
    hit = ranked[ranked["column"].astype(str).str.contains(pattern, case=False, regex=True, na=False)].copy()
    hit = hit[~hit["column"].astype(str).isin(ids)].head(max_extra)
    if hit.empty:
        return base
    return pd.concat([base, hit], ignore_index=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    scores_path = root / "output" / "cycle_bandpower_scores_annual_long_history_long.csv"
    panel_path = root / "data" / "indicator_panel_annual_long_history_year.parquet"
    if not scores_path.exists():
        raise FileNotFoundError(scores_path)
    if not panel_path.exists():
        raise FileNotFoundError(panel_path)

    scores = pd.read_csv(scores_path)
    panel = pd.read_parquet(panel_path)

    scores["bandpower_ratio"] = pd.to_numeric(scores["bandpower_ratio"], errors="coerce")
    scores["n_points"] = pd.to_numeric(scores["n_points"], errors="coerce")

    all_selected: list[pd.DataFrame] = []
    report_lines: list[str] = []
    report_lines.append("# Long-history long-cycle representatives (200m/100m)")
    report_lines.append("")
    report_lines.append(f"- Panel: `{panel_path.relative_to(root)}`")
    report_lines.append(f"- Scores: `{scores_path.relative_to(root)}`")
    report_lines.append("")

    for cyc in CYCLES:
        df = scores[scores["cycle_months"] == cyc.months].copy()
        df = df.dropna(subset=["bandpower_ratio", "n_points"])
        df = df[df["n_points"] >= cyc.min_points]
        df = df.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False])

        top = df.head(max(cyc.top_k * 12, 120)).copy()
        dedup = greedy_dedup(top, panel=panel, corr_threshold=cyc.corr_threshold)
        dedup = dedup.sort_values(["bandpower_ratio", "n_points"], ascending=[False, False]).head(cyc.top_k)
        dedup = ensure_keywords_included(dedup, df, keywords=cyc.keywords)
        dedup["cycle_months"] = cyc.months
        dedup["cycle_label"] = cyc.label
        all_selected.append(dedup)

        report_lines.append(f"## {cyc.months}m – {cyc.label}")
        report_lines.append(f"- Candidates scored: {int(len(df))}")
        report_lines.append(f"- Selected: {int(len(dedup))}")
        cols = ["column", "source", "value_type", "n_points", "start_year", "end_year", "bandpower_ratio"]
        show = dedup[cols].head(40).copy() if not dedup.empty else pd.DataFrame(columns=cols)
        report_lines.append("```")
        report_lines.append(show.to_string(index=False))
        report_lines.append("```")
        report_lines.append("")

    out = pd.concat(all_selected, ignore_index=True) if all_selected else pd.DataFrame()
    out_path = root / "output" / "cycle_representative_indicators_long_history_long.csv"
    out.to_csv(out_path, index=False)

    md_path = root / "output" / "cycle_representative_indicators_long_history_long.md"
    md_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("Wrote:", out_path)
    print("Wrote:", md_path)


if __name__ == "__main__":
    main()

