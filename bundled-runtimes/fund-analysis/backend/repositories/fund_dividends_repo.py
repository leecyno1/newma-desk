"""基金分红事件 Repository。"""

from datetime import date, datetime
from typing import Any, Dict, List

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class FundDividendsRepo:
    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def replace_fund_dividends(self, wind_code: str, rows: List[Dict[str, Any]]) -> int:
        """整只基金分红史替换：tushare fund_div 无稳定唯一键，per-fund 删除重建。"""
        from sqlalchemy import text

        code = str(wind_code or "").strip().upper()
        if not code:
            return 0
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM fund_dividends WHERE wind_code = :wind_code"), {"wind_code": code})
            if not rows:
                return 0
            insert = text("""
                INSERT INTO fund_dividends (
                    wind_code, ann_date, record_date, ex_date, pay_date, net_ex_date,
                    div_proc, div_cash, ear_amount, source, raw_data
                ) VALUES (
                    :wind_code, :ann_date, :record_date, :ex_date, :pay_date, :net_ex_date,
                    :div_proc, :div_cash, :ear_amount, :source, CAST(:raw_data AS JSONB)
                )
            """)
            for row in rows:
                conn.execute(insert, {
                    "wind_code": code,
                    "ann_date": row.get("ann_date"),
                    "record_date": row.get("record_date"),
                    "ex_date": row.get("ex_date"),
                    "pay_date": row.get("pay_date"),
                    "net_ex_date": row.get("net_ex_date"),
                    "div_proc": row.get("div_proc"),
                    "div_cash": row.get("div_cash"),
                    "ear_amount": row.get("ear_amount"),
                    "source": row.get("source") or "tushare.fund_div",
                    "raw_data": _json(row.get("raw_data")),
                })
        return len(rows)

    def list_fund_dividends(self, wind_code: str, limit: int = 50) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text("""
            SELECT wind_code, ann_date, record_date, ex_date, pay_date, net_ex_date,
                   div_proc, div_cash, ear_amount, source, created_at
            FROM fund_dividends
            WHERE wind_code = :wind_code
            ORDER BY ex_date DESC NULLS LAST, record_date DESC NULLS LAST
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"wind_code": str(wind_code or "").strip().upper(), "limit": max(1, min(limit, 500))}).fetchall()
        return [self._serialize(dict(row._mapping)) for row in rows]

    def list_dividend_fund_codes(self) -> List[str]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT DISTINCT wind_code FROM fund_dividends WHERE div_cash IS NOT NULL AND div_cash > 0"
            )).fetchall()
        return [str(row[0]) for row in rows]

    @staticmethod
    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("div_cash", "ear_amount"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        for key in ("ann_date", "record_date", "ex_date", "pay_date", "net_ex_date", "created_at"):
            value = row.get(key)
            if isinstance(value, (datetime, date)):
                row[key] = value.isoformat()
        return row


def _json(value: Any):
    if value is None:
        return None
    import json

    return json.dumps(value, ensure_ascii=False, default=str)
