from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from vibe_visualization_api.portfolio_center.models import (
    StrategicAllocationAsset,
    StrategicAllocationRequest,
    StrategicAllocationResult,
    StrategicAllocationScenario,
)


_EPSILON = 1e-10


@dataclass(frozen=True)
class AssetSpec:
    id: str
    name: str
    category: str
    cycle_asset_id: str | None
    benchmark_weight: float
    prior_volatility: float


ASSETS = (
    AssetSpec("cn-equity", "A股宽基", "权益", "A股宽基指数::沪深300", 0.22, 0.23),
    AssetSpec("us-equity", "美股宽基", "权益", "海外指数/ETF::标普500(SPY)", 0.14, 0.18),
    AssetSpec("cn-government-bond", "中国国债", "固收", "各类债券指数::国债指数(上证)", 0.22, 0.045),
    AssetSpec("cn-credit-bond", "信用债", "固收", "各类债券指数::沪公司债", 0.12, 0.065),
    AssetSpec("gold", "黄金", "商品", "商品::黄金", 0.10, 0.17),
    AssetSpec("commodity", "大宗商品", "商品", "商品::中国大宗商品价格综合指数", 0.08, 0.20),
)

# 长周期相关性先验。周期模块当前只给单资产分布，相关性先由配置模型维护。
CORRELATIONS = (
    (1.00, 0.65, -0.15, 0.05, 0.05, 0.20),
    (0.65, 1.00, -0.10, 0.05, 0.05, 0.25),
    (-0.15, -0.10, 1.00, 0.75, 0.05, -0.10),
    (0.05, 0.05, 0.75, 1.00, 0.05, 0.00),
    (0.05, 0.05, 0.05, 0.05, 1.00, 0.35),
    (0.20, 0.25, -0.10, 0.00, 0.35, 1.00),
)

SCENARIOS = (
    (
        "growth-recovery",
        "增长修复",
        "增长回升、通胀温和，权益与信用资产占优。",
        (10.0, 7.0, -3.0, 2.0, -2.0, 4.0),
    ),
    (
        "inflation-rebound",
        "通胀反弹",
        "通胀重新抬头，久期资产承压，黄金与商品占优。",
        (-8.0, -6.0, -9.0, -6.0, 9.0, 12.0),
    ),
    (
        "liquidity-easing",
        "流动性宽松",
        "资金价格下行，权益、债券与黄金同步受益。",
        (8.0, 5.0, 4.0, 3.0, 4.0, 2.0),
    ),
    (
        "risk-off",
        "风险规避",
        "地缘或信用冲击上升，权益和商品下跌，国债与黄金对冲。",
        (-14.0, -10.0, 6.0, -4.0, 8.0, -6.0),
    ),
)


