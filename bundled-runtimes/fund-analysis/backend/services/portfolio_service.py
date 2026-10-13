"""基金组合构建服务 (Portfolio Construction Service)。

研究型组合：目标配置 → 候选准入（推荐就绪池）→ 等权/自定义权重 → 组合穿透。
边界：组合是研究工具，不执行交易、不做适当性判断、不生成销售规则；
穿透分析只解释公开披露证据，覆盖率不足时披露残差。
"""
import json
import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from repositories.portfolio_repo import PortfolioRepo

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


MAX_SINGLE_WEIGHT = 0.40
WEIGHT_SUM_TOLERANCE = 0.005
CORRELATION_MIN_DAYS = 60
CORRELATION_LOOKBACK_DAYS = 500
REBALANCE_THRESHOLD = 0.05
HISTORY_METHODOLOGY = "portfolio_adj_common_dates_v2"


class PortfolioService:
    def __init__(
        self,
        repo: Optional[PortfolioRepo] = None,
        similarity_service: Optional[Any] = None,
        style_repo: Optional[Any] = None,
    ):
        self.repo = repo or PortfolioRepo()
        if similarity_service is None:
            from services.fund_holding_similarity_service import FundHoldingSimilarityService
            similarity_service = FundHoldingSimilarityService()
        self.similarity_service = similarity_service
        if style_repo is None:
            from repositories import get_holding_style_snapshot_repo
            style_repo = get_holding_style_snapshot_repo()
        self.style_repo = style_repo

    # ─────────────── 组合 CRUD ───────────────

    def create_portfolio(self, name: str, objective: Optional[str] = None, targets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        normalized = str(name or "").strip()
        if not normalized:
            raise ValueError("组合名称不能为空")
        portfolio = self.repo.create_portfolio({"name": normalized, "objective": objective})
        if targets:
            portfolio["targets"] = self._replace_targets(portfolio["id"], targets)
        else:
            portfolio["targets"] = []
        return portfolio

    def list_portfolios(self, status: Optional[str] = None) -> Dict[str, Any]:
        rows = self.repo.list_portfolios(status=status)
        return {
            "data": rows,
            "total": len(rows),
            "boundary": "组合为研究工具，不构成投资建议，不执行交易。",
        }

    def get_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        portfolio = self.repo.get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError("组合不存在")
        holdings = self.repo.list_holdings(portfolio_id)
        portfolio["targets"] = self.repo.list_targets(portfolio_id)
        portfolio["holdings"] = [self._with_evaluation_summary(item) for item in holdings]
        portfolio["weight_summary"] = self._weight_summary(holdings)
        return portfolio

    def update_portfolio(
        self,
        portfolio_id: str,
        *,
        name: Optional[str] = None,
        objective: Optional[str] = None,
        status: Optional[str] = None,
        targets: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        existing = self.repo.get_portfolio(portfolio_id)
        if not existing:
            raise ValueError("组合不存在")
        fields: Dict[str, Any] = {}
        if name is not None:
            normalized = str(name).strip()
            if not normalized:
                raise ValueError("组合名称不能为空")
            fields["name"] = normalized
        if objective is not None:
            fields["objective"] = objective
        if status is not None:
            fields["status"] = status
        if fields:
            self.repo.update_portfolio(portfolio_id, fields)
        if targets is not None:
            self._replace_targets(portfolio_id, targets)
        return self.get_portfolio(portfolio_id)

    # ─────────────── 持仓与权重 ───────────────

    def add_holding(self, portfolio_id: str, wind_code: str, note: Optional[str] = None) -> Dict[str, Any]:
        portfolio = self.repo.get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError("组合不存在")
        normalized = str(wind_code or "").strip().upper()
        admission = self.check_admission(normalized)
        if not admission["admitted"]:
            raise ValueError(admission["reason"])
        self.repo.add_holding(portfolio_id, normalized, note)
        return self.get_portfolio(portfolio_id)

    def remove_holding(self, portfolio_id: str, wind_code: str) -> Dict[str, Any]:
        if not self.repo.get_portfolio(portfolio_id):
            raise ValueError("组合不存在")
        removed = self.repo.remove_holding(portfolio_id, str(wind_code).strip().upper())
        if not removed:
            raise ValueError("持仓不存在")
        return self.get_portfolio(portfolio_id)

    def set_weights(self, portfolio_id: str, items: List[Dict[str, Any]], source: str = "custom") -> Dict[str, Any]:
        if not self.repo.get_portfolio(portfolio_id):
            raise ValueError("组合不存在")
        holdings = self.repo.list_holdings(portfolio_id)
        holding_codes = {item["wind_code"] for item in holdings}
        normalized: List[Dict[str, Any]] = []
        for item in items or []:
            code = str(item.get("wind_code") or "").strip().upper()
            weight = item.get("weight")
            if code not in holding_codes:
                raise ValueError(f"基金不在组合持仓中: {code}")
            if weight is None or not isinstance(weight, (int, float)) or not math.isfinite(float(weight)):
                raise ValueError(f"权重必须是数字: {code}")
            weight_value = float(weight)
            if weight_value <= 0:
                raise ValueError(f"权重必须为正数: {code}")
            if weight_value > MAX_SINGLE_WEIGHT + 1e-9:
                raise ValueError(f"单只基金权重不得超过 {MAX_SINGLE_WEIGHT:.0%}: {code}")
            normalized.append({"wind_code": code, "weight": weight_value})
        if not normalized:
            raise ValueError("权重清单不能为空")
        total = sum(item["weight"] for item in normalized)
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"权重合计必须为 100%（当前 {total:.1%}）")
        self.repo.set_weights(portfolio_id, normalized, source)
        return self.get_portfolio(portfolio_id)

    def equal_weights(self, portfolio_id: str) -> Dict[str, Any]:
        holdings = self.repo.list_holdings(portfolio_id)
        if not holdings:
            raise ValueError("组合暂无持仓，无法等权")
        codes = [item["wind_code"] for item in holdings]
        if 1.0 / len(codes) > MAX_SINGLE_WEIGHT + 1e-9:
            raise ValueError(f"持仓数过少（{len(codes)} 只），等权将突破单只 {MAX_SINGLE_WEIGHT:.0%} 上限")
        weight = round(1.0 / len(codes), 6)
        items = [{"wind_code": code, "weight": weight} for code in codes]
        self.repo.set_weights(portfolio_id, items, "equal")
        return self.get_portfolio(portfolio_id)

    def check_admission(self, wind_code: str) -> Dict[str, Any]:
        """候选准入：基金必须存在于基金库且有滚动指标面板（推荐就绪口径）。"""
        from sqlalchemy import text

        normalized = str(wind_code or "").strip().upper()
        engine = get_engine()
        with engine.connect() as conn:
            fund_row = conn.execute(
                text("SELECT wind_code, name FROM funds WHERE wind_code = :code"),
                {"code": normalized},
            ).fetchone()
            if not fund_row:
                return {
                    "admitted": False,
                    "reason": f"基金不存在于本地基金库: {normalized}",
                    "wind_code": normalized,
                }
            metric_row = conn.execute(
                text(
                    """
                    SELECT MAX(as_of_date)
                    FROM metric_snapshots
                    WHERE target_type = 'fund' AND target_id = :code
                    """
                ),
                {"code": normalized},
            ).fetchone()
        latest_metric_date = metric_row[0] if metric_row else None
        if not latest_metric_date:
            return {
                "admitted": False,
                "reason": f"{normalized} 尚无滚动指标面板，不满足推荐就绪口径；请先补齐净值与滚动指标。",
                "wind_code": normalized,
            }
        return {
            "admitted": True,
            "reason": "基金存在且有滚动指标面板（推荐就绪口径）。",
            "wind_code": normalized,
            "fund_name": str(fund_row[1]) if fund_row else None,
            "latest_metric_date": str(latest_metric_date),
        }

    # ─────────────── 组合穿透分析 ───────────────

    def analyze(self, portfolio_id: str) -> Dict[str, Any]:
        portfolio = self.get_portfolio(portfolio_id)
        holdings = portfolio["holdings"]
        codes = [item["wind_code"] for item in holdings]
        weights = self._effective_weights(holdings)

        overlap = self.similarity_service.build(codes) if len(codes) >= 2 else {
            "status": "insufficient",
            "reason": "至少两只持仓才能比较重仓股重叠。",
        }
        style_aggregate = self._style_aggregate(codes, weights)
        correlation = self._correlation_matrix(codes, weights)

        return {
            "portfolio_id": portfolio_id,
            "name": portfolio["name"],
            "holding_count": len(codes),
            "codes": codes,
            "weights": weights,
            "weights_basis": "saved" if self._weight_summary(holdings)["is_complete"] else "equal_weight_assumption",
            "weight_summary": portfolio["weight_summary"],
            "overlap": overlap,
            "style_aggregate": style_aggregate,
            "correlation": correlation,
            "boundary": "组合穿透只基于公开披露持仓与历史净值；覆盖率不足的结论以残差披露，不构成完整组合画像或投资建议。",
        }

    # ─────────────── 基础回测（仅解释，不优化） ───────────────

    def backtest(
        self,
        portfolio_id: str,
        *,
        lookback_days: int = 365,
        benchmark_wind_code: Optional[str] = None,
        save_snapshot: bool = False,
    ) -> Dict[str, Any]:
        """以当前权重合成历史组合净值曲线：累计收益/年化/最大回撤/波动，并与基准对比。

        边界：这是解释性回测（用当前权重回看历史），不是优化或选基依据；
        样本不足时明确拒绝，不做归因、不做参数优化。
        """
        portfolio = self.get_portfolio(portfolio_id)
        holdings = portfolio["holdings"]
        if not holdings:
            raise ValueError("组合暂无持仓，无法回测")
        weights = self._effective_weights(holdings)
        # 零权重成分不应压缩组合样本；容差内的权重归一化明确披露。
        input_weights = weights
        total_weight = sum(weights.values())
        weights = {code: weight / total_weight for code, weight in weights.items() if weight > 0}
        codes = list(weights)

        nav_map = self._load_nav_series(codes, lookback_days)
        # 先对齐净值点，再计算完全相同起止日的区间收益，不对缺失日填零。
        common_days = sorted(set.intersection(*(set(nav_map[code].keys()) for code in codes))) if codes else []
        if len(common_days) < CORRELATION_MIN_DAYS + 1:
            return {
                "status": "insufficient_sample",
                "methodology_version": HISTORY_METHODOLOGY,
                "nav_basis": "adj_nav",
                "reason": f"正权重持仓共同复权净值点仅 {len(common_days)} 个（至少 {CORRELATION_MIN_DAYS + 1} 个），不输出回测结论；不以累计或单位净值冒充复权数据。",
                "holding_count": len(codes),
            }

        portfolio_returns = [
            sum(weights[code] * (nav_map[code][end] / nav_map[code][start] - 1) for code in codes)
            for start, end in zip(common_days, common_days[1:])
        ]
        union_days = set().union(*(set(nav_map[code]) for code in codes))
        common_set = set(common_days)
        omitted_days = sum(common_days[0] <= day <= common_days[-1] and day not in common_set for day in union_days)
        curve = [1.0, *self._equity_curve(portfolio_returns)]
        metrics = self._performance_metrics(portfolio_returns, common_days, allow_volatility=omitted_days == 0)

        # 显式指定的基金映射基准不得静默替换；自动选择也必须覆盖相同日期网格。
        candidates = [str(benchmark_wind_code).strip().upper()] if benchmark_wind_code else sorted(weights, key=weights.get, reverse=True)
        benchmark_source = candidates[0]
        benchmark_series = {}
        for code in candidates:
            candidate = self._load_benchmark_series(code, common_days[0], common_days[-1])
            if all(day in candidate for day in common_days):
                benchmark_source, benchmark_series = code, candidate
                break

        benchmark_metadata = self._load_benchmark_metadata(benchmark_source)
        benchmark_block: Dict[str, Any] = {
            "source": benchmark_source,
            "source_fund_code": benchmark_source,
            "code": benchmark_metadata.get("code"),
            "name": benchmark_metadata.get("name"),
            "status": "insufficient",
            "reason": "基准未覆盖组合全部共同日期，不计算异区间超额收益。",
            "selection_basis": "explicit_fund_mapping" if benchmark_wind_code else "automatic_fund_mapping",
        }
        if benchmark_series:
            bench_returns = [
                benchmark_series[end] / benchmark_series[start] - 1.0
                for start, end in zip(common_days, common_days[1:])
            ]
            bench_metrics = self._performance_metrics(bench_returns, common_days, allow_volatility=omitted_days == 0)
            benchmark_block.update({
                "status": "available",
                "reason": None,
                "aligned_to_portfolio": True,
                "basis_note": (
                    f"基准为 {benchmark_metadata.get('name') or benchmark_metadata.get('code') or '持仓基金分类映射基准'}"
                    f"；取自 {benchmark_source} 的 fund_nav.benchmark_nav，使用组合完全相同的日期网格。当前分类映射不代表历史组合政策基准。"
                ),
                "metrics": bench_metrics,
                "excess_return": round(metrics["cumulative_return"] - bench_metrics["cumulative_return"], 6),
            })

        result = {
            "status": "available",
            "methodology_version": HISTORY_METHODOLOGY,
            "nav_basis": "adj_nav",
            "portfolio_id": portfolio_id,
            "name": portfolio["name"],
            "weights_basis": ("已保存权重" if self._weight_summary(holdings)["is_complete"] else "等权假设") + "归一化；假设在每个共同净值日恢复固定权重，不是买入持有或实盘业绩",
            "input_weights": input_weights,
            "weights": weights,
            "sample": {
                "days": len(common_days),
                "start_date": str(common_days[0]),
                "end_date": str(common_days[-1]),
                "lookback_days": lookback_days,
                "return_intervals": len(portfolio_returns),
                "omitted_union_dates": omitted_days,
                "requested_start_date": (date.today() - timedelta(days=lookback_days)).isoformat(),
                "requested_end_date": date.today().isoformat(),
                "data_lag_calendar_days": (date.today() - date.fromisoformat(common_days[-1])).days,
            },
            "metrics": metrics,
            "curve": [
                {"date": str(common_days[i]), "value": curve[i]}
                for i in range(len(curve))
            ],
            "benchmark": benchmark_block,
            "boundary": "以当前成分回看过去，存在事后选样偏差，不是可执行策略或实盘业绩。共同日期间按固定权重再平衡，不填补缺失净值；年化收益按实际日历跨度计算。缺日或长间隔时不输出年化波动。不含申赎费用、滑点、税费及执行限制。",
        }

        if save_snapshot:
            self._save_portfolio_snapshot(portfolio_id, holdings, weights, result)

        return result

    # ─────────────── 组合监控 ───────────────

    def monitor(self, portfolio_id: str) -> Dict[str, Any]:
        """组合健康检查：目标配置偏离 + 成分风格漂移 + 再平衡提示。"""
        from services.holding_style_drift_service import HoldingStyleDriftService

        portfolio = self.get_portfolio(portfolio_id)
        holdings = portfolio["holdings"]
        targets = portfolio["targets"]
        weights = self._effective_weights(holdings)

        # 1) 按同类组聚合实际权重 vs 目标权重（未配置目标时只披露实际权重，不做偏离判定）
        group_weights: Dict[str, float] = {}
        group_names: Dict[str, str] = {}
        for item in holdings:
            group = self._holding_peer_group(item["wind_code"])
            group_weights[group] = group_weights.get(group, 0.0) + weights.get(item["wind_code"], 0.0)
            if group not in group_names:
                name = self._peer_group_name(group)
                group_names[group] = name or ("未分类（待补评价/风格快照）" if group == "unclassified" else group)
        unclassified_weight = group_weights.get("unclassified", 0.0)
        deviations = []
        if targets:
            for target in targets:
                key = str(target.get("peer_group_key") or "")
                target_weight = float(target.get("target_weight") or 0)
                actual = group_weights.pop(key, 0.0)
                deviations.append({
                    "peer_group_key": key,
                    "peer_group_name": target.get("peer_group_name") or group_names.get(key, key),
                    "target_weight": target_weight,
                    "actual_weight": round(actual, 6),
                    "deviation": round(actual - target_weight, 6),
                    "needs_rebalance": abs(actual - target_weight) > REBALANCE_THRESHOLD,
                })
            for key, actual in group_weights.items():
                deviations.append({
                    "peer_group_key": key,
                    "peer_group_name": group_names.get(key, key),
                    "target_weight": 0.0,
                    "actual_weight": round(actual, 6),
                    "deviation": round(actual, 6),
                    "needs_rebalance": actual > REBALANCE_THRESHOLD,
                })
        else:
            # 未配置目标同类组权重：不能把目标当 0% 判偏离，只披露实际分组权重
            for key, actual in group_weights.items():
                deviations.append({
                    "peer_group_key": key,
                    "peer_group_name": group_names.get(key, key),
                    "target_weight": None,
                    "actual_weight": round(actual, 6),
                    "deviation": None,
                    "needs_rebalance": False,
                })

        # 2) 成分基金风格漂移
        drift_service = HoldingStyleDriftService()
        drift_items = []
        for item in holdings:
            drift = drift_service.get(item["wind_code"])
            drift_items.append({
                "wind_code": item["wind_code"],
                "fund_name": item.get("fund_name"),
                "status": drift.get("status"),
                "level": drift.get("level"),
                "label": drift.get("label"),
                "note": (drift.get("note") or "")[:120],
                "previous_quarter": drift.get("previous_quarter"),
                "latest_quarter": drift.get("latest_quarter"),
            })

        weights_complete = self._weight_summary(holdings)["is_complete"]
        target_total = sum(float(item.get("target_weight") or 0) for item in targets)
        target_assessable = bool(targets) and abs(target_total - 1.0) <= WEIGHT_SUM_TOLERANCE and weights_complete and unclassified_weight == 0
        rebalance_needed = any(item["needs_rebalance"] for item in deviations) if target_assessable else None
        if not target_assessable:
            for item in deviations:
                item["needs_rebalance"] = None
        assessed = [item for item in drift_items if item.get("status") == "available" and item.get("level") in ("low", "medium", "high")]
        drift_alerts = [item for item in assessed if item.get("level") in ("high", "medium")]
        missing_count = len(holdings) - len(assessed)
        if not targets:
            deviation_summary = "未配置目标同类组权重，暂不做再平衡判定（仅披露实际分组权重）；"
        elif not target_assessable:
            deviation_summary = "权重、目标或分类证据不完整，暂不做再平衡判定；"
        else:
            deviation_summary = "配置偏离超阈值，需复核；" if rebalance_needed else "已检查配置偏离未超阈值；"
        drift_summary = f"已判定 {len(assessed)}/{len(holdings)} 只成分，{len(drift_alerts)} 只出现风格漂移信号。"
        if missing_count or not holdings:
            drift_summary += "证据不足部分不能判断为稳定。"
        return {
            "status": "available" if target_assessable and not missing_count else "partial",
            "portfolio_id": portfolio_id,
            "name": portfolio["name"],
            "target_configured": bool(targets),
            "target_assessable": target_assessable,
            "weights": weights,
            "weights_basis": "saved" if weights_complete else "equal_weight_assumption",
            "drift_coverage": {"assessed_count": len(assessed), "total_count": len(holdings), "missing_count": missing_count,
                               "assessed_weight": round(sum(weights.get(item["wind_code"], 0) for item in assessed), 6)},
            "target_deviations": deviations,
            "rebalance_threshold": REBALANCE_THRESHOLD,
            "rebalance_needed": rebalance_needed,
            "style_drifts": drift_items,
            "drift_alerts": drift_alerts,
            "summary": deviation_summary + drift_summary,
            "boundary": "监控为研究提示，不自动执行任何申赎动作。",
        }

    # ─────────────── 交易清单（研究输出，不执行） ───────────────

    def trade_list(
        self,
        portfolio_id: str,
        current_positions: List[Dict[str, Any]],
        total_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        """目标组合 vs 当前持仓差异 → 申赎建议清单。

        边界：清单是研究输出，仅供专业用户自行决策；系统不做适当性判断，不执行交易。
        """
        portfolio = self.get_portfolio(portfolio_id)
        holdings = portfolio["holdings"]
        if not holdings:
            raise ValueError("组合暂无持仓，无法生成清单")
        target_weights = self._effective_weights(holdings)

        current_weights: Dict[str, float] = {}
        for item in current_positions or []:
            code = str(item.get("wind_code") or "").strip().upper()
            weight = item.get("weight")
            if not code:
                continue
            if weight is not None and isinstance(weight, (int, float)):
                current_weights[code] = float(weight)
            else:
                current_weights[code] = None  # 仅登记存在，权重未知

        latest_nav = self._latest_nav_map(list(set(list(target_weights) + list(current_weights))))
        rows = []
        all_codes = sorted(set(list(target_weights) + list(current_weights)))
        for code in all_codes:
            target = target_weights.get(code, 0.0)
            current = current_weights.get(code)
            if current is None:
                if code in target_weights:
                    current = 0.0
                else:
                    continue
            delta = target - current
            if abs(delta) < 0.005:
                continue
            nav_item = latest_nav.get(code) or {}
            nav_value = nav_item.get("nav")
            amount = round(total_amount * delta, 2) if total_amount and nav_value else None
            shares = round(amount / nav_value, 2) if amount is not None and nav_value else None
            rows.append({
                "wind_code": code,
                "fund_name": nav_item.get("name"),
                "action": "申购" if delta > 0 else "赎回",
                "current_weight": round(current, 6),
                "target_weight": round(target, 6),
                "weight_delta": round(delta, 6),
                "amount": amount,
                "shares": shares,
                "latest_nav": nav_value,
                "nav_date": nav_item.get("nav_date"),
            })
        rows.sort(key=lambda item: abs(item["weight_delta"]), reverse=True)
        return {
            "status": "available",
            "portfolio_id": portfolio_id,
            "name": portfolio["name"],
            "total_amount": total_amount,
            "items": rows,
            "boundary": "交易清单为研究输出，仅供专业用户自行决策；不含费用测算，不构成投资建议，系统不执行任何交易。",
        }

    # ─────────────── 内部工具 ───────────────

    def _replace_targets(self, portfolio_id: str, targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        total = 0.0
        for item in targets or []:
            key = str(item.get("peer_group_key") or "").strip()
            if not key:
                raise ValueError("目标配置的同类组不能为空")
            weight = item.get("target_weight")
            if weight is None or not isinstance(weight, (int, float)) or float(weight) <= 0:
                raise ValueError(f"目标权重必须为正数: {key}")
            total += float(weight)
            normalized.append({
                "peer_group_key": key,
                "peer_group_name": item.get("peer_group_name"),
                "target_weight": float(weight),
                "note": item.get("note"),
            })
        if normalized and abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"目标配置权重合计必须为 100%（当前 {total:.1%}）")
        return self.repo.replace_targets(portfolio_id, normalized)

    def _with_evaluation_summary(self, holding: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text

        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT overall_score, overall_grade, evaluation_window, created_at
                    FROM fund_evaluation_snapshots
                    WHERE wind_code = :code
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"code": holding["wind_code"]},
            ).fetchone()
        summary = {
            "overall_score": float(row[0]) if row and row[0] is not None else None,
            "grade": row[1] if row else None,
            "evaluation_window": row[2] if row else None,
            "evaluated_at": str(row[3].date()) if row and row[3] else None,
        }
        return {**holding, "evaluation": summary}

    @staticmethod
    def _weight_summary(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        weighted = [item for item in holdings if item.get("weight") is not None]
        total = sum(float(item["weight"]) for item in weighted)
        return {
            "holding_count": len(holdings),
            "weighted_count": len(weighted),
            "total_weight": round(total, 6),
            "is_complete": bool(holdings) and len(weighted) == len(holdings) and all(math.isfinite(float(item["weight"])) and 0 <= float(item["weight"]) <= 1 for item in weighted) and abs(total - 1.0) <= WEIGHT_SUM_TOLERANCE,
        }

    @staticmethod
    def _effective_weights(holdings: List[Dict[str, Any]]) -> Dict[str, float]:
        weighted = {
            item["wind_code"]: float(item["weight"])
            for item in holdings
            if item.get("weight") is not None
        }
        if PortfolioService._weight_summary(holdings)["is_complete"]:
            return weighted
        # 未设置完整权重时按等权聚合并披露
        equal = 1.0 / len(holdings) if holdings else 0.0
        return {item["wind_code"]: equal for item in holdings}

    def _style_aggregate(self, codes: List[str], weights: Dict[str, float]) -> Dict[str, Any]:
        if not codes:
            return {"status": "insufficient", "reason": "组合暂无持仓。"}
        snapshots = self.style_repo.get_latest_map(codes)
        if not snapshots:
            return {
                "status": "insufficient",
                "reason": "组合持仓均无公开持仓风格快照，暂不能聚合风格暴露。",
                "coverage": 0.0,
            }
        factor_totals: Dict[str, Dict[str, Any]] = {}
        covered_codes = set()
        for code in codes:
            snapshot = snapshots.get(code)
            if not snapshot:
                continue
            weight = weights.get(code, 0.0)
            seen = set()
            for descriptor in snapshot.get("descriptors") or []:
                if not isinstance(descriptor, dict):
                    continue
                factor = str(descriptor.get("factor") or "").strip()
                exposure = descriptor.get("exposure")
                if not factor or factor in seen or isinstance(exposure, bool) or not isinstance(exposure, (int, float)) or not math.isfinite(exposure):
                    continue
                seen.add(factor)
                covered_codes.add(code)
                bucket = factor_totals.setdefault(factor, {
                    "label": str(descriptor.get("label") or factor),
                    "unit": descriptor.get("unit"),
                    "weighted_exposure": 0.0,
                    "covered_weight": 0.0,
                    "quarters": set(),
                    "units": set(),
                    "undated": False,
                })
                bucket["weighted_exposure"] += float(exposure) * weight
                bucket["covered_weight"] += weight
                bucket["units"].add(descriptor.get("unit"))
                if snapshot.get("quarter"):
                    bucket["quarters"].add(str(snapshot["quarter"]))
                else:
                    bucket["undated"] = True
        factors = [
            {
                "factor": factor,
                "label": bucket["label"],
                "unit": bucket["unit"],
                "weighted_exposure": round(bucket["weighted_exposure"], 6) if len(bucket["units"]) == 1 else None,
                "status": "available" if len(bucket["units"]) == 1 else "incomparable_units",
                "coverage": round(bucket["covered_weight"], 6),
                "quarters": sorted(bucket["quarters"]),
                "undated": bucket["undated"],
            }
            for factor, bucket in sorted(factor_totals.items())
        ]
        covered_weight = sum(weights.get(code, 0.0) for code in covered_codes)
        return {
            "status": "available" if factors else "insufficient",
            "quarter_basis": "各持仓最新已披露季度（可能不完全一致）",
            "coverage": round(covered_weight, 6),
            "coverage_note": f"至少有一个有效因子的基金占计算权重 {covered_weight:.1%}；每个因子覆盖单独列示。这不是底层资产穿透率，未覆盖部分未知。",
            "factors": factors,
        }

    def _correlation_matrix(self, codes: List[str], weights: Dict[str, float]) -> Dict[str, Any]:
        if len(codes) < 2:
            return {"status": "insufficient", "methodology_version": HISTORY_METHODOLOGY,
                    "nav_basis": "adj_nav", "reason": "至少两只持仓才能计算净值相关性。"}
        nav_map = self._load_nav_series(codes, CORRELATION_LOOKBACK_DAYS)
        pairs = []
        for i, code_a in enumerate(codes):
            for code_b in codes[i + 1:]:
                a, b = nav_map[code_a], nav_map[code_b]
                common = sorted(set(a) & set(b))
                intervals = max(0, len(common) - 1)
                sample = {"fund_a": code_a, "fund_b": code_b, "overlap_days": len(common),
                          "return_intervals": intervals, "start_date": common[0] if common else None,
                          "end_date": common[-1] if common else None}
                if intervals < CORRELATION_MIN_DAYS:
                    pairs.append({
                        **sample,
                        "correlation": None,
                        "status": "insufficient_overlap",
                    })
                    continue
                values_a = [a[end] / a[start] - 1 for start, end in zip(common, common[1:])]
                values_b = [b[end] / b[start] - 1 for start, end in zip(common, common[1:])]
                correlation = self._pearson(values_a, values_b)
                pairs.append({
                    **sample,
                    "correlation": round(correlation, 4) if correlation is not None else None,
                    "status": "ok" if correlation is not None else "zero_variance",
                })
        return {
            "status": "available" if any(pair["status"] == "ok" for pair in pairs) else "insufficient",
            "methodology_version": HISTORY_METHODOLOGY,
            "nav_basis": "adj_nav",
            "lookback_days": CORRELATION_LOOKBACK_DAYS,
            "min_overlap_days": CORRELATION_MIN_DAYS,
            "pairs": pairs,
            "note": "仅使用 adj_nav，先对齐配对共同净值日期再计算区间收益；间隔可能不等长，不冒充逐日相关性。每对样本区间可能不同；常数序列相关性未定义，不记为零。",
        }

    @staticmethod
    def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
        n = len(xs)
        if n < 2 or n != len(ys):
            return None
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x <= 1e-24 or var_y <= 1e-24:
            return None
        return max(-1.0, min(1.0, cov / math.sqrt(var_x * var_y)))

    # ─────────────── 回测/监控/清单工具 ───────────────

    def _load_nav_series(self, codes: List[str], lookback_days: int) -> Dict[str, Dict[str, float]]:
        """自然日窗口内的复权净值点；不拼接累计净值或单位净值。"""
        from sqlalchemy import text

        engine = get_engine()
        result: Dict[str, Dict[str, float]] = {}
        with engine.connect() as conn:
            for code in codes:
                rows = conn.execute(
                    text(
                        """
                        SELECT trade_date, adj_nav
                        FROM fund_nav
                        WHERE wind_code = :code
                          AND trade_date BETWEEN CAST(:start AS DATE) AND CAST(:end AS DATE)
                        ORDER BY trade_date
                        """
                    ),
                    {"code": code, "start": (date.today() - timedelta(days=lookback_days)).isoformat(), "end": date.today().isoformat()},
                ).fetchall()
                result[code] = {str(row[0]): float(row[1]) for row in rows
                                if row[1] is not None and math.isfinite(float(row[1])) and float(row[1]) > 0}
        return result

    def _load_benchmark_series(self, wind_code: str, start_date: str, end_date: str) -> Dict[str, float]:
        """取某基金自带的分类映射基准净值序列（fund_nav.benchmark_nav）。"""
        from sqlalchemy import text

        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT trade_date, benchmark_nav
                    FROM fund_nav
                    WHERE wind_code = :code AND benchmark_nav IS NOT NULL AND benchmark_nav != 0
                      AND trade_date BETWEEN CAST(:start AS DATE) AND CAST(:end AS DATE)
                    ORDER BY trade_date
                    """
                ),
                {"code": wind_code, "start": str(start_date), "end": str(end_date)},
            ).fetchall()
        return {str(row[0]): float(row[1]) for row in rows if row[1] is not None and math.isfinite(float(row[1])) and float(row[1]) > 0}

    def _load_benchmark_metadata(self, wind_code: str) -> Dict[str, Optional[str]]:
        """返回该基金当前分类映射的真实基准代码与名称。"""
        from sqlalchemy import text

        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT bm.benchmark_code, bm.benchmark_name
                    FROM funds f
                    JOIN fund_share_classes sc ON sc.fund_id::text = f.id::text
                    JOIN benchmark_mappings bm ON bm.entity_id::text = sc.entity_id::text
                    WHERE f.wind_code = :code AND bm.status = 'active'
                    ORDER BY bm.effective_from DESC NULLS LAST, bm.updated_at DESC
                    LIMIT 1
                    """
                ),
                {"code": wind_code},
            ).fetchone()
        return {
            "code": str(row[0]) if row and row[0] else None,
            "name": str(row[1]) if row and row[1] else None,
        }

    @staticmethod
    def _equity_curve(returns: List[float]) -> List[float]:
        curve: List[float] = []
        value = 1.0
        for daily in returns:
            value *= 1.0 + daily
            curve.append(round(value, 8))
        return curve

    @staticmethod
    def _performance_metrics(returns: List[float], dates: List[Any], *, allow_volatility: bool = True) -> Dict[str, Any]:
        if not returns:
            return {}
        curve = [1.0, *PortfolioService._equity_curve(returns)]
        cumulative = curve[-1] - 1.0
        days = len(returns)
        elapsed_days = (date.fromisoformat(str(dates[-1])) - date.fromisoformat(str(dates[0]))).days
        annualized = (1.0 + cumulative) ** (365.25 / elapsed_days) - 1.0 if elapsed_days > 0 else None
        mean_daily = sum(returns) / days
        variance = sum((item - mean_daily) ** 2 for item in returns) / max(days - 1, 1)
        max_gap = max((date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days for start, end in zip(dates, dates[1:]))
        volatility = math.sqrt(variance * days * 365.25 / elapsed_days) if allow_volatility and max_gap <= 7 and elapsed_days > 0 and days > 1 else None
        peak = curve[0]
        max_drawdown = 0.0
        for value in curve:
            if value > peak:
                peak = value
            drawdown = value / peak - 1.0 if peak else 0.0
            max_drawdown = min(max_drawdown, drawdown)
        return {
            "cumulative_return": round(cumulative, 6),
            "annualized_return": round(annualized, 6) if annualized is not None else None,
            "annualized_volatility": round(volatility, 6) if volatility is not None else None,
            "volatility_note": "按实际观测频率年化的估计" if volatility is not None else "共同日期存在缺日或超过 7 个自然日的间隔，暂不年化波动",
            "annualization_basis": "actual_calendar_days_365.25",
            "max_drawdown": round(max_drawdown, 6),
            "sample_days": days,
            "start_date": str(dates[0]) if dates else None,
            "end_date": str(dates[-1]) if dates else None,
        }

    @staticmethod
    def _holding_peer_group(wind_code: str) -> str:
        """持仓同类组 key：优先评价快照，其次风格快照，均无则 unclassified。"""
        from sqlalchemy import text

        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT peer_group_id FROM fund_evaluation_snapshots
                    WHERE wind_code = :code AND peer_group_id IS NOT NULL
                    ORDER BY created_at DESC LIMIT 1
                    """
                ),
                {"code": wind_code},
            ).fetchone()
            if not row:
                row = conn.execute(
                    text(
                        """
                        SELECT peer_group_key FROM holding_style_snapshots
                        WHERE wind_code = :code AND peer_group_key IS NOT NULL
                        ORDER BY quarter DESC LIMIT 1
                        """
                    ),
                    {"code": wind_code},
                ).fetchone()
        return str(row[0]) if row else "unclassified"

    @staticmethod
    def _peer_group_name(group_key: str) -> Optional[str]:
        from sqlalchemy import text

        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name FROM peer_groups WHERE key = :key LIMIT 1"),
                {"key": group_key},
            ).fetchone()
            if not row:
                try:
                    import uuid as _uuid

                    _uuid.UUID(str(group_key))
                except (ValueError, TypeError):
                    return None
                row = conn.execute(
                    text("SELECT name FROM peer_groups WHERE id = CAST(:key AS UUID) LIMIT 1"),
                    {"key": group_key},
                ).fetchone()
        return str(row[0]) if row else None

    @staticmethod
    def _latest_nav_map(codes: List[str]) -> Dict[str, Dict[str, Any]]:
        from sqlalchemy import text

        engine = get_engine()
        result: Dict[str, Dict[str, Any]] = {}
        with engine.connect() as conn:
            for code in codes:
                nav_row = conn.execute(
                    text(
                        """
                        SELECT nav, trade_date FROM fund_nav
                        WHERE wind_code = :code AND nav IS NOT NULL
                        ORDER BY trade_date DESC LIMIT 1
                        """
                    ),
                    {"code": code},
                ).fetchone()
                name_row = conn.execute(
                    text("SELECT name FROM funds WHERE wind_code = :code"),
                    {"code": code},
                ).fetchone()
                result[code] = {
                    "nav": float(nav_row[0]) if nav_row and nav_row[0] is not None else None,
                    "nav_date": str(nav_row[1]) if nav_row else None,
                    "name": str(name_row[0]) if name_row else None,
                }
        return result

    def _save_portfolio_snapshot(
        self,
        portfolio_id: str,
        holdings: List[Dict[str, Any]],
        weights: Dict[str, float],
        backtest_result: Dict[str, Any],
    ) -> None:
        """回测可选落一份组合画像快照（M5 起写入，供后续时序对比）。"""
        from sqlalchemy import text

        engine = get_engine()
        analysis = self.analyze(portfolio_id)
        sample = backtest_result.get("sample") or {}
        total_weight = sum(weights.values())
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO portfolio_snapshots
                        (portfolio_id, snapshot_date, holding_count, total_weight,
                         style_aggregate, overlap_matrix, correlation_matrix, coverage)
                    VALUES (CAST(:portfolio_id AS UUID), CAST(:snapshot_date AS DATE), :holding_count, :total_weight,
                            CAST(:style_aggregate AS JSONB), CAST(:overlap AS JSONB), CAST(:correlation AS JSONB), CAST(:coverage AS JSONB))
                    """
                ),
                {
                    "portfolio_id": str(portfolio_id),
                    "snapshot_date": sample.get("end_date") or __import__("datetime").date.today().isoformat(),
                    "holding_count": len(holdings),
                    "total_weight": round(total_weight, 6),
                    "style_aggregate": json.dumps(analysis.get("style_aggregate") or {}, ensure_ascii=False, default=str),
                    "overlap": json.dumps(analysis.get("overlap") or {}, ensure_ascii=False, default=str),
                    "correlation": json.dumps(analysis.get("correlation") or {}, ensure_ascii=False, default=str),
                    "coverage": json.dumps({"backtest_metrics": backtest_result.get("metrics") or {}}, ensure_ascii=False, default=str),
                },
            )
