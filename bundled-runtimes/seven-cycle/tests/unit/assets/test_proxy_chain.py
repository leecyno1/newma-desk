from datetime import date

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.assets.proxies import (
    AssetReturnSegment,
    CalibrationStatus,
    OverlapCalibration,
    ProxyStatus,
    ReturnKind,
    build_proxy_chain,
    segments_to_long_frame,
)


def _monthly_series(
    start: str,
    values: list[float],
) -> pd.Series:
    return pd.Series(
        values,
        index=pd.date_range(start, periods=len(values), freq="ME"),
        dtype=float,
        name="return",
    )


def _segment(
    *,
    segment_id: str,
    returns: pd.Series,
    proxy_status: ProxyStatus,
    effective_from: date,
    effective_to: date | None,
    source: str,
    backend: str,
    symbol: str,
    proxy_for: str | None = None,
    confidence_discount: float = 0.0,
) -> AssetReturnSegment:
    calibration = (
        OverlapCalibration.unavailable("not_calibrated")
        if proxy_status is ProxyStatus.PROXY
        else OverlapCalibration.not_required()
    )
    return AssetReturnSegment(
        asset_id="cn_equity_baijiu",
        segment_id=segment_id,
        raw_returns=returns,
        returns=returns,
        source=source,
        backend=backend,
        symbol=symbol,
        currency="CNY",
        calendar="SSE_SZSE",
        return_kind=ReturnKind.PRICE,
        quality_tier="A",
        proxy_status=proxy_status,
        proxy_for=proxy_for,
        effective_from=effective_from,
        effective_to=effective_to,
        overlap_calibration=calibration,
        confidence_discount=confidence_discount,
        benchmark_asset_id="cn_equity_hs300",
        data_start=returns.index[0].date(),
        data_end=returns.index[-1].date(),
    )


def test_overlap_calibration_is_robust_explicit_and_applied() -> None:
    dates = pd.date_range("2014-07-31", periods=6, freq="ME")
    proxy_returns = pd.Series(
        [0.00, 0.01, 0.02, 0.03, 0.04, 0.05],
        index=dates,
        dtype=float,
    )
    primary_returns = pd.Series(
        [0.01, 0.03, 0.05, 0.07, 0.09, 1.50],
        index=dates,
        dtype=float,
    )
    primary = _segment(
        segment_id="cn_equity_baijiu:primary",
        returns=primary_returns,
        proxy_status=ProxyStatus.PRIMARY,
        effective_from=date(2014, 7, 1),
        effective_to=None,
        source="Tushare",
        backend="tushare.index_daily",
        symbol="399997.SZ",
    )
    proxy = _segment(
        segment_id="cn_equity_baijiu_citic_food_beverage",
        returns=proxy_returns,
        proxy_status=ProxyStatus.PROXY,
        effective_from=date(2005, 1, 4),
        effective_to=date(2014, 12, 31),
        source="CITIC Securities",
        backend="tushare.ci_index_daily",
        symbol="CI005019.CI",
        proxy_for="cn_equity_baijiu",
        confidence_discount=0.25,
    )

    calibrated = build_proxy_chain(primary, [proxy])[0]

    assert calibrated.segment_id == proxy.segment_id
    assert calibrated.overlap_calibration.status is CalibrationStatus.CALIBRATED
    assert calibrated.overlap_calibration.method == "theil_sen"
    assert calibrated.overlap_calibration.sample_count == 6
    assert calibrated.overlap_calibration.intercept == pytest.approx(0.01)
    assert calibrated.overlap_calibration.slope == pytest.approx(2.0)
    assert calibrated.returns.iloc[:5].to_numpy() == pytest.approx(
        np.array([0.01, 0.03, 0.05, 0.07, 0.09])
    )
    assert calibrated.raw_returns.equals(proxy_returns)


def test_no_overlap_is_unavailable_without_fabricated_coefficients() -> None:
    primary = _segment(
        segment_id="cn_equity_baijiu:primary",
        returns=_monthly_series("2015-01-31", [0.01, 0.02, 0.03]),
        proxy_status=ProxyStatus.PRIMARY,
        effective_from=date(2015, 1, 1),
        effective_to=None,
        source="Tushare",
        backend="tushare.index_daily",
        symbol="399997.SZ",
    )
    proxy = _segment(
        segment_id="cn_equity_baijiu_citic_food_beverage",
        returns=_monthly_series("2014-09-30", [0.02, 0.01, -0.01]),
        proxy_status=ProxyStatus.PROXY,
        effective_from=date(2005, 1, 4),
        effective_to=date(2014, 12, 31),
        source="CITIC Securities",
        backend="tushare.ci_index_daily",
        symbol="CI005019.CI",
        proxy_for="cn_equity_baijiu",
        confidence_discount=0.25,
    )

    calibrated = build_proxy_chain(primary, [proxy])[0]

    calibration = calibrated.overlap_calibration
    assert calibration.status is CalibrationStatus.UNAVAILABLE
    assert calibration.reason == "no_overlap"
    assert calibration.sample_count == 0
    assert calibration.intercept is None
    assert calibration.slope is None
    assert calibrated.returns.equals(calibrated.raw_returns)


