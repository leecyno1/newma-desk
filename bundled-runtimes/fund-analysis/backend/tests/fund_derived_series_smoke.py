import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_derived_series_service import FundDerivedSeriesService


def build_rows(count=300, dip_at=200, dip_depth=0.20):
    start = date(2025, 1, 2)
    nav = 1.0
    rows = []
    for offset in range(count):
        if offset < dip_at:
            nav *= 1.001
        elif offset == dip_at:
            nav *= 1 - dip_depth
        else:
            nav *= 1.0005
        rows.append({
            "date": (start + timedelta(days=offset)).isoformat(),
            "nav": nav,
            "accum_nav": nav,
        })
    return rows


def main() -> int:
    rows = build_rows()
    result = FundDerivedSeriesService.build(rows, window="3m")

    if result.get("status") != "ok":
        raise AssertionError(f"derived series must be ok for a full window: {result}")

    drawdown = result.get("drawdown_series") or []
    if len(drawdown) != len(rows):
        raise AssertionError(f"drawdown series must cover every nav point: {len(drawdown)} vs {len(rows)}")
    if drawdown[0]["drawdown"] != 0:
        raise AssertionError(f"first drawdown point must be 0: {drawdown[0]}")

    peak_before_dip = 1.0 * (1.001 ** 199)
    trough = peak_before_dip * 0.8
    expected_trough_dd = trough / peak_before_dip - 1
    dip_point = drawdown[200]
    if abs(dip_point["drawdown"] - expected_trough_dd) > 1e-9:
        raise AssertionError(f"drawdown at dip must be nav/peak-1: {dip_point} vs {expected_trough_dd}")

    rolling = result.get("rolling_return_series") or []
    expected_len = len(rows) - 63
    if len(rolling) != expected_len:
        raise AssertionError(f"rolling 3m series must start after 63 observations: {len(rolling)} vs {expected_len}")
    first_rolling = rolling[0]
    expected_first = (1.001 ** 63) - 1
    if abs(first_rolling["value"] - expected_first) > 1e-9:
        raise AssertionError(f"rolling return must be nav_t/nav_t-63-1: {first_rolling} vs {expected_first}")
    if first_rolling["date"] != rows[63]["date"]:
        raise AssertionError(f"rolling series dates must align to nav dates: {first_rolling}")
    if first_rolling.get("window") != "3m":
        raise AssertionError(f"rolling points must carry the window label: {first_rolling}")

    insufficient = FundDerivedSeriesService.build(rows[:10], window="1y")
    if insufficient.get("status") != "insufficient_evidence":
        raise AssertionError(f"short series must be insufficient evidence: {insufficient}")
    if insufficient.get("rolling_return_series"):
        raise AssertionError("insufficient evidence must not fabricate rolling series")
    # 短样本只有滚动窗口不够：真实回撤轨迹必须照常给出，且带真实历史起止日，
    # 否则详情页会把可用的回撤曲线整体隐藏（UAT：短样本回撤隐藏）。
    if len(insufficient.get("drawdown_series") or []) != 10:
        raise AssertionError(f"short sample must expose every real drawdown point: {insufficient.get('drawdown_series')}")
    if insufficient.get("history_start") != rows[0]["date"] or insufficient.get("history_end") != rows[9]["date"]:
        raise AssertionError(
            "short sample must carry real history bounds: "
            f"{insufficient.get('history_start')} ~ {insufficient.get('history_end')}"
        )

    if result.get("nav_basis") != "accum_nav":
        raise AssertionError(f"accum-only rows must keep accum basis: {result.get('nav_basis')}")
    adjusted_rows = [dict(row, adj_nav=row["accum_nav"]) for row in rows]
    adjusted_result = FundDerivedSeriesService.build(adjusted_rows, window="3m")
    if adjusted_result.get("nav_basis") != "adj_nav":
        raise AssertionError(f"adj-populated rows must be labeled adj_nav: {adjusted_result.get('nav_basis')}")

    class FakeNavRepo:
        def get_nav_series(self, code, start_date=None, end_date=None):
            return rows

    class FakeFundRepo:
        def get_fund(self, code):
            return {"wind_code": code}

    service_result = FundDerivedSeriesService(nav_repo=FakeNavRepo(), fund_repo=FakeFundRepo()).get("TEST.OF")
    if service_result.get("wind_code") != "TEST.OF" or service_result.get("status") != "ok":
        raise AssertionError(f"service.get must wrap build with wind_code: {service_result.get('status')}")

    print("OK derived series exposes underwater drawdown and rolling returns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
