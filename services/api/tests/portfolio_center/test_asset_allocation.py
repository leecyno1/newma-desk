from vibe_visualization_api.portfolio_center.asset_allocation import build_strategic_allocation
from vibe_visualization_api.portfolio_center.models import StrategicAllocationRequest


def cycle_rows():
    values = {
        "A股宽基指数::沪深300": (0.04, 0.22),
        "海外指数/ETF::标普500(SPY)": (0.06, 0.16),
        "各类债券指数::国债指数(上证)": (0.02, 0.04),
        "各类债券指数::沪公司债": (0.03, 0.06),
        "商品::黄金": (0.05, 0.14),
        "商品::中国大宗商品价格综合指数": (0.02, 0.12),
    }
    return [
        {
            "asset_id": asset_id,
            "absolute_expected_return": expected,
            "absolute_volatility": volatility,
            "absolute_up_probability": 0.6,
            "publication_status": "partial",
            "evidence_level": "retrospective_only",
            "as_of": "2026-08-14",
            "forecast_origin": "2026-06-30",
        }
        for asset_id, (expected, volatility) in values.items()
    ]


def test_black_litterman_blends_cycle_views_and_keeps_weights_bounded():
    result = build_strategic_allocation(StrategicAllocationRequest(), cycle_rows())

    assert result.status == "partial"
    assert result.method.startswith("Black-Litterman")
    assert abs(sum(asset.target_weight_pct for asset in result.assets) - 100) < 0.2
    assert max(asset.target_weight_pct for asset in result.assets) <= 35.1
    assert any(asset.cycle_view_return_pct is not None for asset in result.assets)
    assert result.warnings


def test_lower_target_volatility_uses_more_cash_without_leverage():
    high = build_strategic_allocation(
        StrategicAllocationRequest(target_volatility_pct=15), []
    )
    low = build_strategic_allocation(
        StrategicAllocationRequest(target_volatility_pct=5), []
    )

    assert low.cash_weight_pct >= high.cash_weight_pct
    assert low.achieved_volatility_pct <= 5.2
    assert high.achieved_volatility_pct <= 15.2
