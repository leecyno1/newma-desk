from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.assets.panel import (
    DEFAULT_BENCHMARK_MAP,
    CoreAssetPanelError,
    build_core_asset_panel,
)
from seven_cycle_platform.assets.proxies import (
    AssetReturnSegment,
    OverlapCalibration,
    ProxyStatus,
    ReturnKind,
)
from seven_cycle_platform.assets.sources import (
    LEGACY_CORE_ASSET_MAP,
    AkShareAdapter,
    AssetSourceError,
    TushareAdapter,
    TushareCredentialError,
    convert_legacy_monthly_returns,
    load_legacy_monthly_returns,
    normalize_daily_prices,
)
from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.registry.models import AssetProxySpec, AssetSpec


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = ROOT / "config" / "seven_cycle"
LEGACY_PATH = ROOT / "output" / "monthly_returns_20y.parquet"


class FakeTushareClient:
    def __init__(
        self,
        *,
        index_frame: pd.DataFrame,
        ci_frame: pd.DataFrame | None = None,
    ) -> None:
        self.index_frame = index_frame
        self.ci_frame = ci_frame if ci_frame is not None else index_frame
        self.calls: list[tuple[str, dict[str, str]]] = []

    def index_daily(self, **kwargs: str) -> pd.DataFrame:
        self.calls.append(("index_daily", kwargs))
        return self.index_frame.copy(deep=True)

    def ci_index_daily(self, **kwargs: str) -> pd.DataFrame:
        self.calls.append(("ci_index_daily", kwargs))
        return self.ci_frame.copy(deep=True)


class FakeAkShareProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[str] = []

    def stock_zh_index_daily_em(self, *, symbol: str) -> pd.DataFrame:
        self.calls.append(symbol)
        return self.frame.copy(deep=True)


def _asset(asset_id: str) -> AssetSpec:
    bundle = load_registry_bundle(REGISTRY_DIR)
    return next(asset for asset in bundle.assets if asset.asset_id == asset_id)


def _daily_frame(
    *,
    date_column: str,
    price_column: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            date_column: [
                "20240328",
                "20240129",
                "20240227",
                "20240131",
                "20240229",
            ],
            price_column: [133.1, 100.0, 120.0, 110.0, 121.0],
        }
    )


def _direct_segment(
    asset: AssetSpec,
    returns: pd.Series,
    *,
    segment_id: str | None = None,
    quality_tier: str | None = None,
) -> AssetReturnSegment:
    return AssetReturnSegment(
        asset_id=asset.asset_id,
        segment_id=segment_id or f"{asset.asset_id}:primary",
        raw_returns=returns,
        returns=returns,
        source=asset.source,
        backend=asset.backend,
        symbol=asset.symbol,
        currency=asset.currency,
        calendar=asset.calendar,
        return_kind=(
            ReturnKind.TOTAL if asset.asset_class == "cash" else ReturnKind.PRICE
        ),
        quality_tier=quality_tier or asset.minimum_quality_tier,
        proxy_status=ProxyStatus.PRIMARY,
        proxy_for=None,
        effective_from=returns.index[0].date(),
        effective_to=None,
        overlap_calibration=OverlapCalibration.not_required(),
        confidence_discount=0.0,
        benchmark_asset_id=DEFAULT_BENCHMARK_MAP[asset.asset_id],
        data_start=returns.index[0].date(),
        data_end=returns.index[-1].date(),
    )


def _complete_legacy_panel() -> pd.DataFrame:
    columns = pd.MultiIndex.from_tuples(list(LEGACY_CORE_ASSET_MAP))
    return pd.DataFrame(
        np.arange(10, dtype=float).reshape(2, 5) / 100.0,
        index=pd.DatetimeIndex(["2024-01-31", "2024-02-29"]),
        columns=columns,
    )


