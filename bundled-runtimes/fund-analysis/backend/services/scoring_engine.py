"""
基金/经理评分引擎 - 多维度量化打分
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal
import math

from services.scoring_contract import build_scoring_output, serialize_scoring_output


class ScoreDimension(str, Enum):
    """评分维度"""
    RETURN = "return"           # 收益能力
    RISK = "risk"               # 风险控制
    RISK_ADJUSTED = "risk_adjusted"  # 风险调整收益
    STYLE = "style"             # 投资风格稳定性
    MANAGEMENT = "management"  # 管理能力
    CONSISTENCY = "consistency"  # 业绩一致性
    CAPACITY = "capacity"      # 规模容量


@dataclass
class ScoringRule:
    """评分规则"""
    dimension: ScoreDimension
    metric_name: str
    min_val: float
    max_val: float
    weight: float = 1.0
    higher_is_better: bool = True  # 指标是否越高越好

    def normalize(self, value: float) -> float:
        """归一化到 0-100 分"""
        if value is None or math.isnan(value):
            return 50.0
        if self.higher_is_better:
            if value <= self.min_val:
                return 0.0
            if value >= self.max_val:
                return 100.0
            return (value - self.min_val) / (self.max_val - self.min_val) * 100
        else:
            if value >= self.max_val:
                return 0.0
            if value <= self.min_val:
                return 100.0
            return (self.max_val - value) / (self.max_val - self.min_val) * 100


class FundScoringEngine:
    """基金评分引擎"""

    RETURN_RULES = [
        # (指标名, 最小值, 最大值, 权重, 越高越好)
        ScoringRule(ScoreDimension.RETURN, "annualized_return_1y", -30, 80, 2.0),
        ScoringRule(ScoreDimension.RETURN, "annualized_return_3y", -20, 50, 1.5),
        ScoringRule(ScoreDimension.RETURN, "annualized_return_5y", -10, 40, 1.0),
    ]

    RISK_RULES = [
        ScoringRule(ScoreDimension.RISK, "max_drawdown", -0.7, 0, 2.0, True),  # 回撤为负值，越接近 0 越好
        ScoringRule(ScoreDimension.RISK, "annualized_volatility_1y", 0.03, 0.40, 1.5, False),
        ScoringRule(ScoreDimension.RISK, "var_95", -0.20, 0, 1.0, True),
    ]

    RISK_ADJUSTED_RULES = [
        ScoringRule(ScoreDimension.RISK_ADJUSTED, "sharpe_ratio", -1.0, 3.0, 2.5),
        ScoringRule(ScoreDimension.RISK_ADJUSTED, "sortino", -1.0, 4.0, 1.5),
        ScoringRule(ScoreDimension.RISK_ADJUSTED, "calmar_ratio", -1.0, 3.0, 1.5),
        ScoringRule(ScoreDimension.RISK_ADJUSTED, "information_ratio", -1.0, 2.0, 1.0),
    ]

    ALL_RULES = RETURN_RULES + RISK_RULES + RISK_ADJUSTED_RULES

    METRIC_SNAPSHOT_ALIASES = {
        "annualized_return_1y": "annualized_return",
        "annualized_return_3y": "annualized_return",
        "annualized_return_5y": "annualized_return",
        "annualized_volatility_1y": "annualized_volatility",
        "sortino": "sortino_ratio",
    }

    DIMENSION_WEIGHTS = {
        ScoreDimension.RETURN: 0.30,
        ScoreDimension.RISK: 0.25,
        ScoreDimension.RISK_ADJUSTED: 0.35,
        ScoreDimension.STYLE: 0.10,
    }

    def get_scoring_rules(self) -> list:
        """返回全部评分规则（供 /api/scoring/rules 等只读端点使用）。"""
        return list(self.ALL_RULES)

    def score_fund(self, performance_data: Dict, risk_data: Dict, style_data: Dict) -> Dict[str, Any]:
        """
        对基金进行综合评分
        返回: { overall_score, dimension_scores, metric_scores }
        """
        dimension_scores = {}
        metric_scores = {}

        # 收益维度
        dimension_scores[ScoreDimension.RETURN] = self._score_dimension(
            self.RETURN_RULES, {**performance_data, **risk_data}, metric_scores
        )

        # 风险维度
        dimension_scores[ScoreDimension.RISK] = self._score_dimension(
            self.RISK_RULES, {**performance_data, **risk_data}, metric_scores
        )

        # 风险调整收益
        dimension_scores[ScoreDimension.RISK_ADJUSTED] = self._score_dimension(
            self.RISK_ADJUSTED_RULES, {**performance_data, **risk_data}, metric_scores
        )

        # 风格维度 (Barra因子分析)
        dimension_scores[ScoreDimension.STYLE] = self._score_style(style_data, metric_scores)

        # 综合评分
        overall = sum(
            score["weighted_score"] * self.DIMENSION_WEIGHTS[d]
            for d, score in dimension_scores.items()
        )

        return {
            "overall_score": round(overall, 2),
            "overall_grade": self._get_grade(overall),
            "dimension_scores": dimension_scores,
            "metric_scores": {k: (round(v, 2) if v is not None else None) for k, v in metric_scores.items()},
            "scoring_time": None,
        }

    def score_fund_from_metric_snapshots(self, fund_code: str, metric_repo=None) -> Dict[str, Any]:
        """基于 MetricSnapshot 的权威基金评分入口。"""
        if metric_repo is None:
            from repositories import get_metric_snapshot_repo
            metric_repo = get_metric_snapshot_repo()

        panel = metric_repo.get_latest_panel("fund", fund_code)
        metric_values = self._metric_panel_to_values(panel)
        adapted = self._adapt_snapshot_metrics(metric_values)
        missing_data = self._missing_metric_names(adapted)
        metric_scores: Dict[str, Any] = {}

        dimension_scores = {
            ScoreDimension.RETURN: self._score_dimension(self.RETURN_RULES, adapted, metric_scores),
            ScoreDimension.RISK: self._score_dimension(self.RISK_RULES, adapted, metric_scores),
            ScoreDimension.RISK_ADJUSTED: self._score_dimension(self.RISK_ADJUSTED_RULES, adapted, metric_scores),
            ScoreDimension.STYLE: {"score": 0.0, "weighted_score": 0.0, "count": 0, "status": "insufficient_evidence"},
        }
        overall = sum(
            score["weighted_score"] * self.DIMENSION_WEIGHTS[dimension]
            for dimension, score in dimension_scores.items()
        )
        positive_factors, negative_factors = self._explain_snapshot_score(adapted, dimension_scores)
        source_snapshot_ids = sorted({
            item.get("source_snapshot_id") for item in panel if item.get("source_snapshot_id")
        })
        as_of_dates = sorted({str(item.get("as_of_date")) for item in panel if item.get("as_of_date")})

        return build_scoring_output(
            target_type="fund",
            target_id=fund_code,
            total_score=overall,
            dimensions=serialize_scoring_output(dimension_scores),
            metric_scores=metric_scores,
            positive_factors=positive_factors,
            negative_factors=negative_factors,
            missing_data=missing_data,
            source_snapshot_ids=source_snapshot_ids,
            as_of_date=as_of_dates[-1] if as_of_dates else None,
            calculation_method="metric_snapshot",
        )

    def _score_dimension(self, rules: List[ScoringRule], data: Dict, metric_scores: Dict) -> Dict:
        total_weight = 0.0
        weighted_sum = 0.0
        for rule in rules:
            raw_val = data.get(rule.metric_name)
            normalized = rule.normalize(raw_val)
            metric_scores[f"{rule.metric_name}_normalized"] = round(normalized, 2)
            metric_scores[f"{rule.metric_name}_raw"] = raw_val
            weighted_sum += normalized * rule.weight
            total_weight += rule.weight

        return {
            "score": round(weighted_sum / total_weight, 2) if total_weight > 0 else 50.0,
            "weighted_score": round(weighted_sum / total_weight, 2) if total_weight > 0 else 50.0,
            "count": len(rules),
        }

    def _metric_panel_to_values(self, panel: List[Dict[str, Any]]) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for item in panel:
            name = item.get("metric_name")
            value = item.get("metric_value")
            if name is None or value is None:
                continue
            try:
                values[name] = float(Decimal(str(value)))
            except Exception:
                continue
        return values

    def _adapt_snapshot_metrics(self, metric_values: Dict[str, float]) -> Dict[str, float]:
        adapted = dict(metric_values)
        for rule in self.ALL_RULES:
            if rule.metric_name in adapted:
                continue
            alias = self.METRIC_SNAPSHOT_ALIASES.get(rule.metric_name)
            if alias and alias in metric_values:
                adapted[rule.metric_name] = metric_values[alias]
        for metric_name in ["annualized_return", "annualized_return_1y", "annualized_return_3y", "annualized_return_5y"]:
            value = adapted.get(metric_name)
            if value is not None and abs(value) <= 2:
                adapted[metric_name] = value * 100
        return adapted

    def _missing_metric_names(self, data: Dict[str, float]) -> List[str]:
        missing = []
        for rule in self.ALL_RULES:
            if rule.metric_name == "var_95":
                continue
            if data.get(rule.metric_name) is None:
                missing.append(rule.metric_name)
        return missing

    def _explain_snapshot_score(self, data: Dict[str, float], dimension_scores: Dict[Any, Dict[str, Any]]) -> tuple[List[str], List[str]]:
        positive_factors: List[str] = []
        negative_factors: List[str] = []
        annualized_return = data.get("annualized_return") or data.get("annualized_return_1y")
        max_drawdown = data.get("max_drawdown")
        sharpe_ratio = data.get("sharpe_ratio")

        if annualized_return is not None:
            if annualized_return >= 0.15:
                positive_factors.append("年化收益表现较强")
            elif annualized_return < 0:
                negative_factors.append("年化收益为负")
        if max_drawdown is not None:
            if max_drawdown >= -0.1:
                positive_factors.append("最大回撤控制较好")
            elif max_drawdown <= -0.3:
                negative_factors.append("最大回撤偏高")
        if sharpe_ratio is not None:
            if sharpe_ratio >= 1:
                positive_factors.append("夏普比率较优")
            elif sharpe_ratio < 0:
                negative_factors.append("风险调整后收益较弱")

        for dimension, result in dimension_scores.items():
            score = result.get("score", 50)
            name = dimension.value if hasattr(dimension, "value") else str(dimension)
            if score >= 80:
                positive_factors.append(f"{name} 维度得分较高")
            elif score < 50:
                negative_factors.append(f"{name} 维度得分较低")
        return positive_factors[:5], negative_factors[:5]

    def _score_style(self, style_data: Dict, metric_scores: Dict) -> Dict:
        """风格稳定性评分 - 基于Barra因子暴露的标准差"""
        factor_stability_score = 0.0
        numeric_exposures = []
        if style_data:
            if style_data.get("data_status") == "unavailable" or style_data.get("style_factors_status") == "unavailable":
                return {
                    "score": factor_stability_score,
                    "weighted_score": factor_stability_score,
                    "count": 0,
                    "status": "insufficient_evidence",
                }
            for value in style_data.values():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric_exposures.append(float(value))
            if len(numeric_exposures) > 1:
                mean_exposure = sum(numeric_exposures) / len(numeric_exposures)
                variance = sum((x - mean_exposure) ** 2 for x in numeric_exposures) / len(numeric_exposures)
                std_dev = math.sqrt(variance)
                # 标准差越小，风格越稳定
                factor_stability_score = max(0, 100 - std_dev * 50)

        return {
            "score": round(factor_stability_score, 2),
            "weighted_score": round(factor_stability_score, 2),
            "count": len(numeric_exposures),
        }

    def _get_grade(self, score: float) -> str:
        if score >= 90:
            return "S"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "E"

    def score_manager(self, manager_data: Dict, performance_data: Dict, style_data: Dict,
                     reports_data: List[Dict]) -> Dict[str, Any]:
        """
        对基金经理进行综合评分
        基于: 从业年限、管理规模、业绩、投资理念一致性、调研纪要
        """
        # 经验评分 (管理年限越久越有价值)
        exp_years = manager_data.get("management_years", 0)
        exp_score = min(100, exp_years * 12)  # 每年12分

        # 业绩评分 (来自基金评分)
        fund_score = performance_data.get("overall_score")
        if not isinstance(fund_score, (int, float)):
            return {
                "overall_score": None,
                "overall_grade": None,
                "dimension_scores": {},
                "scoring_source": "insufficient_evidence",
                "message": "缺少可验证的管理基金业绩评分，不输出默认基金经理分。",
                "scoring_time": None,
            }
        perf_score = fund_score

        # 稳定性评分 (风格一致性)
        style_consistency = performance_data.get("style_stability")
        if not isinstance(style_consistency, (int, float)):
            style_consistency = None

        # 理念一致性评分 (从调研报告提取)
        philosophy_score = self._score_philosophy_consistency(reports_data)

        dimension_scores = {
            "experience": round(exp_score, 2),
            "performance": round(perf_score, 2),
        }

        weighted_scores = [
            (dimension_scores["experience"], 0.20),
            (dimension_scores["performance"], 0.45),
        ]
        if style_consistency is not None:
            dimension_scores["style_consistency"] = round(style_consistency, 2)
            weighted_scores.append((style_consistency, 0.20))
        if philosophy_score is not None:
            dimension_scores["philosophy_consistency"] = round(philosophy_score, 2)
            weighted_scores.append((philosophy_score, 0.15))

        weight_total = sum(weight for _, weight in weighted_scores)
        overall = sum(score * weight for score, weight in weighted_scores) / weight_total

        return {
            "overall_score": round(overall, 2),
            "overall_grade": self._get_grade(overall),
            "dimension_scores": dimension_scores,
            "scoring_source": "manager_fund_performance_evidence",
            "scoring_time": None,
        }

    def _score_philosophy_consistency(self, reports: List[Dict]) -> float:
        """
        通过调研报告内容一致性来评分
        - 分析前后报告中的投资理念表述是否一致
        - 一致性越高分数越高
        """
        if not reports or len(reports) < 2:
            return None

        # 简化版：基于关键词一致性
        key_philosophy_words = ["价值", "成长", "均衡", "集中", "分散", "估值", "质量", "景气"]
        report_keywords = []
        for r in reports:
            content = r.get("content", "") + r.get("summary", "")
            found = [w for w in key_philosophy_words if w in content]
            report_keywords.append(set(found))

        if not report_keywords:
            return None

        consistency_scores = []
        for i in range(len(report_keywords)):
            for j in range(i + 1, len(report_keywords)):
                intersection = len(report_keywords[i] & report_keywords[j])
                union = len(report_keywords[i] | report_keywords[j])
                jaccard = intersection / union if union > 0 else 0
                consistency_scores.append(jaccard)

        avg_consistency = sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0
        return round(avg_consistency * 40 + 60, 2)  # 映射到 60-100


class ManagerScoringEngine:
    """基金经理评分引擎 - 晨星风格 5 星评级"""

    DIMENSIONS = {
        "return": 0.30,        # 收益能力
        "risk_adjusted": 0.35, # 风险调整收益
        "stability": 0.20,     # 业绩稳定性
        "experience": 0.15,    # 从业经验
    }

    def score_manager(self, manager_data: Dict, funds_performance: List[Dict]) -> Dict[str, Any]:
        """
        综合评分 0-100，返回 5 星评级

        Args:
            manager_data: 经理基础信息 (tenure_years, fund_count, etc.)
            funds_performance: 管理的所有基金业绩数据列表

        Returns:
            {
                "overall_score": 0-100,
                "star_rating": 1-5,
                "dimension_scores": {...},
                "percentile_rank": 0-100,
            }
        """
        dimension_scores = {}

        # 1. 收益能力评分 (30%)
        dimension_scores["return"] = self._score_return(funds_performance)

        # 2. 风险调整收益评分 (35%)
        dimension_scores["risk_adjusted"] = self._score_risk_adjusted(funds_performance)

        # 3. 业绩稳定性评分 (20%)
        dimension_scores["stability"] = self._score_stability(funds_performance)

        # 4. 从业经验评分 (15%)
        dimension_scores["experience"] = self._score_experience(manager_data)

        # 加权综合评分
        overall_score = sum(
            dimension_scores[dim] * weight
            for dim, weight in self.DIMENSIONS.items()
        )

        # 映射到 5 星评级
        star_rating = self._score_to_stars(overall_score)

        return {
            "overall_score": round(overall_score, 2),
            "star_rating": star_rating,
            "dimension_scores": {k: round(v, 2) for k, v in dimension_scores.items()},
            "grade": self._get_grade(overall_score),
        }

    def _score_return(self, funds_performance: List[Dict]) -> float:
        """收益能力评分 - 基于管理基金的平均收益"""
        if not funds_performance:
            return 50.0

        returns_1y = [f.get("annualized_return_1y", 0) for f in funds_performance if f.get("annualized_return_1y") is not None]
        returns_3y = [f.get("annualized_return_3y", 0) for f in funds_performance if f.get("annualized_return_3y") is not None]

        if not returns_1y and not returns_3y:
            return 50.0

        # 计算平均收益
        avg_1y = sum(returns_1y) / len(returns_1y) if returns_1y else 0
        avg_3y = sum(returns_3y) / len(returns_3y) if returns_3y else 0

        # 归一化到 0-100 (-30% ~ 80% 映射到 0-100)
        score_1y = self._normalize(avg_1y * 100, -30, 80)
        score_3y = self._normalize(avg_3y * 100, -20, 50)

        # 1年权重60%, 3年权重40%
        return score_1y * 0.6 + score_3y * 0.4

    def _score_risk_adjusted(self, funds_performance: List[Dict]) -> float:
        """风险调整收益评分 - 基于夏普比率和索提诺比率"""
        if not funds_performance:
            return 50.0

        sharpe_ratios = [f.get("sharpe_ratio", 0) for f in funds_performance if f.get("sharpe_ratio") is not None]
        sortino_ratios = [f.get("sortino", 0) for f in funds_performance if f.get("sortino") is not None]

        if not sharpe_ratios and not sortino_ratios:
            return 50.0

        avg_sharpe = sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else 0
        avg_sortino = sum(sortino_ratios) / len(sortino_ratios) if sortino_ratios else 0

        # 归一化 (夏普: -1~3, 索提诺: -1~4)
        score_sharpe = self._normalize(avg_sharpe, -1, 3)
        score_sortino = self._normalize(avg_sortino, -1, 4)

        return score_sharpe * 0.6 + score_sortino * 0.4

    def _score_stability(self, funds_performance: List[Dict]) -> float:
        """业绩稳定性评分 - 基于回撤和波动率"""
        if not funds_performance:
            return 50.0

        max_drawdowns = [abs(f.get("max_drawdown", 0)) for f in funds_performance if f.get("max_drawdown") is not None]
        volatilities = [f.get("volatility", 0) for f in funds_performance if f.get("volatility") is not None]

        if not max_drawdowns and not volatilities:
            return 50.0

        avg_dd = sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else 0.2
        avg_vol = sum(volatilities) / len(volatilities) if volatilities else 0.15

        # 回撤和波动率越小越好 (0-70% 回撤, 3%-40% 波动率)
        score_dd = self._normalize(avg_dd * 100, 0, 70, reverse=True)
        score_vol = self._normalize(avg_vol * 100, 3, 40, reverse=True)

        return score_dd * 0.6 + score_vol * 0.4

    def _score_experience(self, manager_data: Dict) -> float:
        """从业经验评分 - 基于从业年限和管理基金数"""
        tenure_years = manager_data.get("tenure_years", 0)
        fund_count = manager_data.get("fund_count", 0)

        # 从业年限评分 (0-20年映射到0-100)
        tenure_score = self._normalize(tenure_years, 0, 20)

        # 管理基金数评分 (0-10只映射到0-100)
        fund_count_score = self._normalize(fund_count, 0, 10)

        return tenure_score * 0.7 + fund_count_score * 0.3

    def _normalize(self, value: float, min_val: float, max_val: float, reverse: bool = False) -> float:
        """归一化到 0-100"""
        if value is None or math.isnan(value):
            return 50.0

        if reverse:
            # 值越小越好
            if value <= min_val:
                return 100.0
            if value >= max_val:
                return 0.0
            return (max_val - value) / (max_val - min_val) * 100
        else:
            # 值越大越好
            if value <= min_val:
                return 0.0
            if value >= max_val:
                return 100.0
            return (value - min_val) / (max_val - min_val) * 100

    def _score_to_stars(self, score: float) -> int:
        """将评分映射到 1-5 星

        晨星评级分布:
        - 5星: 前10% (90-100分)
        - 4星: 10%-32.5% (67.5-90分)
        - 3星: 32.5%-67.5% (32.5-67.5分)
        - 2星: 67.5%-90% (10-32.5分)
        - 1星: 后10% (0-10分)
        """
        if score >= 90:
            return 5
        elif score >= 67.5:
            return 4
        elif score >= 32.5:
            return 3
        elif score >= 10:
            return 2
        else:
            return 1

    def _get_grade(self, score: float) -> str:
        """评分等级"""
        if score >= 90:
            return "S"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "E"


def get_fund_scoring_rules() -> List[ScoringRule]:
    """获取基金评分规则列表"""
    engine = FundScoringEngine()
    return engine.RETURN_RULES + engine.RISK_RULES + engine.RISK_ADJUSTED_RULES
