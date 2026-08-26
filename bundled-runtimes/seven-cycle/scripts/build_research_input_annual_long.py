from __future__ import annotations

"""
Build a governed annual research panel for long-cycle work.

Goals:
- Fix a common annual research window where macro + market indicators coexist.
- Remove empty / too-short / pre-filtered / return series.
- Collapse extension duplicates such as `_EXT_WB`, `_EXT_OECD`, `_EXT_WB_GROWTH`.

Inputs:
- data/indicator_panel_annual_very_long_history_year.parquet

Outputs:
- data/research_input_annual_long.parquet
- output/research_input_annual_long_selection.csv
- output/research_input_annual_long_selection.md
"""

from pathlib import Path
import re

import pandas as pd


WINDOW_START = 1700
WINDOW_END = 2024
MIN_NON_NULL = 80

VALUE_TYPE_PRIORITY = {
    "rate_yoy": 0,
    "rate_level": 1,
    "level": 2,
    "price_adj": 3,
    "price": 4,
    "return": 99,
}


def infer_source(col: str) -> str:
    c = str(col)
    if c.startswith(("UK_BOE_", "UK_CPI_", "UK_GDP_")):
        return "boe/wb"
    if c.startswith(("UK_OECD_", "EA_OECD_")) or c.endswith("_OECD_CPI_YOY_PCT"):
        return "oecd(openbb)"
    if c.startswith("US_SHILLER_"):
        return "shiller"
    if c.startswith("MPD_"):
        return "maddison_mpd2020"
    if c.startswith("WB_"):
        return "worldbank"
    return "unknown"


def infer_value_type(col: str) -> str:
    c = str(col).upper()
    if "RET" in c:
        return "return"
    if "YOY" in c or "GROWTH_PCT" in c:
        return "rate_yoy"
    if "UNEMPLOY" in c:
        return "level"
    if c.endswith("_PCT") or "YIELD" in c or "IR_LONG" in c or "IR_SHORT" in c or "BANK_RATE" in c:
        return "rate_level"
    return "level"


def family_key_from_column(col: str) -> str:
    c = str(col)
    return re.sub(r"_EXT_[A-Z0-9_]+$", "", c)