def _proxy_segment(
    asset: AssetSpec,
    proxy: AssetProxySpec,
    returns: pd.Series,
) -> AssetReturnSegment:
    return AssetReturnSegment(
        asset_id=asset.asset_id,
        segment_id=proxy.proxy_id,
        raw_returns=returns,
        returns=returns,
        source=proxy.source,
        backend=proxy.backend,
        symbol=proxy.symbol,
        currency=asset.currency,
        calendar=asset.calendar,
        return_kind=ReturnKind.PRICE,
        quality_tier=asset.minimum_quality_tier,
        proxy_status=ProxyStatus.PROXY,
        proxy_for=proxy.proxy_for,
        effective_from=proxy.effective_from,
        effective_to=proxy.effective_to,
        overlap_calibration=OverlapCalibration.unavailable("not_calibrated"),
        confidence_discount=proxy.confidence_discount,
        benchmark_asset_id=DEFAULT_BENCHMARK_MAP[asset.asset_id],
        data_start=returns.index[0].date(),
        data_end=returns.index[-1].date(),
    )


def test_tushare_routes_registry_backends_and_builds_month_end_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "unit-test-placeholder")
    bundle = load_registry_bundle(REGISTRY_DIR)
    direct_frame = _daily_frame(date_column="trade_date", price_column="close")
    proxy_frame = direct_frame.assign(
        trade_date=[
            "20141230",
            "20141030",
            "20141127",
            "20141031",
            "20141128",
        ]
    )
    client = FakeTushareClient(index_frame=direct_frame, ci_frame=proxy_frame)
    adapter = TushareAdapter(bundle, client=client)

    direct = adapter.fetch_segment(
        asset_id="cn_equity_hs300",
        start_date=date(2024, 2, 1),
        end_date=date(2024, 3, 31),
        return_kind=ReturnKind.PRICE,
        date_column="trade_date",
        price_column="close",
        benchmark_asset_id="cn_equity_hs300",
    )
    fallback = adapter.fetch_segment(
        asset_id="cn_equity_baijiu",
        proxy_id="cn_equity_baijiu_citic_food_beverage",
        start_date=date(2014, 10, 1),
        end_date=date(2014, 12, 31),
        return_kind=ReturnKind.PRICE,
        date_column="trade_date",
        price_column="close",
        benchmark_asset_id="cn_equity_hs300",
    )

    assert [call[0] for call in client.calls] == [
        "index_daily",
        "ci_index_daily",
    ]
    assert client.calls[0][1] == {
        "ts_code": "000300.SH",
        "start_date": "20240101",
        "end_date": "20240331",
    }
    assert direct.returns.index.tolist() == [
        pd.Timestamp("2024-02-29"),
        pd.Timestamp("2024-03-31"),
    ]
    assert direct.returns.to_numpy() == pytest.approx([0.1, 0.1])
    assert direct.source == "Tushare"
    assert direct.backend == "tushare.index_daily"
    assert direct.return_kind is ReturnKind.PRICE
    assert fallback.proxy_status is ProxyStatus.PROXY
    assert fallback.proxy_for == "cn_equity_baijiu"
    assert fallback.symbol == "CI005019.CI"
    assert fallback.effective_from == date(2005, 1, 4)
    assert fallback.effective_to == date(2014, 12, 31)
    assert fallback.confidence_discount == 0.25


def test_tushare_proxy_anchor_never_precedes_registry_effective_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "unit-test-placeholder")
    proxy_frame = pd.DataFrame(
        {
            "trade_date": ["20050131", "20050228", "20050331"],
            "close": [100.0, 110.0, 121.0],
        }
    )
    client = FakeTushareClient(index_frame=proxy_frame, ci_frame=proxy_frame)
    adapter = TushareAdapter(load_registry_bundle(REGISTRY_DIR), client=client)

    segment = adapter.fetch_segment(
        asset_id="cn_equity_baijiu",
        proxy_id="cn_equity_baijiu_citic_food_beverage",
        start_date=date(2005, 1, 4),
        end_date=date(2005, 3, 31),
        return_kind=ReturnKind.PRICE,
        date_column="trade_date",
        price_column="close",
        benchmark_asset_id="cn_equity_hs300",
    )

    assert client.calls == [
        (
            "ci_index_daily",
            {
                "ts_code": "CI005019.CI",
                "start_date": "20050104",
                "end_date": "20050331",
            },
        )
    ]
    assert segment.returns.to_numpy() == pytest.approx([0.1, 0.1])


