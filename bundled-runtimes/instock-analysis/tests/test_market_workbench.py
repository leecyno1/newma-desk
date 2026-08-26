from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.workbench import MarketWorkbenchEngine, MarketWorkbenchError


def _quote(symbol, name, *, change, amount, turnover, volume_ratio, industry):
    return {
        "symbol": symbol,
        "name": name,
        "price": 20.0,
        "change_pct": change,
        "amount": amount,
        "turnover_pct": turnover,
        "volume_ratio": volume_ratio,
        "market_cap": 50_000_000_000,
        "float_market_cap": 30_000_000_000,
        "pe": 25.0,
        "pb": 3.0,
        "industry": industry,
    }


ITEMS = [
    _quote("300502", "新易盛", change=7.2, amount=8.2e9, turnover=8.1, volume_ratio=2.4, industry="通信"),
    _quote("000001", "平安银行", change=1.1, amount=5.5e9, turnover=1.2, volume_ratio=1.1, industry="银行"),
    _quote("600000", "浦发银行", change=-2.4, amount=3.1e9, turnover=0.9, volume_ratio=0.8, industry="银行"),
]


class FixtureProvider(MarketDataProvider):
    name = "fixture-desk"

    def __init__(self, fail_sort=None, fail_overview=False):
        self.fail_sort = fail_sort
        self.fail_overview = fail_overview
        self.scan_calls = []
        self.turnover_calls = []

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        raise NotImplementedError

    def get_market_overview(self):
        if self.fail_overview:
            raise MarketDataError("overview unavailable")
        return {
            "sentiment": {"up": 3405, "down": 1664, "flat": 128, "breadth": "偏强"},
            "sectors": [
                {"name": "通信", "pct": 3.2, "net": 8.1, "firms": 90},
                {"name": "银行", "pct": -0.7, "net": -2.2, "firms": 42},
            ],
            "updated": "2026-08-11 15:00:00",
        }

    def get_market_emotion(self):
        return {"state": "available", "limit_up_count": 12, "limit_down_count": 3}

    def get_stock_scan(self, *, sort="amount", order="desc", limit=50):
        self.scan_calls.append((sort, order, limit))
        if sort == self.fail_sort:
            raise MarketDataError(f"{sort} unavailable")
        rows = [dict(row) for row in ITEMS]
        key = {
            "changePct": "change_pct",
            "amount": "amount",
            "turnoverPct": "turnover_pct",
            "volumeRatio": "volume_ratio",
            "marketCap": "market_cap",
        }[sort]
        rows.sort(key=lambda row: row[key], reverse=order == "desc")
        return {
            "items": rows,
            "source": self.name,
            "as_of": "2026-08-11T15:00:00+08:00",
            "coverage": {
                "requested": limit,
                "returned": len(rows),
                "sort_basis": sort,
                "scope": "full_market_ranked_top",
            },
        }

    def get_market_turnover_top(self, *, limit=20):
        self.turnover_calls.append(limit)
        rows = [
            dict(row)
            for row in sorted(ITEMS, key=lambda row: row["amount"], reverse=True)[:limit]
        ]
        return {
            "items": rows,
            "source": "fixture-turnover",
            "as_of": "2026-08-11T15:00:00+08:00",
            "coverage": {
                "requested": limit,
                "returned": len(rows),
                "sort_basis": "amount",
                "scope": "full_market_top20",
            },
        }


def test_market_workbench_builds_desk_native_market_tape():
    provider = FixtureProvider()
    result = MarketWorkbenchEngine(provider).analyze(scan_limit=50)

    assert result["engine"]["name"] == "instock-market-workbench"
    assert result["data_state"] == "complete"
    assert result["summary"] == {
        "market_breadth": "偏强",
        "up": 3405,
        "down": 1664,
        "flat": 128,
        "up_ratio": 65.52,
        "leading_sector": "通信",
        "most_active_symbol": "300502",
        "most_active_name": "新易盛",
    }
    assert result["leaderboards"]["gainers"][0]["symbol"] == "300502"
    assert result["leaderboards"]["losers"][0]["symbol"] == "600000"
    assert result["leaderboards"]["amount"][0]["amount"] == 8.2e9
    assert result["leaderboards"]["turnover"][0]["name"] == "新易盛"
    assert result["leaderboards"]["volume_ratio"][0]["volume_ratio"] == 2.4
    assert result["market_emotion"] == {
        "state": "available", "limit_up_count": 12, "limit_down_count": 3
    }
    assert result["sector_leaders"][0]["name"] == "通信"
    assert result["sector_basis"] == {
        "source": "desk_overview", "sample_size": 0, "sample_sort": None
    }
    anomalies = result["market_anomalies"]
    assert anomalies["volume_spikes"][0]["symbol"] == "300502"
    assert anomalies["turnover_heat"][0]["symbol"] == "300502"
    assert anomalies["price_volume_surges"][0]["signal"] == "量价同步上行"
    assert anomalies["sector_fund_flows"][0] == {
        "name": "通信",
        "change_pct": 3.2,
        "net": 8.1,
        "direction": "inflow",
        "source": "desk_overview",
    }
    assert [item["label"] for item in anomalies["unavailable_topics"]] == [
        "早盘抢筹", "尾盘抢筹", "涨停原因 / 概念资金",
    ]
    assert result["snapshot"]["analysis"]["name"] == "instock-market-workbench"
    assert result["snapshot"]["parameters"] == {"scanLimit": 50}
    assert len(provider.scan_calls) == 4
    assert not any(call[0] == "marketCap" for call in provider.scan_calls)
    assert provider.turnover_calls == [20]
    assert result["coverage"]["leaderboard_scopes"]["amount"] == "full_market_top20"


