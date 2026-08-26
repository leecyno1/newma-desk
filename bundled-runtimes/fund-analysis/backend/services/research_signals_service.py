"""研究信号雷达 (Research Signals) — 主动推送值得关注的研究变化。

三类信号：
1. 经理观点新入库 (#11)：关注的经理（活跃论点/队列中）有新纪要入库
2. 归因残差恶化 (#12)：某基金最新归因残差/质量相对上一期恶化
3. 纪要新证据雷达 (#2)：新纪要匹配到某只活跃论点基金或其经理，提示证据更新

设计原则：
- 只扫描主动研究范围内的基金/经理（活跃论点 + 研究队列），不做全库轰炸
- 每条信号带证据引用（纪要 ID / 归因期间），用户可点击直达
- 信号不自动触发任何操作
"""
from datetime import date, timedelta
from typing import Any, Dict, List

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class ResearchSignalsService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def scan(self, days: int = 14) -> Dict[str, Any]:
        """扫描三类研究信号。"""
        focus = self._focus_funds()
        signals: Dict[str, List[Dict[str, Any]]] = {
            "manager_new_memo": self._scan_manager_new_memo(focus, days),
            "attribution_degradation": self._scan_attribution_degradation(focus),
            "memo_evidence_radar": self._scan_memo_evidence_radar(focus, days),
        }
        total = sum(len(v) for v in signals.values())
        return {
            "scan_date": date.today().isoformat(),
            "window_days": days,
            "focus_fund_count": len(focus),
            "total_signals": total,
            "by_type": {k: len(v) for k, v in signals.items()},
            "signals": signals,
        }

    def _focus_funds(self) -> List[Dict[str, Any]]:
        """活跃研究范围：活跃论点 + 研究队列中的基金。"""
        from sqlalchemy import text
        sql = text("""
            SELECT DISTINCT wind_code, manager_name FROM (
                SELECT t.fund_wind_code AS wind_code, NULL AS manager_name
                FROM investment_theses t WHERE t.state IN ('candidate','researching','observing')
                UNION
                SELECT q.fund_wind_code, NULL FROM research_queue_items q WHERE q.status IN ('queued','researching')
            ) focus
            LEFT JOIN LATERAL (
                SELECT m.name AS manager_name FROM managers m LIMIT 0
            ) mm ON FALSE
        """)
        # 简化：直接取基金代码集合
        sql = text("""
            SELECT fund_wind_code FROM (
                SELECT fund_wind_code FROM investment_theses WHERE state IN ('candidate','researching','observing')
                UNION
                SELECT fund_wind_code FROM research_queue_items WHERE status IN ('queued','researching')
            ) f
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql).fetchall()
            return [{"wind_code": str(r[0])} for r in rows]
        except Exception:
            return []

    def _scan_manager_new_memo(self, focus: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
        """关注经理的新纪要。"""
        from sqlalchemy import text
        codes = [f["wind_code"] for f in focus]
        if not codes:
            return []
        # 取关注基金的经理，再找这些经理最近 days 天的新纪要
        sql = text("""
            WITH focus_managers AS (
                SELECT DISTINCT unnest(m.manager_ids) AS manager_id
                FROM funds f
                WHERE f.wind_code = ANY(:codes)
            )
            SELECT r.id, r.title, r.manager_name, r.report_date, r.created_at
            FROM research_reports r
            WHERE r.created_at >= NOW() - (:days || ' days')::INTERVAL
              AND (r.manager_id IN (SELECT manager_id FROM focus_managers) OR r.manager_name IS NOT NULL)
            ORDER BY r.created_at DESC
            LIMIT 50
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"codes": codes, "days": days}).fetchall()
            return [
                {
                    "type": "manager_new_memo",
                    "report_id": str(r[0]),
                    "title": str(r[1] or ""),
                    "manager_name": str(r[2] or ""),
                    "report_date": str(r[3]) if r[3] else None,
                    "description": f"{r[2] or '经理'} 有新纪要入库",
                }
                for r in rows
            ]
        except Exception:
            return []

    def _scan_attribution_degradation(self, focus: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """归因残差恶化：最新一期残差绝对值大于上一期。"""
        from sqlalchemy import text
        codes = [f["wind_code"] for f in focus]
        if not codes:
            return []
        sql = text("""
            WITH ranked AS (
                SELECT entity_id, period_end,
                       (COALESCE(total_return,0) - COALESCE(allocation_effect,0)
                        - COALESCE(selection_effect,0) - COALESCE(interaction_effect,0)) AS residual,
                       ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY period_end DESC) AS rn
                FROM attribution_explanations
                WHERE entity_id = ANY(:codes)
            )
            SELECT cur.entity_id, cur.residual, prev.residual
            FROM ranked cur
            JOIN ranked prev ON cur.entity_id = prev.entity_id AND prev.rn = 2
            WHERE cur.rn = 1 AND ABS(cur.residual) > ABS(prev.residual)
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"codes": codes}).fetchall()
            return [
                {
                    "type": "attribution_degradation",
                    "wind_code": str(r[0]),
                    "current_residual": float(r[1]) if r[1] else None,
                    "previous_residual": float(r[2]) if r[2] else None,
                    "description": f"归因残差扩大：{float(r[2]):.2%} → {float(r[1]):.2%}，论点需复查",
                }
                for r in rows
            ]
        except Exception:
            return []

    def _scan_memo_evidence_radar(self, focus: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
        """纪要新证据雷达：新纪要标题/经理匹配到关注基金。"""
        from sqlalchemy import text
        codes = [f["wind_code"] for f in focus]
        if not codes:
            return []
        # 匹配：纪要关联的经理 = 关注基金的经理
        sql = text("""
            WITH focus_managers AS (
                SELECT DISTINCT unnest(m.manager_ids) AS manager_id, f.wind_code
                FROM funds f
                WHERE f.wind_code = ANY(:codes)
            )
            SELECT r.id, r.title, r.manager_name, fm.wind_code, r.created_at
            FROM research_reports r
            JOIN focus_managers fm ON fm.manager_id = r.manager_id
            WHERE r.created_at >= NOW() - (:days || ' days')::INTERVAL
            ORDER BY r.created_at DESC
            LIMIT 50
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"codes": codes, "days": days}).fetchall()
            return [
                {
                    "type": "memo_evidence_radar",
                    "report_id": str(r[0]),
                    "title": str(r[1] or ""),
                    "manager_name": str(r[2] or ""),
                    "wind_code": str(r[3]),
                    "description": f"{r[3]} 的经理 {r[2] or ''} 有新纪要，论点证据可更新",
                }
                for r in rows
            ]
        except Exception:
            return []
