"""研究决策记录 (Research Decision Logs) — 每次研究结论的结构化记录。

与论点(thesis)的关系：论点是"为什么买/何时卖"的容器，决策记录是"某时点我得出
了什么结论、基于哪些证据、何时必须回来复查"的时间线。

设计原则：
- 每条记录带证据快照 ID，保证日后可回放当时依据
- review_due_date 到期后强制回到复盘环节（配合 #13 决策复盘）
- 不做任何交易/买卖执行，只记录研究结论
"""
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


VALID_TYPES = {"buy_research", "hold", "avoid", "exit_research", "observe"}


class ResearchDecisionLogService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def list_logs(
        self,
        fund_wind_code: Optional[str] = None,
        due_soon: bool = False,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        where: List[str] = []
        params: Dict[str, Any] = {"limit": limit}
        if fund_wind_code:
            where.append("l.fund_wind_code = :wc")
            params["wc"] = fund_wind_code
        if due_soon:
            where.append("l.reviewed = FALSE AND l.review_due_date IS NOT NULL AND l.review_due_date <= CURRENT_DATE")
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""
        sql = text(f"""
            SELECT l.*, t.title AS thesis_title, f.name AS fund_name
            FROM research_decision_logs l
            LEFT JOIN investment_theses t ON t.id = l.thesis_id
            LEFT JOIN funds f ON f.wind_code = l.fund_wind_code
            {where_sql}
            ORDER BY l.created_at DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    def create_log(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text
        import json as _json

        wind_code = str(payload.get("fund_wind_code") or "").strip()
        conclusion = str(payload.get("conclusion") or "").strip()
        decision_type = str(payload.get("decision_type") or "observe").strip()
        if not wind_code or not conclusion:
            raise ValueError("fund_wind_code and conclusion are required")
        if decision_type not in VALID_TYPES:
            raise ValueError(f"decision_type must be one of {sorted(VALID_TYPES)}")

        review_days = int(payload.get("review_after_days") or 90)
        review_due = payload.get("review_due_date")
        if not review_due:
            review_due = (date.today() + timedelta(days=review_days)).isoformat()

        log_id = str(uuid.uuid4())
        sql = text("""
            INSERT INTO research_decision_logs
                (id, fund_wind_code, thesis_id, decision_type, conclusion, confidence,
                 evidence_snapshot, review_after_days, review_due_date)
            VALUES
                (CAST(:id AS UUID), :wc, CAST(:thesis_id AS UUID), :dtype, :conclusion, :confidence,
                 CAST(:evidence AS JSONB), :review_days, CAST(:review_due AS DATE))
        """)
        with self.engine.begin() as conn:
            conn.execute(sql, {
                "id": log_id, "wc": wind_code,
                "thesis_id": payload.get("thesis_id") or None,
                "dtype": decision_type, "conclusion": conclusion,
                "confidence": payload.get("confidence"),
                "evidence": _json.dumps(payload.get("evidence_snapshot") or {}),
                "review_days": review_days, "review_due": review_due,
            })
        return self.get_log(log_id) or {}

    def get_log(self, log_id: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT l.*, t.title AS thesis_title, f.name AS fund_name
                    FROM research_decision_logs l
                    LEFT JOIN investment_theses t ON t.id = l.thesis_id
                    LEFT JOIN funds f ON f.wind_code = l.fund_wind_code
                    WHERE l.id = CAST(:id AS UUID)
                """),
                {"id": log_id},
            ).fetchone()
        return self._row(row) if row else None

    def mark_reviewed(self, log_id: str, review_note: Optional[str] = None) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE research_decision_logs SET reviewed = TRUE, review_note = COALESCE(:note, review_note) WHERE id = CAST(:id AS UUID)"),
                {"id": log_id, "note": review_note},
            )
        return self.get_log(log_id)

    def due_count(self) -> int:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) FROM research_decision_logs WHERE reviewed = FALSE AND review_due_date IS NOT NULL AND review_due_date <= CURRENT_DATE")
            ).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _row(row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row._mapping)
        d["id"] = str(d.get("id") or "")
        if d.get("thesis_id"):
            d["thesis_id"] = str(d["thesis_id"])
        v = d.get("evidence_snapshot")
        if isinstance(v, str):
            import json as _json
            try:
                d["evidence_snapshot"] = _json.loads(v)
            except (TypeError, ValueError):
                d["evidence_snapshot"] = {}
        for df in ("review_due_date",):
            val = d.get(df)
            if hasattr(val, "isoformat"):
                d[df] = val.isoformat()
        for tf in ("created_at",):
            val = d.get(tf)
            if hasattr(val, "isoformat"):
                d[tf] = val.isoformat()
        return d