def test_market_workbench_marks_partial_scan_and_keeps_available_evidence():
    result = MarketWorkbenchEngine(
        FixtureProvider(fail_sort="turnoverPct", fail_overview=True)
    ).analyze(scan_limit=50)

    assert result["data_state"] == "partial"
    assert result["leaderboards"]["turnover"] == []
    assert result["leaderboards"]["amount"][0]["symbol"] == "300502"
    assert "overview_unavailable" in result["limitations"]
    assert any(item["board"] == "turnover" for item in result["failures"])


def test_market_workbench_marks_emotion_failure_without_faking_zero_counts():
    class EmotionFailureProvider(FixtureProvider):
        def get_market_emotion(self):
            raise MarketDataError("emotion unavailable")

    result = MarketWorkbenchEngine(EmotionFailureProvider()).analyze(scan_limit=50)

    assert result["data_state"] == "partial"
    assert result["market_emotion"] == {
        "state": "unavailable", "leaders": [], "ladder": []
    }
    assert "market_emotion_unavailable" in result["limitations"]
    assert any(item["board"] == "market_emotion" for item in result["failures"])


def test_market_workbench_derives_honest_sector_sample_when_desk_sector_is_empty():
    class EmptySectorProvider(FixtureProvider):
        def get_market_overview(self):
            result = super().get_market_overview()
            result["sectors"] = []
            return result

    result = MarketWorkbenchEngine(EmptySectorProvider()).analyze(scan_limit=50)

    assert result["data_state"] == "partial"
    assert result["sector_basis"] == {
        "source": "ranked_scan_sample", "sample_size": 3, "sample_sort": "amount"
    }
    assert result["sector_leaders"] == [{
        "name": "银行",
        "change_pct": -0.65,
        "net": 0.0,
        "firms": 2,
        "up_ratio": 50.0,
        "source": "ranked_scan_sample",
    }]
    assert result["summary"]["leading_sector"] == "银行"
    assert "sector_leaders_from_ranked_scan_sample" in result["limitations"]


def test_market_workbench_marks_missing_market_breadth_without_zero_claims():
    class MissingBreadthProvider(FixtureProvider):
        def get_market_overview(self):
            result = super().get_market_overview()
            result["sentiment"] = {}
            return result

    result = MarketWorkbenchEngine(MissingBreadthProvider()).analyze(scan_limit=50)

    assert result["data_state"] == "partial"
    assert result["market_breadth"]["state"] == "unavailable"
    assert "market_breadth_unavailable" in result["limitations"]


def test_market_workbench_does_not_build_zero_filled_turnover_or_volume_ratio_boards():
    class MissingFieldProvider(FixtureProvider):
        def get_stock_scan(self, *, sort="amount", order="desc", limit=50):
            result = super().get_stock_scan(sort=sort, order=order, limit=limit)
            if sort == "turnoverPct":
                for row in result["items"]:
                    row["turnover_pct"] = 0
            if sort == "volumeRatio":
                for row in result["items"]:
                    row["volume_ratio"] = 0
            return result

    result = MarketWorkbenchEngine(MissingFieldProvider()).analyze(scan_limit=50)

    assert result["data_state"] == "partial"
    assert result["leaderboards"]["turnover"] == []
    assert result["leaderboards"]["volume_ratio"] == []
    assert "turnover_leaderboard_unavailable" in result["limitations"]
    assert "volume_ratio_leaderboard_unavailable" in result["limitations"]


def test_market_workbench_requires_at_least_one_scan():
    class EmptyProvider(FixtureProvider):
        def get_stock_scan(self, **kwargs):
            raise MarketDataError("scan unavailable")

        def get_market_turnover_top(self, **kwargs):
            raise MarketDataError("turnover unavailable")

    try:
        MarketWorkbenchEngine(EmptyProvider()).analyze(scan_limit=50)
    except MarketWorkbenchError as exc:
        assert "扫描" in str(exc)
    else:
        raise AssertionError("expected MarketWorkbenchError")


def test_market_workbench_limit_watch_respects_board_rules_and_skips_new_listings():
    rows = [
        _quote("000001", "主板观察", change=9.2, amount=1e9, turnover=5, volume_ratio=1.8, industry="银行"),
        _quote("000002", "略超阈值", change=10.3, amount=1e9, turnover=5, volume_ratio=1.8, industry="银行"),
        _quote("300001", "创业观察", change=18.5, amount=1e9, turnover=5, volume_ratio=1.8, industry="电子"),
        _quote("688001", "N新股", change=19.9, amount=1e9, turnover=5, volume_ratio=1.8, industry="电子"),
    ]

    anomalies = MarketWorkbenchEngine._market_anomalies(rows, [])

    assert [(item["symbol"], item["limit_pct"]) for item in anomalies["limit_watch"]] == [
        ("000002", 10.0),
        ("000001", 10.0),
        ("300001", 20.0),
    ]
    states = {item["symbol"]: item["threshold_state"] for item in anomalies["limit_watch"]}
    assert states == {"000002": "above", "000001": "below", "300001": "below"}
