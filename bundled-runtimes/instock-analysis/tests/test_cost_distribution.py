from datetime import datetime, timedelta

import pandas as pd

from instock.core.kline.cost_distribution import build_volume_cost_distribution


def _frame(size=120):
    rows = []
    for index in range(size):
        close = 10 + index * 0.05
        rows.append({
            "date": datetime(2026, 1, 1) + timedelta(days=index),
            "open": close - 0.1,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1000 + index * 20,
            "amount": close * (1000 + index * 20),
        })
    return pd.DataFrame(rows)


def test_volume_cost_distribution_builds_normalized_proxy():
    result = build_volume_cost_distribution(_frame())

    assert result["state"] == "available"
    assert result["label"] == "成交成本分布代理"
    assert result["window_bars"] == 120
    assert result["current_price"] > result["average_cost"]
    assert result["profit_volume_pct"] == 100.0
    assert 99.9 <= sum(item["volume_share_pct"] for item in result["profile"]) <= 100.1
    assert result["intervals"]["70"]["low"] < result["intervals"]["70"]["high"]
    assert "volume_price_proxy_not_shareholder_chip_distribution" in result["limitations"]


def test_volume_cost_distribution_rejects_zero_volume_input():
    frame = _frame(20)
    frame["volume"] = 0

    result = build_volume_cost_distribution(frame)

    assert result["state"] == "unavailable"
    assert result["profile"] == []