@pytest.mark.parametrize("token", [None, "", "   "])
def test_tushare_requires_nonblank_environment_token_before_client_call(
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
) -> None:
    if token is None:
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("TUSHARE_TOKEN", token)
    client = FakeTushareClient(
        index_frame=_daily_frame(date_column="trade_date", price_column="close")
    )
    adapter = TushareAdapter(load_registry_bundle(REGISTRY_DIR), client=client)

    with pytest.raises(TushareCredentialError, match="TUSHARE_TOKEN"):
        adapter.fetch_segment(
            asset_id="cn_equity_hs300",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            return_kind=ReturnKind.PRICE,
            date_column="trade_date",
            price_column="close",
            benchmark_asset_id="cn_equity_hs300",
        )

    assert client.calls == []


def test_tushare_errors_and_repr_never_expose_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "unit-test-secret-placeholder"
    monkeypatch.setenv("TUSHARE_TOKEN", token)

    class ExplodingClient:
        def index_daily(self, **kwargs: str) -> pd.DataFrame:
            raise RuntimeError(f"upstream rejected token={token}: {kwargs}")

    adapter = TushareAdapter(
        load_registry_bundle(REGISTRY_DIR),
        client=ExplodingClient(),
    )

    with pytest.raises(AssetSourceError) as error_info:
        adapter.fetch_segment(
            asset_id="cn_equity_hs300",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            return_kind=ReturnKind.PRICE,
            date_column="trade_date",
            price_column="close",
            benchmark_asset_id="cn_equity_hs300",
        )

    assert token not in str(error_info.value)
    assert token not in repr(error_info.value)
    assert token not in repr(adapter)


def test_akshare_adapter_uses_injected_provider_without_credentials() -> None:
    provider = FakeAkShareProvider(
        _daily_frame(date_column="date", price_column="close")
    )
    adapter = AkShareAdapter(
        load_registry_bundle(REGISTRY_DIR),
        provider=provider,
    )

    segment = adapter.fetch_segment(
        asset_id="cn_bond_government_index",
        start_date=date(2024, 2, 1),
        end_date=date(2024, 3, 31),
        return_kind=ReturnKind.PRICE,
        date_column="date",
        price_column="close",
        benchmark_asset_id="cny_cash",
    )

    assert provider.calls == ["sh000012"]
    assert segment.returns.to_numpy() == pytest.approx([0.1, 0.1])
    assert segment.source == "Eastmoney"
    assert segment.backend == "akshare.stock_zh_index_daily_em"


def test_adapters_require_a_validated_registry_bundle() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)

    with pytest.raises(TypeError, match="RegistryBundle"):
        TushareAdapter(bundle.assets, client=object())
    with pytest.raises(TypeError, match="RegistryBundle"):
        AkShareAdapter(bundle.assets, provider=object())


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("symbol", "ROGUE.CI"),
        ("backend", "tushare.index_daily"),
        ("source", "Rogue Source"),
    ],
)
def test_tushare_rejects_forged_proxy_metadata_before_client_call(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    forged_value: str,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "unit-test-placeholder")
    bundle = load_registry_bundle(REGISTRY_DIR)
    baijiu = next(
        asset for asset in bundle.assets if asset.asset_id == "cn_equity_baijiu"
    )
    forged_proxy = baijiu.proxy_chain[0].model_copy(
        update={field_name: forged_value}
    )
    client = FakeTushareClient(
        index_frame=_daily_frame(date_column="trade_date", price_column="close")
    )
    adapter = TushareAdapter(bundle, client=client)

    with pytest.raises(ValueError, match="proxy.*canonical registry"):
        adapter.fetch_segment(
            asset_id="cn_equity_baijiu",
            proxy=forged_proxy,
            start_date=date(2014, 10, 1),
            end_date=date(2014, 12, 31),
            return_kind=ReturnKind.PRICE,
            date_column="trade_date",
            price_column="close",
            benchmark_asset_id="cn_equity_hs300",
        )

    assert client.calls == []


def test_tushare_rejects_unknown_proxy_id_before_client_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "unit-test-placeholder")
    client = FakeTushareClient(
        index_frame=_daily_frame(date_column="trade_date", price_column="close")
    )
    adapter = TushareAdapter(
        load_registry_bundle(REGISTRY_DIR),
        client=client,
    )

    with pytest.raises(ValueError, match="unknown proxy_id"):
        adapter.fetch_segment(
            asset_id="cn_equity_baijiu",
            proxy_id="rogue_proxy",
            start_date=date(2014, 10, 1),
            end_date=date(2014, 12, 31),
            return_kind=ReturnKind.PRICE,
            date_column="trade_date",
            price_column="close",
            benchmark_asset_id="cn_equity_hs300",
        )

    assert client.calls == []


