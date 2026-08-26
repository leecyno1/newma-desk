"""
Summarize and classify the current indicator universe (INDICATORS) according to:
cycle_analysis_system/docs/INDICATOR_UNIVERSE_100PLUS.md

Outputs:
- output/indicator_universe_639_mapped.md
- output/indicator_universe_639_mapped.csv

The report includes:
- Category counts
- Frequency distribution (source base_freq)
- Data availability ranges (monthly/annual panels)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cycle_analysis_system.indicators.indicator_registry import INDICATORS, IndicatorSpec


# Windows (consistent with scripts/check_indicator_panel_completeness.py)
MONTHLY_START = pd.Timestamp("2000-01-31")
MONTHLY_END = pd.Timestamp("2024-12-31")
ANNUAL_START = pd.Timestamp("1960-12-31")
ANNUAL_END = pd.Timestamp("2024-12-31")

MONTHLY_INDEX = pd.date_range(MONTHLY_START, MONTHLY_END, freq="ME")
ANNUAL_INDEX = pd.date_range(ANNUAL_START, ANNUAL_END, freq="YE-DEC")


# Canonical categories (aligned to INDICATOR_UNIVERSE_100PLUS.md section titles)
C_MACRO_GROWTH = "宏观增长类（Macro Growth）"
C_INFLATION = "通胀与价格类（Inflation & Prices）"
C_MONEY_CREDIT = "货币与信用类（Money & Credit）"
C_RATES_BONDS = "利率与债券类（Rates & Bonds）"
C_FX_EXTERNAL = "汇率与外部部门（FX & External）"
C_EQUITY_VAL = "股票市场与估值（Equity Market & Valuation）"
C_SENTIMENT = "情绪与风险偏好（Sentiment & Risk Appetite）"
C_GLOBAL = "全球资产与对照指标（Global Assets & Benchmarks）"
C_OTHER = "其他/未映射（Other/Unmapped）"

UNIVERSE_CATEGORIES = [
    C_MACRO_GROWTH,
    C_INFLATION,
    C_MONEY_CREDIT,
    C_RATES_BONDS,
    C_FX_EXTERNAL,
    C_EQUITY_VAL,
    C_SENTIMENT,
    C_GLOBAL,
    C_OTHER,
]


def map_to_universe_category(ind: IndicatorSpec) -> str:
    cid = ind.id
    cat = ind.category or ""

    # Equity / valuation (domestic)
    if cat.startswith("CN/EquityValuation") or cat.startswith("CN/Equity"):
        return C_EQUITY_VAL

    # Rates
    if cat.startswith("CN/Rates") or cat.startswith("HK/Rates") or "Rates" in cat:
        return C_RATES_BONDS
    if "LPR" in cid or "SHIBOR" in cid or "HIBOR" in cid:
        return C_RATES_BONDS

    # Money & credit
    if cat.startswith("CN/MoneyCredit") or "MoneyCredit" in cat:
        return C_MONEY_CREDIT
    if "SOCIAL_FIN" in cid or "NEW_CREDIT" in cid or cid.startswith("CN_M_"):
        return C_MONEY_CREDIT

    # Inflation / prices (include global commodity proxies)
    if cat.startswith("CN/Inflation") or cat.startswith("Global/Commodity"):
        return C_INFLATION

    # FX & external
    if cat.startswith("Global/FX"):
        return C_FX_EXTERNAL
    if cid.startswith(("CN_EXPORT", "CN_IMPORT")) or "TRADE_BALANCE" in cid:
        return C_FX_EXTERNAL
    if cid in {"DXY", "USDCNY"}:
        return C_FX_EXTERNAL

    # Macro growth (CN growth/PMI + most CN macro)
    if cat.startswith("CN/Growth") or cat.startswith("CN/PMI"):
        return C_MACRO_GROWTH
    if cat.startswith("CN/Macro") or cat.startswith("CN/Macro("):
        # default CN macro -> growth bucket unless it matches a more specific rule above
        return C_MACRO_GROWTH

    # Sentiment
    if "Sentiment" in cat or "SENTIMENT" in cid or cid in {"VIX"}:
        return C_SENTIMENT

    # Global assets: global equity, OECD macro, FF, etc.
    if cat.startswith("Global/"):
        return C_GLOBAL
    if cat.startswith("US/") or cat.startswith("HK/") or cat.startswith("EU/") or cat.startswith("JP/"):
        return C_GLOBAL

    return C_OTHER


def main_column(ind: IndicatorSpec) -> str:
    if ind.value_type in {"rate_yoy", "rate_mom"}:
        return ind.id
    if ind.value_type == "return":
        return f"{ind.id}_RET"
    return f"{ind.id}_LEVEL"


def _load_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run scripts/build_indicator_panel_multi_source.py first.")
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _range_of(s: pd.Series) -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    non_na = s.dropna()
    if non_na.empty:
        return None, None
    return pd.Timestamp(non_na.index.min()), pd.Timestamp(non_na.index.max())


def _coverage(s: pd.Series, idx: pd.DatetimeIndex) -> tuple[float, int, int]:
    s2 = s.reindex(idx)
    missing = int(s2.isna().sum())
    total = int(len(idx))
    available = int(total - missing)
    cov = float(available / total) if total else 0.0
    return cov, available, missing


def build_summary_df(df_m: pd.DataFrame, df_a: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for ind in INDICATORS:
        ucat = map_to_universe_category(ind)
        col = main_column(ind)

        m_present = col in df_m.columns
        a_present = col in df_a.columns

        m_first = m_last = a_first = a_last = None
        m_cov = a_cov = 0.0
        m_avail = m_miss = a_avail = a_miss = 0

        if m_present:
            s = df_m[col]
            m_first, m_last = _range_of(s)
            m_cov, m_avail, m_miss = _coverage(s, MONTHLY_INDEX)
        if a_present:
            s = df_a[col]
            a_first, a_last = _range_of(s)
            a_cov, a_avail, a_miss = _coverage(s, ANNUAL_INDEX)

        rows.append(
            {
                "universe_category": ucat,
                "id": ind.id,
                "name": ind.name,
                "internal_category": ind.category,
                "primary_source": ind.primary_source,
                "backend": ind.backend,
                "base_freq": ind.base_freq,
                "value_type": ind.value_type,
                "panel_main_column": col,
                "monthly_present": bool(m_present),
                "annual_present": bool(a_present),
                "monthly_first": m_first,
                "monthly_last": m_last,
                "monthly_coverage_2000_2024": m_cov,
                "monthly_available_points_2000_2024": m_avail,
                "monthly_missing_points_2000_2024": m_miss,
                "annual_first": a_first,
                "annual_last": a_last,
                "annual_coverage_1960_2024": a_cov,
                "annual_available_points_1960_2024": a_avail,
                "annual_missing_points_1960_2024": a_miss,
            }
        )

    out = pd.DataFrame(rows)
    out["universe_category"] = pd.Categorical(out["universe_category"], categories=UNIVERSE_CATEGORIES, ordered=True)
    out = out.sort_values(["universe_category", "id"]).reset_index(drop=True)
    return out


def _fmt_ts(ts: Optional[pd.Timestamp]) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def build_markdown(df: pd.DataFrame) -> str:
    lines: list[str] = []
    lines.append(f"# Indicator Universe ({df.shape[0]}) — 分类与取数区间/频度统计")
    lines.append("")
    lines.append("对齐指标体系文件：`cycle_analysis_system/docs/INDICATOR_UNIVERSE_100PLUS.md`。")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 指标数（registry）：{df.shape[0]}")
    lines.append("")
    # Frequency distribution
    freq_tab = (
        df.groupby(["base_freq"], observed=True)["id"]
        .count()
        .rename("count")
        .reset_index()
        .sort_values("count", ascending=False)
    )
    lines.append("### 来源频度分布（base_freq）")
    lines.append("")
    lines.append(freq_tab.to_markdown(index=False))
    lines.append("")

    src_tab = (
        df.groupby(["primary_source"], observed=True)["id"]
        .count()
        .rename("count")
        .reset_index()
        .sort_values("count", ascending=False)
    )
    lines.append("### 数据源分布（primary_source）")
    lines.append("")
    lines.append(src_tab.to_markdown(index=False))
    lines.append("")

    cat_tab = (
        df.groupby(["universe_category"], observed=True)["id"]
        .count()
        .rename("count")
        .reset_index()
        .sort_values("count", ascending=False)
    )
    lines.append("### 体系分类分布（对齐 INDICATOR_UNIVERSE_100PLUS）")
    lines.append("")
    lines.append(cat_tab.to_markdown(index=False))
    lines.append("")

    lines.append("## 分类明细（每类列出指标 + 区间/覆盖）")
    lines.append("")
    lines.append("字段说明：")
    lines.append("")
    lines.append("- `base_freq`: 源数据频度（D/M/Q/A）")
    lines.append("- `monthly_first/last`: 月度面板中该指标主列的首末非空日期（面板月度从 2000 起）")
    lines.append("- `annual_first/last`: 年度面板中该指标主列的首末非空日期（面板年频覆盖更长历史）")
    lines.append("- `*_coverage_*`: 在指定窗口（月：2000-2024；年：1960-2024）内的非空覆盖率")
    lines.append("")

    show_cols = [
        "id",
        "name",
        "primary_source",
        "base_freq",
        "value_type",
        "panel_main_column",
        "monthly_first",
        "monthly_last",
        "monthly_coverage_2000_2024",
        "annual_first",
        "annual_last",
        "annual_coverage_1960_2024",
    ]

    df2 = df.copy()
    for c in ["monthly_first", "monthly_last", "annual_first", "annual_last"]:
        df2[c] = df2[c].apply(_fmt_ts)
    df2["monthly_coverage_2000_2024"] = df2["monthly_coverage_2000_2024"].map(lambda x: f"{x:.3f}")
    df2["annual_coverage_1960_2024"] = df2["annual_coverage_1960_2024"].map(lambda x: f"{x:.3f}")

    for cat in UNIVERSE_CATEGORIES:
        sub = df2[df2["universe_category"] == cat]
        if sub.empty:
            continue
        lines.append(f"### {cat}（{sub.shape[0]}）")
        lines.append("")

        # Quick range stats
        def _min_date(col: str) -> str:
            x = pd.to_datetime(sub[col], errors="coerce").min()
            return "" if pd.isna(x) else pd.Timestamp(x).strftime("%Y-%m-%d")

        def _max_date(col: str) -> str:
            x = pd.to_datetime(sub[col], errors="coerce").max()
            return "" if pd.isna(x) else pd.Timestamp(x).strftime("%Y-%m-%d")

        lines.append(
            f"- 月频面板可用区间（按非空统计）：{_min_date('monthly_first')} ~ {_max_date('monthly_last')}"
        )
        lines.append(
            f"- 年频面板可用区间（按非空统计）：{_min_date('annual_first')} ~ {_max_date('annual_last')}"
        )
        lines.append("")

        lines.append(sub[show_cols].to_markdown(index=False))
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    monthly_path = Path("data") / "indicator_panel_monthly.parquet"
    annual_path = Path("data") / "indicator_panel_annual.parquet"
    df_m = _load_panel(monthly_path)
    df_a = _load_panel(annual_path)

    summary = build_summary_df(df_m, df_a)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    n = int(summary.shape[0])

    csv_path = out_dir / f"indicator_universe_{n}_mapped.csv"
    md_path = out_dir / f"indicator_universe_{n}_mapped.md"
    latest_csv = out_dir / "indicator_universe_latest_mapped.csv"
    latest_md = out_dir / "indicator_universe_latest_mapped.md"

    summary.to_csv(csv_path, index=False)
    summary.to_csv(latest_csv, index=False)

    md_text = build_markdown(summary)
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {latest_md}")
    print(f"Wrote {latest_csv}")


if __name__ == "__main__":
    main()
