"""Runner fallback regressions."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from backtest import runner
from backtest.loaders.base import NoAvailableSourceError


def _frame(close: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [close],
            "high": [close],
            "low": [close],
            "close": [close],
            "volume": [1000],
        },
        index=pd.DatetimeIndex(["2024-01-02"]),
    )


class _PartialSinaLoader:
    name = "sina"
    markets = {"us_equity"}
    requires_auth = False

    def is_available(self) -> bool:
        return True

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        return {"MSFT.US": _frame(101.0)} if "MSFT.US" in codes else {}


class _YahooFallbackLoader:
    name = "yahoo"
    markets = {"us_equity"}
    requires_auth = False

    def is_available(self) -> bool:
        return True

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        return {code: _frame(102.0) for code in codes}


class _RateLimitedSinaLoader:
    name = "sina"
    markets = {"us_equity"}
    requires_auth = False

    def is_available(self) -> bool:
        return True

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        raise RuntimeError("YFRateLimitError: Too Many Requests")


class _EmptyYahooLoader:
    name = "yahoo"
    markets = {"hk_equity"}
    requires_auth = False

    def is_available(self) -> bool:
        return True

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        return {}


class _TushareMustNotRun:
    name = "tushare"
    markets = {"us_equity", "hk_equity"}
    requires_auth = True
    constructions = 0

    def __init__(self) -> None:
        type(self).constructions += 1

    def is_available(self) -> bool:
        return True

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        raise AssertionError("overseas auto routing reached Tushare")


def test_fetch_auto_falls_back_per_missing_symbol(monkeypatch) -> None:
    config = {"start_date": "2024-01-01", "end_date": "2024-01-05"}
    monkeypatch.setattr(runner, "resolve_loader", lambda market: _PartialSinaLoader())
    _TushareMustNotRun.constructions = 0

    with patch.dict(
        runner.LOADER_REGISTRY,
        {"yahoo": _YahooFallbackLoader, "tushare": _TushareMustNotRun},
        clear=True,
    ):
        with patch.dict(
            runner.FALLBACK_CHAINS,
            {"us_equity": ["sina", "yahoo"]},
            clear=True,
        ):
            data = runner._fetch_auto(["MSFT.US", "AAPL"], config)

    assert set(data) == {"MSFT.US", "AAPL"}
    assert config["_run_card_effective_sources"] == ["sina", "yahoo"]
    assert _TushareMustNotRun.constructions == 0


def test_fetch_auto_falls_back_when_primary_fetch_raises(monkeypatch) -> None:
    config = {"start_date": "2024-01-01", "end_date": "2024-01-05"}
    monkeypatch.setattr(runner, "resolve_loader", lambda market: _RateLimitedSinaLoader())
    _TushareMustNotRun.constructions = 0

    with patch.dict(
        runner.LOADER_REGISTRY,
        {"yahoo": _YahooFallbackLoader, "tushare": _TushareMustNotRun},
        clear=True,
    ):
        with patch.dict(
            runner.FALLBACK_CHAINS,
            {"us_equity": ["sina", "yahoo"]},
            clear=True,
        ):
            data = runner._fetch_auto(["AAPL"], config)

    assert set(data) == {"AAPL"}
    assert config["_run_card_effective_sources"] == ["yahoo"]
    assert _TushareMustNotRun.constructions == 0


def test_fetch_auto_hk_failure_never_falls_through_to_tushare(monkeypatch) -> None:
    config = {"start_date": "2024-01-01", "end_date": "2024-01-05"}
    monkeypatch.setattr(runner, "resolve_loader", lambda market: _EmptyYahooLoader())
    _TushareMustNotRun.constructions = 0

    with patch.dict(
        runner.LOADER_REGISTRY,
        {"tushare": _TushareMustNotRun},
        clear=True,
    ):
        with patch.dict(
            runner.FALLBACK_CHAINS,
            {"hk_equity": ["yahoo"]},
            clear=True,
        ):
            data = runner._fetch_auto(["00700.HK"], config)

    assert data == {}
    assert _TushareMustNotRun.constructions == 0


def test_fetch_auto_overseas_without_approved_source_skips_legacy_fallback(
    monkeypatch,
) -> None:
    def no_source(_market: str):
        raise NoAvailableSourceError("approved sources unavailable")

    def legacy_loader_must_not_run(_source: str):
        raise AssertionError("overseas auto routing reached a legacy loader")

    monkeypatch.setattr(runner, "resolve_loader", no_source)
    monkeypatch.setattr(runner, "_get_loader", legacy_loader_must_not_run)

    for symbol in ("AAPL", "00700.HK"):
        config = {"start_date": "2024-01-01", "end_date": "2024-01-05"}
        assert runner._fetch_auto([symbol], config) == {}


def test_explicit_source_falls_back_per_missing_symbol(monkeypatch) -> None:
    config = {"start_date": "2024-01-01", "end_date": "2024-01-05"}
    monkeypatch.setattr(runner, "_get_loader", lambda source: _PartialSinaLoader)

    with patch.dict(
        runner.LOADER_REGISTRY,
        {"yahoo": _YahooFallbackLoader},
        clear=True,
    ):
        with patch.dict(
            runner.FALLBACK_CHAINS,
            {"us_equity": ["sina", "yahoo"]},
            clear=True,
        ):
            data, loader, source = runner._fetch_with_runtime_fallback(
                ["MSFT.US", "AAPL.US"],
                "sina",
                config,
                "1D",
            )

    assert set(data) == {"MSFT.US", "AAPL.US"}
    assert source == "sina"
    assert loader.name == "yahoo"
    assert config["_run_card_effective_sources"] == ["sina", "yahoo"]


def test_explicit_source_retries_only_symbols_still_missing(monkeypatch) -> None:
    config = {"start_date": "2024-01-01", "end_date": "2024-01-05"}
    calls: dict[str, list[str]] = {}

    class _FirstFallbackLoader:
        name = "yahoo"

        def is_available(self) -> bool:
            return True

        def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
            calls[self.name] = list(codes)
            return {"AAPL.US": _frame(102.0)} if "AAPL.US" in codes else {}

    class _SecondFallbackLoader:
        name = "stooq"

        def is_available(self) -> bool:
            return True

        def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
            calls[self.name] = list(codes)
            return {code: _frame(103.0) for code in codes}

    monkeypatch.setattr(runner, "_get_loader", lambda source: _PartialSinaLoader)

    with patch.dict(
        runner.LOADER_REGISTRY,
        {"yahoo": _FirstFallbackLoader, "stooq": _SecondFallbackLoader},
        clear=True,
    ):
        with patch.dict(
            runner.FALLBACK_CHAINS,
            {"us_equity": ["sina", "yahoo", "stooq"]},
            clear=True,
        ):
            data, loader, source = runner._fetch_with_runtime_fallback(
                ["MSFT.US", "AAPL.US", "TSLA.US"],
                "sina",
                config,
                "1D",
            )

    assert set(data) == {"MSFT.US", "AAPL.US", "TSLA.US"}
    assert calls == {
        "yahoo": ["AAPL.US", "TSLA.US"],
        "stooq": ["TSLA.US"],
    }
    assert source == "sina"
    assert loader.name == "stooq"
    assert config["_run_card_effective_sources"] == ["sina", "stooq", "yahoo"]


def test_auto_run_card_sources_preserve_actual_fallbacks() -> None:
    config = {"_run_card_effective_sources": ["sina", "yahoo"]}

    runner._set_run_card_effective_sources("auto", ["AAPL.US"], config)

    assert config["_run_card_effective_sources"] == ["sina", "yahoo"]


def test_expand_universe_uses_csi300_constituents(monkeypatch) -> None:
    calls = []

    def fake_csi300(start_date: str, end_date: str) -> list[str]:
        calls.append((start_date, end_date))
        return ["600519.SH", "300750.SZ", "600519.SH"]

    monkeypatch.setattr(runner, "_load_csi300_constituents", fake_csi300)

    config = {
        "source": "auto",
        "codes": ["000001.SZ"],
        "universe": "csi300",
        "start_date": "2023-01-01",
        "end_date": "2024-12-31",
    }

    expanded = runner._expand_universe_codes(config)

    assert expanded == ["600519.SH", "300750.SZ"]
    assert config["codes"] == ["600519.SH", "300750.SZ"]
    assert calls == [("2023-01-01", "2024-12-31")]
