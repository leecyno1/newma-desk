import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.investment_analysis_service import InvestmentAnalysisService  # noqa: E402
from services.performance_attribution_service import PerformanceAttributionService  # noqa: E402


class FakeMarketDataAdapter:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get_benchmark_nav(self, benchmark_code, start_date, end_date):
        self.calls.append((benchmark_code, start_date, end_date))
        return list(self.rows)


def main() -> int:
    attribution = PerformanceAttributionService()
    mapped_code, mapped_source = attribution._resolve_benchmark(
        None,
        {"benchmark_mapping": {"benchmark_code": "000905.SH"}},
    )
    if (mapped_code, mapped_source) != ("000905.SH", "fund_classification_catalog"):
        raise AssertionError(f"Default attribution benchmark must come from classification: {(mapped_code, mapped_source)}")

    detailed_code, detailed_source, detailed_mapping = attribution._resolve_attribution_benchmark(
        None,
        {
            "primary_benchmark": "中证500",
            "benchmark_mapping": {
                "benchmark_code": "000905.SH",
                "benchmark_name": "中证500",
                "benchmark_type": "tracked_index",
                "confidence": 0.99,
            },
        },
        {},
    )
    if (detailed_code, detailed_source) != ("000905.SH", "fund_classification_catalog"):
        raise AssertionError(f"Classification benchmark detail lost its source: {(detailed_code, detailed_source)}")
    if detailed_mapping.get("benchmark_name") != "中证500" or detailed_mapping.get("benchmark_code") != "000905.SH":
        raise AssertionError(f"Classification benchmark name/code missing from attribution evidence: {detailed_mapping}")

    override_code, override_source = attribution._resolve_benchmark("000852", {})
    if (override_code, override_source) != ("000852.SH", "user_override"):
        raise AssertionError(f"Explicit benchmark override should be normalized and disclosed: {(override_code, override_source)}")

    missing_code, missing_source = attribution._resolve_benchmark(None, {})
    if missing_code is not None or missing_source != "missing_classification_benchmark":
        raise AssertionError(f"Missing classification benchmark must remain unavailable: {(missing_code, missing_source)}")

    declared_code, declared_source, declared_detail = attribution._resolve_attribution_benchmark(
        None,
        {"benchmark_mapping": {"benchmark_code": "MIXED-EQUITY-60"}},
        {"raw_data": {"universe": {"benchmark": "中证800指数收益率×85%+上证国债指数收益率×15%"}}},
    )
    if declared_code != "000906.SH" or declared_source != "fund_declared_benchmark_equity_component":
        raise AssertionError(f"Mixed fund attribution must resolve its declared equity component: {(declared_code, declared_source)}")
    if declared_detail.get("declared_weight") != 0.85:
        raise AssertionError(f"Declared equity benchmark weight missing: {declared_detail}")

    verified_sector_cases = {
        "中债-综合指数×20%+中证医药卫生指数×80%": ("000933.SH", 0.8),
        "中债-综合指数-财富指数×50%+中证环保产业指数×50%": ("000827.SH", 0.5),
        "上海证券交易所国债指数×20%+沪深300金融地产指数×80%": ("000914.SH", 0.8),
        "中国战略新兴产业成份指数收益率×65%+中债综合指数收益率×35%": ("000171.CSI", 0.65),
        "中证TMT产业主题指数收益率×80%+中证全债指数收益率×20%": ("000998.CSI", 0.8),
        "中证综合债券指数×50%+国证航天军工指数×50%": ("399368.SZ", 0.5),
        "中债-综合指数×50%+中证移动互联网指数×50%": ("399970.SZ", 0.5),
        "中证周期100指数收益率×75%+恒生指数收益率×5%+中证综合债指数收益率×20%": ("931355.CSI", 0.75),
        "中证沪港深高股息精选指数收益率×80%+中债综合指数收益率×20%": ("930836.CSI", 0.8),
        "中证港股通综合指数收益率×70%+中债新综合指数×30%": ("930930.CSI", 0.7),
    }
    for declared_benchmark, expected in verified_sector_cases.items():
        sector_code, sector_source, sector_detail = attribution._resolve_attribution_benchmark(
            None,
            {"benchmark_mapping": {"benchmark_code": "SECTOR-BUCKET"}},
            {"raw_data": {"universe": {"benchmark": declared_benchmark}}},
        )
        if (sector_code, sector_detail.get("declared_weight")) != expected:
            raise AssertionError(
                f"Verified sector benchmark was not resolved: "
                f"{declared_benchmark} -> {(sector_code, sector_detail)}"
            )
        if sector_source != "fund_declared_benchmark_equity_component":
            raise AssertionError(f"Verified sector benchmark lost its evidence source: {sector_source}")

    consumption_code, consumption_source, consumption_detail = attribution._resolve_attribution_benchmark(
        None,
        {"benchmark_mapping": {"benchmark_code": "MIXED-EQUITY-60"}},
        {
            "raw_data": {
                "universe": {
                    "benchmark": "上海证券交易所国债指数×20%+中证可选消费指数×40%+中证主要消费指数×40%"
                }
            }
        },
    )
    if consumption_code != "000931.CSI" or consumption_source != "fund_declared_benchmark_equity_component":
        raise AssertionError(f"Consumption composite benchmark was not resolved: {(consumption_code, consumption_source)}")
    consumption_components = consumption_detail.get("equity_components") or []
    if [(item.get("code"), item.get("weight")) for item in consumption_components] != [
        ("000931.CSI", 0.4),
        ("000932.SH", 0.4),
    ]:
        raise AssertionError(f"Consumption composite components lost contract weights: {consumption_detail}")

    technology_code, _, technology_detail = attribution._resolve_attribution_benchmark(
        None,
        {"benchmark_mapping": {"benchmark_code": "MIXED-EQUITY-60"}},
        {
            "raw_data": {
                "universe": {
                    "benchmark": "中证科技100指数收益率×80%+中证港股通综合指数收益率×10%+中债总指数收益率×10%"
                }
            }
        },
    )
    if technology_code != "931187.CSI":
        raise AssertionError(f"Technology composite benchmark was not resolved: {technology_detail}")
    if [item.get("code") for item in technology_detail.get("equity_components") or []] != [
        "931187.CSI",
        "930930.CSI",
    ]:
        raise AssertionError(f"Technology composite lost its mainland and Hong Kong components: {technology_detail}")

    qualified_code, _, qualified_detail = attribution._resolve_attribution_benchmark(
        None,
        {"benchmark_mapping": {"benchmark_code": "MIXED-BALANCED-30-60"}},
        {
            "raw_data": {
                "universe": {
                    "benchmark": "沪深300指数收益率×17%+中证港股通综合指数(人民币)收益率×3%+中债综合财富(总值)指数收益率×80%"
                }
            }
        },
    )
    if qualified_code != "000300.SH" or [
        item.get("weight") for item in qualified_detail.get("equity_components") or []
    ] != [0.17, 0.03]:
        raise AssertionError(f"Currency-qualified contract index weights were not parsed: {qualified_detail}")

    state_owned_code, _, state_owned_detail = attribution._resolve_attribution_benchmark(
        None,
        {"benchmark_mapping": {"benchmark_code": "MIXED-EQUITY-60"}},
        {
            "raw_data": {
                "universe": {
                    "benchmark": "中证国有企业综合指数收益率×50%+中证国新央企综合指数收益率×20%+恒生中国企业指数收益率×10%+中证综合债指数收益率×20%"
                }
            }
        },
    )
    if state_owned_code != "000955.CSI" or [
        item.get("code") for item in state_owned_detail.get("equity_components") or []
    ] != ["000955.CSI", "932004.CSI"]:
        raise AssertionError(f"State-owned enterprise composite was not resolved: {state_owned_detail}")

    rate_only = attribution._brinson_evidence(
        data_service=object(),
        fund={
            "type": "混合型",
            "raw_data": {"universe": {"benchmark": "一年定期存款利率(税后)×100%+2%"}},
        },
        holdings=[{"stock_code": "600000.SH", "weight": 0.1}],
        benchmark_code=None,
        benchmark_source="missing_verifiable_attribution_benchmark",
        benchmark_detail={"declared_benchmark": "一年定期存款利率(税后)×100%+2%"},
        attribution_quarter="2026Q2",
        holding_quarter="2026Q1",
    )
    if rate_only.get("status") != "not_applicable" or "存款利率" not in rate_only.get("missing_items", [""])[0]:
        raise AssertionError(f"Rate-only contract benchmark must not be reported as missing Brinson data: {rate_only}")

    cross_code, cross_source, cross_detail = attribution._resolve_attribution_benchmark(
        None,
        {
            "benchmark_mapping": {
                "benchmark_code": "CONTRACT-CN-HK-EQUITY",
                "benchmark_name": "合同沪港深复合基准",
                "benchmark_type": "contract_composite_benchmark",
                "evidence_refs": {
                    "benchmarkComponents": [
                        {"code": "000300.SH", "weight": 45},
                        {"code": "HSI", "weight": 45},
                        {"code": "H11001.CSI", "weight": 10},
                    ],
                },
            },
        },
        {"raw_data": {"universe": {"benchmark": "沪深300指数×45%+香港恒生指数×45%+中证全债指数×10%"}}},
    )
    if cross_code != "000300.SH" or cross_source != "fund_declared_benchmark_equity_component":
        raise AssertionError(f"Cross-market industry reference must remain explicit: {(cross_code, cross_source)}")
    if len(cross_detail.get("contract_components") or []) != 3:
        raise AssertionError(f"Cross-market contract components missing from attribution evidence: {cross_detail}")

    bond_barra = attribution._barra_evidence(
        {"type": "债券型"},
        [],
        {},
        "2026Q1",
    )
    if bond_barra.get("status") != "not_applicable":
        raise AssertionError(f"Bond funds must not be presented as failed equity Barra models: {bond_barra}")

    bond_status = attribution._aggregate_status("not_applicable", "not_applicable", "insufficient_evidence")
    if bond_status != "not_applicable":
        raise AssertionError(f"Bond equity attribution should aggregate to not_applicable: {bond_status}")
    if attribution._equity_attribution_applicable({"type": "债券型"}):
        raise AssertionError("Bond funds must skip stock holdings and style-profile retrieval before attribution")
    if not attribution._equity_attribution_applicable({"type": "股票型"}):
        raise AssertionError("Equity funds must retain stock holdings attribution")

    market = FakeMarketDataAdapter([
        {"date": "2026-07-01", "nav": 100.0},
        {"date": "2026-07-02", "nav": 101.0},
        {"date": "2026-07-03", "nav": 100.5},
    ])
    nav_analysis = InvestmentAnalysisService(market_data_adapter=market)
    nav_analysis._returns = lambda *_args, **_kwargs: {}
    returns, label, source = nav_analysis._benchmark_returns(
        {"wind_code": "000001.OF", "type": "stock"},
        "000905.SH",
        "2026-07-01",
        "2026-07-03",
    )
    if label != "000905.SH" or source != "market_data_adapter" or len(returns) != 2:
        raise AssertionError(f"Mapped benchmark must use a real benchmark series: {(returns, label, source)}")
    if market.calls != [("000905.SH", "2026-07-01", "2026-07-03")]:
        raise AssertionError(f"Benchmark adapter received the wrong request: {market.calls}")

    empty_market = FakeMarketDataAdapter([])
    unavailable = InvestmentAnalysisService(market_data_adapter=empty_market)
    unavailable._returns = lambda *_args, **_kwargs: {}
    returns, label, source = unavailable._benchmark_returns(
        {"wind_code": "000001.OF", "type": "stock"},
        "000905.SH",
        "2026-07-01",
        "2026-07-03",
    )
    if returns or label != "000905.SH" or source != "benchmark_series_unavailable":
        raise AssertionError(f"Explicit benchmark failure must not fall back to a broad peer average: {(returns, label, source)}")

    print("OK attribution uses classification benchmarks and never disguises peer averages as explicit indexes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
