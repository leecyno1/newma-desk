"""投资论点结构化 (Investment Thesis) — 研究结论的容器仓储。

每只重点研究基金能保存一份结构化论点：为什么买、卖出触发条件、有效期、
支撑证据快照 ID、状态机与编辑历史。
"""
import json
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


VALID_STATES = {"candidate", "researching", "observing", "invalid", "archived"}


class InvestmentThesisRepo:
    def __init__(self, engine: Optional[Any] = None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    # ─────────────── 查询 ───────────────

    def list_theses(
        self,
        *,
        fund_wind_code: Optional[str] = None,
        state: Optional[str] = None,
        due_before: Optional[date] = None,
        include_closed: bool = False,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        where: List[str] = []
        params: Dict[str, Any] = {"limit": limit}
        if fund_wind_code:
            where.append("fund_wind_code = :wind_code")
            params["wind_code"] = fund_wind_code
        if state:
            if state not in VALID_STATES:
                raise ValueError(f"invalid state: {state}")
            where.append("state = :state")
            params["state"] = state
        elif not include_closed:
            where.append("state IN ('candidate','researching','observing')")
        if due_before:
            where.append("next_review_date IS NOT NULL AND next_review_date <= :due_before")
            params["due_before"] = due_before
        where_sql = f" WHERE {' AND '.join(where)}" if where else ""
        sql = text(
            f"SELECT * FROM investment_theses{where_sql} ORDER BY updated_at DESC LIMIT :limit"
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    def get_thesis(self, thesis_id: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM investment_theses WHERE id = CAST(:id AS UUID)"),
                {"id": str(thesis_id)},
            ).fetchone()
        return self._row(row) if row else None

    # ─────────────── 写入 ───────────────

    def create_thesis(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text

        wind_code = str(payload.get("fund_wind_code") or "").strip()
        title = str(payload.get("title") or "").strip()
        if not wind_code or not title:
            raise ValueError("fund_wind_code and title are required")

        state = str(payload.get("state") or "candidate")
        if state not in VALID_STATES:
            raise ValueError(f"invalid state: {state}")

        cadence = int(payload.get("review_cadence_days") or 30)
        next_review = payload.get("next_review_date")
        if not next_review:
            next_review = (date.today() + timedelta(days=cadence)).isoformat()
        valid_until = payload.get("valid_until")

        state_history = [{
            "state": state,
            "ts": datetime.utcnow().isoformat() + "Z",
            "note": "created",
        }]

        thesis_id = str(uuid.uuid4())
        sql = text("""
            INSERT INTO investment_theses (
                id, fund_wind_code, title, state,
                core_reasoning, sell_triggers, one_liner, counter_view, risks,
                valid_until, next_review_date, review_cadence_days,
                evidence_snapshot, state_history, edit_history
            ) VALUES (
                CAST(:id AS UUID), :wind_code, :title, CAST(:state AS "InvestmentThesisState"),
                CAST(:core_reasoning AS JSONB), CAST(:sell_triggers AS JSONB),
                :one_liner, :counter_view, CAST(:risks AS JSONB),
                CAST(:valid_until AS DATE), CAST(:next_review_date AS DATE), :review_cadence_days,
                CAST(:evidence_snapshot AS JSONB), CAST(:state_history AS JSONB), '[]'::jsonb
            )
        """)
        with self.engine.begin() as conn:
            conn.execute(sql, {
                "id": thesis_id,
                "wind_code": wind_code,
                "title": title,
                "state": state,
                "core_reasoning": json.dumps(payload.get("core_reasoning") or []),
                "sell_triggers": json.dumps(payload.get("sell_triggers") or []),
                "one_liner": payload.get("one_liner") or None,
                "counter_view": payload.get("counter_view") or None,
                "risks": json.dumps(payload.get("risks") or []),
                "valid_until": valid_until,
                "next_review_date": next_review,
                "review_cadence_days": cadence,
                "evidence_snapshot": json.dumps(payload.get("evidence_snapshot") or {}),
                "state_history": json.dumps(state_history),
            })
        return self.get_thesis(thesis_id) or {}

    def update_thesis(self, thesis_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        existing = self.get_thesis(thesis_id)
        if not existing:
            return None

        # 编辑历史：记录本次变更了哪些字段
        changes: Dict[str, Any] = {}
        editable_fields = [
            "title", "one_liner", "counter_view",
            "core_reasoning", "sell_triggers", "risks",
            "valid_until", "next_review_date", "review_cadence_days",
            "evidence_snapshot",
        ]
        for field in editable_fields:
            if field in payload and payload[field] != existing.get(field):
                changes[field] = {
                    "from": existing.get(field),
                    "to": payload[field],
                }

        if not changes:
            return existing

        edit_history = list(existing.get("edit_history") or [])
        edit_history.append({
            "ts": datetime.utcnow().isoformat() + "Z",
            "changes": changes,
        })

        # 构造 UPDATE
        sets: List[str] = []
        params: Dict[str, Any] = {"id": thesis_id, "edit_history": json.dumps(edit_history)}
        if "title" in payload:
            sets.append("title = :title"); params["title"] = payload["title"]
        if "one_liner" in payload:
            sets.append("one_liner = :one_liner"); params["one_liner"] = payload["one_liner"]
        if "counter_view" in payload:
            sets.append("counter_view = :counter_view"); params["counter_view"] = payload["counter_view"]
        if "core_reasoning" in payload:
            sets.append("core_reasoning = CAST(:core_reasoning AS JSONB)")
            params["core_reasoning"] = json.dumps(payload["core_reasoning"] or [])
        if "sell_triggers" in payload:
            sets.append("sell_triggers = CAST(:sell_triggers AS JSONB)")
            params["sell_triggers"] = json.dumps(payload["sell_triggers"] or [])
        if "risks" in payload:
            sets.append("risks = CAST(:risks AS JSONB)")
            params["risks"] = json.dumps(payload["risks"] or [])
        if "valid_until" in payload:
            sets.append("valid_until = CAST(:valid_until AS DATE)")
            params["valid_until"] = payload["valid_until"]
        if "next_review_date" in payload:
            sets.append("next_review_date = CAST(:next_review_date AS DATE)")
            params["next_review_date"] = payload["next_review_date"]
        if "review_cadence_days" in payload:
            sets.append("review_cadence_days = :cadence"); params["cadence"] = int(payload["review_cadence_days"])
        if "evidence_snapshot" in payload:
            sets.append("evidence_snapshot = CAST(:evidence_snapshot AS JSONB)")
            params["evidence_snapshot"] = json.dumps(payload["evidence_snapshot"] or {})
        sets.append("edit_history = CAST(:edit_history AS JSONB)")

        sql = text(
            f"UPDATE investment_theses SET {', '.join(sets)} WHERE id = CAST(:id AS UUID)"
        )
        with self.engine.begin() as conn:
            conn.execute(sql, params)
        return self.get_thesis(thesis_id)

    def transition_state(
        self,
        thesis_id: str,
        new_state: str,
        *,
        note: Optional[str] = None,
        close_reason: Optional[str] = None,
        close_verdict: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        if new_state not in VALID_STATES:
            raise ValueError(f"invalid state: {new_state}")

        existing = self.get_thesis(thesis_id)
        if not existing:
            return None

        history = list(existing.get("state_history") or [])
        history.append({
            "state": new_state,
            "ts": datetime.utcnow().isoformat() + "Z",
            "note": note or "",
            "from": existing.get("state"),
        })

        is_closed = new_state in ("invalid", "archived")
        sql = text("""
            UPDATE investment_theses SET
                state = CAST(:state AS "InvestmentThesisState"),
                state_history = CAST(:history AS JSONB),
                closed_at = CASE WHEN :is_closed THEN NOW() ELSE closed_at END,
                close_reason = COALESCE(:close_reason, close_reason),
                close_verdict = COALESCE(:close_verdict, close_verdict)
            WHERE id = CAST(:id AS UUID)
        """)
        with self.engine.begin() as conn:
            conn.execute(sql, {
                "id": thesis_id,
                "state": new_state,
                "history": json.dumps(history),
                "is_closed": is_closed,
                "close_reason": close_reason,
                "close_verdict": close_verdict,
            })
        return self.get_thesis(thesis_id)

    def count_by_state(self) -> Dict[str, int]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT state, COUNT(*) AS n FROM investment_theses GROUP BY state")
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    # ─────────────── 内部工具 ───────────────

    @staticmethod
    def _row(row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row._mapping)
        for jf in ("core_reasoning", "sell_triggers", "risks", "evidence_snapshot", "state_history", "edit_history"):
            v = d.get(jf)
            if isinstance(v, str):
                try:
                    d[jf] = json.loads(v)
                except (TypeError, ValueError):
                    d[jf] = None
        # 日期 → 字符串
        for df in ("valid_until", "next_review_date"):
            v = d.get(df)
            if hasattr(v, "isoformat"):
                d[df] = v.isoformat()
        for tf in ("created_at", "updated_at", "closed_at"):
            v = d.get(tf)
            if hasattr(v, "isoformat"):
                d[tf] = v.isoformat()
        d["id"] = str(d.get("id") or "")
        return d
