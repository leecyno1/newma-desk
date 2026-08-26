"""决策复盘 (Decision Post-mortems) — 论点关闭后强制复盘。

当投资论点进入 invalid/archived 状态时，系统要求用户完成一份结构化复盘：
- 结果：论点被证实 / 证伪 / 无法判断
- 实际收益 vs 同类中位 vs 超额
- 核心逻辑逐条验证（哪些被证实、哪些被证伪）
- 卖出触发是否被触发
- 教训与决策偏差识别

这是平台"越用越聪明"的关键：复盘数据积累后可识别系统性决策偏差。
"""
import uuid
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


VALID_OUTCOMES = {"validated", "invalidated", "inconclusive"}


class DecisionPostmortemService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def list_postmortems(
        self,
        outcome: Optional[str] = None,
        fund_wind_code: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        where: List[str] = []
        params: Dict[str, Any] = {"limit": limit}
        if outcome:
            where.append("p.outcome = :outcome")
            params["outcome"] = outcome
        if fund_wind_code:
            where.append("p.fund_wind_code = :wc")
            params["wc"] = fund_wind_code
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""
        sql = text(f"""
            SELECT p.*, t.title AS thesis_title, t.state AS thesis_state, f.name AS fund_name
            FROM decision_postmortems p
            LEFT JOIN investment_theses t ON t.id = p.thesis_id
            LEFT JOIN funds f ON f.wind_code = p.fund_wind_code
            {where_sql}
            ORDER BY p.reviewed_at DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    def get_postmortem(self, postmortem_id: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT p.*, t.title AS thesis_title, t.state AS thesis_state, f.name AS fund_name
                    FROM decision_postmortems p
                    LEFT JOIN investment_theses t ON t.id = p.thesis_id
                    LEFT JOIN funds f ON f.wind_code = p.fund_wind_code
                    WHERE p.id = CAST(:id AS UUID)
                """),
                {"id": postmortem_id},
            ).fetchone()
        return self._row(row) if row else None

    def create_postmortem(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text
        import json as _json

        thesis_id = str(payload.get("thesis_id") or "").strip()
        outcome = str(payload.get("outcome") or "").strip()
        if not thesis_id:
            raise ValueError("thesis_id is required")
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of {sorted(VALID_OUTCOMES)}")

        # 获取论点对应的基金代码
        with self.engine.connect() as conn:
            thesis_row = conn.execute(
                text("SELECT fund_wind_code, state FROM investment_theses WHERE id = CAST(:id AS UUID)"),
                {"id": thesis_id},
            ).fetchone()
        if not thesis_row:
            raise ValueError("thesis not found")
        wind_code = str(thesis_row[0])

        postmortem_id = str(uuid.uuid4())
        sql = text("""
            INSERT INTO decision_postmortems
                (id, thesis_id, fund_wind_code, outcome, actual_return_pct,
                 peer_median_return_pct, excess_return_pct, reasoning_verdicts,
                 trigger_fired, trigger_detail, lesson_learned, decision_bias, would_repeat)
            VALUES
                (CAST(:id AS UUID), CAST(:thesis_id AS UUID), :wc, :outcome,
                 :actual_ret, :peer_ret, :excess_ret, CAST(:verdicts AS JSONB),
                 :trigger_fired, :trigger_detail, :lesson, :bias, :would_repeat)
        """)
        with self.engine.begin() as conn:
            conn.execute(sql, {
                "id": postmortem_id,
                "thesis_id": thesis_id,
                "wc": wind_code,
                "outcome": outcome,
                "actual_ret": payload.get("actual_return_pct"),
                "peer_ret": payload.get("peer_median_return_pct"),
                "excess_ret": payload.get("excess_return_pct"),
                "verdicts": _json.dumps(payload.get("reasoning_verdicts") or []),
                "trigger_fired": bool(payload.get("trigger_fired")),
                "trigger_detail": payload.get("trigger_detail"),
                "lesson": payload.get("lesson_learned"),
                "bias": payload.get("decision_bias"),
                "would_repeat": payload.get("would_repeat"),
            })
        return self.get_postmortem(postmortem_id) or {}

    def stats(self) -> Dict[str, Any]:
        """复盘统计：用于识别系统性决策偏差。"""
        from sqlalchemy import text
        with self.engine.connect() as conn:
            outcome_rows = conn.execute(
                text("SELECT outcome, COUNT(*) FROM decision_postmortems GROUP BY outcome")
            ).fetchall()
            bias_rows = conn.execute(
                text("SELECT decision_bias, COUNT(*) FROM decision_postmortems WHERE decision_bias IS NOT NULL GROUP BY decision_bias ORDER BY COUNT(*) DESC")
            ).fetchall()
            avg_rows = conn.execute(
                text("SELECT AVG(actual_return_pct), AVG(excess_return_pct), COUNT(*) FROM decision_postmortems WHERE actual_return_pct IS NOT NULL")
            ).fetchone()
        return {
            "by_outcome": {str(r[0]): int(r[1]) for r in outcome_rows},
            "by_bias": {str(r[0]): int(r[1]) for r in bias_rows},
            "avg_actual_return_pct": float(avg_rows[0]) if avg_rows and avg_rows[0] is not None else None,
            "avg_excess_return_pct": float(avg_rows[1]) if avg_rows and avg_rows[1] is not None else None,
            "total_with_returns": int(avg_rows[2]) if avg_rows else 0,
        }

    def patterns(self, min_occurrences: int = 2) -> Dict[str, Any]:
        """决策模式识别 (#14)：从复盘中识别系统性偏差。

        当某一类偏差（decision_bias）累计达到 min_occurrences 次，或某类
        outcome 占比过高时，输出模式提示。数据不足时返回空 patterns 并提示
        需要更多复盘。
        """
        stats = self.stats()
        by_bias = stats.get("by_bias") or {}
        by_outcome = stats.get("by_outcome") or {}
        total = sum(by_outcome.values())

        patterns: List[Dict[str, Any]] = []
        for bias, count in by_bias.items():
            if count >= min_occurrences:
                patterns.append({
                    "pattern": "recurring_bias",
                    "bias": bias,
                    "occurrences": count,
                    "message": f"你已 {count} 次识别出「{bias}」偏差，建议建立对应检查清单。",
                })

        invalidated = by_outcome.get("invalidated", 0)
        if total >= 3 and invalidated / total >= 0.5:
            patterns.append({
                "pattern": "high_invalidation_rate",
                "occurrences": invalidated,
                "ratio": round(invalidated / total, 2),
                "message": f"论点证伪率 {invalidated}/{total}，建议收紧入池门槛或加强反向证据。",
            })

        avg_excess = stats.get("avg_excess_return_pct")
        if avg_excess is not None and stats.get("total_with_returns", 0) >= 3 and avg_excess < 0:
            patterns.append({
                "pattern": "negative_avg_excess",
                "avg_excess_return_pct": avg_excess,
                "message": f"平均超额收益 {avg_excess:.1f}% 为负，整体选择未跑赢同类中位。",
            })

        return {
            "total_postmortems": total,
            "sufficient": total >= min_occurrences,
            "patterns": patterns,
            "by_bias": by_bias,
        }

    @staticmethod
    def _row(row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row._mapping)
        d["id"] = str(d.get("id") or "")
        if d.get("thesis_id"):
            d["thesis_id"] = str(d["thesis_id"])
        v = d.get("reasoning_verdicts")
        if isinstance(v, str):
            import json as _json
            try:
                d["reasoning_verdicts"] = _json.loads(v)
            except (TypeError, ValueError):
                d["reasoning_verdicts"] = []
        for tf in ("reviewed_at", "created_at"):
            val = d.get(tf)
            if hasattr(val, "isoformat"):
                d[tf] = val.isoformat()
        return d
