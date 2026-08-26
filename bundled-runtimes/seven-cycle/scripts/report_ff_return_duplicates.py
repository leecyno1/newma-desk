"""
Report duplicate Fama-French return series in the monthly indicator panel.

Duplicates here mean: exact same time series (within the window) under different
column names (usually due to overlapping FF portfolio sets).

Outputs:
- output/ff_return_duplicates.md
- output/ff_return_duplicates.csv
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd


MONTHLY_START = pd.Timestamp("2000-01-31")
MONTHLY_END = pd.Timestamp("2024-12-31")
MONTHLY_INDEX = pd.date_range(MONTHLY_START, MONTHLY_END, freq="ME")


def _load_monthly_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run scripts/build_indicator_panel_multi_source.py first.")
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _series_signature(s: pd.Series) -> str:
    s = s.reindex(MONTHLY_INDEX).astype("float64")
    mask = s.isna().to_numpy(dtype="uint8")
    vals = s.fillna(0.0).round(12).to_numpy(dtype="float64")
    h = hashlib.md5()
    h.update(mask.tobytes())
    h.update(vals.tobytes())
    return h.hexdigest()


def find_duplicate_groups(df: pd.DataFrame, prefix: str, suffix: str) -> list[dict]:
    cols = [c for c in df.columns if c.startswith(prefix) and c.endswith(suffix)]
    sig_map: dict[str, list[str]] = {}
    for c in cols:
        sig = _series_signature(df[c])
        sig_map.setdefault(sig, []).append(c)
    groups = [{"signature": sig, "columns": sorted(cols)} for sig, cols in sig_map.items() if len(cols) > 1]
    groups = sorted(groups, key=lambda g: (-len(g["columns"]), g["signature"]))
    return groups


def choose_keep(columns: list[str]) -> str:
    """
    Pick a preferred representative within a duplicate group.

    Preference order:
    - FF49 industries (most granular)
    - FF48/38/30/17/12/10/5 industry buckets
    - otherwise lexicographically first
    """
    preferences = [
        "US_FF49_",
        "US_FF48IND_",
        "US_FF38IND_",
        "US_FF30IND_",
        "US_FF17IND_",
        "US_FF12IND_",
        "US_FF10IND_",
        "US_FF5IND_",
    ]
    for p in preferences:
        for c in columns:
            if c.startswith(p):
                return c
    return sorted(columns)[0]


def build_md(prefix: str, suffix: str, total_cols: int, groups: list[dict]) -> str:
    dup_cols = sum(len(g["columns"]) for g in groups)
    lines: list[str] = []
    lines.append("# FF Return Duplicate Report")
    lines.append("")
    lines.append(f"- Window: {MONTHLY_START.date()} ~ {MONTHLY_END.date()} (month-end, {len(MONTHLY_INDEX)} points)")
    lines.append(f"- Match: columns starting with `{prefix}` and ending with `{suffix}`")
    lines.append(f"- Matched columns: {total_cols}")
    lines.append(f"- Duplicate groups: {len(groups)}")
    lines.append(f"- Columns involved in duplicates: {dup_cols}")
    lines.append("")
    if not groups:
        lines.append("No duplicates found.")
        return "\n".join(lines)

    lines.append("## Duplicate Groups (exact same series)")
    lines.append("")
    for g in groups:
        keep = choose_keep(g["columns"])
        lines.append(f"### {g['signature']} (n={len(g['columns'])})")
        lines.append("")
        for c in g["columns"]:
            if c == keep:
                lines.append(f"- `{c}`  ← keep")
                continue
            lines.append(f"- `{c}`")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--monthly-panel", default="data/indicator_panel_monthly.parquet")
    ap.add_argument("--prefix", default="US_FF")
    ap.add_argument("--suffix", default="_RET")
    args = ap.parse_args()

    df = _load_monthly_panel(Path(args.monthly_panel))
    cols = [c for c in df.columns if c.startswith(args.prefix) and c.endswith(args.suffix)]
    groups = find_duplicate_groups(df, args.prefix, args.suffix)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "ff_return_duplicates.csv"
    md_path = out_dir / "ff_return_duplicates.md"

    rows = []
    for g in groups:
        keep = choose_keep(g["columns"])
        rows.append(
            {
                "signature": g["signature"],
                "n": len(g["columns"]),
                "columns": "|".join(g["columns"]),
                "keep_suggested": keep,
            }
        )
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    md_path.write_text(build_md(args.prefix, args.suffix, len(cols), groups), encoding="utf-8")

    # Also emit a keep-list for easy feature selection.
    dup_members = {c for g in groups for c in g["columns"]}
    keep_set = set()
    for g in groups:
        keep_set.add(choose_keep(g["columns"]))
    for c in cols:
        if c not in dup_members:
            keep_set.add(c)
    keep_list = sorted(keep_set)
    (out_dir / "ff_return_dedup_keep_list.txt").write_text("\n".join(keep_list) + "\n", encoding="utf-8")

    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {out_dir / 'ff_return_dedup_keep_list.txt'}")


if __name__ == "__main__":
    main()
