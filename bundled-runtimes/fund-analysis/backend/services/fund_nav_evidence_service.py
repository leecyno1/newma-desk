"""基金净值证据 Module。

把货币基金短周期收益派生、标准化基准映射和基准净值对齐收口到
一个可审计 Interface；没有真实基准数据时不生成相对指标输入。
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


class FundNavEvidenceService:
    """从已取得的净值序列中生成评价事实。"""

    MONEY_MARKET_SOURCE = "derived:tushare.fund_nav.adj_nav"

    def validate_nav_series(
        self,
        nav_series: List[Dict[str, Any]],
        fund_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """阻断类型冲突或跳点污染的净值序列，不让异常事实进入评价。"""
        normalized_type = str(fund_type or "").strip().lower()
        explicitly_money_market = "货币" in normalized_type or "money" in normalized_type
        explicitly_non_money = bool(normalized_type) and not explicitly_money_market

        selected_points = []
        unit_values = []
        adjusted_values = []
        reported_accum_values = []
        sources = set()
        for item in nav_series:
            item_date = self._parse_date(item.get("date") or item.get("trade_date"))
            selected_nav = self._positive_number(item.get("accum_nav") or item.get("nav") or item.get("unit_nav"))
            if item_date is not None and selected_nav is not None:
                selected_points.append((item_date, selected_nav))
            unit_nav = self._positive_number(item.get("unit_nav") or item.get("nav"))
            adjusted_nav = self._positive_number(item.get("adj_nav"))
            reported_accum = self._positive_number(item.get("reported_accum_nav"))
            if unit_nav is not None:
                unit_values.append(unit_nav)
            if adjusted_nav is not None:
                adjusted_values.append(adjusted_nav)
            reported_accum_values.append(reported_accum)
            if item.get("metric_nav_source"):
                sources.add(str(item.get("metric_nav_source")))

        selected_points.sort(key=lambda point: point[0])
        daily_returns = [
            current[1] / previous[1] - 1.0
            for previous, current in zip(selected_points, selected_points[1:])
            if previous[1] > 0
        ]
        extreme_returns = [value for value in daily_returns if abs(value) > 0.30]
        money_market_shape = (
            bool(adjusted_values)
            and adjusted_values[-1] > 100.0
            and bool(unit_values)
            and sum(1 for value in unit_values if 0.9 <= value <= 1.1) / len(unit_values) >= 0.8
            and sum(1 for value in reported_accum_values if value is None) / len(reported_accum_values) >= 0.8
        )

        issues = []
        if explicitly_non_money and money_market_shape:
            issues.append("nav_shape_conflicts_with_declared_fund_type")
        if extreme_returns:
            issues.append("extreme_daily_nav_return")
        return {
            "status": "invalid" if issues else "valid",
            "issues": issues,
            "observations": len(selected_points),
            "metric_nav_sources": sorted(sources),
            "max_absolute_daily_return": round(max((abs(value) for value in daily_returns), default=0.0), 8),
            "money_market_shape": money_market_shape,
            "declared_money_market": explicitly_money_market,
        }

    def derive_money_market_facts(
        self,
        nav_series: List[Dict[str, Any]],
        fund_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从货币基金累计收益序列派生七日年化与最新万份收益。"""
        points = self._money_market_points(nav_series, fund_type)
        if len(points) < 4:
            return {}

        end_date, end_value, _ = points[-1]
        target_date = end_date - timedelta(days=7)
        candidates = [point for point in points[:-1] if point[0] <= target_date + timedelta(days=2)]
        if not candidates:
            return {}
        start_date, start_value, _ = min(
            candidates,
            key=lambda point: abs((point[0] - target_date).days),
        )
        span_days = (end_date - start_date).days
        if span_days < 5 or span_days > 9 or start_value <= 0 or end_value <= 0:
            return {}

        total_return = end_value / start_value - 1.0
        if total_return <= -1.0 or abs(total_return) > 0.10:
            return {}
        annualized_yield = (1.0 + total_return) ** (365.0 / span_days) - 1.0
        window_observations = sum(1 for item_date, _, _ in points if start_date <= item_date <= end_date)

        result: Dict[str, Any] = {
            "seven_day_annualized_yield": round(annualized_yield, 8),
            "seven_day_yield_source": self.MONEY_MARKET_SOURCE,
            "seven_day_yield_as_of": end_date.isoformat(),
            "seven_day_yield_window_days": span_days,
            "seven_day_yield_observations": window_observations,
        }
        previous_date, previous_value, _ = points[-2]
        if 0 < (end_date - previous_date).days <= 3:
            result["income_per_10000"] = round(end_value - previous_value, 6)
            result["income_per_10000_as_of"] = end_date.isoformat()
        return result

    def attach_benchmark_nav(
        self,
        nav_series: List[Dict[str, Any]],
        benchmark_series: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], int]:
        """仅按真实共同日期对齐基准净值，不前值填充、不伪造覆盖率。"""
        benchmark_by_date = {
            normalized_date: value
            for item in benchmark_series
            if (normalized_date := self._date_text(item.get("date") or item.get("trade_date")))
            if (value := self._positive_number(item.get("nav") or item.get("close"))) is not None
        }
        enriched = []
        matched = 0
        for item in nav_series:
            copied = dict(item)
            item_date = self._date_text(item.get("date") or item.get("trade_date"))
            benchmark_nav = benchmark_by_date.get(item_date)
            if benchmark_nav is not None:
                copied["benchmark_nav"] = benchmark_nav
                matched += 1
            else:
                copied.pop("benchmark_nav", None)
            enriched.append(copied)
        return enriched, matched

    def derive_benchmark_rate_facts(
        self,
        benchmark_code: str,
        rate_series: List[Dict[str, Any]],
        as_of_date: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """提取最新利率型基准事实；禁止把利率水平伪装成基准净值。"""
        evaluation_date = self._parse_date(as_of_date)
        points = []
        for item in rate_series:
            item_date = self._parse_date(item.get("date") or item.get("trade_date"))
            annualized_rate = self._number(item.get("annualized_rate"))
            if item_date is None or annualized_rate is None or annualized_rate < 0 or annualized_rate > 1:
                continue
            if evaluation_date is not None and item_date > evaluation_date:
                continue
            points.append((item_date, annualized_rate, item.get("source")))
        if not points:
            return {}
        points.sort(key=lambda point: point[0])
        latest_date, latest_rate, latest_source = points[-1]
        return {
            "benchmark_annualized_rate": round(latest_rate, 8),
            "benchmark_rate_code": str(benchmark_code or "").strip().upper(),
            "benchmark_rate_source": latest_source or "market_data.rate_series",
            "benchmark_rate_as_of": latest_date.isoformat(),
            "benchmark_rate_observations": len(points),
        }

    def _money_market_points(
        self,
        nav_series: List[Dict[str, Any]],
        fund_type: Optional[str],
    ) -> List[Tuple[date, float, Optional[float]]]:
        points = []
        reported_accum_values = []
        unit_values = []
        for item in nav_series:
            item_date = self._parse_date(item.get("date") or item.get("trade_date"))
            cumulative = self._positive_number(item.get("adj_nav") or item.get("accum_nav"))
            if item_date is None or cumulative is None:
                continue
            reported_accum = self._number(item.get("reported_accum_nav"))
            unit_nav = self._number(item.get("unit_nav") or item.get("nav"))
            points.append((item_date, cumulative, unit_nav))
            reported_accum_values.append(reported_accum)
            if unit_nav is not None:
                unit_values.append(unit_nav)
        points.sort(key=lambda point: point[0])
        if not points:
            return []

        normalized_type = str(fund_type or "").strip().lower()
        explicitly_money_market = "货币" in normalized_type or "money" in normalized_type
        source_shape_is_money_market = (
            points[-1][1] > 100.0
            and bool(unit_values)
            and sum(1 for value in unit_values if 0.9 <= value <= 1.1) / len(unit_values) >= 0.8
            and sum(1 for value in reported_accum_values if value is None) / len(reported_accum_values) >= 0.8
        )
        type_is_unspecified = not normalized_type
        return points if explicitly_money_market or (type_is_unspecified and source_shape_is_money_market) else []

    @staticmethod
    def _date_text(value: Any) -> Optional[str]:
        parsed = FundNavEvidenceService._parse_date(value)
        return parsed.isoformat() if parsed else None

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if len(text) == 8 and text.isdigit():
            text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        try:
            return datetime.fromisoformat(text[:10]).date()
        except ValueError:
            return None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed != parsed or parsed in {float("inf"), float("-inf")}:
            return None
        return parsed

    @classmethod
    def _positive_number(cls, value: Any) -> Optional[float]:
        parsed = cls._number(value)
        return parsed if parsed is not None and parsed > 0 else None


class FundNavDataEnrichmentService:
    """组合标准化基准映射、Tushare 基准 Adapter 和净值证据派生。"""

    def __init__(
        self,
        market_data_adapter: Any,
        classification_adapter: Optional[Any] = None,
        evidence_service: Optional[FundNavEvidenceService] = None,
    ):
        self.market_data_adapter = market_data_adapter
        self._classification_adapter = classification_adapter
        self.evidence_service = evidence_service or FundNavEvidenceService()

    def enrich(
        self,
        wind_code: str,
        fund_type: Optional[str],
        nav_series: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        context = self._classification_context(wind_code)
        benchmark_mapping = context.get("benchmark_mapping") or {}
        benchmark_code = str(benchmark_mapping.get("benchmark_code") or "").strip() or None
        evidence_refs = benchmark_mapping.get("evidence_refs") or {}
        benchmark_components = (
            evidence_refs.get("benchmarkComponents")
            if isinstance(evidence_refs, dict)
            else None
        )
        performance_benchmark_type = None
        performance_benchmark_components = None
        if benchmark_mapping.get("benchmark_type") == "contract_composite_benchmark":
            performance_benchmark_type = "contract_composite_benchmark"
            performance_benchmark_components = benchmark_components
        elif benchmark_mapping.get("benchmark_type") == "declared_allocation_bucket":
            declared_benchmark = (
                evidence_refs.get("declaredBenchmark")
                if isinstance(evidence_refs, dict)
                else None
            )
            if not benchmark_components and declared_benchmark:
                from services.fund_classification_ingestion_service import FundClassificationIngestionService

                benchmark_components = FundClassificationIngestionService.resolve_contract_benchmark_components(
                    declared_benchmark
                )
            if benchmark_components:
                performance_benchmark_type = "contract_composite_benchmark"
                performance_benchmark_components = benchmark_components
        enriched_series = list(nav_series)
        nav_validation = self.evidence_service.validate_nav_series(enriched_series, fund_type=fund_type)
        if nav_validation.get("status") != "valid":
            return {
                "nav_series": enriched_series,
                "performance_facts": {},
                "benchmark_code": benchmark_code,
                "benchmark_mapping": benchmark_mapping or None,
                "benchmark_data_status": "not_checked_invalid_nav",
                "benchmark_data_kind": None,
                "benchmark_observations": 0,
                "benchmark_nav_observations": 0,
                "benchmark_rate_observations": 0,
                "benchmark_source": None,
                "performance_benchmark_type": performance_benchmark_type,
                "performance_benchmark_components": performance_benchmark_components,
                "money_market_metric_status": "invalid_nav",
                "nav_data_status": "invalid",
                "nav_validation": nav_validation,
            }
        benchmark_points = 0
        benchmark_rate_points = 0
        benchmark_data_kind = None
        benchmark_source = None
        benchmark_status = "mapping_missing"
        benchmark_rate_facts: Dict[str, Any] = {}
        performance_facts = self.evidence_service.derive_money_market_facts(
            enriched_series,
            fund_type=fund_type,
        )
        rate_alignment_as_of = performance_facts.get("seven_day_yield_as_of")
        if not rate_alignment_as_of:
            available_dates = [
                self.evidence_service._date_text(item.get("date") or item.get("trade_date"))
                for item in nav_series
            ]
            rate_alignment_as_of = max((item for item in available_dates if item), default=None)

        if benchmark_code:
            benchmark_status = "data_unavailable"
            if performance_benchmark_type == "contract_composite_benchmark":
                benchmark_series = self._contract_composite_series(
                    performance_benchmark_components or [],
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                try:
                    benchmark_series = self.market_data_adapter.get_benchmark_nav(
                        benchmark_code,
                        start_date=start_date,
                        end_date=end_date,
                    )
                except Exception:
                    benchmark_series = []
            enriched_series, benchmark_points = self.evidence_service.attach_benchmark_nav(
                nav_series,
                benchmark_series,
            )
            if benchmark_points >= 2:
                benchmark_status = "available"
                benchmark_data_kind = "nav"
                benchmark_source = (
                    benchmark_series[0].get("source")
                    if benchmark_series
                    else None
                )
            elif hasattr(self.market_data_adapter, "get_benchmark_rate"):
                try:
                    rate_series = self.market_data_adapter.get_benchmark_rate(
                        benchmark_code,
                        start_date=start_date,
                        end_date=end_date,
                    )
                except Exception:
                    rate_series = []
                benchmark_rate_facts = self.evidence_service.derive_benchmark_rate_facts(
                    benchmark_code,
                    rate_series,
                    as_of_date=rate_alignment_as_of,
                )
                benchmark_rate_points = int(benchmark_rate_facts.get("benchmark_rate_observations") or 0)
                if benchmark_rate_facts:
                    benchmark_status = "available"
                    benchmark_data_kind = "annualized_rate"
                    benchmark_source = benchmark_rate_facts.get("benchmark_rate_source")

        performance_facts.update(benchmark_rate_facts)
        if (
            performance_facts.get("seven_day_annualized_yield") is not None
            and performance_facts.get("benchmark_annualized_rate") is not None
        ):
            performance_facts["benchmark_yield_spread"] = round(
                performance_facts["seven_day_annualized_yield"]
                - performance_facts["benchmark_annualized_rate"],
                8,
            )
        return {
            "nav_series": enriched_series,
            "performance_facts": performance_facts,
            "benchmark_code": benchmark_code,
            "benchmark_mapping": benchmark_mapping or None,
            "benchmark_data_status": benchmark_status,
            "benchmark_data_kind": benchmark_data_kind,
            "benchmark_observations": benchmark_points or benchmark_rate_points,
            "benchmark_nav_observations": benchmark_points,
            "benchmark_rate_observations": benchmark_rate_points,
            "benchmark_source": benchmark_source,
            "performance_benchmark_type": performance_benchmark_type,
            "performance_benchmark_components": performance_benchmark_components,
            "performance_benchmark_source": benchmark_source if performance_benchmark_type else None,
            "money_market_metric_status": "available" if performance_facts else "not_available",
            "nav_data_status": "valid",
            "nav_validation": nav_validation,
        }

    def _contract_composite_series(
        self,
        components: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """按合同固定权重构建日频再平衡复合基准，只使用所有成分共同交易日。"""
        if len(components) < 2:
            return []
        weights = [self.evidence_service._number(item.get("weight")) for item in components]
        if any(weight is None or weight <= 0 for weight in weights):
            return []
        if abs(sum(weights) - 100) > 0.001:
            return []

        component_maps = []
        for component in components:
            code = str(component.get("code") or "").strip().upper()
            if not code:
                return []
            try:
                series = self.market_data_adapter.get_benchmark_nav(
                    code,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                return []
            values = {
                item_date: value
                for item in series
                if (item_date := self.evidence_service._date_text(item.get("date") or item.get("trade_date")))
                if (value := self.evidence_service._positive_number(item.get("nav") or item.get("close"))) is not None
            }
            if len(values) < 2:
                return []
            component_maps.append(values)

        common_dates = sorted(set.intersection(*(set(values) for values in component_maps)))
        if len(common_dates) < 2:
            return []
        composite_nav = 1.0
        result = [{
            "date": common_dates[0],
            "nav": composite_nav,
            "source": "derived:tushare.contract_composite.daily_rebalanced_v1",
        }]
        previous_date = common_dates[0]
        for item_date in common_dates[1:]:
            composite_return = sum(
                (weight / 100.0) * (values[item_date] / values[previous_date] - 1.0)
                for weight, values in zip(weights, component_maps)
            )
            if composite_return <= -1:
                return []
            composite_nav *= 1.0 + composite_return
            result.append({
                "date": item_date,
                "nav": composite_nav,
                "source": "derived:tushare.contract_composite.daily_rebalanced_v1",
            })
            previous_date = item_date
        return result

    def build_contract_composite_series(
        self,
        components: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        return self._contract_composite_series(components, start_date, end_date)

    def _classification_context(self, wind_code: str) -> Dict[str, Any]:
        try:
            return self._get_classification_adapter().get_classification_context(wind_code) or {}
        except Exception:
            return {}

    def _get_classification_adapter(self):
        if self._classification_adapter is None:
            from repositories import get_fund_classification_repo

            self._classification_adapter = get_fund_classification_repo()
        return self._classification_adapter