def choose_reason(row: pd.Series) -> str:
    col = str(row["column"])
    if "_EXT_" in col:
        return "prefer_extended_latest"
    vt = str(row["value_type"])
    if vt == "rate_yoy":
        return "prefer_yoy"
    if vt == "rate_level":
        return "prefer_rate_level"
    return "base_singleton_or_best_coverage"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    panel_path = root / "data" / "indicator_panel_annual_very_long_history_year.parquet"
    out_panel_path = root / "data" / "research_input_annual_long.parquet"
    out_sel_csv = root / "output" / "research_input_annual_long_selection.csv"
    out_sel_md = root / "output" / "research_input_annual_long_selection.md"

    panel = pd.read_parquet(panel_path).sort_index()
    panel = panel.loc[WINDOW_START:WINDOW_END].copy()

    rows: list[dict[str, object]] = []
    for col in panel.columns:
        s = pd.to_numeric(panel[col], errors="coerce")
        non_null_count = int(s.notna().sum())
        first = s.first_valid_index()
        last = s.last_valid_index()
        rows.append(
            {
                "column": str(col),
                "family_key": family_key_from_column(col),
                "source": infer_source(col),
                "value_type": infer_value_type(col),
                "non_null_count": non_null_count,
                "coverage_pct": round(100.0 * non_null_count / len(panel), 4),
                "start_year": int(first) if first is not None else None,
                "end_year": int(last) if last is not None else None,
                "status": "candidate",
                "status_reason": "",
            }
        )

    cand = pd.DataFrame(rows)
    if cand.empty:
        raise RuntimeError("No annual candidates available for research input build.")

    cand.loc[cand["non_null_count"] == 0, ["status", "status_reason"]] = ["excluded", "all_missing"]
    cand.loc[
        (cand["status"] == "candidate") & (cand["non_null_count"] < MIN_NON_NULL),
        ["status", "status_reason"],
    ] = ["excluded", f"too_short(<{MIN_NON_NULL})"]
    cand.loc[
        (cand["status"] == "candidate") & (cand["value_type"] == "return"),
        ["status", "status_reason"],
    ] = ["excluded", "return_series"]
    cand.loc[
        (cand["status"] == "candidate")
        & cand["column"].astype(str).str.contains("HP_filter|HP_FILTER", case=False, na=False),
        ["status", "status_reason"],
    ] = ["excluded", "pre_filtered_series"]

    valid = cand[cand["status"] == "candidate"].copy()
    valid["value_type_rank"] = valid["value_type"].map(lambda x: VALUE_TYPE_PRIORITY.get(str(x), 50))
    valid["is_extended"] = valid["column"].astype(str).str.contains("_EXT_", regex=False).astype(int)
    valid = valid.sort_values(
        ["family_key", "is_extended", "end_year", "non_null_count", "start_year", "value_type_rank", "column"],
        ascending=[True, False, False, False, True, True, True],
    )

    winners = valid.groupby("family_key", as_index=False).head(1).copy()
    winners["status"] = "selected"
    winners["status_reason"] = winners.apply(choose_reason, axis=1)

    selected_cols = winners["column"].tolist()
    selected_by_family = dict(zip(winners["family_key"], winners["column"]))

    loser_mask = (cand["status"] == "candidate") & (~cand["column"].isin(selected_cols))
    cand.loc[loser_mask, "status"] = "excluded"
    cand.loc[loser_mask, "status_reason"] = cand.loc[loser_mask, "family_key"].map(
        lambda k: f"deduped_to:{selected_by_family.get(k, '')}"
    )

    cand.loc[cand["column"].isin(selected_cols), "status"] = "selected"
    reason_map = dict(zip(winners["column"], winners["status_reason"]))
    cand.loc[cand["column"].isin(selected_cols), "status_reason"] = cand.loc[
        cand["column"].isin(selected_cols), "column"
    ].map(reason_map)

    research_panel = panel[selected_cols].copy().sort_index(axis=1)
    out_panel_path.parent.mkdir(parents=True, exist_ok=True)
    research_panel.to_parquet(out_panel_path)

    cand = cand.sort_values(["status", "source", "family_key", "column"]).reset_index(drop=True)
    out_sel_csv.parent.mkdir(parents=True, exist_ok=True)
    cand.to_csv(out_sel_csv, index=False)

    selected = cand[cand["status"] == "selected"].copy()
    excluded = cand[cand["status"] == "excluded"].copy()

    lines = [
        "# Research-ready annual long-cycle input selection",
        "",
        f"- Source panel: `{panel_path.relative_to(root)}`",
        f"- Output panel: `{out_panel_path.relative_to(root)}`",
        f"- Window: `{WINDOW_START}` to `{WINDOW_END}`",
        f"- Candidate rows: {len(cand)}",
        f"- Selected rows: {len(selected)}",
        f"- Excluded rows: {len(excluded)}",
        f"- Minimum non-null observations: {MIN_NON_NULL}",
        "",
        "## Selected summary by source",
        "",
        selected.groupby("source", as_index=False).size().to_markdown(index=False),
        "",
        "## Selected summary by value type",
        "",
        selected.groupby("value_type", as_index=False).size().to_markdown(index=False),
        "",
        "## Selected rows",
        "",
        selected[
            [
                "column",
                "family_key",
                "source",
                "value_type",
                "non_null_count",
                "coverage_pct",
                "start_year",
                "end_year",
                "status_reason",
            ]
        ].to_markdown(index=False),
        "",
        "## Excluded rows (first 200)",
        "",
        excluded[
            [
                "column",
                "family_key",
                "source",
                "value_type",
                "non_null_count",
                "coverage_pct",
                "start_year",
                "end_year",
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
