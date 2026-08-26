"""分类内基金评价方法 Module。"""
import math
from typing import Any, Dict, List, Optional, Tuple


class FundEvaluationMethodology:
    """集中管理类别专属证据门禁、维度、阈值和同类代理评分。"""

    METHODOLOGY_VERSION = "category_evaluation_methodology_v6"
    PEER_METHODOLOGY_VERSION = "category_peer_percentiles_v6"

    PROFILE_NAMES = {
        "active_equity": "主动权益基金评价",
        "fixed_income": "纯债基金评价",
        "fixed_income_plus": "固收增强基金评价",
        "multi_asset": "多资产配置基金评价",
        "multi_asset_equity": "偏股混合基金评价",
        "multi_asset_balanced": "平衡混合基金评价",
        "multi_asset_bond": "偏债混合基金评价",
        "fof_equity": "偏股 FOF 评价",
        "fof_balanced": "平衡 FOF 评价",
        "fof_bond": "偏债 FOF 评价",
        "qdii_equity": "QDII 主动权益基金评价",
        "qdii_bond": "QDII 债券基金评价",
        "qdii_multi_asset": "QDII 多资产基金评价",
        "qdii_index": "QDII 被动指数基金评价",
        "index_fund": "被动指数基金评价",
        "index_enhanced": "指数增强基金评价",
        "money_market": "货币基金评价",
    }

    RETURN_RISK_WEIGHTS = {
        "active_equity": {"return": 0.25, "risk": 0.25, "risk_adjusted": 0.20, "consistency": 0.15, "manager_tenure": 0.10, "data_quality": 0.05},
        "fixed_income": {"return": 0.20, "risk": 0.35, "risk_adjusted": 0.15, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.10},
        "fixed_income_plus": {"return": 0.20, "risk": 0.38, "risk_adjusted": 0.17, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.05},
        "multi_asset": {"return": 0.18, "risk": 0.35, "risk_adjusted": 0.20, "consistency": 0.12, "manager_tenure": 0.10, "data_quality": 0.05},
        "multi_asset_equity": {"return": 0.25, "risk": 0.30, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.05},
        "multi_asset_balanced": {"return": 0.20, "risk": 0.35, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.05},
        "multi_asset_bond": {"return": 0.15, "risk": 0.40, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.05},
        "fof_equity": {"return": 0.20, "risk": 0.35, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.05},
        "fof_balanced": {"return": 0.15, "risk": 0.40, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.05},
        "fof_bond": {"return": 0.12, "risk": 0.43, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.05},
        "qdii_equity": {"return": 0.25, "risk": 0.25, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.10},
        "qdii_bond": {"return": 0.15, "risk": 0.35, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.10},
        "qdii_multi_asset": {"return": 0.20, "risk": 0.30, "risk_adjusted": 0.20, "consistency": 0.10, "manager_tenure": 0.10, "data_quality": 0.10},
    }
    INDEX_WEIGHTS = {"tracking_quality": 0.55, "cost_efficiency": 0.25, "scale_liquidity": 0.10, "data_quality": 0.10}
    QDII_INDEX_WEIGHTS = {"tracking_quality": 0.60, "cost_efficiency": 0.20, "scale_liquidity": 0.10, "data_quality": 0.10}
    INDEX_ENHANCED_WEIGHTS = {"excess_return": 0.30, "active_efficiency": 0.30, "drawdown_control": 0.15, "cost_efficiency": 0.10, "scale_liquidity": 0.05, "data_quality": 0.10}
    MONEY_MARKET_WEIGHTS = {"income_competitiveness": 0.35, "capital_preservation": 0.30, "income_stability": 0.15, "scale_liquidity": 0.10, "data_quality": 0.10}
    DIMENSION_LABELS = {
        "return": "收益能力",
        "risk": "风险控制",
        "risk_adjusted": "风险调整后收益",
        "consistency": "表现稳定性",
        "manager_tenure": "经理任期",
        "tracking_quality": "跟踪质量",
        "cost_efficiency": "成本效率",
        "scale_liquidity": "规模与流动性",
        "excess_return": "超额收益",
        "active_efficiency": "主动管理效率",
        "drawdown_control": "回撤控制",
        "income_competitiveness": "收益竞争力",
        "capital_preservation": "净值稳定性",
        "income_stability": "收益稳定性",
        "data_quality": "数据质量",
    }

    PROFILES: Dict[str, Dict[str, Any]] = {
        "active_equity": {
            "return_range": (-0.10, 0.25),
            "drawdown_range": (-0.35, -0.03),
            "volatility_range": (0.35, 0.08),
        },
        "fixed_income": {
            "return_range": (0.00, 0.08),
            "drawdown_range": (-0.08, -0.005),
            "volatility_range": (0.08, 0.01),
        },
        "fixed_income_plus": {
            "return_range": (-0.02, 0.12),
            "drawdown_range": (-0.16, -0.01),
            "volatility_range": (0.16, 0.025),
        },
        "multi_asset": {
            "return_range": (-0.08, 0.18),
            "drawdown_range": (-0.30, -0.01),
            "volatility_range": (0.30, 0.03),
        },
        "multi_asset_equity": {
            "return_range": (-0.08, 0.20),
            "drawdown_range": (-0.30, -0.02),
            "volatility_range": (0.30, 0.06),
        },
        "multi_asset_balanced": {
            "return_range": (-0.05, 0.15),
            "drawdown_range": (-0.22, -0.015),
            "volatility_range": (0.22, 0.04),
        },
        "multi_asset_bond": {
            "return_range": (-0.02, 0.10),
            "drawdown_range": (-0.12, -0.005),
            "volatility_range": (0.12, 0.015),
        },
        "fof_equity": {
            "return_range": (-0.08, 0.18),
            "drawdown_range": (-0.28, -0.02),
            "volatility_range": (0.28, 0.05),
        },
        "fof_balanced": {
            "return_range": (-0.05, 0.13),
            "drawdown_range": (-0.20, -0.012),
            "volatility_range": (0.20, 0.035),
        },
        "fof_bond": {
            "return_range": (-0.02, 0.09),
            "drawdown_range": (-0.10, -0.004),
            "volatility_range": (0.10, 0.012),
        },
        "qdii_equity": {
            "return_range": (-0.15, 0.30),
            "drawdown_range": (-0.45, -0.04),
            "volatility_range": (0.45, 0.10),
        },
        "qdii_bond": {
            "return_range": (-0.05, 0.12),
            "drawdown_range": (-0.15, -0.01),
            "volatility_range": (0.15, 0.02),
        },
        "qdii_multi_asset": {
            "return_range": (-0.10, 0.20),
            "drawdown_range": (-0.30, -0.02),
            "volatility_range": (0.30, 0.05),
        },
        "index_fund": {
            "required_evidence": ["tracking_error", "tracking_difference", "expense_ratio", "aum"],
            "tracking_error_score_range": (0.03, 0.002),
            "tracking_difference_score_range": (0.03, 0.001),
            "expense_ratio_score_range": (0.018, 0.0015),
            "aum_score_range": (1.0, 100.0),
            "maximum_tracking_error": 0.10,
            "maximum_tracking_difference": 0.25,
        },
        "qdii_index": {
            "required_evidence": ["tracking_error", "tracking_difference", "expense_ratio", "aum"],
            "tracking_error_score_range": (0.06, 0.003),
            "tracking_difference_score_range": (0.04, 0.002),
            "expense_ratio_score_range": (0.025, 0.002),
            "aum_score_range": (0.5, 100.0),
            "maximum_tracking_error": 0.15,
            "maximum_tracking_difference": 0.25,
        },
        "index_enhanced": {
            "required_evidence": ["excess_return", "information_ratio", "tracking_error", "max_drawdown", "expense_ratio", "aum"],
        },
        "money_market": {
            "required_evidence": ["seven_day_annualized_yield", "annualized_return", "max_drawdown", "aum"],
        },
    }

    PEER_METRIC_CONFIGS: Dict[str, List[Dict[str, Any]]] = {
        "active_equity": [
            {"metric_name": "annualized_return", "label": "1Y 年化收益", "unit": "percent", "higher_is_better": True, "paths": [("selected", "annualized_return")], "required_for_sample": True},
            {"metric_name": "max_drawdown", "label": "1Y 最大回撤", "unit": "percent", "higher_is_better": True, "paths": [("selected", "max_drawdown")], "required_for_sample": True},
            {"metric_name": "sharpe_ratio", "label": "1Y 夏普比率", "unit": "number", "higher_is_better": True, "paths": [("selected", "sharpe_ratio")], "required_for_sample": True},
            {"metric_name": "annualized_volatility", "label": "1Y 年化波动", "unit": "percent", "higher_is_better": False, "paths": [("selected", "annualized_volatility")], "required_for_sample": False},
            {"metric_name": "calmar_ratio", "label": "1Y Calmar", "unit": "number", "higher_is_better": True, "paths": [("selected", "calmar_ratio")], "required_for_sample": False},
            {"metric_name": "positive_return_ratio", "label": "1Y 正收益占比", "unit": "percent", "higher_is_better": True, "paths": [("selected", "positive_return_ratio")], "required_for_sample": False},
            {"metric_name": "expense_ratio", "label": "基础费率", "unit": "percent", "higher_is_better": False, "paths": [("latest", "expense_ratio"), ("selected", "expense_ratio")], "valid_range": (0.0, 0.05), "required_for_sample": False},
            {"metric_name": "aum", "label": "基金规模", "unit": "cny_100m", "higher_is_better": True, "paths": [("latest", "aum"), ("selected", "aum")], "valid_range": (0.000001, 1000000.0), "required_for_sample": False},
        ],
        "fixed_income": [
            {"metric_name": "annualized_return", "label": "1Y 年化收益", "unit": "percent", "higher_is_better": True, "paths": [("selected", "annualized_return")], "required_for_sample": True},
            {"metric_name": "max_drawdown", "label": "1Y 最大回撤", "unit": "percent", "higher_is_better": True, "paths": [("selected", "max_drawdown")], "required_for_sample": True},
            {"metric_name": "sharpe_ratio", "label": "1Y 夏普比率", "unit": "number", "higher_is_better": True, "paths": [("selected", "sharpe_ratio")], "required_for_sample": True},
            {"metric_name": "annualized_volatility", "label": "1Y 年化波动", "unit": "percent", "higher_is_better": False, "paths": [("selected", "annualized_volatility")], "required_for_sample": False},
            {"metric_name": "positive_return_ratio", "label": "1Y 正收益占比", "unit": "percent", "higher_is_better": True, "paths": [("selected", "positive_return_ratio")], "required_for_sample": False},
            {"metric_name": "expense_ratio", "label": "基础费率", "unit": "percent", "higher_is_better": False, "paths": [("latest", "expense_ratio"), ("selected", "expense_ratio")], "valid_range": (0.0, 0.05), "required_for_sample": False},
            {"metric_name": "aum", "label": "基金规模", "unit": "cny_100m", "higher_is_better": True, "paths": [("latest", "aum"), ("selected", "aum")], "valid_range": (0.000001, 1000000.0), "required_for_sample": False},
        ],
        "index_fund": [
            {"metric_name": "tracking_error", "label": "1Y 跟踪误差", "unit": "percent", "higher_is_better": False, "paths": [("selected", "tracking_error")], "valid_range": (0.0, 0.10), "required_for_sample": True},
            {"metric_name": "absolute_tracking_difference", "label": "1Y 跟踪差异绝对值", "unit": "percent", "higher_is_better": False, "paths": [("selected", "tracking_difference"), ("selected", "excess_return")], "transform": "absolute", "valid_range": (0.0, 0.25), "required_for_sample": True},
            {"metric_name": "expense_ratio", "label": "基础费率", "unit": "percent", "higher_is_better": False, "paths": [("latest", "expense_ratio"), ("selected", "expense_ratio")], "valid_range": (0.0, 0.05), "required_for_sample": True},
            {"metric_name": "aum", "label": "基金规模", "unit": "cny_100m", "higher_is_better": True, "paths": [("latest", "aum"), ("selected", "aum")], "valid_range": (0.000001, 1000000.0), "required_for_sample": True},
        ],
        "index_enhanced": [
            {"metric_name": "excess_return", "label": "1Y 超额收益", "unit": "percent", "higher_is_better": True, "paths": [("selected", "excess_return"), ("selected", "tracking_difference")], "valid_range": (-0.50, 0.50), "required_for_sample": True},
            {"metric_name": "information_ratio", "label": "1Y 信息比率", "unit": "number", "higher_is_better": True, "paths": [("selected", "information_ratio")], "valid_range": (-10.0, 10.0), "required_for_sample": True},
            {"metric_name": "tracking_error", "label": "1Y 跟踪误差", "unit": "percent", "higher_is_better": False, "paths": [("selected", "tracking_error")], "valid_range": (0.0, 0.35), "required_for_sample": True},
            {"metric_name": "max_drawdown", "label": "1Y 最大回撤", "unit": "percent", "higher_is_better": True, "paths": [("selected", "max_drawdown")], "valid_range": (-0.80, 0.01), "required_for_sample": True},
            {"metric_name": "expense_ratio", "label": "基础费率", "unit": "percent", "higher_is_better": False, "paths": [("latest", "expense_ratio"), ("selected", "expense_ratio")], "valid_range": (0.0, 0.05), "required_for_sample": True},
            {"metric_name": "aum", "label": "基金规模", "unit": "cny_100m", "higher_is_better": True, "paths": [("latest", "aum"), ("selected", "aum")], "valid_range": (0.000001, 1000000.0), "required_for_sample": True},
        ],
        "money_market": [
            {"metric_name": "seven_day_annualized_yield", "label": "七日年化收益率", "unit": "percent", "higher_is_better": True, "paths": [("latest", "seven_day_annualized_yield"), ("selected", "seven_day_annualized_yield")], "valid_range": (0.0, 0.20), "required_for_sample": True},
            {"metric_name": "annualized_return", "label": "1Y 年化收益", "unit": "percent", "higher_is_better": True, "paths": [("selected", "annualized_return")], "valid_range": (-0.05, 0.20), "required_for_sample": True},
            {"metric_name": "max_drawdown", "label": "1Y 最大回撤", "unit": "percent", "higher_is_better": True, "paths": [("selected", "max_drawdown")], "valid_range": (-0.20, 0.01), "required_for_sample": True},
            {"metric_name": "aum", "label": "基金规模", "unit": "cny_100m", "higher_is_better": True, "paths": [("latest", "aum"), ("selected", "aum")], "valid_range": (0.000001, 1000000.0), "required_for_sample": True},
            {"metric_name": "benchmark_yield_spread", "label": "相对 DR007 收益利差", "unit": "percent", "higher_is_better": True, "paths": [("latest", "benchmark_yield_spread")], "required_for_sample": False},
        ],
    }
    RETURN_RISK_PROFILES = {
        "active_equity", "fixed_income", "fixed_income_plus",
        "multi_asset",
        "multi_asset_equity", "multi_asset_balanced", "multi_asset_bond",
        "fof_equity", "fof_balanced", "fof_bond",
        "qdii_equity", "qdii_bond", "qdii_multi_asset",
    }

    PEER_METRIC_CONFIGS["qdii_index"] = [dict(config) for config in PEER_METRIC_CONFIGS["index_fund"]]
    PEER_METRIC_CONFIGS["qdii_index"][0]["valid_range"] = (0.0, 0.15)

    for _profile_key in (
        "fixed_income_plus", "multi_asset", "multi_asset_equity", "multi_asset_balanced", "multi_asset_bond",
        "fof_equity", "fof_balanced", "fof_bond",
        "qdii_equity", "qdii_bond", "qdii_multi_asset",
    ):
        PEER_METRIC_CONFIGS[_profile_key] = [dict(config) for config in PEER_METRIC_CONFIGS["active_equity"]]
    del _profile_key

    def peer_metric_configs(self, profile_key: str) -> List[Dict[str, Any]]:
        """返回与类别评价方法一致的同类分位指标，不跨类别复用风险收益模板。"""
        return [dict(config) for config in self.PEER_METRIC_CONFIGS.get(profile_key, [])]

    def describe(self, profile_key: str, selected_window: str = "1y") -> Dict[str, Any]:
        """返回可供评分详情页直接展示的方法、权重、输入指标和规则。"""
        window = str(selected_window or "1y")
        dimensions = self._methodology_dimensions(profile_key, window)
        return {
            "status": "available" if dimensions else "unsupported_methodology",
            "methodology_version": self.METHODOLOGY_VERSION,
            "profile_key": profile_key,
            "profile_name": self.PROFILE_NAMES.get(profile_key, profile_key or "评价方法待确认"),
            "evaluation_window": window,
            "score_formula": "综合分 = 各维度得分 × 维度权重后求和",
            "dimensions": dimensions,
            "boundary": "评分规则只适用于当前基金类别；不同类别使用不同指标和权重，禁止跨类别直接比较。",
        }

    def evaluate(
        self,
        profile_key: str,
        metrics: Dict[str, Dict[str, float]],
        quality: Dict[str, Any],
        selected_window: str = "1y",
    ) -> Dict[str, Any]:
        window = str(selected_window or "1y")
        if profile_key not in self.PROFILES:
            return self._unavailable(
                "unsupported_methodology",
                [f"{profile_key} 专属基金评价方法尚未实现"],
                profile_key,
                window,
            )
        if profile_key in self.RETURN_RISK_PROFILES:
            return self._evaluate_return_risk(profile_key, metrics, quality, window)
        if profile_key in {"index_fund", "qdii_index"}:
            return self._evaluate_index(metrics, quality, window, profile_key=profile_key)
        if profile_key == "index_enhanced":
            return self._evaluate_index_enhanced(metrics, quality, window)
        return self._evaluate_money_market(metrics, quality, window)

    def score_peer(self, profile_key: str, metrics: Dict[str, Any]) -> Optional[float]:
        """用同一类别方法生成轻量同类代理分，不跨类别复用指标。"""
        return self.score_peer_details(profile_key, metrics).get("overall_score")

    def score_peer_details(self, profile_key: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """生成同类横比使用的可比总分和维度分，不混入经理任期等非齐备证据。"""
        if profile_key in self.RETURN_RISK_PROFILES:
            profile = self.PROFILES[profile_key]
            return_low, return_high = profile["return_range"]
            drawdown_low, drawdown_high = profile["drawdown_range"]
            volatility_high, volatility_low = profile["volatility_range"]
            pieces = [
                self._normalize(self._number(metrics.get("annualized_return")), return_low, return_high),
                self._normalize(self._drawdown(metrics.get("max_drawdown")), drawdown_low, drawdown_high),
                self._normalize(
                    self._number(metrics.get("annualized_volatility")),
                    volatility_high,
                    volatility_low,
                    higher_is_better=False,
                ),
                self._normalize(self._number(metrics.get("sharpe_ratio")), 0.0, 2.0),
                self._normalize(self._number(metrics.get("positive_return_ratio")), 0.45, 0.70),
            ]
            valid = [piece for piece in pieces if piece is not None]
            dimensions = {}
            if metrics.get("annualized_return") is not None:
                dimensions["return"] = self._dimension(
                    self._normalize(self._number(metrics.get("annualized_return")), return_low, return_high),
                    ["所选窗口年化收益"],
                )
            if metrics.get("max_drawdown") is not None or metrics.get("annualized_volatility") is not None:
                dimensions["risk"] = self._dimension(self._average([
                    self._normalize(self._drawdown(metrics.get("max_drawdown")), drawdown_low, drawdown_high),
                    self._normalize(
                        self._number(metrics.get("annualized_volatility")),
                        volatility_high,
                        volatility_low,
                        higher_is_better=False,
                    ),
                ]), ["所选窗口最大回撤与年化波动"])
            if metrics.get("sharpe_ratio") is not None or metrics.get("calmar_ratio") is not None:
                dimensions["risk_adjusted"] = self._dimension(self._average([
                    self._normalize(self._number(metrics.get("sharpe_ratio")), 0.0, 2.0),
                    self._normalize(self._number(metrics.get("calmar_ratio")), 0.0, 4.0),
                ]), ["所选窗口夏普与 Calmar"])
            if metrics.get("positive_return_ratio") is not None:
                dimensions["consistency"] = self._dimension(
                    self._normalize(self._number(metrics.get("positive_return_ratio")), 0.45, 0.70),
                    ["所选窗口正收益占比"],
                )
            return {
                "status": "ok" if len(valid) >= 2 else "insufficient_evidence",
                "overall_score": round(sum(valid) / len(valid), 2) if len(valid) >= 2 else None,
                "dimension_scores": dimensions,
                "calculation_method": f"{self.PEER_METHODOLOGY_VERSION}:{profile_key}",
            }

        if profile_key in {"index_fund", "qdii_index"}:
            result = self._evaluate_index(
                {"1y": metrics, "latest": metrics},
                {"score": 100, "issues": []},
                profile_key=profile_key,
            )
        elif profile_key == "index_enhanced":
            result = self._evaluate_index_enhanced({"1y": metrics, "latest": metrics}, {"score": 100, "issues": []})
        elif profile_key == "money_market":
            result = self._evaluate_money_market({"1y": metrics, "latest": metrics}, {"score": 100, "issues": []})
        else:
            return {
                "status": "unsupported_methodology",
                "overall_score": None,
                "dimension_scores": {},
                "calculation_method": f"{self.PEER_METHODOLOGY_VERSION}:{profile_key or 'unknown'}",
            }
        ready = result.get("status") in {"ok", "partial"}
        return {
            "status": result.get("status"),
            "overall_score": result.get("total_score") if ready else None,
            "dimension_scores": {
                key: value
                for key, value in (result.get("dimensions") or {}).items()
                if key != "data_quality"
            } if ready else {},
            "calculation_method": f"{self.PEER_METHODOLOGY_VERSION}:{profile_key}",
        }

    def _methodology_dimensions(self, profile_key: str, window: str) -> List[Dict[str, Any]]:
        if profile_key in self.RETURN_RISK_WEIGHTS:
            profile = self.PROFILES[profile_key]
            return_low, return_high = profile["return_range"]
            drawdown_low, drawdown_high = profile["drawdown_range"]
            volatility_high, volatility_low = profile["volatility_range"]
            dimensions = [
                self._dimension_description("return", self.RETURN_RISK_WEIGHTS[profile_key], [
                    self._metric_description(f"{window}.annualized_return", "所选窗口年化收益", "percent", "higher", self._range_rule(return_low, return_high, True)),
                    self._metric_description("3y.annualized_return", "近3年年化收益", "percent", "higher", "作为长期收益参考"),
                ]),
                self._dimension_description("risk", self.RETURN_RISK_WEIGHTS[profile_key], [
                    self._metric_description(f"{window}.max_drawdown", "所选窗口最大回撤", "percent", "higher", self._range_rule(drawdown_low, drawdown_high, True)),
                    self._metric_description(f"{window}.annualized_volatility", "所选窗口年化波动", "percent", "lower", self._range_rule(volatility_low, volatility_high, False)),
                    self._metric_description("3y.max_drawdown", "近3年最大回撤", "percent", "higher", "作为长期回撤参考"),
                ]),
                self._dimension_description("risk_adjusted", self.RETURN_RISK_WEIGHTS[profile_key], [
                    self._metric_description(f"{window}.sharpe_ratio", "所选窗口夏普比率", "number", "higher", "0分对应0，100分对应2.5"),
                    self._metric_description(f"{window}.calmar_ratio", "所选窗口Calmar", "number", "higher", "0分对应0，100分对应4"),
                    self._metric_description("3y.sharpe_ratio", "近3年夏普比率", "number", "higher", "作为长期风险收益参考"),
                ]),
                self._dimension_description("consistency", self.RETURN_RISK_WEIGHTS[profile_key], [
                    self._metric_description(f"{window}.positive_return_ratio", "所选窗口正收益占比", "percent", "higher", "45%对应0分，65%对应100分"),
                    self._metric_description(f"{window}.annualized_return", "所选窗口与近3年收益差", "percent", "lower", "差异越小，稳定性得分越高"),
                ]),
                self._dimension_description("manager_tenure", self.RETURN_RISK_WEIGHTS[profile_key], [
                    self._metric_description("manager_tenure.annualized_return", "现任经理任期年化收益", "percent", "higher", "按当前类别收益区间归一"),
                    self._metric_description("manager_tenure.max_drawdown", "现任经理任期最大回撤", "percent", "higher", "按当前类别回撤区间归一"),
                    self._metric_description("manager_tenure.tenure_days", "现任经理任期天数", "days", "higher", "180天对应0分，900天对应100分"),
                ]),
                self._dimension_description("data_quality", self.RETURN_RISK_WEIGHTS[profile_key], []),
            ]
            return self._deduplicate_dimension_metrics(dimensions)

        if profile_key in {"index_fund", "qdii_index"}:
            profile = self.PROFILES[profile_key]
            weights = self.QDII_INDEX_WEIGHTS if profile_key == "qdii_index" else self.INDEX_WEIGHTS
            tracking_error_low, tracking_error_high = profile["tracking_error_score_range"]
            tracking_difference_low, tracking_difference_high = profile["tracking_difference_score_range"]
            expense_low, expense_high = profile["expense_ratio_score_range"]
            aum_low, aum_high = profile["aum_score_range"]
            return [
                self._dimension_description("tracking_quality", weights, [
                    self._metric_description(f"{window}.tracking_error", "所选窗口跟踪误差", "percent", "lower", self._range_rule(tracking_error_high, tracking_error_low, False)),
                    self._metric_description(f"{window}.tracking_difference", "所选窗口跟踪差异", "percent", "lower", f"按绝对值计分；{self._range_rule(tracking_difference_high, tracking_difference_low, False)}", [f"{window}.excess_return"]),
                ]),
                self._dimension_description("cost_efficiency", weights, [
                    self._metric_description("latest.expense_ratio", "管理费与托管费合计", "percent", "lower", self._range_rule(expense_high, expense_low, False)),
                ]),
                self._dimension_description("scale_liquidity", weights, [
                    self._metric_description("latest.aum", "基金规模", "cny_100m", "higher", f"按对数刻度计分；{aum_low:g}亿元对应0分，{aum_high:g}亿元对应100分"),
                ]),
                self._dimension_description("data_quality", weights, []),
            ]

        if profile_key == "index_enhanced":
            return [
                self._dimension_description("excess_return", self.INDEX_ENHANCED_WEIGHTS, [
                    self._metric_description(f"{window}.excess_return", "所选窗口超额收益", "percent", "higher", "-5%对应0分，8%对应100分", [f"{window}.tracking_difference"]),
                ]),
                self._dimension_description("active_efficiency", self.INDEX_ENHANCED_WEIGHTS, [
                    self._metric_description(f"{window}.information_ratio", "所选窗口信息比率", "number", "higher", "-0.5对应0分，1.5对应100分"),
                    self._metric_description(f"{window}.tracking_error", "所选窗口跟踪误差", "percent", "lower", "3%附近得分高，25%及以上得分低"),
                ]),
                self._dimension_description("drawdown_control", self.INDEX_ENHANCED_WEIGHTS, [
                    self._metric_description(f"{window}.max_drawdown", "所选窗口最大回撤", "percent", "higher", "-45%对应0分，-8%对应100分"),
                ]),
                self._dimension_description("cost_efficiency", self.INDEX_ENHANCED_WEIGHTS, [
                    self._metric_description("latest.expense_ratio", "管理费与托管费合计", "percent", "lower", "0.4%附近得分高，2.5%及以上得分低"),
                ]),
                self._dimension_description("scale_liquidity", self.INDEX_ENHANCED_WEIGHTS, [
                    self._metric_description("latest.aum", "基金规模", "cny_100m", "higher", "按对数刻度计分；1亿元对应0分，100亿元对应100分"),
                ]),
                self._dimension_description("data_quality", self.INDEX_ENHANCED_WEIGHTS, []),
            ]

        if profile_key == "money_market":
            return [
                self._dimension_description("income_competitiveness", self.MONEY_MARKET_WEIGHTS, [
                    self._metric_description("latest.seven_day_annualized_yield", "七日年化收益率", "percent", "higher", "1%对应0分，3.5%对应100分", [f"{window}.seven_day_annualized_yield"]),
                    self._metric_description(f"{window}.annualized_return", "所选窗口年化收益", "percent", "higher", "1%对应0分，3.5%对应100分"),
                ]),
                self._dimension_description("capital_preservation", self.MONEY_MARKET_WEIGHTS, [
                    self._metric_description(f"{window}.max_drawdown", "所选窗口最大回撤", "percent", "higher", "-1%对应0分，0%对应100分"),
                    self._metric_description(f"{window}.annualized_volatility", "所选窗口年化波动", "percent", "lower", "0.1%附近得分高，2%及以上得分低"),
                ]),
                self._dimension_description("income_stability", self.MONEY_MARKET_WEIGHTS, [
                    self._metric_description(f"{window}.positive_return_ratio", "所选窗口正收益占比", "percent", "higher", "95%对应0分，100%对应100分"),
                ]),
                self._dimension_description("scale_liquidity", self.MONEY_MARKET_WEIGHTS, [
                    self._metric_description("latest.aum", "基金规模", "cny_100m", "higher", "按对数刻度计分；5亿元对应0分，300亿元对应100分"),
                ]),
                self._dimension_description("data_quality", self.MONEY_MARKET_WEIGHTS, []),
            ]
        return []

    def _dimension_description(
        self,
        key: str,
        weights: Dict[str, float],
        metrics: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "label": self.DIMENSION_LABELS.get(key, key),
            "weight": weights.get(key),
            "metrics": metrics,
        }

    @staticmethod
    def _metric_description(
        path: str,
        label: str,
        unit: str,
        direction: str,
        rule: str,
        fallback_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "path": path,
            "label": label,
            "unit": unit,
            "direction": direction,
            "rule": rule,
            "fallback_paths": fallback_paths or [],
        }

    @staticmethod
    def _range_rule(low: float, high: float, higher_is_better: bool) -> str:
        low_text = f"{low * 100:.1f}%"
        high_text = f"{high * 100:.1f}%"
        if higher_is_better:
            return f"{low_text}对应0分，{high_text}对应100分"
        return f"{low_text}附近得分高，{high_text}及以上得分低"

    @staticmethod
    def _deduplicate_dimension_metrics(dimensions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for dimension in dimensions:
            seen = set()
            unique = []
            for metric in dimension.get("metrics") or []:
                path = metric.get("path")
                if not path or path in seen:
                    continue
                seen.add(path)
                unique.append(metric)
            dimension["metrics"] = unique
        return dimensions

    def _evaluate_return_risk(
        self,
        profile_key: str,
        metrics: Dict[str, Dict[str, float]],
        quality: Dict[str, Any],
        selected_window: str,
    ) -> Dict[str, Any]:
        selected = metrics.get(selected_window, {})
        core_gaps = [
            f"core_metric:{selected_window}.{metric_name}"
            for metric_name in ["annualized_return", "max_drawdown", "sharpe_ratio"]
            if selected.get(metric_name) is None
        ]
        if core_gaps:
            return self._unavailable("insufficient_evidence", core_gaps, profile_key, selected_window)

        profile = self.PROFILES[profile_key]
        weights = self.RETURN_RISK_WEIGHTS[profile_key]
        dimensions = {
            "return": self._return_dimension(metrics, profile, selected_window),
            "risk": self._risk_dimension(metrics, profile, selected_window),
            "risk_adjusted": self._risk_adjusted_dimension(metrics, selected_window),
            "consistency": self._consistency_dimension(metrics, selected_window),
            "manager_tenure": self._manager_dimension(metrics, profile),
            "data_quality": self._dimension(quality.get("score", 0), ["数据质量评分进入综合修正"]),
        }
        missing = []
        for window in [selected_window, "manager_tenure"]:
            if window not in metrics:
                missing.append(f"metric_window:{window}")
        missing.extend(f"quality:{issue}" for issue in quality.get("issues", []))
        return self._finalize(profile_key, dimensions, weights, metrics, missing, selected_window)

    def _evaluate_index(
        self,
        metrics: Dict[str, Dict[str, float]],
        quality: Dict[str, Any],
        selected_window: str = "1y",
        profile_key: str = "index_fund",
    ) -> Dict[str, Any]:
        profile = self.PROFILES[profile_key]
        weights = self.QDII_INDEX_WEIGHTS if profile_key == "qdii_index" else self.INDEX_WEIGHTS
        tracking_error = self._first(metrics, [(selected_window, "tracking_error")])
        tracking_difference = self._first(metrics, [(selected_window, "tracking_difference"), (selected_window, "excess_return")])
        expense_ratio = self._rate(self._first(metrics, [("latest", "expense_ratio"), (selected_window, "expense_ratio")]))
        aum = self._asset_yi(self._first(metrics, [("latest", "aum"), (selected_window, "aum")]))
        values = {
            "tracking_error": tracking_error,
            "tracking_difference": tracking_difference,
            "expense_ratio": expense_ratio,
            "aum": aum,
        }
        gaps = [f"core_metric:{name}" for name, value in values.items() if value is None]
        if gaps:
            return self._unavailable("insufficient_evidence", gaps, profile_key, selected_window)
        invalid_ranges = []
        if tracking_error < 0 or tracking_error > profile["maximum_tracking_error"]:
            invalid_ranges.append("invalid_metric_range:tracking_error")
        if abs(tracking_difference) > profile["maximum_tracking_difference"]:
            invalid_ranges.append("invalid_metric_range:tracking_difference")
        if expense_ratio < 0 or expense_ratio > 0.05:
            invalid_ranges.append("invalid_metric_range:expense_ratio")
        if aum <= 0:
            invalid_ranges.append("invalid_metric_range:aum")
        if invalid_ranges:
            return self._unavailable("insufficient_evidence", invalid_ranges, profile_key, selected_window)

        tracking_error_low, tracking_error_high = profile["tracking_error_score_range"]
        tracking_difference_low, tracking_difference_high = profile["tracking_difference_score_range"]
        expense_low, expense_high = profile["expense_ratio_score_range"]
        aum_low, aum_high = profile["aum_score_range"]

        dimensions = {
            "tracking_quality": self._dimension(
                self._average([
                    self._normalize(tracking_error, tracking_error_low, tracking_error_high, higher_is_better=False),
                    self._normalize(abs(tracking_difference), tracking_difference_low, tracking_difference_high, higher_is_better=False),
                ]),
                ["跟踪误差与跟踪差异共同衡量复制质量"],
            ),
            "cost_efficiency": self._dimension(
                self._normalize(expense_ratio, expense_low, expense_high, higher_is_better=False),
                ["管理费与托管费形成的总费率衡量长期成本拖累"],
            ),
            "scale_liquidity": self._dimension(
                self._normalize_log(aum, aum_low, aum_high),
                ["基金规模作为流动性和运营可持续性的代理证据"],
            ),
            "data_quality": self._dimension(quality.get("score", 0), ["数据质量评分进入综合修正"]),
        }
        missing = [f"quality:{issue}" for issue in quality.get("issues", [])]
        return self._finalize(
            profile_key,
            dimensions,
            weights,
            metrics,
            missing,
            selected_window,
        )

    def _evaluate_index_enhanced(
        self,
        metrics: Dict[str, Dict[str, float]],
        quality: Dict[str, Any],
        selected_window: str = "1y",
    ) -> Dict[str, Any]:
        excess_return = self._first(metrics, [(selected_window, "excess_return"), (selected_window, "tracking_difference")])
        information_ratio = self._first(metrics, [(selected_window, "information_ratio")])
        tracking_error = self._first(metrics, [(selected_window, "tracking_error")])
        max_drawdown = self._drawdown(self._first(metrics, [(selected_window, "max_drawdown")]))
        expense_ratio = self._rate(self._first(metrics, [("latest", "expense_ratio"), (selected_window, "expense_ratio")]))
        aum = self._asset_yi(self._first(metrics, [("latest", "aum"), (selected_window, "aum")]))
        values = {
            "excess_return": excess_return,
            "information_ratio": information_ratio,
            "tracking_error": tracking_error,
            "max_drawdown": max_drawdown,
            "expense_ratio": expense_ratio,
            "aum": aum,
        }
        gaps = [f"core_metric:{name}" for name, value in values.items() if value is None]
        if gaps:
            return self._unavailable("insufficient_evidence", gaps, "index_enhanced", selected_window)

        invalid_ranges = []
        if abs(excess_return) > 0.50:
            invalid_ranges.append("invalid_metric_range:excess_return")
        if abs(information_ratio) > 10:
            invalid_ranges.append("invalid_metric_range:information_ratio")
        if tracking_error < 0 or tracking_error > 0.35:
            invalid_ranges.append("invalid_metric_range:tracking_error")
        if max_drawdown < -0.80 or max_drawdown > 0.01:
            invalid_ranges.append("invalid_metric_range:max_drawdown")
        if expense_ratio < 0 or expense_ratio > 0.05:
            invalid_ranges.append("invalid_metric_range:expense_ratio")
        if aum <= 0:
            invalid_ranges.append("invalid_metric_range:aum")
        if invalid_ranges:
            return self._unavailable("insufficient_evidence", invalid_ranges, "index_enhanced", selected_window)

        dimensions = {
            "excess_return": self._dimension(
                self._normalize(excess_return, -0.05, 0.08),
                ["相对合同主指数的近一年超额收益衡量增强结果"],
            ),
            "active_efficiency": self._dimension(
                self._average([
                    self._normalize(information_ratio, -0.5, 1.5),
                    self._normalize(tracking_error, 0.25, 0.03, higher_is_better=False),
                ]),
                ["信息比率与跟踪误差共同衡量主动风险使用效率"],
            ),
            "drawdown_control": self._dimension(
                self._normalize(max_drawdown, -0.45, -0.08),
                ["最大回撤衡量增强策略在下行阶段的风险控制"],
            ),
            "cost_efficiency": self._dimension(
                self._normalize(expense_ratio, 0.025, 0.004, higher_is_better=False),
                ["管理费与托管费形成的总费率衡量增强收益的成本侵蚀"],
            ),
            "scale_liquidity": self._dimension(
                self._normalize_log(aum, 1.0, 100.0),
                ["基金规模作为流动性和策略可持续性的代理证据"],
            ),
            "data_quality": self._dimension(quality.get("score", 0), ["数据质量评分进入综合修正"]),
        }
        missing = [f"quality:{issue}" for issue in quality.get("issues", [])]
        return self._finalize(
            "index_enhanced",
            dimensions,
            self.INDEX_ENHANCED_WEIGHTS,
            metrics,
            missing,
            selected_window,
        )

    def _evaluate_money_market(
        self,
        metrics: Dict[str, Dict[str, float]],
        quality: Dict[str, Any],
        selected_window: str = "1y",
    ) -> Dict[str, Any]:
        seven_day_yield = self._rate(self._first(metrics, [
            ("latest", "seven_day_annualized_yield"),
            (selected_window, "seven_day_annualized_yield"),
        ]))
        annualized_return = self._rate(self._first(metrics, [(selected_window, "annualized_return")]))
        max_drawdown = self._drawdown(self._first(metrics, [(selected_window, "max_drawdown")]))
        aum = self._asset_yi(self._first(metrics, [("latest", "aum"), (selected_window, "aum")]))
        values = {
            "seven_day_annualized_yield": seven_day_yield,
            "annualized_return": annualized_return,
            "max_drawdown": max_drawdown,
            "aum": aum,
        }
        gaps = [f"core_metric:{name}" for name, value in values.items() if value is None]
        if gaps:
            return self._unavailable("insufficient_evidence", gaps, "money_market", selected_window)
        invalid_ranges = []
        if seven_day_yield < 0 or seven_day_yield > 0.20:
            invalid_ranges.append("invalid_metric_range:seven_day_annualized_yield")
        if annualized_return < -0.05 or annualized_return > 0.20:
            invalid_ranges.append("invalid_metric_range:annualized_return")
        if max_drawdown < -0.20 or max_drawdown > 0.01:
            invalid_ranges.append("invalid_metric_range:max_drawdown")
        if aum <= 0:
            invalid_ranges.append("invalid_metric_range:aum")
        if invalid_ranges:
            return self._unavailable("insufficient_evidence", invalid_ranges, "money_market", selected_window)

        volatility = self._first(metrics, [(selected_window, "annualized_volatility")])
        positive_ratio = self._first(metrics, [(selected_window, "positive_return_ratio")])
        benchmark_rate = self._rate(self._first(metrics, [("latest", "benchmark_annualized_rate")]))
        benchmark_spread = self._first(metrics, [("latest", "benchmark_yield_spread")])
        stability_gap = abs(seven_day_yield - annualized_return)
        income_evidence = ["七日年化收益率与近一年收益共同描述收益中枢"]
        if benchmark_rate is not None and benchmark_spread is not None:
            income_evidence.append("DR007 作为利率型参照单独披露收益利差，不转换为净值或跟踪误差")
        dimensions = {
            "income_competitiveness": self._dimension(
                self._average([
                    self._normalize(seven_day_yield, 0.01, 0.035),
                    self._normalize(annualized_return, 0.01, 0.035),
                ]),
                income_evidence,
            ),
            "capital_preservation": self._dimension(
                self._average([
                    self._normalize(max_drawdown, -0.01, 0.0),
                    self._normalize(volatility, 0.02, 0.001, higher_is_better=False),
                ]),
                ["最大回撤与波动衡量净值稳定和本金保护特征"],
            ),
            "income_stability": self._dimension(
                self._average([
                    self._normalize(stability_gap, 0.02, 0.0, higher_is_better=False),
                    self._normalize(positive_ratio, 0.95, 1.0),
                ]),
                ["七日年化与一年收益差异、正收益比例衡量收益稳定性"],
            ),
            "scale_liquidity": self._dimension(
                self._normalize_log(aum, 5.0, 300.0),
                ["基金规模作为流动性管理和赎回承接能力的代理证据"],
            ),
            "data_quality": self._dimension(quality.get("score", 0), ["数据质量评分进入综合修正"]),
        }
        missing = []
        if volatility is None:
            missing.append("optional_metric:1y.annualized_volatility")
        if positive_ratio is None:
            missing.append("optional_metric:1y.positive_return_ratio")
        if benchmark_rate is None:
            missing.append("optional_metric:latest.benchmark_annualized_rate")
        missing.extend(f"quality:{issue}" for issue in quality.get("issues", []))
        return self._finalize(
            "money_market",
            dimensions,
            self.MONEY_MARKET_WEIGHTS,
            metrics,
            missing,
            selected_window,
        )

    def _finalize(
        self,
        profile_key: str,
        dimensions: Dict[str, Dict[str, Any]],
        weights: Dict[str, float],
        metrics: Dict[str, Dict[str, float]],
        missing_data: List[str],
        selected_window: str = "1y",
    ) -> Dict[str, Any]:
        total_score = 0.0
        included_weight = sum(
            weight
            for key, weight in weights.items()
            if dimensions[key].get("included_in_score") is not False
        )
        for key, weight in weights.items():
            dimensions[key]["weight"] = weight
            included = dimensions[key].get("included_in_score") is not False
            effective_weight = weight / included_weight if included and included_weight else 0.0
            dimensions[key]["included_in_score"] = included
            dimensions[key]["effective_weight"] = round(effective_weight, 6)
            score = dimensions[key].get("score")
            dimensions[key]["weighted_score"] = (
                round(float(score) * effective_weight, 2)
                if included and score is not None
                else 0.0
            )
            if included and score is not None:
                total_score += float(score) * effective_weight
        return {
            "status": "partial" if missing_data else "ok",
            "profile_key": profile_key,
            "methodology_version": self.METHODOLOGY_VERSION,
            "evaluation_window": selected_window,
            "calculation_method": f"{self.METHODOLOGY_VERSION}:{profile_key}:{selected_window}",
            "total_score": round(total_score, 4),
            "dimensions": dimensions,
            "metric_scores": self._metric_scores(metrics),
            "missing_data": list(dict.fromkeys(missing_data)),
        }

    def _unavailable(
        self,
        status: str,
        missing_data: List[str],
        profile_key: str,
        selected_window: str = "1y",
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "profile_key": profile_key,
            "methodology_version": self.METHODOLOGY_VERSION,
            "evaluation_window": selected_window,
            "calculation_method": f"{self.METHODOLOGY_VERSION}:{profile_key}:{selected_window}",
            "total_score": None,
            "dimensions": {},
            "metric_scores": {},
            "missing_data": missing_data,
        }

    def _return_dimension(
        self,
        metrics: Dict[str, Dict[str, float]],
        profile: Dict[str, Any],
        selected_window: str,
    ) -> Dict[str, Any]:
        low, high = profile["return_range"]
        values = [self._normalize(metrics.get(selected_window, {}).get("annualized_return"), low, high)]
        if selected_window != "3y":
            values.append(self._normalize(metrics.get("3y", {}).get("annualized_return"), low, high))
        return self._dimension(self._average(values), [f"{selected_window}/3y 年化收益进入收益能力评分"])

    def _risk_dimension(
        self,
        metrics: Dict[str, Dict[str, float]],
        profile: Dict[str, Any],
        selected_window: str,
    ) -> Dict[str, Any]:
        drawdown_low, drawdown_high = profile["drawdown_range"]
        volatility_high, volatility_low = profile["volatility_range"]
        values = [
            self._normalize(metrics.get(selected_window, {}).get("max_drawdown"), drawdown_low, drawdown_high),
            self._normalize(
                metrics.get(selected_window, {}).get("annualized_volatility"),
                volatility_high,
                volatility_low,
                higher_is_better=False,
            ),
        ]
        if selected_window != "3y":
            values.append(self._normalize(metrics.get("3y", {}).get("max_drawdown"), drawdown_low, drawdown_high))
        return self._dimension(self._average(values), ["所选窗口最大回撤、年化波动和长期回撤进入风险控制评分"])

    def _risk_adjusted_dimension(
        self,
        metrics: Dict[str, Dict[str, float]],
        selected_window: str,
    ) -> Dict[str, Any]:
        values = [
            self._normalize(metrics.get(selected_window, {}).get("sharpe_ratio"), 0, 2.5),
            self._normalize(metrics.get(selected_window, {}).get("calmar_ratio"), 0, 4),
        ]
        if selected_window != "3y":
            values.append(self._normalize(metrics.get("3y", {}).get("sharpe_ratio"), 0, 2.5))
        return self._dimension(self._average(values), ["所选窗口夏普、Calmar 和长期夏普进入风险调整收益评分"])

    def _consistency_dimension(
        self,
        metrics: Dict[str, Dict[str, float]],
        selected_window: str,
    ) -> Dict[str, Any]:
        selected = metrics.get(selected_window, {})
        three_year = metrics.get("3y", {})
        return_gap = None
        if selected_window != "3y" and selected.get("annualized_return") is not None and three_year.get("annualized_return") is not None:
            return_gap = abs(selected["annualized_return"] - three_year["annualized_return"])
        return self._dimension(self._average([
            self._normalize(selected.get("positive_return_ratio"), 0.45, 0.65),
            self._normalize(return_gap, 0.12, 0.01, higher_is_better=False),
        ]), ["所选窗口胜率和长期收益差异进入一致性评分"])

    def _manager_dimension(self, metrics: Dict[str, Dict[str, float]], profile: Dict[str, Any]) -> Dict[str, Any]:
        tenure = metrics.get("manager_tenure", {})
        if not tenure:
            return {
                "score": None,
                "weighted_score": 0.0,
                "included_in_score": False,
                "evidence": ["现任经理完整任期净值证据不足，该维度不计分"],
            }
        low, high = profile["return_range"]
        drawdown_low, drawdown_high = profile["drawdown_range"]
        return self._dimension(self._average([
            self._normalize(tenure.get("annualized_return"), low, high),
            self._normalize(tenure.get("max_drawdown"), drawdown_low, drawdown_high),
            self._normalize(tenure.get("tenure_days"), 180, 900),
        ]), ["现任经理任期内收益、回撤和任期长度进入评分"])

    def _metric_scores(self, metrics: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
        allowed = {
            "annualized_return", "max_drawdown", "annualized_volatility", "sharpe_ratio",
            "calmar_ratio", "positive_return_ratio", "tenure_days", "tracking_error",
            "tracking_difference", "excess_return", "information_ratio", "expense_ratio", "aum",
            "seven_day_annualized_yield", "income_per_10000",
            "benchmark_annualized_rate", "benchmark_yield_spread",
        }
        return {
            f"{window}.{metric_name}": value
            for window, window_metrics in metrics.items()
            for metric_name, value in window_metrics.items()
            if metric_name in allowed
        }

    def _first(
        self,
        metrics: Dict[str, Dict[str, float]],
        paths: List[Tuple[str, str]],
    ) -> Optional[float]:
        for window, metric_name in paths:
            value = self._number(metrics.get(window, {}).get(metric_name))
            if value is not None:
                return value
        return None

    def _dimension(self, score: Optional[float], evidence: List[str]) -> Dict[str, Any]:
        effective_score = 50.0 if score is None else score
        return {
            "score": round(max(0.0, min(100.0, effective_score)), 2),
            "weighted_score": round(max(0.0, min(100.0, effective_score)), 2),
            "evidence": evidence,
        }

    def _normalize(
        self,
        value: Optional[float],
        low: float,
        high: float,
        higher_is_better: bool = True,
    ) -> Optional[float]:
        if value is None or low == high:
            return None
        if higher_is_better:
            if value <= low:
                return 0.0
            if value >= high:
                return 100.0
            return (value - low) / (high - low) * 100.0
        if value <= high:
            return 100.0
        if value >= low:
            return 0.0
        return (low - value) / (low - high) * 100.0

    def _normalize_log(self, value: Optional[float], low: float, high: float) -> Optional[float]:
        if value is None or value <= 0:
            return None
        return self._normalize(math.log10(value), math.log10(low), math.log10(high))

    def _average(self, values: List[Optional[float]]) -> float:
        valid = [value for value in values if value is not None]
        return sum(valid) / len(valid) if valid else 50.0

    def _number(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _drawdown(self, value: Any) -> Optional[float]:
        number = self._number(value)
        return -abs(number) if number is not None else None

    def _rate(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return value / 100.0 if abs(value) > 0.20 else value

    def _asset_yi(self, value: Optional[float]) -> Optional[float]:
        if value is None or value <= 0:
            return None
        return value / 100_000_000.0 if value >= 1_000_000 else value
