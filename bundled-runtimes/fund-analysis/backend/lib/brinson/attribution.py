"""使用真实行业权重和同期收益的 Brinson-Fachler 归因。"""
from typing import Any, Dict, List


MIN_PORTFOLIO_COVERAGE = 0.20


class BrinsonAttributor:
    """Brinson 业绩归因计算器"""

    def calculate_from_industry_inputs(
        self,
        portfolio_industries: Dict[str, Dict[str, float]],
        benchmark_industries: Dict[str, Dict[str, float]],
        fund_return: float,
        benchmark_return: float,
        portfolio_coverage: float,
        benchmark_coverage: float,
        return_coverage: float,
    ) -> Dict[str, Any]:
        """使用明确的行业权重与区间收益计算 Brinson-Fachler 归因。"""
        if not portfolio_industries:
            return self._unavailable_attribution(
                fund_return,
                benchmark_return,
                ["基金行业权重缺失，不能计算 Brinson 配置与选择效应"],
            )
        if not benchmark_industries:
            return self._unavailable_attribution(
                fund_return,
                benchmark_return,
                ["基准行业权重缺失，不能计算 Brinson 配置效应"],
            )
        if portfolio_coverage < MIN_PORTFOLIO_COVERAGE:
            return self._unavailable_attribution(
                fund_return,
                benchmark_return,
                [
                    f"基金持仓披露覆盖率仅 {portfolio_coverage:.1%}，"
                    f"低于 {MIN_PORTFOLIO_COVERAGE:.0%} 最低门槛，不输出行业配置与选择效应。"
                ],
                coverage={
                    "portfolio_holdings": round(portfolio_coverage, 6),
                    "benchmark_constituents": round(benchmark_coverage, 6),
                    "holding_returns": round(return_coverage, 6),
                },
            )

        allocation_effect = 0.0
        selection_effect = 0.0
        interaction_effect = 0.0
        industry_details = []
        missing_items = []
        skipped_portfolio_weight = 0.0

        for industry in sorted(set(portfolio_industries) | set(benchmark_industries)):
            portfolio = portfolio_industries.get(industry) or {}
            benchmark = benchmark_industries.get(industry) or {}
            portfolio_weight = float(portfolio.get("weight") or 0)
            benchmark_weight = float(benchmark.get("weight") or 0)
            benchmark_industry_return = benchmark.get("return")
            portfolio_industry_return = portfolio.get("return")

            if benchmark_industry_return is None and benchmark_weight == 0 and portfolio_weight > 0:
                benchmark_industry_return = benchmark_return
            if benchmark_industry_return is None:
                missing_items.append(f"{industry} 缺少基准行业收益")
                skipped_portfolio_weight += portfolio_weight
                continue
            if portfolio_weight > 0 and portfolio_industry_return is None:
                missing_items.append(f"{industry} 缺少基金持仓区间收益")
                skipped_portfolio_weight += portfolio_weight
                continue
            if portfolio_industry_return is None:
                portfolio_industry_return = benchmark_industry_return

            allocation = (portfolio_weight - benchmark_weight) * (
                float(benchmark_industry_return) - benchmark_return
            )
            selection = benchmark_weight * (
                float(portfolio_industry_return) - float(benchmark_industry_return)
            )
            interaction = (portfolio_weight - benchmark_weight) * (
                float(portfolio_industry_return) - float(benchmark_industry_return)
            )

            allocation_effect += allocation
            selection_effect += selection
            interaction_effect += interaction
            industry_details.append({
                "industry": industry,
                "portfolio_weight": round(portfolio_weight, 6),
                "benchmark_weight": round(benchmark_weight, 6),
                "weight_diff": round(portfolio_weight - benchmark_weight, 6),
                "portfolio_return": round(float(portfolio_industry_return), 6),
                "benchmark_return": round(float(benchmark_industry_return), 6),
                "allocation_contrib": round(allocation, 6),
                "selection_contrib": round(selection, 6),
                "interaction_contrib": round(interaction, 6),
            })

        if not industry_details:
            return self._unavailable_attribution(fund_return, benchmark_return, missing_items)

        active_return = fund_return - benchmark_return
        explained_return = allocation_effect + selection_effect + interaction_effect
        residual = active_return - explained_return
        if portfolio_coverage < 0.8:
            missing_items.append(f"基金持仓披露覆盖率仅 {portfolio_coverage:.1%}，结果只代表已披露持仓")
        if benchmark_coverage < 0.95:
            missing_items.append(f"基准成分收益覆盖率仅 {benchmark_coverage:.1%}")
        if return_coverage < 0.95:
            missing_items.append(f"基金持仓收益覆盖率仅 {return_coverage:.1%}")
        if skipped_portfolio_weight > 0:
            missing_items.append(f"约 {skipped_portfolio_weight:.2%} 的已披露持仓因行情或行业收益缺失未进入效应分解")

        industry_details.sort(
            key=lambda item: abs(item["allocation_contrib"] + item["selection_contrib"] + item["interaction_contrib"]),
            reverse=True,
        )
        return {
            "status": "partial_evidence" if missing_items else "ok",
            "source": "brinson_fachler_industry_inputs",
            "active_return": round(active_return, 6),
            "allocation_effect": round(allocation_effect, 6),
            "selection_effect": round(selection_effect, 6),
            "interaction_effect": round(interaction_effect, 6),
            "residual": round(residual, 6),
            "explained_return": round(explained_return, 6),
            "industry_details": industry_details,
            "coverage": {
                "portfolio_holdings": round(portfolio_coverage, 6),
                "benchmark_constituents": round(benchmark_coverage, 6),
                "holding_returns": round(return_coverage, 6),
                "skipped_portfolio_weight": round(skipped_portfolio_weight, 6),
            },
            "missing_items": missing_items,
        }

    def _unavailable_attribution(
        self,
        fund_return: float,
        benchmark_return: float,
        missing_items: List[str],
        coverage: Dict[str, float] | None = None,
    ) -> Dict[str, Any]:
        """证据不足时显式返回不可用，禁止用随机/估算数据冒充归因。"""
        active = fund_return - benchmark_return
        return {
            "status": "insufficient_evidence",
            "source": "evidence_gate",
            "active_return": round(active, 4),
            "allocation_effect": None,
            "selection_effect": None,
            "interaction_effect": None,
            "residual": None,
            "explained_return": None,
            "industry_details": [],
            "coverage": coverage or {},
            "missing_items": missing_items,
        }
