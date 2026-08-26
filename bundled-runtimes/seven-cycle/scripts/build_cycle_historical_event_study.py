from __future__ import annotations

"""Build a descriptive event study from robust annual and monthly cycle timelines."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from cycle_robustness_core import ROOT


ANNUAL_PATH = ROOT / "output" / "cycle_phase_timeline_robust_annual.parquet"
HYBRID_PATH = ROOT / "output" / "cycle_phase_timeline_robust_hybrid.parquet"
OUT_DETAIL = ROOT / "output" / "cycle_historical_event_study_detail.csv"
OUT_SUMMARY = ROOT / "output" / "cycle_historical_event_study_summary.csv"
OUT_REPORT = ROOT / "output" / "cycle_historical_event_study.md"


PHASE_LABELS = {
    1: "Expansion",
    2: "Downturn",
    3: "Contraction",
    4: "Recovery",
}


@dataclass(frozen=True)
class Event:
    name: str
    scope: str
    start: str
    anchor: str
    end: str
    description: str


EVENTS = (
    Event("South Sea Bubble", "annual", "1717", "1720", "1724", "British credit and asset-price reversal"),
    Event("Credit Crisis of 1772", "annual", "1769", "1772", "1776", "Atlantic credit contraction"),
    Event("Railway Mania Crisis", "annual", "1844", "1847", "1852", "Investment boom and financial retrenchment"),
    Event("Long Depression Onset", "annual", "1870", "1873", "1880", "Post-railway deflation and financial stress"),
    Event("World War I", "annual", "1911", "1914", "1919", "War mobilisation and price disruption"),
    Event("Great Depression", "annual", "1926", "1929", "1935", "Global output and financial collapse"),
    Event("World War II", "annual", "1936", "1939", "1946", "War mobilisation and post-war transition"),
    Event("1970s Oil and Inflation Shock", "annual", "1970", "1973", "1982", "Commodity shock, inflation and tightening"),
    Event("Global Financial Crisis", "annual", "2005", "2008", "2012", "Credit bust and policy response"),
    Event("COVID-19 Shock", "annual", "2017", "2020", "2024", "Pandemic collapse and reopening inflation"),
    Event("Dot-com Bust", "monthly", "2000-03-31", "2001-09-30", "2003-03-31", "Equity and technology investment reversal"),
    Event("Global Financial Crisis", "monthly", "2007-07-31", "2008-09-30", "2010-06-30", "Global credit seizure and policy rescue"),
    Event("Euro-area Debt Crisis", "monthly", "2010-04-30", "2011-10-31", "2013-06-30", "Sovereign stress and recession"),
    Event("China Slowdown and Market Stress", "monthly", "2014-06-30", "2015-08-31", "2016-12-31", "Industrial slowdown and market volatility"),
    Event("COVID-19 Shock", "monthly", "2019-07-31", "2020-03-31", "2021-12-31", "Pandemic shock and global reopening"),
    Event("Inflation and Tightening", "monthly", "2021-01-31", "2022-06-30", "2023-12-31", "Inflation surge and rapid rate increases"),
    Event("Post-pandemic Divergence", "monthly", "2024-01-31", "2025-06-30", "2025-12-31", "Disinflation with uneven regional growth"),
)


def nearest_label(index: pd.Index, value: str, scope: str):
    if scope == "annual":
        target = int(value)
        position = index.get_indexer([target], method="nearest")[0]
    else:
        target = pd.Timestamp(value).to_period("M").to_timestamp("M")
        position = index.get_indexer([target], method="nearest")[0]
    return index[position]


def phase_text(value: float) -> str:
    if not np.isfinite(value):
        return "NA"
    phase = int(value)
    return PHASE_LABELS.get(phase, "NA")


def event_rows(event: Event, timeline: pd.DataFrame) -> list[dict[str, object]]:
    start_label = nearest_label(timeline.index, event.start, event.scope)
    anchor_label = nearest_label(timeline.index, event.anchor, event.scope)
    end_label = nearest_label(timeline.index, event.end, event.scope)
    rows = []
    for phase_column in [column for column in timeline.columns if column.startswith("Phase_")]:
        cycle = phase_column.removeprefix("Phase_")
        component_column = f"Cycle_{cycle}"
        start_level = float(timeline.loc[start_label, component_column])
        anchor_level = float(timeline.loc[anchor_label, component_column])
        end_level = float(timeline.loc[end_label, component_column])
        rows.append(
            {
                "event": event.name,
                "scope": event.scope,
                "description": event.description,
                "cycle": cycle,
                "start": start_label,
                "anchor": anchor_label,
                "end": end_label,
                "phase_start": phase_text(float(timeline.loc[start_label, phase_column])),
                "phase_anchor": phase_text(float(timeline.loc[anchor_label, phase_column])),
                "phase_end": phase_text(float(timeline.loc[end_label, phase_column])),
                "level_start": start_level,
                "level_anchor": anchor_level,
                "level_end": end_level,
                "change_to_anchor": anchor_level - start_level,
                "change_after_anchor": end_level - anchor_level,
            }
        )
    return rows


def summarize_events(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (event, scope), group in detail.groupby(["event", "scope"], sort=False):
        anchor_phases = dict(zip(group["cycle"], group["phase_anchor"]))
        stress_count = int(group["phase_anchor"].isin(["Downturn", "Contraction"]).sum())
        tailwind_count = int(group["phase_anchor"].isin(["Expansion", "Recovery"]).sum())
        if stress_count > tailwind_count:
            classification = "cycle_headwind"
        elif tailwind_count > stress_count:
            classification = "cycle_tailwind_or_recovery"
        else:
            classification = "mixed"
        rows.append(
            {
                "event": event,
                "scope": scope,
                "anchor": group["anchor"].iloc[0],
                "cycle_count": len(group),
                "stress_count": stress_count,
                "tailwind_count": tailwind_count,
                "classification": classification,
                "anchor_phases": "; ".join(f"{cycle}={phase}" for cycle, phase in anchor_phases.items()),
            }
        )
    return pd.DataFrame(rows)


def write_report(summary: pd.DataFrame, detail: pd.DataFrame) -> None:
    annual_summary = summary[summary["scope"] == "annual"].copy()
    monthly_summary = summary[summary["scope"] == "monthly"].copy()
    monthly_detail = detail[detail["scope"] == "monthly"].copy()
    phase_transition = (
        monthly_detail.groupby("cycle")
        .apply(
            lambda group: pd.Series(
                {
                    "event_count": group["event"].nunique(),
                    "anchor_stress_share": group["phase_anchor"].isin(["Downturn", "Contraction"]).mean(),
                    "end_recovery_share": group["phase_end"].isin(["Expansion", "Recovery"]).mean(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )

    lines = [
        "# 多周期历史事件检验",
        "",
        "## 结论",
        "",
        "- 周期状态对部分危机提供了背景性解释，但并非所有冲击都发生在周期下行阶段；战争、疫情和政策冲击仍包含显著外生部分。",
        "- 历史事件应被理解为“周期位置 × 外生冲击 × 政策响应”的共同结果，不能仅由滤波曲线反推因果。",
        "- 月频事件中，42个月周期更适合描述中期宏观环境；16.5月和21月周期更像市场、流动性与政策节奏。",
        "- 由于使用双边滤波，事件后的数据会改善历史相位识别；本报告是事后解释，不是实时预测回测。",
        "",
        "## 长历史事件",
        "",
        annual_summary.to_markdown(index=False),
        "",
        "## 2000年以来月频事件",
        "",
        monthly_summary.to_markdown(index=False),
        "",
        "## 月频周期在事件窗口中的统计",
        "",
        phase_transition.round(4).to_markdown(index=False),
        "",
        "## 使用边界",
        "",
        "1. `cycle_headwind`只表示多数周期处于下行或收缩，不等同于事件由周期造成。",
        "2. 年频事件只能观察9年和14年背景，无法刻画危机发生月份。",
        "3. 组合成员和符号对齐会影响相位，后续需要滚动样本与实时估计复核。",
        "",
        f"- 事件汇总：`{OUT_SUMMARY.relative_to(ROOT)}`",
        f"- 分周期明细：`{OUT_DETAIL.relative_to(ROOT)}`",
        "",
    ]
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    annual = pd.read_parquet(ANNUAL_PATH)
    hybrid = pd.read_parquet(HYBRID_PATH)
    rows = []
    for event in EVENTS:
        timeline = annual if event.scope == "annual" else hybrid
        rows.extend(event_rows(event, timeline))
    detail = pd.DataFrame(rows)
    summary = summarize_events(detail)

    detail.to_csv(OUT_DETAIL, index=False)
    summary.to_csv(OUT_SUMMARY, index=False)
    write_report(summary, detail)

    print("Wrote:", OUT_DETAIL)
    print("Wrote:", OUT_SUMMARY)
    print("Wrote:", OUT_REPORT)


if __name__ == "__main__":
    main()

