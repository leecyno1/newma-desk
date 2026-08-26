from __future__ import annotations

"""
Build a research-ready monthly macro panel from the raw monthly panel.

Goals:
- Fix the analysis window for short-cycle research.
- Remove empty / too-short / cumulative series.
- Collapse LEVEL/MOM/YOY siblings into one canonical series per variable family.

Inputs:
- data/indicator_panel_monthly.parquet
- output/cycle_bandpower_scores_monthly.csv

Outputs:
- data/research_input_monthly_macro.parquet
- output/research_input_monthly_macro_selection.csv
- output/research_input_monthly_macro_selection.md
"""

from pathlib import Path
import re

import pandas as pd


WINDOW_START = "2000-01-31"
WINDOW_END = "2025-12-31"
MIN_NON_NULL = 60

KEEP_CATEGORIES = {
    "宏观增长类（Macro Growth）",
    "通胀与价格类（Inflation & Prices）",
    "货币与信用类（Money & Credit）",
    "利率与债券类（Rates & Bonds）",
    "汇率与外部部门（FX & External）",
    "股票市场与估值（Equity Market & Valuation）",
}

VALUE_TYPE_PRIORITY = {
    "rate_yoy": 0,
    "rate_mom": 1,
    "rate_level": 2,
    "price_adj": 3,
    "price": 4,
    "level": 5,
    "return": 99,
}


def family_key_from_column(col: str) -> str:
    col = str(col)
    return re.sub(r"_(LEVEL|MOM|YOY)$", "", col)