def test_akshare_rejects_forged_asset_symbol_before_provider_call() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    bond = next(
        asset
        for asset in bundle.assets
        if asset.asset_id == "cn_bond_government_index"
    )
    forged_asset = bond.model_copy(update={"symbol": "sz399999"})
    provider = FakeAkShareProvider(
        _daily_frame(date_column="date", price_column="close")
    )
    adapter = AkShareAdapter(bundle, provider=provider)

    with pytest.raises(ValueError, match="asset.*canonical registry"):
        adapter.fetch_segment(
            asset=forged_asset,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            return_kind=ReturnKind.PRICE,
            date_column="date",
            price_column="close",
            benchmark_asset_id="cny_cash",
        )

    assert provider.calls == []


def test_adapters_reject_unsupported_registry_backends_before_external_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    bundle = load_registry_bundle(REGISTRY_DIR)
    client = FakeTushareClient(
        index_frame=_daily_frame(date_column="trade_date", price_column="close")
    )
    provider = FakeAkShareProvider(
        _daily_frame(date_column="date", price_column="close")
    )

    with pytest.raises(ValueError, match="unsupported Tushare backend"):
        TushareAdapter(bundle, client=client).fetch_segment(
            asset_id="gold",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            return_kind=ReturnKind.PRICE,
            date_column="trade_date",
            price_column="close",
            benchmark_asset_id="cny_cash",
        )
    with pytest.raises(ValueError, match="unsupported AkShare backend"):
        AkShareAdapter(bundle, provider=provider).fetch_segment(
            asset_id="cn_equity_hs300",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            return_kind=ReturnKind.PRICE,
            date_column="date",
            price_column="close",
            benchmark_asset_id="cn_equity_hs300",
        )

    assert client.calls == []
    assert provider.calls == []


