"""统一基金业绩归因。

正式 Barra、Brinson 与净值行为解释分开输出，避免代理指标冒充专业模型。
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging
import re

from lib.holding_weight_validation import (
    INVALID_WEIGHT_SCALE,
    fund_nav_weight,
    validate_fund_nav_weights,
)

logger = logging.getLogger(__name__)


class PerformanceAttributionService:
    """面向基金详情与 AI 分析的统一归因入口。"""

    def __init__(self, classification_adapter: Optional[Any] = None):
        self._classification_adapter = classification_adapter

    def latest_completed_quarter(self) -> str:
        return self._latest_completed_quarter()

    def analyze(
        self,
        wind_code: str,
        benchmark: Optional[str] = None,
        quarter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        from repositories import get_factor_repo, get_fund_repo, get_holding_repo, get_holding_style_snapshot_repo
        from service_registry import get_data_service
        from services.investment_analysis_service import InvestmentAnalysisService

        fund = get_fund_repo().get_fund_by_identifier(wind_code)
        if not fund:
            raise ValueError(f"Fund not found: {wind_code}")

        fund_code = str(fund.get("wind_code") or wind_code)
        normalized_quarter = self._normalize_quarter(quarter)
        if quarter and not normalized_quarter:
            raise ValueError("quarter must use YYYYQ1-YYYYQ4, for example 2026Q2")
        attribution_quarter = normalized_quarter or self._latest_completed_quarter()
        holding_quarter = self._previous_quarter(attribution_quarter)
        classification_context = self._get_classification_adapter().get_classification_context(fund_code) or {}
        benchmark_code, benchmark_source, benchmark_detail = self._resolve_attribution_benchmark(
            benchmark,
            classification_context,
            fund,
        )
        data_service = get_data_service()
        equity_attribution_applicable = self._equity_attribution_applicable(fund)
        holdings = []
        if equity_attribution_applicable:
            holdings = get_holding_repo().get_holdings(fund_code, holding_quarter)
            if not holdings:
                holdings = data_service.get_fund_holdings(fund_code, holding_quarter)
            if holdings:
                from services.fund_holding_weight_service import FundHoldingWeightService

                enrichment = FundHoldingWeightService().enrich(
                    fund_code,
                    holding_quarter,
                    holdings,
                    refresh_allocation=False,
                )
                holdings = enrichment["holdings"]
                if enrichment.get("changed"):
                    get_holding_repo().upsert_holdings(fund_code, holding_quarter, holdings)

        style_factor_values: Dict[str, float] = {}
        style_factor_payload: Dict[str, Any] = {}
        if not equity_attribution_applicable:
            pass
        else:
            holding_style_snapshot = get_holding_style_snapshot_repo().get(fund_code, holding_quarter)
            if holding_style_snapshot:
                style_factor_payload = {
                    "status": holding_style_snapshot.get("status") or "insufficient_evidence",
                    "source": holding_style_snapshot.get("source") or "local_postgres.holding_style_snapshots",
                    "quarter": holding_quarter,
                    "descriptors": holding_style_snapshot.get("descriptors") or [],
                    "peer_percentiles": holding_style_snapshot.get("peer_percentiles") or [],
                    "style_labels": holding_style_snapshot.get("style_labels") or [],
                    "peer_group_id": holding_style_snapshot.get("peer_group_id"),
                    "peer_group_key": holding_style_snapshot.get("peer_group_key"),
                    "peer_group_name": holding_style_snapshot.get("peer_group_name"),
                    "peer_sample_size": holding_style_snapshot.get("peer_sample_size") or 0,
                    "minimum_peer_count": holding_style_snapshot.get("minimum_peer_count") or 5,
                    "holdings_disclosed_weight": holding_style_snapshot.get("holdings_disclosed_weight"),
                    "missing_items": list(holding_style_snapshot.get("missing_items") or []),
                }
            saved_factors = get_factor_repo().get_exposures(fund_code, holding_quarter)
            if saved_factors and not style_factor_payload:
                style_factor_values = {
                    str(item.get("factor_name")): float(item.get("exposure"))
                    for item in saved_factors
                    if item.get("factor_name") and item.get("exposure") is not None
                }
                style_factor_payload = {
                    "status": "partial_evidence",
                    "source": "local_postgres.factor_exposures",
                    "quarter": holding_quarter,
                    "descriptors": [
                        {
                            "factor": str(item.get("factor_name")),
                            "exposure": float(item.get("exposure")),
                            "risk_contribution": (
                                float(item.get("risk_contribution"))
                                if item.get("risk_contribution") is not None else None
                            ),
                        }
                        for item in saved_factors
                        if item.get("factor_name") and item.get("exposure") is not None
                    ],
                    "missing_items": [
                        "现场分析复用已沉淀的因子暴露；因子协方差矩阵和特异风险未接入，不能输出完整 Barra 风险分解。"
                    ],
                }
        if equity_attribution_applicable and not style_factor_payload and data_service.__class__.__name__ != "TushareDataService":
            try:
                style_payload = data_service.get_fund_style(fund_code) or {}
                style_factor_values = {
                    key: float(value)
                    for key, value in style_payload.items()
                    if key in self._barra_factor_names() and value is not None
                }
            except Exception as exc:
                logger.warning("Formal style factors unavailable for %s: %s", fund_code, exc)

        barra = self._barra_evidence(
            fund,
            holdings,
            style_factor_values,
            holding_quarter,
            style_factor_payload,
        )
        if equity_attribution_applicable and holdings and data_service.__class__.__name__ == "TushareDataService":
            from services.public_holdings_risk_service import PublicHoldingsRiskService

            barra["public_risk_model"] = PublicHoldingsRiskService(data_service).analyze(
                holdings,
                holding_quarter,
            )
        else:
            barra["public_risk_model"] = {
                "status": "not_applicable" if not equity_attribution_applicable else "insufficient_evidence",
                "method": "public_holdings_single_market_factor_model",
                "is_formal_barra": False,
                "quarter": holding_quarter,
                "risk_contributions": [],
                "missing_items": [
                    "当前基金不适用股票持仓风险模型。"
                    if not equity_attribution_applicable
                    else "缺少真实 A 股持仓或行情 adapter，不能估计公开持仓统计风险。"
                ],
            }
        from services.cross_market_holding_profile_service import CrossMarketHoldingProfileService

        cross_market_holding_profile = CrossMarketHoldingProfileService().analyze(
            holdings,
            holding_quarter,
        ) if equity_attribution_applicable else {
            "status": "not_applicable",
            "quarter": holding_quarter,
            "markets": [],
            "missing_items": ["当前基金不适用股票跨市场持仓画像。"],
        }
        brinson = self._brinson_evidence(
            data_service=data_service,
            fund=fund,
            holdings=holdings,
            benchmark_code=benchmark_code,
            benchmark_source=benchmark_source,
            benchmark_detail=benchmark_detail,
            attribution_quarter=attribution_quarter,
            holding_quarter=holding_quarter,
        )

        investment_analysis = InvestmentAnalysisService()
        nav_factor = self._safe_analysis(
            lambda: investment_analysis.factor_lens(fund_code, start_date, end_date),
            "净值行为因子证据不可用",
        )
        if benchmark_code:
            nav_attribution = self._safe_analysis(
                lambda: investment_analysis.advanced_attribution(
                    fund_code,
                    benchmark=benchmark_code,
                    start_date=start_date,
                    end_date=end_date,
                ),
                "净值主动收益解释不可用",
            )
        else:
            nav_attribution = {
                "status": "insufficient_evidence",
                "source": "standardized_classification_gate",
                "missing_items": ["基金分类目录缺少有效基准，不能计算主动收益。"],
            }
        nav_factor["method"] = "nav_behavior_factor_lens"
        nav_factor["is_barra"] = False
        nav_attribution["method"] = "nav_return_attribution"
        nav_attribution["is_brinson"] = False

        status = self._aggregate_status(
            barra.get("status"),
            brinson.get("status"),
            nav_attribution.get("status"),
        )

        bundle = {
            "fund": {
                "id": str(fund.get("id") or fund_code),
                "wind_code": fund_code,
                "name": fund.get("name"),
                "type": fund.get("type"),
            },
            "status": status,
            "quarter": attribution_quarter,
            "holding_snapshot_quarter": holding_quarter,
            "benchmark": benchmark_code,
            "benchmark_source": benchmark_source,
            "benchmark_detail": benchmark_detail,
            "barra": barra,
            "cross_market_holding_profile": cross_market_holding_profile,
            "brinson": brinson,
            "nav_factor_lens": nav_factor,
            "nav_return_attribution": nav_attribution,
            "methodology": {
                "formal_models": ["Barra style/risk exposure", "Brinson-Fachler industry attribution"],
                "supplementary_models": ["Cross-market disclosed-holding profile", "NAV behavior factor lens", "NAV active-return decomposition"],
                "public_risk_model": "公开持仓单市场因子统计模型仅补充市场风险与特异风险，不等同于商业 Barra。",
                "rule": "净值行为解释不得标记为 Barra 或 Brinson。",
                "market_scope_rule": "A 股 Barra 描述子与港股公开持仓画像分开计算，不跨市场混算。",
                "benchmark_rule": "默认基准只来自基金分类目录；用户可在单次分析中显式覆盖。",
            },
        }
        try:
            from repositories import get_attribution_repo

            bundle["history_saved"] = get_attribution_repo().save_bundle(bundle)
        except Exception as exc:
            logger.warning("Attribution history save failed for %s: %s", fund_code, exc)
            bundle["history_saved"] = False
        return bundle

    def _barra_evidence(
        self,
        fund: Dict[str, Any],
        holdings: List[Dict[str, Any]],
        style_factors: Dict[str, float],
        holding_quarter: str,
        style_factor_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        fund_type = str(fund.get("type") or "").lower()
        if any(token in fund_type for token in ["money", "货币", "bond", "债"]):
            return {
                "method": "barra_style_risk_model",
                "status": "not_applicable",
                "formal_model_ready": False,
                "source": "methodology_scope",
                "quarter": holding_quarter,
                "factor_exposures": [],
                "industry_exposures": {},
                "risk_contributions": [],
                "r_squared": None,
                "holdings_count": 0,
                "holdings_disclosed_weight": 0.0,
                "missing_items": ["货币或债券基金不适用当前股票 Barra 风格与风险模型。"],
            }
        weight_validation = validate_fund_nav_weights(holdings)
        if weight_validation.status == INVALID_WEIGHT_SCALE:
            return {
                "method": "barra_style_risk_model",
                "status": "insufficient_evidence",
                "formal_model_ready": False,
                "descriptor_model_ready": False,
                "source": "invalid_weight_scale_gate",
                "quarter": holding_quarter,
                "factor_exposures": [],
                "industry_exposures": {},
                "risk_contributions": [],
                "r_squared": None,
                "holdings_count": len(holdings),
                "holdings_disclosed_weight": 0.0,
                "weight_validation": weight_validation.as_dict(),
                "missing_items": ["持仓基金净值权重口径异常，已阻止进入 Barra 风格与行业暴露计算。"],
            }
        industry_exposures: Dict[str, float] = {}
        disclosed_weight = 0.0
        model_eligible_weight = 0.0
        model_eligible_holdings = 0
        for holding in holdings:
            weight = self._fund_nav_weight(holding)
            if weight is None or weight <= 0:
                continue
            disclosed_weight += weight
            code = str(holding.get("stock_code") or "").upper()
            if not code.endswith((".SH", ".SZ", ".BJ")):
                continue
            industry = str(holding.get("industry") or "未知")
            model_eligible_weight += weight
            model_eligible_holdings += 1
            industry_exposures[industry] = industry_exposures.get(industry, 0.0) + weight

        style_factor_payload = style_factor_payload or {}
        descriptors = style_factor_payload.get("descriptors") or []
        if descriptors:
            status = "partial_evidence"
            missing_items = list(style_factor_payload.get("missing_items") or [])
        elif style_factor_payload.get("status") == "insufficient_evidence":
            status = "insufficient_evidence"
            missing_items = list(style_factor_payload.get("missing_items") or [])
            if str(style_factor_payload.get("source") or "") == "fund_portfolio_disclosure_gate":
                industry_exposures = {}
        elif style_factors:
            status = "partial_evidence"
            missing_items = ["已取得 Barra 风格因子暴露，但缺少可核验的因子协方差矩阵和特异风险，暂不输出正式风险贡献与 R²。"]
        elif industry_exposures:
            status = "partial_evidence"
            missing_items = ["已取得持仓行业暴露，但未接入正式 Barra 风格因子库，不能输出 SIZE、BETA、MOMENTUM 等因子结论。"]
        elif disclosed_weight > 0 and model_eligible_weight <= 0:
            status = "insufficient_evidence"
            missing_items = ["公开持仓没有可进入当前 A 股 Barra 描述子的证券；港股等市场已在独立跨市场持仓画像中展示。"]
        elif holdings:
            status = "insufficient_evidence"
            missing_items = ["持仓只有占股票市值比，缺少同报告期基金资产净值，不能当作基金整体行业暴露。"]
        else:
            status = "insufficient_evidence"
            missing_items = ["持仓明细缺失，不能计算 Barra 风格或行业暴露。"]

        return {
            "method": "barra_style_risk_model",
            "status": status,
            "formal_model_ready": False,
            "descriptor_model_ready": bool(descriptors),
            "source": style_factor_payload.get("source") or ("factor_exposure_input" if style_factors else "fund_portfolio_disclosure"),
            "quarter": holding_quarter,
            "market_scope": "china_a_share",
            "factor_exposures": descriptors or [
                {
                    "factor": factor,
                    "exposure": exposure,
                }
                for factor, exposure in style_factors.items()
            ],
            "industry_exposures": dict(
                sorted(
                    ((key, round(value, 6)) for key, value in industry_exposures.items()),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ),
            "risk_contributions": [],
            "r_squared": None,
            "holdings_count": len(holdings),
            "holdings_disclosed_weight": round(disclosed_weight, 6),
            "model_eligible_holdings_count": model_eligible_holdings,
            "model_eligible_weight": round(model_eligible_weight, 6),
            "cross_market_excluded_weight": round(max(0.0, disclosed_weight - model_eligible_weight), 6),
            "weight_validation": weight_validation.as_dict(),
            "market_benchmark": style_factor_payload.get("market_benchmark"),
            "as_of_date": style_factor_payload.get("as_of_date"),
            "peer_percentiles": style_factor_payload.get("peer_percentiles") or [],
            "style_labels": style_factor_payload.get("style_labels") or [],
            "peer_group": {
                "id": style_factor_payload.get("peer_group_id"),
                "key": style_factor_payload.get("peer_group_key"),
                "name": style_factor_payload.get("peer_group_name"),
                "sample_size": style_factor_payload.get("peer_sample_size") or 0,
                "minimum_peer_count": style_factor_payload.get("minimum_peer_count") or 5,
            },
            "missing_items": missing_items,
        }

    def _brinson_evidence(
        self,
        data_service: Any,
        fund: Dict[str, Any],
        holdings: List[Dict[str, Any]],
        benchmark_code: Optional[str],
        benchmark_source: str,
        benchmark_detail: Dict[str, Any],
        attribution_quarter: str,
        holding_quarter: str,
    ) -> Dict[str, Any]:
        fund_type = str(fund.get("type") or "").lower()
        if any(token in fund_type for token in ["money", "货币", "bond", "债"]):
            return self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                ["货币或债券基金不适用当前股票行业 Brinson 归因。"],
                status="not_applicable",
            )
        if not benchmark_code:
            raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
            universe = raw_data.get("universe") if isinstance(raw_data.get("universe"), dict) else {}
            info = raw_data.get("info") if isinstance(raw_data.get("info"), dict) else {}
            declared_benchmark = str(
                benchmark_detail.get("declared_benchmark")
                or universe.get("benchmark")
                or info.get("benchmark")
                or fund.get("benchmark")
                or ""
            )
            if "存款利率" in declared_benchmark and not re.search(r"(?:股票|权益|沪深|中证|上证|深证|恒生|国证)", declared_benchmark):
                return self._missing_brinson(
                    benchmark_code,
                    attribution_quarter,
                    holding_quarter,
                    ["基金合同基准仅为存款利率目标，没有可比较的行业权重；不适用股票行业 Brinson 归因。"],
                    status="not_applicable",
                )
            return self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                ["基金分类目录缺少有效基准，不能计算 Brinson 行业归因。"],
            )
        if not holdings:
            return self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                [f"缺少 {holding_quarter} 持仓，不能解释 {attribution_quarter} 的行业配置与选择效应。"],
            )
        weight_validation = validate_fund_nav_weights(holdings)
        if weight_validation.status == INVALID_WEIGHT_SCALE:
            payload = self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                ["持仓基金净值权重口径异常，已阻止进入 Brinson 行业归因。"],
            )
            payload["source"] = "invalid_weight_scale_gate"
            payload["weight_validation"] = weight_validation.as_dict()
            return payload
        if any(self._fund_nav_weight(holding) is None for holding in holdings):
            return self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                ["持仓只有占股票市值比，缺少同报告期基金资产净值，不能作为 Brinson 的基金整体行业权重。"],
            )
        if data_service.__class__.__name__ != "TushareDataService" or getattr(data_service, "mock_mode", False):
            return self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                ["当前数据 adapter 未提供基金、基准、成分股和行业的同区间收益。"],
            )

        try:
            return self._tushare_brinson(
                data_service=data_service,
                fund=fund,
                holdings=holdings,
                benchmark_code=benchmark_code,
                benchmark_source=benchmark_source,
                benchmark_detail=benchmark_detail,
                attribution_quarter=attribution_quarter,
                holding_quarter=holding_quarter,
            )
        except Exception as exc:
            logger.exception("Brinson input preparation failed for %s", fund.get("wind_code"))
            return self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                [f"Brinson 输入准备失败：{exc.__class__.__name__}"],
            )

    def _tushare_brinson(
        self,
        data_service: Any,
        fund: Dict[str, Any],
        holdings: List[Dict[str, Any]],
        benchmark_code: str,
        benchmark_source: str,
        benchmark_detail: Dict[str, Any],
        attribution_quarter: str,
        holding_quarter: str,
    ) -> Dict[str, Any]:
        from lib.brinson.attribution import BrinsonAttributor
        from services.tushare_service import _to_ts_code

        period_start, period_end = self._quarter_dates(attribution_quarter)
        pro = data_service.pro
        index_frame = pro.index_daily(ts_code=benchmark_code, start_date=period_start, end_date=period_end)
        if index_frame is None or index_frame.empty or len(index_frame) < 2:
            return self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                ["基准指数区间行情缺失。"],
            )
        index_frame = index_frame.sort_values("trade_date")
        first_trade = str(index_frame.iloc[0]["trade_date"])
        last_trade = str(index_frame.iloc[-1]["trade_date"])
        benchmark_return = float(index_frame.iloc[-1]["close"]) / float(index_frame.iloc[0]["close"]) - 1
        equity_components = benchmark_detail.get("equity_components") or []
        if len(equity_components) >= 2:
            component_weight = sum(self._number(item.get("weight")) or 0 for item in equity_components)
            component_returns = []
            for component in equity_components:
                code = str(component.get("code") or "")
                weight = self._number(component.get("weight")) or 0
                frame = pro.index_daily(ts_code=code, start_date=period_start, end_date=period_end)
                if not code or weight <= 0 or frame is None or frame.empty or len(frame) < 2:
                    return self._missing_brinson(
                        benchmark_code,
                        attribution_quarter,
                        holding_quarter,
                        [f"合同权益复合基准成分行情缺失：{component.get('name') or code or '未知指数'}。"],
                    )
                frame = frame.sort_values("trade_date")
                component_return = float(frame.iloc[-1]["close"]) / float(frame.iloc[0]["close"]) - 1
                component_returns.append((weight, component_return))
            benchmark_return = sum(weight * value for weight, value in component_returns) / component_weight

        fund_frame = pro.fund_nav(
            ts_code=_to_ts_code(str(fund.get("wind_code"))),
            start_date=period_start,
            end_date=period_end,
        )
        fund_return = self._frame_return(fund_frame, ("adj_nav", "accum_nav", "unit_nav"), "nav_date")
        if fund_return is None:
            return self._missing_brinson(
                benchmark_code,
                attribution_quarter,
                holding_quarter,
                ["基金区间净值不足，不能计算主动收益。"],
            )

        active_benchmark_return = benchmark_return
        contract_components = benchmark_detail.get("contract_components") or []
        contract_composite_return = None
        contract_component_returns: Dict[str, float] = {}
        if len(contract_components) >= 2:
            from services.fund_nav_evidence_service import FundNavDataEnrichmentService

            composite_series = FundNavDataEnrichmentService(data_service).build_contract_composite_series(
                contract_components,
                period_start,
                period_end,
            )
            if len(composite_series) >= 2 and float(composite_series[0]["nav"]) > 0:
                contract_composite_return = (
                    float(composite_series[-1]["nav"]) / float(composite_series[0]["nav"]) - 1
                )
                active_benchmark_return = contract_composite_return
                contract_component_returns = self._contract_component_returns(
                    data_service,
                    contract_components,
                    period_start,
                    period_end,
                )

        weight_start = (datetime.strptime(first_trade, "%Y%m%d") - timedelta(days=220)).strftime("%Y%m%d")
        benchmark_weight_rows = []
        selected_weight_dates = []
        weight_components = equity_components if len(equity_components) >= 2 else [
            {"code": benchmark_code, "weight": 1.0}
        ]
        total_component_weight = sum(self._number(item.get("weight")) or 0 for item in weight_components)
        for component in weight_components:
            component_code = str(component.get("code") or "")
            component_weight = self._number(component.get("weight")) or 0
            weight_frame = pro.index_weight(index_code=component_code, start_date=weight_start, end_date=first_trade)
            if component_weight <= 0 or weight_frame is None or weight_frame.empty:
                return self._missing_brinson(
                    benchmark_code,
                    attribution_quarter,
                    holding_quarter,
                    [f"基准成分权重缺失：{component.get('name') or component_code or '未知指数'}。"],
                )
            available_dates = [str(value) for value in weight_frame["trade_date"].dropna().tolist()]
            selected_date = max((value for value in available_dates if value <= first_trade), default=max(available_dates))
            selected_weight_dates.append({"code": component_code, "date": selected_date})
            scale = component_weight / total_component_weight
            for row in weight_frame[weight_frame["trade_date"].astype(str) == selected_date].to_dict("records"):
                benchmark_weight_rows.append({**row, "weight": (self._number(row.get("weight")) or 0) * scale})
        selected_weight_date = max(item["date"] for item in selected_weight_dates)

        start_prices = pro.daily(trade_date=first_trade)
        end_prices = pro.daily(trade_date=last_trade)
        start_factors = pro.adj_factor(trade_date=first_trade)
        end_factors = pro.adj_factor(trade_date=last_trade)
        stock_returns = self._adjusted_stock_returns(start_prices, end_prices, start_factors, end_factors)
        hong_kong_codes = sorted({
            str(item.get("stock_code") or item.get("con_code") or "")
            for item in [*holdings, *benchmark_weight_rows]
            if str(item.get("stock_code") or item.get("con_code") or "").endswith(".HK")
        })
        benchmark_hong_kong_codes = {
            str(item.get("con_code") or "")
            for item in benchmark_weight_rows
            if str(item.get("con_code") or "").endswith(".HK")
        }
        hong_kong_return_evidence = self._hong_kong_stock_returns(
            data_service,
            pro,
            hong_kong_codes,
            period_start,
            period_end,
        )
        hong_kong_returns = hong_kong_return_evidence.get("returns") or {}
        hong_kong_return_source = hong_kong_return_evidence.get("source")
        stock_returns.update(hong_kong_returns)
        hsi_snapshot: Optional[Dict[str, Any]] = None
        hsi_constituent_returns: Dict[str, float] = {}
        hsi_return_source = None
        if any(str(component.get("code") or "").upper() == "HSI" for component in contract_components):
            try:
                if hasattr(data_service, "get_hang_seng_index_snapshot_before"):
                    hsi_snapshot = data_service.get_hang_seng_index_snapshot_before(first_trade)
                if hsi_snapshot:
                    hsi_codes = [
                        str(item.get("constituent_code") or "")
                        for item in hsi_snapshot.get("constituents") or []
                        if item.get("weight") is not None
                    ]
                    hsi_return_evidence = self._hong_kong_stock_returns(
                        data_service,
                        pro,
                        hsi_codes,
                        period_start,
                        period_end,
                    )
                    hsi_constituent_returns = hsi_return_evidence.get("returns") or {}
                    hsi_return_source = hsi_return_evidence.get("source")
            except Exception:
                hsi_snapshot = None
        stock_profiles = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry")
        industries = {
            str(row["ts_code"]): str(row.get("industry") or "未知")
            for _, row in stock_profiles.iterrows()
        } if stock_profiles is not None and not stock_profiles.empty else {}
        hsi_industry_map = {
            str(item.get("constituent_code")): str(item.get("industry"))
            for item in (hsi_snapshot or {}).get("constituents") or []
            if item.get("constituent_code") and item.get("industry")
        }

        portfolio_industries: Dict[str, Dict[str, float]] = {}
        disclosed_weight = 0.0
        return_weight = 0.0
        for holding in holdings:
            code = str(holding.get("stock_code") or "")
            weight = self._fund_nav_weight(holding)
            if not code or weight is None or weight <= 0:
                continue
            disclosed_weight += weight
            if code.endswith(".HK") and hsi_snapshot:
                industry = hsi_industry_map.get(code) or "港股-行业未知"
            else:
                industry = "港股" if code.endswith(".HK") else str(holding.get("industry") or industries.get(code) or "未知")
            bucket = portfolio_industries.setdefault(industry, {"weight": 0.0, "weighted_return": 0.0, "return_weight": 0.0})
            bucket["weight"] += weight
            stock_return = stock_returns.get(code)
            if stock_return is not None:
                bucket["weighted_return"] += weight * stock_return
                bucket["return_weight"] += weight
                return_weight += weight

        for bucket in portfolio_industries.values():
            covered_weight = bucket.pop("return_weight")
            weighted_return = bucket.pop("weighted_return")
            bucket["return"] = weighted_return / covered_weight if covered_weight > 0 else None

        benchmark_industries: Dict[str, Dict[str, float]] = {}
        benchmark_total_weight = 0.0
        benchmark_return_weight = 0.0
        contract_weights = {
            self._contract_component_asset(component, benchmark_code):
            (self._number(component.get("weight")) or 0) / 100.0
            for component in contract_components
        }
        cross_market_ready = bool(
            contract_composite_return is not None
            and contract_component_returns
            and all(
                str(component.get("code") or "").upper() in contract_component_returns
                for component in contract_components
            )
        )
        mainland_weight = contract_weights.get("mainland_equity", 1.0) if cross_market_ready else 1.0
        for row in benchmark_weight_rows:
            code = str(row.get("con_code") or "")
            weight = (self._number(row.get("weight")) or 0) / 100.0 * mainland_weight
            if not code or weight <= 0:
                continue
            benchmark_total_weight += weight
            stock_return = stock_returns.get(code)
            if stock_return is None:
                continue
            benchmark_return_weight += weight
            industry = industries.get(code) or ("港股-行业未知" if code.endswith(".HK") else "未知")
            bucket = benchmark_industries.setdefault(industry, {"weight": 0.0, "weighted_return": 0.0})
            bucket["weight"] += weight
            bucket["weighted_return"] += weight * stock_return

        if cross_market_ready:
            for component in contract_components:
                asset = self._contract_component_asset(component, benchmark_code)
                if asset == "mainland_equity":
                    continue
                code = str(component.get("code") or "").upper()
                weight = (self._number(component.get("weight")) or 0) / 100.0
                component_return = contract_component_returns.get(code)
                if weight <= 0:
                    continue
                if asset == "hong_kong_equity" and hsi_snapshot:
                    published_weight = 0.0
                    for constituent in hsi_snapshot.get("constituents") or []:
                        constituent_weight = self._number(constituent.get("weight"))
                        constituent_code = str(constituent.get("constituent_code") or "")
                        if constituent_weight is None or constituent_weight <= 0 or not constituent_code:
                            continue
                        scaled_weight = weight * constituent_weight
                        published_weight += scaled_weight
                        benchmark_total_weight += scaled_weight
                        constituent_return = hsi_constituent_returns.get(constituent_code)
                        if constituent_return is None:
                            continue
                        benchmark_return_weight += scaled_weight
                        industry = str(constituent.get("industry") or "港股-行业未知")
                        bucket = benchmark_industries.setdefault(
                            industry,
                            {"weight": 0.0, "weighted_return": 0.0},
                        )
                        bucket["weight"] += scaled_weight
                        bucket["weighted_return"] += scaled_weight * constituent_return
                    unpublished_weight = max(0.0, weight - published_weight)
                    if unpublished_weight > 0:
                        benchmark_total_weight += unpublished_weight
                        if component_return is not None:
                            benchmark_return_weight += unpublished_weight
                            bucket = benchmark_industries.setdefault(
                                "港股-其他成分",
                                {"weight": 0.0, "weighted_return": 0.0},
                            )
                            bucket["weight"] += unpublished_weight
                            bucket["weighted_return"] += unpublished_weight * component_return
                    continue
                benchmark_total_weight += weight
                if component_return is None:
                    continue
                benchmark_return_weight += weight
                industry = self._contract_component_bucket(component, benchmark_code)
                bucket = benchmark_industries.setdefault(industry, {"weight": 0.0, "weighted_return": 0.0})
                bucket["weight"] += weight
                bucket["weighted_return"] += weight * component_return

        for bucket in benchmark_industries.values():
            weight = bucket["weight"]
            weighted_return = bucket.pop("weighted_return")
            bucket["return"] = weighted_return / weight if weight > 0 else None

        portfolio_coverage = min(disclosed_weight, 1.0)
        benchmark_coverage = benchmark_return_weight / benchmark_total_weight if benchmark_total_weight > 0 else 0.0
        holding_return_coverage = return_weight / disclosed_weight if disclosed_weight > 0 else 0.0
        attribution = BrinsonAttributor().calculate_from_industry_inputs(
            portfolio_industries=portfolio_industries,
            benchmark_industries=benchmark_industries,
            fund_return=fund_return,
            benchmark_return=active_benchmark_return,
            portfolio_coverage=portfolio_coverage,
            benchmark_coverage=benchmark_coverage,
            return_coverage=holding_return_coverage,
        )
        missing_items = list(attribution.get("missing_items") or [])
        if benchmark_hong_kong_codes and not cross_market_ready:
            covered_hong_kong = len(benchmark_hong_kong_codes.intersection(hong_kong_returns))
            missing_items.append(
                f"基准包含 {len(benchmark_hong_kong_codes)} 只港股成分，区间收益覆盖 "
                f"{covered_hong_kong}/{len(benchmark_hong_kong_codes)}；"
                "港股收益使用未复权收盘价，尚未计入现金股息，缺少历史行业分类的成分归入“港股-行业未知”。"
            )
        if cross_market_ready:
            hong_kong_return_note = (
                "港股持仓收益来自腾讯证券公开日K线的未复权收盘价，尚未计入现金股息；"
                if hong_kong_return_source == "tencent.hk.fqkline"
                else "港股持仓收益来自未复权收盘价，尚未计入现金股息；"
                if hong_kong_return_source
                else "港股持仓区间行情尚未取得；"
            )
            if hsi_snapshot:
                published = sum(
                    float(item.get("weight") or 0)
                    for item in hsi_snapshot.get("constituents") or []
                )
                missing_items.append(
                    "主动收益及基准资产权重已按合同固定权重复合基准计算；A股使用指数成分行业，"
                    f"港股使用 {hsi_snapshot.get('as_of_date')} 恒生指数官方成分快照。"
                    f"官方事实表公布权重覆盖 {published:.1%}，其余成分归入“港股-其他成分”。"
                    f"{hong_kong_return_note}"
                )
            else:
                missing_items.append(
                    "主动收益及基准资产权重已按合同固定权重复合基准计算；A股使用指数成分行业，"
                    "港股与债券先按资产桶归因。"
                    f"{hong_kong_return_note}"
                    "当前没有区间开始日前的恒生指数成分权重快照，不使用事后权重倒推历史归因。"
                )
        elif contract_components and contract_composite_return is not None:
            missing_items.append("合同复合基准收益可用，但成分收益未完整对齐，行业效应暂只使用单一权益指数。")
        elif contract_components:
            missing_items.append("合同复合基准成分序列不足，本次只能使用单一权益指数作为行业参照。")
        elif benchmark_source == "fund_declared_benchmark_equity_component":
            weight = benchmark_detail.get("declared_weight")
            weight_text = f"{float(weight):.0%}" if weight is not None else "部分"
            if len(equity_components) >= 2:
                missing_items.append(
                    f"基金合同复合基准中权益指数合计权重为 {weight_text}；"
                    "本次已按合同权重合并多个权益指数的真实收益与成分行业，"
                    "基金整体主动收益仍包含非权益资产和未披露持仓影响。"
                )
            else:
                missing_items.append(
                    f"基金合同复合基准中权益指数权重为 {weight_text}；"
                    "本次仅以该指数作为权益行业参照，基金整体主动收益仍包含非权益资产和未披露持仓影响。"
                )
        return {
            "method": "brinson_fachler",
            "status": "partial_evidence" if missing_items and attribution.get("status") == "ok" else attribution.get("status", "insufficient_evidence"),
            "source": (
                "tushare.fund_portfolio+contract_composite+index_weight+daily+adj_factor+"
                f"{hong_kong_return_source}+fund_nav"
                if cross_market_ready and hong_kong_return_source and not hsi_snapshot
                else "tushare.fund_portfolio+contract_composite+index_weight+daily+adj_factor+"
                f"{hsi_return_source or hong_kong_return_source}+hang_seng_indexes.official+fund_nav"
                if cross_market_ready and hsi_snapshot
                else "tushare.fund_portfolio+contract_composite+index_weight+daily+adj_factor+fund_nav"
                if contract_composite_return is not None
                else "tushare.fund_portfolio+index_weight+daily+adj_factor+"
                f"{hong_kong_return_source}+fund_nav"
                if benchmark_hong_kong_codes and hong_kong_return_source
                else "tushare.fund_portfolio+index_weight+daily+adj_factor+fund_nav"
            ),
            "benchmark": benchmark_code,
            "benchmark_source": benchmark_source,
            "benchmark_detail": benchmark_detail,
            "period": {
                "quarter": attribution_quarter,
                "start": first_trade,
                "end": last_trade,
                "holding_snapshot_quarter": holding_quarter,
                "benchmark_weight_date": selected_weight_date,
                "benchmark_weight_dates": selected_weight_dates,
                "hong_kong_benchmark_weight_date": hsi_snapshot.get("as_of_date") if hsi_snapshot else None,
            },
            "returns": {
                "fund": round(fund_return, 6),
                "benchmark": round(active_benchmark_return, 6),
                "active": round(fund_return - active_benchmark_return, 6),
                "benchmark_basis": "contract_composite" if contract_composite_return is not None else "industry_reference_index",
            },
            "effects": [
                {"name": "allocation", "label": "行业配置效应", "value": attribution.get("allocation_effect")},
                {"name": "selection", "label": "行业内选择效应", "value": attribution.get("selection_effect")},
                {"name": "interaction", "label": "交互效应", "value": attribution.get("interaction_effect")},
                {"name": "residual", "label": "未披露持仓与残差", "value": attribution.get("residual")},
            ],
            "industry_detail": attribution.get("industry_details") or [],
            "coverage": attribution.get("coverage") or {},
            "component_evidence": {
                "hong_kong": {
                    "status": (
                        "point_in_time_snapshot"
                        if hsi_snapshot
                        else "constituent_returns"
                        if benchmark_hong_kong_codes and hong_kong_return_source
                        else "unavailable"
                        if benchmark_hong_kong_codes
                        else "aggregate_only"
                    ),
                    "as_of_date": hsi_snapshot.get("as_of_date") if hsi_snapshot else None,
                    "source": hsi_snapshot.get("source") if hsi_snapshot else hong_kong_return_source,
                    "constituent_count": len(benchmark_hong_kong_codes),
                    "return_coverage": (
                        round(len(benchmark_hong_kong_codes.intersection(hong_kong_returns)) / len(benchmark_hong_kong_codes), 6)
                        if benchmark_hong_kong_codes
                        else None
                    ),
                },
            },
            "missing_items": missing_items,
        }

    def _contract_component_returns(
        self,
        data_service: Any,
        components: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> Dict[str, float]:
        component_values: List[Tuple[str, Dict[str, float]]] = []
        for component in components:
            code = str(component.get("code") or "").strip().upper()
            if not code:
                return {}
            try:
                series = data_service.get_benchmark_nav(code, start_date, end_date)
            except Exception:
                return {}
            values = {
                str(item.get("date") or item.get("trade_date") or "")[:10]: float(value)
                for item in series
                if (value := self._number(item.get("nav") or item.get("close"))) is not None and value > 0
            }
            if len(values) < 2:
                return {}
            component_values.append((code, values))

        common_dates = sorted(set.intersection(*(set(values) for _, values in component_values)))
        if len(common_dates) < 2:
            return {}
        first_date = common_dates[0]
        last_date = common_dates[-1]
        return {
            code: values[last_date] / values[first_date] - 1
            for code, values in component_values
            if values[first_date] > 0
        }

    def _hong_kong_stock_returns(
        self,
        data_service: Any,
        pro: Any,
        stock_codes: List[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        if hasattr(data_service, "get_hong_kong_stock_returns"):
            try:
                evidence = data_service.get_hong_kong_stock_returns(stock_codes, start_date, end_date) or {}
                if isinstance(evidence, dict) and "returns" in evidence:
                    return evidence
            except Exception:
                pass
        returns: Dict[str, float] = {}
        for code in sorted(set(stock_codes)):
            if not code.endswith(".HK"):
                continue
            try:
                frame = pro.hk_daily(
                    ts_code=code,
                    start_date=start_date,
                    end_date=end_date,
                    fields="ts_code,trade_date,close",
                )
            except Exception:
                continue
            stock_return = self._frame_return(frame, ("close",), "trade_date")
            if stock_return is not None:
                returns[code] = stock_return
        return {
            "returns": returns,
            "source": "tushare.hk_daily" if returns else None,
            "adjustment": "unadjusted_close",
        }

    @staticmethod
    def _contract_component_asset(component: Dict[str, Any], benchmark_code: str) -> str:
        asset = str(component.get("asset") or "")
        if asset:
            return asset
        code = str(component.get("code") or "").upper()
        if code == str(benchmark_code or "").upper():
            return "mainland_equity"
        if code == "HSI":
            return "hong_kong_equity"
        if code == "H11001.CSI":
            return "fixed_income"
        return "other"

    @classmethod
    def _contract_component_bucket(cls, component: Dict[str, Any], benchmark_code: str) -> str:
        asset = cls._contract_component_asset(component, benchmark_code)
        if asset == "hong_kong_equity":
            return "港股"
        if asset == "fixed_income":
            return "固定收益"
        return str(component.get("name") or component.get("code") or "其他资产")

    def _adjusted_stock_returns(self, start_prices: Any, end_prices: Any, start_factors: Any, end_factors: Any) -> Dict[str, float]:
        def values(frame: Any, field: str) -> Dict[str, float]:
            if frame is None or frame.empty:
                return {}
            return {
                str(row["ts_code"]): float(row[field])
                for _, row in frame.iterrows()
                if row.get("ts_code") and self._number(row.get(field)) is not None
            }

        start_close = values(start_prices, "close")
        end_close = values(end_prices, "close")
        start_factor = values(start_factors, "adj_factor")
        end_factor = values(end_factors, "adj_factor")
        returns = {}
        for code in set(start_close) & set(end_close):
            start_value = start_close[code] * start_factor.get(code, 1.0)
            end_value = end_close[code] * end_factor.get(code, 1.0)
            if start_value > 0:
                returns[code] = end_value / start_value - 1
        return returns

    def _frame_return(self, frame: Any, value_columns: Tuple[str, ...], date_column: str) -> Optional[float]:
        if frame is None or frame.empty:
            return None
        frame = frame.sort_values(date_column)
        for column in value_columns:
            if column not in frame.columns:
                continue
            values = frame[column].dropna()
            if len(values) >= 2 and float(values.iloc[0]) > 0:
                return float(values.iloc[-1]) / float(values.iloc[0]) - 1
        return None

    def _safe_analysis(self, call, message: str) -> Dict[str, Any]:
        try:
            return call()
        except Exception as exc:
            return {
                "status": "insufficient_evidence",
                "source": "evidence_gate",
                "missing_items": [f"{message}：{exc.__class__.__name__}"],
            }

    def _aggregate_status(self, barra_status: str, brinson_status: str, nav_status: str) -> str:
        formal_statuses = {barra_status, brinson_status}
        if formal_statuses == {"not_applicable"}:
            return "not_applicable"
        if formal_statuses == {"ok"}:
            return "ok"
        if any(item in {"ok", "partial_evidence"} for item in formal_statuses) or nav_status == "ok":
            return "partial_evidence"
        return "insufficient_evidence"

    @staticmethod
    def _equity_attribution_applicable(fund: Dict[str, Any]) -> bool:
        fund_type = str(fund.get("type") or "").lower()
        return not any(token in fund_type for token in ["money", "货币", "bond", "债"])

    def _missing_brinson(
        self,
        benchmark_code: Optional[str],
        attribution_quarter: str,
        holding_quarter: str,
        missing_items: List[str],
        status: str = "insufficient_evidence",
    ) -> Dict[str, Any]:
        return {
            "method": "brinson_fachler",
            "status": status,
            "source": "evidence_gate",
            "benchmark": benchmark_code,
            "period": {
                "quarter": attribution_quarter,
                "holding_snapshot_quarter": holding_quarter,
            },
            "returns": {"fund": None, "benchmark": None, "active": None},
            "effects": [],
            "industry_detail": [],
            "coverage": {},
            "missing_items": missing_items,
        }

    def _resolve_benchmark(
        self,
        benchmark: Optional[str],
        classification_context: Dict[str, Any],
    ) -> Tuple[Optional[str], str]:
        value = str(benchmark or "").strip().upper()
        if not value:
            mapping = classification_context.get("benchmark_mapping") or {}
            value = str(mapping.get("benchmark_code") or "").strip().upper()
            source = "fund_classification_catalog" if value else "missing_classification_benchmark"
        else:
            source = "user_override"
        if re.fullmatch(r"\d{6}", value):
            suffix = ".SZ" if value.startswith("399") else ".SH"
            value = f"{value}{suffix}"
        return (value or None), source

    def _resolve_attribution_benchmark(
        self,
        benchmark: Optional[str],
        classification_context: Dict[str, Any],
        fund: Dict[str, Any],
    ) -> Tuple[Optional[str], str, Dict[str, Any]]:
        code, source = self._resolve_benchmark(benchmark, classification_context)
        if benchmark:
            return code, source, {
                "role": "user_override",
                "benchmark_code": code,
                "benchmark_name": code,
            }
        if code and re.fullmatch(r"[0-9A-Z]{6,12}\.(SH|SZ|CSI)", code):
            mapping = classification_context.get("benchmark_mapping") or {}
            return code, source, {
                "role": "classification_benchmark",
                "benchmark_code": code,
                "benchmark_name": mapping.get("benchmark_name") or classification_context.get("primary_benchmark") or code,
                "benchmark_type": mapping.get("benchmark_type"),
                "confidence": mapping.get("confidence"),
            }

        raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
        universe = raw_data.get("universe") if isinstance(raw_data.get("universe"), dict) else {}
        info = raw_data.get("info") if isinstance(raw_data.get("info"), dict) else {}
        declared_benchmark = (
            universe.get("benchmark")
            or info.get("benchmark")
            or fund.get("benchmark")
            or ""
        )
        from services.fund_classification_catalog import FundClassificationCatalog

        resolved = FundClassificationCatalog.resolve_declared_equity_benchmark(str(declared_benchmark))
        if resolved:
            mapping = classification_context.get("benchmark_mapping") or {}
            evidence_refs = mapping.get("evidence_refs") if isinstance(mapping.get("evidence_refs"), dict) else {}
            components = evidence_refs.get("benchmarkComponents") if isinstance(evidence_refs, dict) else None
            detail = {**resolved, "role": "equity_component_reference"}
            if mapping.get("benchmark_type") == "contract_composite_benchmark" and isinstance(components, list):
                detail.update({
                    "role": "equity_component_reference_with_contract_composite_return",
                    "contract_composite_code": mapping.get("benchmark_code"),
                    "contract_composite_name": mapping.get("benchmark_name"),
                    "contract_components": components,
                })
            return (
                str(resolved["benchmark_code"]),
                "fund_declared_benchmark_equity_component",
                detail,
            )
        return None, "missing_verifiable_attribution_benchmark", {
            "role": "unavailable",
            "classification_benchmark": code,
            "declared_benchmark": declared_benchmark or None,
        }

    def _get_classification_adapter(self):
        if self._classification_adapter is None:
            from repositories import get_fund_classification_repo

            self._classification_adapter = get_fund_classification_repo()
        return self._classification_adapter

    def _normalize_quarter(self, quarter: Optional[str]) -> Optional[str]:
        value = str(quarter or "").strip().upper()
        return value if re.fullmatch(r"\d{4}Q[1-4]", value) else None

    def _latest_completed_quarter(self) -> str:
        now = datetime.now()
        current_quarter = (now.month - 1) // 3 + 1
        if current_quarter == 1:
            return f"{now.year - 1}Q4"
        return f"{now.year}Q{current_quarter - 1}"

    def _previous_quarter(self, quarter: str) -> str:
        year = int(quarter[:4])
        number = int(quarter[-1])
        return f"{year - 1}Q4" if number == 1 else f"{year}Q{number - 1}"

    def _quarter_dates(self, quarter: str) -> Tuple[str, str]:
        year = int(quarter[:4])
        number = int(quarter[-1])
        starts = {1: "0101", 2: "0401", 3: "0701", 4: "1001"}
        ends = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
        return f"{year}{starts[number]}", f"{year}{ends[number]}"

    def _barra_factor_names(self) -> set:
        from lib.barra.factor_calculation import BARRA_FACTORS

        return set(BARRA_FACTORS)

    def _number(self, value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if number == number else None
        except (TypeError, ValueError):
            return None

    def _fund_nav_weight(self, holding: Dict[str, Any]) -> Optional[float]:
        return fund_nav_weight(holding)
