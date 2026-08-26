import pytest

from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.workbench import MarketMapEngine, MarketMapError


def _quote(
    symbol,
    name,
    *,
    industry,
    industry_l1="",
    industry_l2="",
    change=1.0,
    market_cap=5e10,
    float_cap=3e10,
    amount=1e9,
):
    row = {
        "symbol": symbol,
        "name": name,
        "market": "CN",
        "exchange": "",
        "price": 20.0,
        "change_pct": change,
        "amount": amount,
        "turnover_pct": 3.0,
        "volume_ratio": 1.2,
        "market_cap": market_cap,
        "float_market_cap": float_cap,
        "pe": 25.0,
        "pb": 3.0,
        "industry": industry,
    }
    if industry_l1:
        row["industry_l1"] = industry_l1
    if industry_l2:
        row["industry_l2"] = industry_l2
    return row


class MapProvider(MarketDataProvider):
    name = "fixture-desk"

    def __init__(self, *, fail_sort=None):
        self.fail_sort = fail_sort
        self.scan_calls = []

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        raise NotImplementedError

    def get_stock_scan(self, *, sort="amount", order="desc", limit=50):
        self.scan_calls.append((sort, order, limit))
        if sort == self.fail_sort:
            raise MarketDataError(f"{sort} unavailable")
        rows = [
            _quote("688001", "芯片", industry="半导体", change=2.0),
            _quote("688002", "材料", industry="电子化学品Ⅱ", change=1.0, market_cap=0),
            _quote("688003", "未知", industry="未来产业", change=-1.0, market_cap=0, float_cap=0),
        ]
        return {
            "items": rows,
            "source": self.name,
            "as_of": "2026-08-13T15:00:00+08:00",
            "coverage": {
                "requested": limit,
                "returned": len(rows),
                "sort_basis": sort,
                "scope": "full_market_ranked_top",
            },
        }


class LargeMapProvider(MapProvider):
    def get_stock_scan(self, *, sort="amount", order="desc", limit=50):
        self.scan_calls.append((sort, order, limit))
        if sort == self.fail_sort:
            raise MarketDataError(f"{sort} unavailable")
        blocks = {
            ("marketCap", "desc"): 0,
            ("amount", "desc"): 1,
            ("turnoverPct", "desc"): 2,
            ("volumeRatio", "desc"): 3,
            ("changePct", "desc"): 4,
            ("changePct", "asc"): 5,
        }
        block = blocks[(sort, order)]
        industries = ("银行", "半导体", "通信设备")
        rows = [
            _quote(
                f"{600000 + block * 100 + index:06d}",
                f"样本{block}-{index}",
                industry=industries[index % len(industries)],
                change=(index % 21) - 10,
                market_cap=(700 - block * 100 - index) * 1e8,
                amount=(index + 1) * 1e7,
            )
            for index in range(min(limit, 100))
        ]
        return {
            "items": rows,
            "source": f"fixture-{sort}-{order}",
            "as_of": "2026-08-13T15:00:00+08:00",
            "coverage": {
                "requested": limit,
                "returned": len(rows),
                "sort_basis": sort,
                "scope": "full_market_ranked_top",
            },
        }


def test_market_map_top100_uses_only_market_cap_ranking_and_discloses_fallbacks():
    provider = MapProvider()
    result = MarketMapEngine(provider).analyze(capacity=100)

    assert provider.scan_calls == [("marketCap", "desc", 100)]
    assert result["engine"]["name"] == "instock-market-map"
    assert result["coverage"]["pool_kind"] == "market_cap_ranked_top"
    assert result["coverage"]["requested_capacity"] == 100
    assert result["coverage"]["displayed_securities"] == 3
    assert result["coverage"]["represented_l1_industries"] == 1
    assert result["coverage"]["unclassified_securities"] == 1
    assert result["coverage"]["float_market_cap_fallback_count"] == 1
    assert result["coverage"]["amount_fallback_count"] == 1
    assert [group["name"] for group in result["groups"]] == ["电子", "未分类"]
    assert result["groups"][0]["stock_count"] == 2
    assert result["groups"][0]["secondary_count"] == 2
    assert [group["name"] for group in result["groups"][0]["secondary_groups"]] == [
        "半导体",
        "电子化学品Ⅱ",
    ]
    assert result["coverage"]["verified_l2_securities"] == 2
    assert result["coverage"]["represented_l2_industries"] == 2
    assert result["groups"][0]["items"][0]["rank_sources"] == [
        {"id": "market_cap", "label": "市值", "rank": 1}
    ]
    assert "market_map_uses_float_market_cap_fallback" in result["limitations"]
    assert "market_map_uses_amount_fallback" in result["limitations"]
    assert result["snapshot"]["parameters"] == {"capacity": 100, "perRankingLimit": 100}


def test_market_map_top500_is_round_robin_multi_rank_union_not_market_cap_claim():
    provider = LargeMapProvider()
    result = MarketMapEngine(provider).analyze(capacity=500)

    assert len(provider.scan_calls) == 6
    assert result["data_state"] == "complete"
    assert result["coverage"]["pool_kind"] == "multi_rank_union"
    assert result["coverage"]["unique_securities"] == 600
    assert result["coverage"]["displayed_securities"] == 500
    assert result["coverage"]["rankings_succeeded"] == 6
    assert len(result["coverage"]["contributing_rankings"]) == 6
    assert result["coverage"]["full_market"] is False
    assert "top500_is_multi_rank_union_not_market_cap_top500" in result["limitations"]
    symbols = {
        item["symbol"]
        for group in result["groups"]
        for item in group["items"]
    }
    assert len(symbols) == 500
    assert any(symbol.startswith("6004") for symbol in symbols)


def test_market_map_top500_keeps_partial_union_when_one_ranking_fails():
    result = MarketMapEngine(
        LargeMapProvider(fail_sort="turnoverPct")
    ).analyze(capacity=500)

    assert result["data_state"] == "partial"
    assert result["coverage"]["rankings_succeeded"] == 5
    assert result["failures"][0]["ranking"] == "turnover"
    assert "partial_ranking_coverage" in result["limitations"]


def test_market_map_rejects_unsupported_capacity():
    with pytest.raises(MarketMapError, match="Top100"):
        MarketMapEngine(MapProvider()).analyze(capacity=200)


def test_market_map_uses_real_l1_l2_hierarchy_and_keeps_ambiguous_rows_at_l1():
    rows = [
        _quote("300308", "中际旭创", industry="通信设备"),
        _quote("600030", "中信证券", industry="证券"),
        _quote("601398", "工商银行", industry="银行Ⅱ"),
        _quote(
            "688825",
            "长鑫科技",
            industry="电子",
            industry_l1="电子",
            industry_l2="半导体",
        ),
    ]

    groups, coverage, _ = MarketMapEngine._build_groups(rows)
    by_name = {group["name"]: group for group in groups}

    assert [group["name"] for group in by_name["通信"]["secondary_groups"]] == [
        "通信设备"
    ]
    assert [group["name"] for group in by_name["非银金融"]["secondary_groups"]] == [
        "证券Ⅱ"
    ]
    assert [group["name"] for group in by_name["电子"]["secondary_groups"]] == [
        "半导体"
    ]
    assert by_name["银行"]["secondary_groups"] == []
    assert [item["symbol"] for item in by_name["银行"]["direct_items"]] == ["601398"]
    assert coverage["verified_l2_securities"] == 3
    assert coverage["l1_only_securities"] == 1
    assert coverage["total_l2_industries"] == 134
