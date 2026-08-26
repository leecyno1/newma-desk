"""研究队列 (Research Queue) — 候选基金进入"研究中"状态，带优先级、复查日期、产出承诺。

与自选(watchlist)的区别：
- watchlist = 关注列表，无产出承诺
- research_queue = 研究队列，每只基金必须有产出承诺（论点或结论）才能出队

与论点(thesis)的关系：
- 研究队列是"正在研究"的容器
- 论点是"研究产出"的容器
- 队列项可以关联一个论点 ID，表示产出已落地
"""
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


VALID_STATUSES = {"queued", "researching", "concluded", "dropped"}


class ResearchQueueService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    # ─── 查询 ───

    def list_items(
        self,
        status: Optional[str] = None,
        due_soon: bool = False,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        where: List[str] = []
        params: Dict[str, Any] = {"limit": limit}
        if status:
            if status not in VALID_STATUSES:
                raise ValueError(f"invalid status: {status}")
            where.append("status = CAST(:status AS \"ResearchQueueStatus\")")
            params["status"] = status
        else:
            where.append("status IN ('queued','researching')")
        if due_soon:
            where.append("next_review_date IS NOT NULL AND next_review_date <= CURRENT_DATE")
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""
        sql = text(f"""
            SELECT q.*, f.name AS fund_name
            FROM research_queue_items q
            LEFT JOIN funds f ON f.wind_code = q.fund_wind_code
            {where_sql}
            ORDER BY priority ASC, next_review_date ASC NULLS LAST, created_at DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT q.*, f.name AS fund_name
                    FROM research_queue_items q
                    LEFT JOIN funds f ON f.wind_code = q.fund_wind_code
                    WHERE q.id = CAST(:id AS UUID)
                """),
                {"id": item_id},
            ).fetchone()
        return self._row(row) if row else None

    def count_by_status(self) -> Dict[str, int]:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT status, COUNT(*) FROM research_queue_items GROUP BY status")).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    # ─── 写入 ───

    def add_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text
        wind_code = str(payload.get("fund_wind_code") or "").strip()
        if not wind_code:
            raise ValueError("fund_wind_code is required")
        priority = int(payload.get("priority") or 3)
        priority = max(1, min(5, priority))
        next_review = payload.get("next_review_date")
        if not next_review:
            next_review = (date.today() + timedelta(days=14)).isoformat()

        item_id = str(uuid.uuid4())
        sql = text("""
            INSERT INTO research_queue_items
                (id, fund_wind_code, status, priority, source, source_ref, next_review_date, notes)
            VALUES
                (CAST(:id AS UUID), :wc, 'queued', :priority, :source, :source_ref, CAST(:nrd AS DATE), :notes)
        """)
        with self.engine.begin() as conn:
            conn.execute(sql, {
                "id": item_id, "wc": wind_code, "priority": priority,
                "source": payload.get("source") or "manual",
                "source_ref": payload.get("source_ref"),
                "nrd": next_review, "notes": payload.get("notes"),
            })
        return self.get_item(item_id) or {}

    def update_item(self, item_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        existing = self.get_item(item_id)
        if not existing:
            return None
        sets: List[str] = []
        params: Dict[str, Any] = {"id": item_id}
        for field in ("priority", "next_review_date", "notes", "source_ref"):
            if field in payload:
                sets.append(f"{field} = :{field}")
                params[field] = payload[field]
        if "status" in payload:
            if payload["status"] not in VALID_STATUSES:
                raise ValueError("invalid status")
            sets.append("status = CAST(:status AS \"ResearchQueueStatus\")")
            params["status"] = payload["status"]
            if payload["status"] == "concluded":
                sets.append("concluded_at = NOW()")
        if "conclusion" in payload:
            sets.append("conclusion = :conclusion")
            params["conclusion"] = payload["conclusion"]
        if "thesis_id" in payload:
            sets.append("thesis_id = CAST(:thesis_id AS UUID)")
            params["thesis_id"] = payload["thesis_id"]
            if payload["thesis_id"]:
                sets.append("output_committed = TRUE")
        if not sets:
            return existing
        sets.append("updated_at = NOW()")
        sql = text(f"UPDATE research_queue_items SET {', '.join(sets)} WHERE id = CAST(:id AS UUID)")
        with self.engine.begin() as conn:
            conn.execute(sql, params)
        return self.get_item(item_id)

    def remove_item(self, item_id: str) -> bool:
        from sqlalchemy import text
        with self.engine.begin() as conn:
            result = conn.execute(text("DELETE FROM research_queue_items WHERE id = CAST(:id AS UUID)"), {"id": item_id})
        return result.rowcount > 0

    @staticmethod
    def _row(row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row._mapping)
        d["id"] = str(d.get("id") or "")
        if d.get("thesis_id"):
            d["thesis_id"] = str(d["thesis_id"])
        for df in ("next_review_date",):
            v = d.get(df)
            if hasattr(v, "isoformat"):
                d[df] = v.isoformat()
        for tf in ("created_at", "updated_at", "concluded_at"):
            v = d.get(tf)
            if hasattr(v, "isoformat"):
                d[tf] = v.isoformat()
        return d
