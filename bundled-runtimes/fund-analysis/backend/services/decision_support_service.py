"""决策支持 (Decision Support) — 反向证据 / 三选一辅助 / 同类组基准回顾。

三个能力，全部基于真实数据、规则化输出，不让 LLM 编造：

#5 反向证据 (counter_evidence): 对单只基金强制输出"看空理由"，
   用同类组内更优可比基金、持仓集中度、归因残差/覆盖率、风格漂移等反面证据，
   对冲只堆正面证据的确认偏差。

#8 三选一辅助 (forced_choice): 用户选 3-5 只候选后，规则化输出
   "若只能选一只选谁 / 理由 / 弃选其余的原因"，逼迫产出研究结论。

#15 同类组基准回顾 (peer_review): 输出同类组内近期表现最强基金 vs
   用户关注但未选的基金，机会成本可视化。
"""
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class DecisionSupportService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    # ─────────────── #5 反向证据 ───────────────

    def counter_evidence(self, wind_code: str) -> Dict[str, Any]:
        """对单只基金输出看空理由（反面证据）。"""
        from sqlalchemy import text

        result: Dict[str, Any] = {
            "wind_code": wind_code,
            "better_peers": [],
            "concentration_risk": None,
            "attribution_concern": None,
            "style_drift": None,
        }

        # 1) 同类组内风险调整收益更优的可比基金
        peer_group = self._peer_group_of(wind_code)
        if peer_group:
            sql = text("""
                WITH target AS (
                    SELECT metric_value AS sharpe FROM metric_snapshots
                    WHERE target_type='fund' AND target_id=:wc
                      AND metric_name='sharpe_ratio' AND metric_window='1y'
                    ORDER BY as_of_date DESC LIMIT 1
                )
                SELECT ms.target_id, ms.metric_value, f.name
                FROM metric_snapshots ms
                JOIN funds f ON f.wind_code = ms.target_id
                JOIN peer_group_members pgm ON pgm.entity_id = (
                    SELECT fe.id FROM fund_entities fe WHERE fe.canonical_code = ms.target_id LIMIT 1
                )
                JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                WHERE ms.metric_name='sharpe_ratio' AND ms.metric_window='1y'
                  AND pg.name = :pg
                  AND ms.metric_value > (SELECT sharpe FROM target)
                ORDER BY ms.metric_value DESC
                LIMIT 3
            """)
            try:
                with self.engine.connect() as conn:
                    rows = conn.execute(sql, {"wc": wind_code, "pg": peer_group}).fetchall()
                result["better_peers"] = [
                    {"wind_code": str(r[0]), "sharpe": float(r[1]) if r[1] else None, "name": str(r[2] or "")}
                    for r in rows
                ]
            except Exception:
                pass

        # 2) 持仓集中度风险
        sql = text("""
            SELECT SUM(weight) FROM (
                SELECT weight FROM holdings WHERE wind_code=:wc
                  AND quarter=(SELECT MAX(quarter) FROM holdings WHERE wind_code=:wc)
                ORDER BY weight DESC LIMIT 10
            ) t
        """)
        try:
            with self.engine.connect() as conn:
                row = conn.execute(sql, {"wc": wind_code}).fetchone()
            if row and row[0] is not None:
                top10 = float(row[0])
                if top10 > 0.6:
                    result["concentration_risk"] = {
                        "top_ten_weight": round(top10, 4),
                        "note": f"前十大持仓占 {top10*100:.0f}%，集中度偏高，单一持仓波动影响大",
                    }
        except Exception:
            pass

        # 3) 归因残差/覆盖率隐忧
        sql = text("""
            SELECT (COALESCE(total_return,0)-COALESCE(allocation_effect,0)
                    -COALESCE(selection_effect,0)-COALESCE(interaction_effect,0)) AS residual
            FROM attribution_explanations WHERE entity_id=:wc
            ORDER BY period_end DESC LIMIT 1
        """)
        try:
            with self.engine.connect() as conn:
                row = conn.execute(sql, {"wc": wind_code}).fetchone()
            if row and row[0] is not None and abs(float(row[0])) > 0.05:
                result["attribution_concern"] = {
                    "residual": round(float(row[0]), 4),
                    "note": "归因残差偏大，公开持仓无法解释的收益占比高，结论需谨慎",
                }
        except Exception:
            pass

        # 4) 风格漂移
        sql = text("""
            SELECT style_label FROM holding_style_snapshots
            WHERE wind_code=:wc ORDER BY quarter DESC LIMIT 2
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"wc": wind_code}).fetchall()
            if len(rows) >= 2 and str(rows[0][0]) != str(rows[1][0]):
                result["style_drift"] = {
                    "latest": str(rows[0][0]), "previous": str(rows[1][0]),
                    "note": f"风格由 {rows[1][0]} 变为 {rows[0][0]}，存在漂移",
                }
        except Exception:
            pass

        return result

    # ─────────────── #8 三选一辅助 ───────────────

    def forced_choice(self, codes: List[str]) -> Dict[str, Any]:
        """3-5 只候选中规则化选出最强并给出弃选理由。"""
        from sqlalchemy import text

        if len(codes) < 2:
            raise ValueError("forced_choice needs at least 2 funds")

        scored: List[Dict[str, Any]] = []
        for code in codes:
            metrics = self._risk_metrics(code)
            score = 0.0
            if metrics.get("sharpe") is not None:
                score += min(max(metrics["sharpe"], -2), 3) * 1.0
            if metrics.get("max_drawdown") is not None:
                score += min(max(-metrics["max_drawdown"] * 10, -2), 2) * 0.5
            if metrics.get("annualized_return") is not None:
                score += min(max(metrics["annualized_return"] * 5, -2), 2) * 0.5
            scored.append({"wind_code": code, **metrics, "score": round(score, 3)})

        scored.sort(key=lambda x: x["score"], reverse=True)
        best = scored[0]
        rejected = scored[1:]
        return {
            "pick": best["wind_code"],
            "pick_score": best["score"],
            "pick_metrics": {k: best.get(k) for k in ("sharpe", "max_drawdown", "annualized_return")},
            "reason": "综合 Sharpe、回撤、年化收益的加权得分最高",
            "rejected": [
                {
                    "wind_code": r["wind_code"],
                    "score": r["score"],
                    "reason": self._reject_reason(r, best),
                }
                for r in rejected
            ],
            "note": "规则化辅助，非投资建议；最终结论需结合论点与纪要",
        }

    # ─────────────── #15 同类组基准回顾 ───────────────

    def peer_review(self, focus_codes: List[str], top_n: int = 5) -> Dict[str, Any]:
        """同类组近期最强基金 vs 关注但未选基金，机会成本可视化。"""
        from sqlalchemy import text

        # 取关注基金的同类组
        groups = set()
        for code in focus_codes:
            g = self._peer_group_of(code)
            if g:
                groups.add(g)

        top_performers: List[Dict[str, Any]] = []
        for group in list(groups)[:3]:
            sql = text("""
                SELECT ms.target_id, ms.metric_value, f.name
                FROM metric_snapshots ms
                JOIN funds f ON f.wind_code = ms.target_id
                JOIN peer_group_members pgm ON pgm.entity_id = (
                    SELECT fe.id FROM fund_entities fe WHERE fe.canonical_code = ms.target_id LIMIT 1
                )
                JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                WHERE ms.metric_name='annualized_return' AND ms.metric_window='1y'
                  AND pg.name = :pg
                ORDER BY ms.metric_value DESC
                LIMIT :top_n
            """)
            try:
                with self.engine.connect() as conn:
                    rows = conn.execute(sql, {"pg": group, "top_n": top_n}).fetchall()
                top_performers.append({
                    "peer_group": group,
                    "top": [
                        {"wind_code": str(r[0]), "annualized_return": float(r[1]) if r[1] else None, "name": str(r[2] or "")}
                        for r in rows
                    ],
                })
            except Exception:
                pass

        # 关注但未进同类组 top 的基金 = 机会成本
        missed = []
        for group in top_performers:
            top_codes = {t["wind_code"] for t in group["top"]}
            for code in focus_codes:
                if self._peer_group_of(code) == group["peer_group"] and code not in top_codes:
                    missed.append({"wind_code": code, "peer_group": group["peer_group"]})

        return {
            "top_performers": top_performers,
            "missed_opportunities": missed,
            "note": "展示同类组最强基金与你关注但未选的基金，用于复盘机会成本",
        }

    # ─────────────── helpers ───────────────

    def _peer_group_of(self, wind_code: str) -> Optional[str]:
        from sqlalchemy import text
        sql = text("""
            SELECT pg.name FROM peer_group_members pgm
            JOIN peer_groups pg ON pg.id = pgm.peer_group_id
            WHERE pgm.entity_id = (
                SELECT fe.id FROM fund_entities fe WHERE fe.canonical_code=:wc LIMIT 1
            )
            LIMIT 1
        """)
        try:
            with self.engine.connect() as conn:
                row = conn.execute(sql, {"wc": wind_code}).fetchone()
            return str(row[0]) if row and row[0] else None
        except Exception:
            return None

    def _risk_metrics(self, wind_code: str) -> Dict[str, Optional[float]]:
        from sqlalchemy import text
        out: Dict[str, Optional[float]] = {"sharpe": None, "max_drawdown": None, "annualized_return": None}
        for name in out:
            sql = text("""
                SELECT metric_value FROM metric_snapshots
                WHERE target_type='fund' AND target_id=:wc AND metric_name=:mn AND metric_window='1y'
                ORDER BY as_of_date DESC LIMIT 1
            """)
            try:
                with self.engine.connect() as conn:
                    row = conn.execute(sql, {"wc": wind_code, "mn": name}).fetchone()
                if row and row[0] is not None:
                    out[name] = float(row[0])
            except Exception:
                pass
        return out

    @staticmethod
    def _reject_reason(candidate: Dict[str, Any], best: Dict[str, Any]) -> str:
        reasons = []
        if (candidate.get("sharpe") or 0) < (best.get("sharpe") or 0):
            reasons.append("风险调整收益(Sharpe)更低")
        if (candidate.get("max_drawdown") or 0) < (best.get("max_drawdown") or 0):
            reasons.append("回撤更深")
        if (candidate.get("annualized_return") or 0) < (best.get("annualized_return") or 0):
            reasons.append("年化收益更低")
        return "；".join(reasons) or "综合得分较低"
