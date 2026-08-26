from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd

from src.tools import alpha_bench_tool as tool


def _daily() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["20240102"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "vol": [100.0],
            "amount": [105.0],
        }
    )


def test_csi300_fallback_is_disclosed(monkeypatch) -> None:
    class Pro:
        def index_weight(self, **kwargs):
            raise RuntimeError("offline")

        def daily(self, **kwargs):
            return _daily()

    monkeypatch.setattr(tool, "_CSI300_FALLBACK_CODES", ["600000.SH", "000001.SZ"])
    monkeypatch.setattr(
        tool,
        "get_env_config",
        lambda: SimpleNamespace(data=SimpleNamespace(tushare_token="test")),
    )
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: Pro()))

    panel = tool._load_csi300_panel("2024-01-01", "2024-01-31")

    assert panel["_meta"] == {
        "universe": "csi300",
        "survivorship_bias": True,
        "degraded": True,
        "constituent_source": "hand-picked fallback",
        "constituent_source_date": None,
        "constituent_count": 2,
        "fetched_count": 2,
    }


def test_sp500_fallback_does_not_claim_wikipedia_date(monkeypatch) -> None:
    class Loader:
        def fetch(self, codes, start, end):
            return {}

    from backtest.loaders import registry

    monkeypatch.setattr(tool, "_fetch_sp500_constituents", lambda: [])
    monkeypatch.setattr(tool, "_SP500_FALLBACK_CODES", ["AAPL", "MSFT"])
    monkeypatch.setattr(registry, "resolve_loader", lambda market: Loader())

    panel = tool._load_sp500_panel("2024-01-01", "2024-01-31")

    assert panel["_meta"]["degraded"] is True
    assert panel["_meta"]["constituent_source"] == "hand-picked fallback"
    assert panel["_meta"]["constituent_source_date"] is None
    assert panel["_meta"]["constituent_count"] == 2