async def fetch_cycle_views(
    base_url: str,
    horizon_months: int,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    http_client = client or httpx.AsyncClient(timeout=8, follow_redirects=True)
    try:
        response = await http_client.get(
            f"{base_url.rstrip('/')}/v1/assets/compare",
            params={"limit": 500, "horizon": horizon_months},
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", []) if isinstance(payload, dict) else []
    finally:
        if client is None:
            await http_client.aclose()


def build_strategic_allocation(
    request: StrategicAllocationRequest,
    cycle_rows: list[dict[str, Any]],
) -> StrategicAllocationResult:
    risk_free = request.risk_free_rate_pct / 100
    row_by_id = {
        str(row.get("asset_id")): row
        for row in cycle_rows
        if isinstance(row, dict) and row.get("asset_id")
    }
    confidences = [_view_confidence(row_by_id.get(asset.cycle_asset_id or "")) for asset in ASSETS]
    volatilities = [
        _forward_volatility(asset, row_by_id.get(asset.cycle_asset_id or ""), confidence, request.horizon_months)
        for asset, confidence in zip(ASSETS, confidences, strict=True)
    ]
    covariance = [
        [CORRELATIONS[left][right] * volatilities[left] * volatilities[right] for right in range(len(ASSETS))]
        for left in range(len(ASSETS))
    ]
    risky_benchmark_total = sum(asset.benchmark_weight for asset in ASSETS)
    benchmark = [asset.benchmark_weight / risky_benchmark_total for asset in ASSETS]
    equilibrium_excess = _mat_vec(covariance, benchmark)
    equilibrium = [risk_free + 2.5 * value for value in equilibrium_excess]
    views = [
        _annualized_view(row_by_id.get(asset.cycle_asset_id or ""), request.horizon_months)
        for asset in ASSETS
    ]
    posterior = _black_litterman_posterior(
        equilibrium,
        covariance,
        views,
        confidences,
    )

    if request.model == "minimum-volatility":
        scores = _minimum_variance_scores(covariance)
        method = "minimum-variance + target-volatility"
    elif request.model == "risk-parity":
        scores = [1 / max(volatility, 0.01) for volatility in volatilities]
        method = "inverse-volatility risk parity + target-volatility"
    else:
        scores = _mean_variance_scores(covariance, posterior, risk_free)
        method = "Black-Litterman + mean-variance + target-volatility"
    risky_weights = _capped_weights(scores, request.max_weight)
    risky_volatility = math.sqrt(max(0.0, _portfolio_variance(risky_weights, covariance)))
    target_volatility = request.target_volatility_pct / 100
    scale = min(1.0, target_volatility / risky_volatility) if risky_volatility > _EPSILON else 0.0
    weights = [weight * scale for weight in risky_weights]
    cash_weight = max(0.0, 1 - sum(weights))
    achieved_volatility = math.sqrt(max(0.0, _portfolio_variance(weights, covariance)))
    expected_return = sum(weight * value for weight, value in zip(weights, posterior, strict=True)) + cash_weight * risk_free
    risk_contributions = _risk_contributions(weights, covariance)

    assets: list[StrategicAllocationAsset] = []
    cycle_dates: list[str] = []
    usable_views = 0
    for index, spec in enumerate(ASSETS):
        row = row_by_id.get(spec.cycle_asset_id or "")
        view = views[index]
        if view is not None:
            usable_views += 1
        if row and row.get("as_of"):
            cycle_dates.append(str(row["as_of"]))
        assets.append(
            StrategicAllocationAsset(
                id=spec.id,
                name=spec.name,
                category=spec.category,
                cycleAssetId=spec.cycle_asset_id,
                benchmarkWeightPct=round(spec.benchmark_weight * 100, 2),
                targetWeightPct=round(weights[index] * 100, 2),
                expectedReturnPct=round(posterior[index] * 100, 2),
                volatilityPct=round(volatilities[index] * 100, 2),
                riskContributionPct=round(risk_contributions[index] * 100, 2),
                equilibriumReturnPct=round(equilibrium[index] * 100, 2),
                cycleViewReturnPct=round(view * 100, 2) if view is not None else None,
                upProbabilityPct=_optional_pct(row, "absolute_up_probability"),
                confidencePct=round(confidences[index] * 100, 1),
                publicationStatus=str(row.get("publication_status", "unavailable")) if row else "unavailable",
                evidenceLevel=str(row.get("evidence_level", "prior-only")) if row else "prior-only",
                sourceAsOf=str(row["as_of"]) if row and row.get("as_of") else None,
                forecastOrigin=str(row["forecast_origin"]) if row and row.get("forecast_origin") else None,
            )
        )
    assets.append(
        StrategicAllocationAsset(
            id="cash",
            name="现金",
            category="现金",
            benchmarkWeightPct=12,
            targetWeightPct=round(cash_weight * 100, 2),
            expectedReturnPct=round(request.risk_free_rate_pct, 2),
            volatilityPct=0,
            riskContributionPct=0,
            equilibriumReturnPct=round(request.risk_free_rate_pct, 2),
            confidencePct=100,
            publicationStatus="model-input",
            evidenceLevel="risk-free-rate",
        )
    )
    assets.sort(key=lambda item: item.target_weight_pct, reverse=True)

    scenario_results = [
        StrategicAllocationScenario(
            id=scenario_id,
            name=name,
            description=description,
            portfolioImpactPct=round(
                sum(weight * shock for weight, shock in zip(weights, shocks, strict=True)),
                2,
            ),
            assetImpactsPct={ASSETS[index].id: shock for index, shock in enumerate(shocks)},
        )
        for scenario_id, name, description, shocks in SCENARIOS
    ]
    status = "prior-only" if usable_views == 0 else "partial" if usable_views < len(ASSETS) or any(confidence < 0.5 for confidence in confidences) else "ready"
    warnings = ["周期结论用于研究观点融合，不代表正式收益承诺。"]
    if status == "partial":
        warnings.append("当前周期预测多为回溯证据或未通过模型门槛，已低权重收缩到长期均衡先验。")
    if cash_weight > 0.5:
        warnings.append("目标波动率较低，组合主要通过提高现金比例降风险。")
    top_asset = max((asset for asset in assets if asset.id != "cash"), key=lambda item: item.target_weight_pct)
    top_risk = max((asset for asset in assets if asset.id != "cash"), key=lambda item: item.risk_contribution_pct)
    best_forward = max((asset for asset in assets if asset.cycle_view_return_pct is not None), key=lambda item: item.cycle_view_return_pct or -999, default=None)
    insights = [
        f"核心配置为{top_asset.name} {top_asset.target_weight_pct:.1f}%，组合风险主要来自{top_risk.name}。",
        f"目标波动率 {request.target_volatility_pct:.1f}%，模型预计达到 {achieved_volatility * 100:.1f}%。",
    ]
    if best_forward:
        insights.append(
            f"周期数据中{best_forward.name}的前瞻收益最高，但当前证据置信度仅 {best_forward.confidence_pct:.0f}%。"
        )
    return StrategicAllocationResult(
        status=status,
        model=request.model,
        method=method,
        horizonMonths=request.horizon_months,
        targetVolatilityPct=request.target_volatility_pct,
        achievedVolatilityPct=round(achieved_volatility * 100, 2),
        expectedReturnPct=round(expected_return * 100, 2),
        sharpe=round((expected_return - risk_free) / achieved_volatility, 2) if achieved_volatility > _EPSILON else None,
        cashWeightPct=round(cash_weight * 100, 2),
        assets=assets,
        scenarios=scenario_results,
        insights=insights,
        warnings=warnings,
        dataSources=["周期叠加 /v1/assets/compare", "Newma 长周期相关性先验"],
        cycleAsOf=max(cycle_dates) if cycle_dates else None,
        generatedAt=datetime.now(UTC),
    )


def _view_confidence(row: dict[str, Any] | None) -> float:
    if not row or row.get("absolute_expected_return") is None:
        return 0.0
    status = str(row.get("publication_status", "")).lower()
    confidence = 0.65 if status in {"ready", "published", "complete"} else 0.18 if status == "partial" else 0.08
    evidence = str(row.get("evidence_level", "")).lower()
    if "retrospective" in evidence:
        confidence *= 0.75
    return max(0.02, min(0.8, confidence))


def _annualized_view(row: dict[str, Any] | None, horizon_months: int) -> float | None:
    if not row:
        return None
    value = row.get("absolute_expected_return")
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= -1:
        return None
    return (1 + float(value)) ** (12 / horizon_months) - 1


def _forward_volatility(asset: AssetSpec, row: dict[str, Any] | None, confidence: float, horizon_months: int) -> float:
    value = row.get("absolute_volatility") if row else None
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return asset.prior_volatility
    annualized = float(value) * math.sqrt(12 / horizon_months)
    return asset.prior_volatility * (1 - confidence) + annualized * confidence


def _black_litterman_posterior(
    equilibrium: list[float],
    covariance: list[list[float]],
    views: list[float | None],
    confidences: list[float],
) -> list[float]:
    tau_covariance = [[value * 0.05 for value in row] for row in covariance]
    active = [index for index, view in enumerate(views) if view is not None and confidences[index] > 0]
    if not active:
        return equilibrium
    matrix = [[tau_covariance[left][right] for right in active] for left in active]
    target = [float(views[index]) - equilibrium[index] for index in active]
    for position, index in enumerate(active):
        confidence = confidences[index]
        matrix[position][position] += tau_covariance[index][index] * (1 - confidence) / confidence
    solved = _solve(matrix, target)
    return [
        equilibrium[index] + sum(tau_covariance[index][active[position]] * solved[position] for position in range(len(active)))
        for index in range(len(equilibrium))
    ]


def _mean_variance_scores(covariance: list[list[float]], returns: list[float], risk_free: float) -> list[float]:
    scale = max(covariance[index][index] for index in range(len(covariance)))
    regularized = [
        [value + (scale * 1e-4 if row == column else 0) for column, value in enumerate(values)]
        for row, values in enumerate(covariance)
    ]
    try:
        solved = _solve(regularized, [value - risk_free for value in returns])
    except ValueError:
        solved = [(returns[index] - risk_free) / max(covariance[index][index], _EPSILON) for index in range(len(returns))]
    positive = [max(0.0, value) for value in solved]
    return positive if sum(positive) > _EPSILON else [1 / math.sqrt(max(covariance[index][index], _EPSILON)) for index in range(len(returns))]


def _minimum_variance_scores(covariance: list[list[float]]) -> list[float]:
    try:
        solved = _solve(covariance, [1.0] * len(covariance))
        positive = [max(0.0, value) for value in solved]
        if sum(positive) > _EPSILON:
            return positive
    except ValueError:
        pass
    return [1 / math.sqrt(max(covariance[index][index], _EPSILON)) for index in range(len(covariance))]


def _capped_weights(scores: list[float], cap: float) -> list[float]:
    weights = [0.0] * len(scores)
    active = set(range(len(scores)))
    remaining = 1.0
    effective_cap = max(cap, 1 / len(scores))
    while active:
        total = sum(max(0.0, scores[index]) for index in active)
        proposed = {
            index: remaining * (max(0.0, scores[index]) / total if total > _EPSILON else 1 / len(active))
            for index in active
        }
        over = [index for index, value in proposed.items() if value > effective_cap]
        if not over:
            for index, value in proposed.items():
                weights[index] = value
            break
        for index in over:
            weights[index] = effective_cap
            remaining -= effective_cap
            active.remove(index)
    return weights


def _mat_vec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(value * vector[column] for column, value in enumerate(row)) for row in matrix]


def _portfolio_variance(weights: list[float], covariance: list[list[float]]) -> float:
    return sum(weights[left] * covariance[left][right] * weights[right] for left in range(len(weights)) for right in range(len(weights)))


def _risk_contributions(weights: list[float], covariance: list[list[float]]) -> list[float]:
    marginal = _mat_vec(covariance, weights)
    total = sum(weight * value for weight, value in zip(weights, marginal, strict=True))
    return [weight * value / total if total > _EPSILON else 0.0 for weight, value in zip(weights, marginal, strict=True)]


def _solve(matrix: list[list[float]], target: list[float]) -> list[float]:
    size = len(target)
    augmented = [list(matrix[row]) + [target[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= _EPSILON:
            raise ValueError("singular matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [value - factor * pivot_value for value, pivot_value in zip(augmented[row], augmented[column], strict=True)]
    return [augmented[row][-1] for row in range(size)]


def _optional_pct(row: dict[str, Any] | None, field: str) -> float | None:
    value = row.get(field) if row else None
    return round(float(value) * 100, 1) if isinstance(value, (int, float)) and math.isfinite(value) else None