def choose_reason(row: pd.Series) -> str:
    vt = str(row["value_type"])
    if vt == "rate_yoy":
        return "prefer_yoy"
    if vt == "rate_mom":
        return "prefer_mom"
    if vt == "rate_level":
        return "prefer_rate_level"
    if vt in {"price_adj", "price"}:
        return "prefer_price_like"
    return "fallback_level"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    panel_path = root / "data" / "indicator_panel_monthly.parquet"
    scores_path = root / "output" / "cycle_bandpower_scores_monthly.csv"
    out_panel_path = root / "data" / "research_input_monthly_macro.parquet"
    out_sel_csv = root / "output" / "research_input_monthly_macro_selection.csv"
    out_sel_md = root / "output" / "research_input_monthly_macro_selection.md"

    panel = pd.read_parquet(panel_path)
    panel = panel.sort_index()
    panel = panel.loc[pd.Timestamp(WINDOW_START) : pd.Timestamp(WINDOW_END)].copy()

    meta = pd.read_csv(scores_path)
    meta = meta[meta["freq"] == "M"].copy()
    meta = meta[
        [
            "id",
            "name",
            "universe_category",
            "primary_source",
            "backend",
            "base_freq",
            "value_type",
            "panel_main_column",
        ]
    ].drop_duplicates()
    meta = meta[meta["universe_category"].isin(KEEP_CATEGORIES)].copy()
    meta = meta[meta["value_type"] != "return"].copy()
    meta = meta[~meta["panel_main_column"].astype(str).str.contains("ACCU", case=False, na=False)].copy()
    meta = meta[~meta["panel_main_column"].astype(str).str.contains("_CUM_", case=False, na=False)].copy()
    meta = meta[meta["panel_main_column"].isin(panel.columns)].copy()

    rows: list[dict[str, object]] = []
    selected_cols: list[str] = []
    selected_by_family: dict[str, str] = {}

    for row in meta.itertuples(index=False):
        col = str(getattr(row, "panel_main_column"))
        s = pd.to_numeric(panel[col], errors="coerce")
        non_null_count = int(s.notna().sum())
        first = s.first_valid_index()
        last = s.last_valid_index()
        rows.append(
            {
                "id": str(getattr(row, "id")),
                "name": str(getattr(row, "name")),
                "universe_category": str(getattr(row, "universe_category")),
                "primary_source": str(getattr(row, "primary_source")),
                "backend": str(getattr(row, "backend")),
                "base_freq": str(getattr(row, "base_freq")),
                "value_type": str(getattr(row, "value_type")),
                "panel_main_column": col,
                "family_key": family_key_from_column(col),
                "non_null_count": non_null_count,
                "coverage_pct": round(100.0 * non_null_count / len(panel), 4),
                "start": first.strftime("%Y-%m-%d") if first is not None else "",
                "end": last.strftime("%Y-%m-%d") if last is not None else "",
                "status": "candidate",
                "status_reason": "",
            }
        )

    cand = pd.DataFrame(rows)
    if cand.empty:
        raise RuntimeError("No monthly macro candidates available for research input build.")

    cand.loc[cand["non_null_count"] == 0, ["status", "status_reason"]] = ["excluded", "all_missing"]
    cand.loc[
        (cand["status"] == "candidate") & (cand["non_null_count"] < MIN_NON_NULL),
        ["status", "status_reason"],
    ] = ["excluded", f"too_short(<{MIN_NON_NULL})"]

    valid = cand[cand["status"] == "candidate"].copy()
    valid["value_type_rank"] = valid["value_type"].map(lambda x: VALUE_TYPE_PRIORITY.get(str(x), 50))
    valid["start_rank"] = pd.to_datetime(valid["start"], errors="coerce")
    valid["end_rank"] = pd.to_datetime(valid["end"], errors="coerce")
    valid = valid.sort_values(
        ["family_key", "value_type_rank", "non_null_count", "end_rank", "start_rank"],
        ascending=[True, True, False, False, True],
    )

    winners = valid.groupby("family_key", as_index=False).head(1).copy()
    winners["status"] = "selected"
    winners["status_reason"] = winners.apply(choose_reason, axis=1)
    selected_by_family = dict(zip(winners["family_key"], winners["panel_main_column"]))
    selected_cols = winners["panel_main_column"].tolist()

    loser_mask = (cand["status"] == "candidate") & (~cand["panel_main_column"].isin(selected_cols))
    cand.loc[loser_mask, "status"] = "excluded"
    cand.loc[loser_mask, "status_reason"] = cand.loc[loser_mask, "family_key"].map(
        lambda k: f"deduped_to:{selected_by_family.get(k, '')}"
    )

    cand.loc[cand["panel_main_column"].isin(selected_cols), "status"] = "selected"
    reason_map = dict(zip(winners["panel_main_column"], winners["status_reason"]))
    cand.loc[cand["panel_main_column"].isin(selected_cols), "status_reason"] = cand.loc[
        cand["panel_main_column"].isin(selected_cols), "panel_main_column"
    ].map(reason_map)

    research_panel = panel[selected_cols].copy().sort_index(axis=1)
    out_panel_path.parent.mkdir(parents=True, exist_ok=True)
    research_panel.to_parquet(out_panel_path)

    cand = cand.sort_values(["status", "universe_category", "family_key", "panel_main_column"]).reset_index(drop=True)
    out_sel_csv.parent.mkdir(parents=True, exist_ok=True)
    cand.to_csv(out_sel_csv, index=False)

    selected = cand[cand["status"] == "selected"].copy()
    excluded = cand[cand["status"] == "excluded"].copy()

    lines = [
        "# Research-ready monthly macro input selection",
        "",
        f"- Source panel: `{panel_path.relative_to(root)}`",
        f"- Output panel: `{out_panel_path.relative_to(root)}`",
        f"- Window: `{WINDOW_START}` to `{WINDOW_END}`",
        f"- Candidate rows: {len(cand)}",
        f"- Selected rows: {len(selected)}",
        f"- Excluded rows: {len(excluded)}",
        f"- Minimum non-null observations: {MIN_NON_NULL}",
        "",
        "## Selected summary by category",
        "",
        selected.groupby("universe_category", as_index=False).size().to_markdown(index=False),
        "",
        "## Selected rows",
        "",
        selected[
            [
                "id",
                "name",
                "universe_category",
                "value_type",
                "panel_main_column",
                "family_key",
                "non_null_count",
                "coverage_pct",
                "start",
                "end",
                "status_reason",
            ]
        ].to_markdown(index=False),
        "",
        "## Excluded rows",
        "",
        excluded[
            [
                "id",
                "name",
                "universe_category",
                "value_type",
                "panel_main_column",
                "family_key",
                "non_null_count",
                "coverage_pct",
                "start",
                "end",
                "status_reason",
            ]
        ].head(200).to_markdown(index=False),
        "",
    ]
    out_sel_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Wrote:", out_panel_path)
    print("Wrote:", out_sel_csv)
    print("Wrote:", out_sel_md)


if __name__ == "__main__":
    main()