def test_proxy_discount_reduces_effective_confidence() -> None:
    proxy = _segment(
        segment_id="cn_equity_baijiu_citic_food_beverage",
        returns=_monthly_series("2014-10-31", [0.01, 0.02, 0.03]),
        proxy_status=ProxyStatus.PROXY,
        effective_from=date(2005, 1, 4),
        effective_to=date(2014, 12, 31),
        source="CITIC Securities",
        backend="tushare.ci_index_daily",
        symbol="CI005019.CI",
        proxy_for="cn_equity_baijiu",
        confidence_discount=0.25,
    )

    assert proxy.confidence_discount == 0.25
    assert proxy.effective_confidence == 0.75


def test_proxy_effective_boundaries_are_inclusive_and_enforced() -> None:
    boundary_segment = _segment(
        segment_id="cn_equity_baijiu_citic_food_beverage",
        returns=pd.Series(
            [0.01, 0.02],
            index=pd.DatetimeIndex(["2005-01-31", "2014-12-31"]),
            dtype=float,
        ),
        proxy_status=ProxyStatus.PROXY,
        effective_from=date(2005, 1, 4),
        effective_to=date(2014, 12, 31),
        source="CITIC Securities",
        backend="tushare.ci_index_daily",
        symbol="CI005019.CI",
        proxy_for="cn_equity_baijiu",
        confidence_discount=0.25,
    )

    assert boundary_segment.data_start == date(2005, 1, 31)
    assert boundary_segment.data_end == date(2014, 12, 31)

    with pytest.raises(ValueError, match="outside its effective interval"):
        _segment(
            segment_id="cn_equity_baijiu_citic_food_beverage",
            returns=_monthly_series("2015-01-31", [0.01, 0.02]),
            proxy_status=ProxyStatus.PROXY,
            effective_from=date(2005, 1, 4),
            effective_to=date(2014, 12, 31),
            source="CITIC Securities",
            backend="tushare.ci_index_daily",
            symbol="CI005019.CI",
            proxy_for="cn_equity_baijiu",
            confidence_discount=0.25,
        )


def test_baijiu_chain_never_silently_concatenates_proxy_and_primary() -> None:
    overlap_dates = pd.date_range("2014-10-31", periods=3, freq="ME")
    primary = _segment(
        segment_id="cn_equity_baijiu:primary",
        returns=pd.Series([0.03, 0.04, 0.05], index=overlap_dates),
        proxy_status=ProxyStatus.PRIMARY,
        effective_from=date(2014, 10, 1),
        effective_to=None,
        source="Tushare",
        backend="tushare.index_daily",
        symbol="399997.SZ",
    )
    proxy = _segment(
        segment_id="cn_equity_baijiu_citic_food_beverage",
        returns=pd.Series([0.01, 0.02, 0.03], index=overlap_dates),
        proxy_status=ProxyStatus.PROXY,
        effective_from=date(2005, 1, 4),
        effective_to=date(2014, 12, 31),
        source="CITIC Securities",
        backend="tushare.ci_index_daily",
        symbol="CI005019.CI",
        proxy_for="cn_equity_baijiu",
        confidence_discount=0.25,
    )

    chain = build_proxy_chain(primary, [proxy])
    frame = segments_to_long_frame((*chain, primary))

    assert [segment.segment_id for segment in chain] == [proxy.segment_id]
    assert set(frame["segment_id"]) == {proxy.segment_id, primary.segment_id}
    assert not frame.duplicated(["asset_id", "segment_id", "date"]).any()
    assert frame.duplicated(["asset_id", "date"], keep=False).all()
    assert set(frame["proxy_status"]) == {"primary", "proxy"}
    assert set(frame["benchmark_asset_id"]) == {"cn_equity_hs300"}


def test_segment_outputs_are_defensive_copies() -> None:
    segment = _segment(
        segment_id="cn_equity_baijiu:primary",
        returns=_monthly_series("2015-01-31", [0.01, 0.02, 0.03]),
        proxy_status=ProxyStatus.PRIMARY,
        effective_from=date(2015, 1, 1),
        effective_to=None,
        source="Tushare",
        backend="tushare.index_daily",
        symbol="399997.SZ",
    )

    detached = segment.returns
    detached.iloc[0] = 9.0

    assert segment.returns.iloc[0] == 0.01

