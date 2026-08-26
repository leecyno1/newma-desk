"""
Generate a domestic investable instrument list (ETFs/LOFs) from Tushare Pro.

Outputs:
- cycle_analysis_system/docs/DOMESTIC_INVESTABLE_LIST_2026.md

This is meant to be used as an appendix for the 2026 outlook article, with a
China-focused mapping from global themes to onshore investable tickers.
"""

from __future__ import annotations

from pathlib import Path
import os

import pandas as pd


def _get_pro():
    import tushare as ts  # type: ignore

    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("Missing TUSHARE_TOKEN in environment.")
    ts.set_token(token)
    return ts.pro_api()


def _fund_basic_etf() -> pd.DataFrame:
    pro = _get_pro()
    df = pro.fund_basic(market="E")
    # Keep only listed-ish products (L=listed, I=issuing, D=delisted)
    keep = ["ts_code", "name", "fund_type", "invest_type", "management", "status", "market"]
    df = df[keep].copy()
    return df


def _filter(df: pd.DataFrame, keyword: str, regex: bool = False) -> pd.DataFrame:
    m = df["name"].str.contains(keyword, regex=regex, na=False)
    return df[m].copy()


def _format_table(df: pd.DataFrame, limit: int = 30) -> str:
    if df.empty:
        return "_（未检索到）_"
    show = df.sort_values(["status", "name"]).head(limit)
    return show.to_markdown(index=False)


def build_md(df: pd.DataFrame) -> str:
    lines: list[str] = []
    lines.append("# 国内可投资标的清单（基于 Tushare Pro `fund_basic(market='E')` 自动生成）")
    lines.append("")
    lines.append("> 用途：作为《2026年全球资产配置展望》的国内可投资映射附录。")
    lines.append("> 说明：本清单仅列示可交易品种，不构成投资建议；最终选择请以规模、跟踪误差与流动性为准。")
    lines.append("")

    sections = [
        ("A股宽基：A500/沪深300/中证500/中证1000", [
            ("A500", r"A500|中证A500"),
            ("沪深300", "沪深300"),
            ("中证500", "中证500"),
            ("中证1000", "中证1000"),
        ]),
        ("风格与策略：红利/价值/成长/现金流", [
            ("红利", "红利"),
            ("价值", "价值ETF"),
            ("成长", "成长ETF"),
            ("现金流", "现金流"),
        ]),
        ("科技与产业链：科创/创业板/半导体/算力/机器人", [
            ("科创50", "科创50"),
            ("创业板", "创业板"),
            ("半导体", "半导体"),
            ("算力", "算力"),
            ("机器人", "机器人"),
        ]),
        ("资源与实物：黄金/白银/油气/有色/豆粕", [
            ("黄金", "黄金"),
            ("白银", "白银"),
            ("原油", "原油"),
            ("油气", "油气"),
            ("有色金属", "有色金属"),
            ("豆粕", "豆粕"),
        ]),
        ("利率与固收：国债/政金债/信用债/可转债/货币ETF", [
            ("国债ETF", "国债ETF"),
            ("政金债", "政金债"),
            ("信用债", "信用债"),
            ("可转债", "可转债"),
            ("货币ETF", "货币ETF"),
        ]),
        ("海外可投资映射（QDII/跨境）：标普/纳指/日经/德国/法国/港股/中概", [
            ("标普500/标普", "标普"),
            ("纳指", "纳指"),
            ("日经", "日经"),
            ("德国", "德国"),
            ("法国", "法国"),
            ("恒生/港股通", "恒生"),
            ("中概", "中概"),
        ]),
    ]

    for title, items in sections:
        lines.append(f"## {title}")
        lines.append("")
        for sub_title, kw in items:
            sub = _filter(df, kw, regex=kw.startswith("A500") or "|" in kw)
            # Keep only listed products by default
            sub = sub[sub["status"].isin(["L", "I"])].copy()
            lines.append(f"### {sub_title}")
            lines.append("")
            lines.append(_format_table(sub, limit=30))
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    df = _fund_basic_etf()
    md = build_md(df)
    out_path = Path("cycle_analysis_system") / "docs" / "DOMESTIC_INVESTABLE_LIST_2026.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