def test_daily_normalization_uses_explicit_total_price_and_rejects_bad_data() -> None:
    daily = pd.DataFrame(
        {
            "date": ["2024-01-31", "2024-02-29", "2024-03-29"],
            "close": [100.0, 80.0, 100.0],
            "total_index": [100.0, 110.0, 121.0],
        }
    )

    total_returns = normalize_daily_prices(
        daily,
        date_column="date",
        price_column="close",
        total_price_column="total_index",
        return_kind=ReturnKind.TOTAL,
    )

    assert total_returns.to_numpy() == pytest.approx([0.1, 0.1])

    with pytest.raises(ValueError, match="total_price_column"):
        normalize_daily_prices(
            daily,
            date_column="date",
            price_column="close",
            return_kind=ReturnKind.TOTAL,
        )
    with pytest.raises(ValueError, match="close cannot be used"):
        normalize_daily_prices(
            daily,
            date_column="date",
            price_column="close",
            total_price_column="close",
            return_kind=ReturnKind.TOTAL,
        )

    duplicated = pd.concat([daily, daily.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate dates"):
        normalize_daily_prices(
            duplicated,
            date_column="date",
            price_column="close",
            return_kind=ReturnKind.PRICE,
        )

    nonpositive = daily.copy()
    nonpositive.loc[1, "close"] = 0.0
    with pytest.raises(ValueError, match="positive"):
        normalize_daily_prices(
            nonpositive,
            date_column="date",
            price_column="close",
            return_kind=ReturnKind.PRICE,
        )

    with pytest.raises(ValueError, match="missing required field"):
        normalize_daily_prices(
            daily,
            date_column="trade_date",
            price_column="close",
            return_kind=ReturnKind.PRICE,
        )


def test_daily_normalization_uses_prior_month_anchor_before_date_filtering() -> None:
    daily = pd.DataFrame(
        {
            "date": ["2024-01-31", "2024-02-29", "2024-03-29"],
            "close": [100.0, 110.0, 121.0],
        }
    )

    returns = normalize_daily_prices(
        daily,
        date_column="date",
        price_column="close",
        return_kind=ReturnKind.PRICE,
        start_date=date(2024, 2, 1),
        end_date=date(2024, 3, 31),
    )

    assert returns.index.tolist() == [
        pd.Timestamp("2024-02-29"),
        pd.Timestamp("2024-03-31"),
    ]
    assert returns.to_numpy() == pytest.approx([0.1, 0.1])


def test_daily_normalization_rejects_timezone_aware_local_dates() -> None:
    daily = pd.DataFrame(
        {
            "date": [
                pd.Timestamp("2024-01-31 23:30:00+14:00"),
                pd.Timestamp("2024-02-29 23:30:00+14:00"),
                pd.Timestamp("2024-03-31 23:30:00+14:00"),
            ],
            "close": [100.0, 110.0, 121.0],
        }
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_daily_prices(
            daily,
            date_column="date",
            price_column="close",
            return_kind=ReturnKind.PRICE,
        )


def test_daily_normalization_rejects_mixed_offset_date_strings() -> None:
    daily = pd.DataFrame(
        {
            "date": [
                "2024-01-31T23:30:00+14:00",
                "2024-02-29T23:30:00-05:00",
                "2024-03-31T23:30:00+08:00",
            ],
            "close": [100.0, 110.0, 121.0],
        }
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_daily_prices(
            daily,
            date_column="date",
            price_column="close",
            return_kind=ReturnKind.PRICE,
        )


def test_legacy_converter_uses_only_exact_multiindex_mapping() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    columns = pd.MultiIndex.from_tuples(
        [
            ("A股宽基指数", "沪深300"),
            ("A股宽基指数", "中证500"),
            ("A股宽基指数", "中证1000"),
            ("各类债券指数", "国债指数(上证)"),
            ("海外指数/ETF", "标普500(SPY)"),
            ("A股宽基指数", "沪深300指数"),
        ]
    )
    panel = pd.DataFrame(
        np.arange(12, dtype=float).reshape(2, 6) / 100.0,
        index=pd.DatetimeIndex(["2024-01-15", "2024-02-20"]),
        columns=columns,
    )

    segments = convert_legacy_monthly_returns(
        panel,
        assets=bundle.assets,
    )

    assert len(segments) == len(LEGACY_CORE_ASSET_MAP) == 5
    assert {segment.asset_id for segment in segments} == {
        "cn_equity_hs300",
        "cn_equity_csi500",
        "cn_equity_csi1000",
        "cn_bond_government_index",
        "us_equity_sp500",
    }
    assert all(
        segment.returns.index.tolist()
        == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29")]
        for segment in segments
    )
    assert all(
        segment.source == "legacy_monthly_returns_20y"
        and segment.backend == "legacy.parquet_multiindex"
        for segment in segments
    )
    assert all(segment.segment_id.startswith("legacy:") for segment in segments)


def test_legacy_converter_loads_the_existing_seed_file() -> None:
    segments = load_legacy_monthly_returns(
        LEGACY_PATH,
        assets=load_registry_bundle(REGISTRY_DIR).assets,
    )

    assert {segment.asset_id for segment in segments} == {
        mapping.asset_id for mapping in LEGACY_CORE_ASSET_MAP.values()
    }
    assert all(segment.returns.index.is_unique for segment in segments)
    assert all(
        segment.returns.index.equals(segment.returns.index.to_period("M").to_timestamp("M"))
        for segment in segments
    )


def test_legacy_converter_requires_every_mapped_column_by_default() -> None:
    panel = _complete_legacy_panel().drop(
        columns=[("A股宽基指数", "中证1000")]
    )

    with pytest.raises(ValueError, match="missing mapped columns.*中证1000"):
        convert_legacy_monthly_returns(
            panel,
            assets=load_registry_bundle(REGISTRY_DIR).assets,
        )


def test_legacy_converter_rejects_all_nan_mapped_column_by_default() -> None:
    panel = _complete_legacy_panel()
    panel.loc[:, ("A股宽基指数", "中证500")] = np.nan

    with pytest.raises(ValueError, match="mapped column has no observations.*中证500"):
        convert_legacy_monthly_returns(
            panel,
            assets=load_registry_bundle(REGISTRY_DIR).assets,
        )


def test_legacy_converter_partial_mode_must_be_explicit() -> None:
    panel = _complete_legacy_panel().loc[
        :,
        [("A股宽基指数", "沪深300")],
    ]

    segments = convert_legacy_monthly_returns(
        panel,
        assets=load_registry_bundle(REGISTRY_DIR).assets,
        require_complete=False,
    )

    assert [segment.asset_id for segment in segments] == ["cn_equity_hs300"]


def test_legacy_converter_rejects_duplicate_calendar_months() -> None:
    panel = pd.DataFrame(
        [0.01, 0.02],
        index=pd.DatetimeIndex(["2024-01-10", "2024-01-31"]),
        columns=pd.MultiIndex.from_tuples([("A股宽基指数", "沪深300")]),
    )

    with pytest.raises(ValueError, match="more than one row for a calendar month"):
        convert_legacy_monthly_returns(
            panel,
            assets=load_registry_bundle(REGISTRY_DIR).assets,
            require_complete=False,
        )


def test_core_panel_contains_all_11_assets_benchmarks_and_baijiu_segments() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    source_segments: list[AssetReturnSegment] = []
    standard_dates = pd.date_range("2015-01-31", periods=120, freq="ME")
    for asset in bundle.assets:
        if asset.asset_id == "cn_equity_baijiu":
            dates = pd.date_range("2010-01-31", periods=120, freq="ME")
        else:
            dates = standard_dates
        values = np.linspace(-0.02, 0.03, len(dates))
        source_segments.append(
            _direct_segment(asset, pd.Series(values, index=dates, dtype=float))
        )

    baijiu = next(
        asset for asset in bundle.assets if asset.asset_id == "cn_equity_baijiu"
    )
    proxy = baijiu.proxy_chain[0]
    proxy_dates = pd.date_range("2005-01-31", periods=120, freq="ME")
    proxy_values = np.linspace(-0.01, 0.02, len(proxy_dates))
    source_segments.append(
        _proxy_segment(
            baijiu,
            proxy,
            pd.Series(proxy_values, index=proxy_dates, dtype=float),
        )
    )

    legacy_panel = pd.DataFrame(
        [0.01, 0.02],
        index=standard_dates[:2],
        columns=pd.MultiIndex.from_tuples([("A股宽基指数", "沪深300")]),
    )
    legacy_seeds = convert_legacy_monthly_returns(
        legacy_panel,
        assets=bundle.assets,
        require_complete=False,
    )

    panel = build_core_asset_panel(
        bundle.assets,
        source_segments=source_segments,
        legacy_seeds=legacy_seeds,
    )
    returns = panel.returns
    availability = panel.availability

    assert len(availability) == 11
    assert set(availability["asset_id"]) == {
        asset.asset_id for asset in bundle.assets if asset.active and asset.tier == "core"
    }
    assert set(availability["status"]) == {"available"}
    assert not returns.duplicated(["asset_id", "segment_id", "date"]).any()
    assert set(returns["benchmark_asset_id"]) == set(DEFAULT_BENCHMARK_MAP.values())
    assert (
        returns.groupby("asset_id")["benchmark_asset_id"].nunique().max() == 1
    )
    assert DEFAULT_BENCHMARK_MAP["cn_equity_baijiu"] == "cn_equity_hs300"
    baijiu_rows = returns[returns["asset_id"] == "cn_equity_baijiu"]
    assert set(baijiu_rows["segment_id"]) == {
        "cn_equity_baijiu:primary",
        "cn_equity_baijiu_citic_food_beverage",
    }
    proxy_rows = baijiu_rows[
        baijiu_rows["segment_id"] == "cn_equity_baijiu_citic_food_beverage"
    ]
    assert set(proxy_rows["proxy_status"]) == {"proxy"}
    assert set(proxy_rows["proxy_for"]) == {"cn_equity_baijiu"}
    assert set(proxy_rows["confidence_discount"]) == {0.25}
    assert set(proxy_rows["effective_confidence"]) == {0.75}
    assert set(proxy_rows["overlap_calibration_status"]) == {"calibrated"}
    assert set(proxy_rows["overlap_sample_count"]) == {60}
    assert set(proxy_rows["effective_from"]) == {date(2005, 1, 4)}
    assert set(proxy_rows["effective_to"]) == {date(2014, 12, 31)}
    assert set(proxy_rows["data_start"]) == {date(2005, 1, 31)}
    assert set(proxy_rows["data_end"]) == {date(2014, 12, 31)}
    required_metadata = {
        "source",
        "backend",
        "symbol",
        "currency",
        "calendar",
        "return_kind",
        "proxy_status",
        "effective_from",
        "effective_to",
        "overlap_calibration_status",
        "overlap_method",
        "overlap_sample_count",
        "overlap_intercept",
        "overlap_slope",
        "confidence_discount",
        "benchmark_asset_id",
        "data_start",
        "data_end",
    }
    assert required_metadata <= set(returns.columns)

    detached = panel.returns
    detached.loc[:, "return"] = 9.0
    assert not (panel.returns["return"] == 9.0).all()


def test_core_panel_audits_missing_and_unavailable_assets_and_strict_fails() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    hs300 = next(
        asset for asset in bundle.assets if asset.asset_id == "cn_equity_hs300"
    )
    short_segment = _direct_segment(
        hs300,
        pd.Series(
            [0.01, 0.02, 0.03],
            index=pd.date_range("2024-01-31", periods=3, freq="ME"),
            dtype=float,
        ),
    )

    panel = build_core_asset_panel(
        bundle.assets,
        source_segments=[short_segment],
    )
    availability = panel.availability.set_index("asset_id")

    assert availability.loc["cn_equity_hs300", "status"] == "unavailable"
    assert "minimum_history_months" in availability.loc[
        "cn_equity_hs300", "reason"
    ]
    assert availability.loc["cn_equity_csi500", "status"] == "missing"
    assert set(panel.returns["asset_status"]) == {"unavailable"}

    with pytest.raises(
        CoreAssetPanelError,
        match="cn_equity_hs300.*cn_equity_csi500",
    ):
        build_core_asset_panel(
            bundle.assets,
            source_segments=[short_segment],
            strict=True,
        )


def test_quality_tier_uses_worst_monthly_best_coverage() -> None:
    hs300 = _asset("cn_equity_hs300")
    dates = pd.date_range("2015-01-31", periods=120, freq="ME")
    primary = _direct_segment(
        hs300,
        pd.Series(np.linspace(-0.02, 0.03, 120), index=dates),
        quality_tier="B",
    )
    one_month_a = convert_legacy_monthly_returns(
        pd.DataFrame(
            [0.01],
            index=dates[:1],
            columns=pd.MultiIndex.from_tuples([("A股宽基指数", "沪深300")]),
        ),
        assets=[hs300],
        require_complete=False,
    )

    panel = build_core_asset_panel(
        [hs300],
        source_segments=[primary],
        legacy_seeds=one_month_a,
    )
    record = panel.availability.iloc[0]

    assert record["quality_tier"] == "B"
    assert record["status"] == "unavailable"
    assert "minimum_quality_tier" in record["reason"]
    with pytest.raises(CoreAssetPanelError, match="minimum_quality_tier"):
        build_core_asset_panel(
            [hs300],
            source_segments=[primary],
            legacy_seeds=one_month_a,
            strict=True,
        )


def test_quality_tier_uses_best_available_segment_for_each_month() -> None:
    hs300 = _asset("cn_equity_hs300")
    dates = pd.date_range("2015-01-31", periods=120, freq="ME")
    primary = _direct_segment(
        hs300,
        pd.Series(np.linspace(-0.02, 0.03, 120), index=dates),
        quality_tier="B",
    )
    full_a = convert_legacy_monthly_returns(
        pd.DataFrame(
            np.linspace(-0.01, 0.02, 120),
            index=dates,
            columns=pd.MultiIndex.from_tuples([("A股宽基指数", "沪深300")]),
        ),
        assets=[hs300],
        require_complete=False,
    )

    panel = build_core_asset_panel(
        [hs300],
        source_segments=[primary],
        legacy_seeds=full_a,
        strict=True,
    )

    assert panel.availability.iloc[0]["quality_tier"] == "A"
    assert panel.availability.iloc[0]["status"] == "available"


def test_real_legacy_seeds_are_legacy_only_not_proxy_only() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    legacy_seeds = load_legacy_monthly_returns(
        LEGACY_PATH,
        assets=bundle.assets,
    )

    panel = build_core_asset_panel(
        bundle.assets,
        legacy_seeds=legacy_seeds,
    )
    availability = panel.availability.set_index("asset_id")
    legacy_asset_ids = {segment.asset_id for segment in legacy_seeds}

    assert set(availability.loc[list(legacy_asset_ids), "proxy_only"]) == {False}
    assert set(availability.loc[list(legacy_asset_ids), "legacy_only"]) == {True}
