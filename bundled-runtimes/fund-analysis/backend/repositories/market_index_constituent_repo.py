"""市场指数成分快照仓储。"""

import json
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class MarketIndexConstituentRepo:
    def __init__(self, engine: Optional[Any] = None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def replace_snapshot(self, snapshot: Dict[str, Any]) -> int:
        from sqlalchemy import text

        index_code = str(snapshot.get("index_code") or "").upper()
        as_of_date = snapshot.get("as_of_date")
        rows = snapshot.get("constituents") or []
        if not index_code or not as_of_date or not rows:
            return 0
        with self.engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM market_index_constituent_snapshots
                WHERE index_code = :index_code AND as_of_date = :as_of_date
            """), {"index_code": index_code, "as_of_date": as_of_date})
            conn.execute(text("""
                INSERT INTO market_index_constituent_snapshots (
                    index_code, as_of_date, constituent_code, constituent_name,
                    weight, industry, source, evidence_url, metadata
                ) VALUES (
                    :index_code, :as_of_date, :constituent_code, :constituent_name,
                    :weight, :industry, :source, :evidence_url, CAST(:metadata AS jsonb)
                )
            """), [
                {
                    "index_code": index_code,
                    "as_of_date": as_of_date,
                    "constituent_code": row.get("constituent_code"),
                    "constituent_name": row.get("constituent_name"),
                    "weight": row.get("weight"),
                    "industry": row.get("industry"),
                    "source": snapshot.get("source"),
                    "evidence_url": (snapshot.get("source_urls") or [None])[-1],
                    "metadata": json.dumps({
                        "share_class": row.get("share_class"),
                        "industry_source": row.get("industry_source"),
                        "isin": row.get("isin"),
                    }, ensure_ascii=False),
                }
                for row in rows
                if row.get("constituent_code")
            ])
        return len(rows)

    def get_latest_on_or_before(self, index_code: str, as_of_date: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            snapshot_date = conn.execute(text("""
                SELECT MAX(as_of_date)
                FROM market_index_constituent_snapshots
                WHERE index_code = :index_code AND as_of_date <= :as_of_date
            """), {"index_code": index_code.upper(), "as_of_date": as_of_date}).scalar()
            if snapshot_date is None:
                return None
            rows = conn.execute(text("""
                SELECT * FROM market_index_constituent_snapshots
                WHERE index_code = :index_code AND as_of_date = :snapshot_date
                ORDER BY weight DESC NULLS LAST, constituent_code
            """), {"index_code": index_code.upper(), "snapshot_date": snapshot_date}).fetchall()
        return {
            "index_code": index_code.upper(),
            "as_of_date": snapshot_date.isoformat(),
            "constituents": [dict(row._mapping) for row in rows],
            "source": rows[0].source if rows else None,
        }

    def get_latest(self, index_code: str) -> Optional[Dict[str, Any]]:
        return self.get_latest_on_or_before(index_code, "9999-12-31")

    def industry_map(self, index_code: str = "HSI") -> Dict[str, str]:
        snapshot = self.get_latest(index_code) or {}
        return {
            str(row.get("constituent_code")): str(row.get("industry"))
            for row in snapshot.get("constituents") or []
            if row.get("constituent_code") and row.get("industry")
        }
