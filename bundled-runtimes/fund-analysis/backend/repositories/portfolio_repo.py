"""基金组合构建 (Portfolio Construction) — 研究型组合仓储。

组合 = 目标配置（同类组权重）+ 持仓（基金 + 等权/自定义权重）。
组合是研究工具：不执行交易、不做适当性判断、不生成销售规则。
"""
import json
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


VALID_STATUSES = {"draft", "active", "archived"}
VALID_WEIGHT_SOURCES = {"equal", "custom"}


class PortfolioRepo:
    def __init__(self, engine: Optional[Any] = None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    # ─────────────── 组合主表 ───────────────

    def list_portfolios(self, *, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        params: Dict[str, Any] = {"limit": limit}
        where_sql = ""
        if status:
            if status not in VALID_STATUSES:
                raise ValueError(f"invalid status: {status}")
            where_sql = " WHERE p.status = :status"
            params["status"] = status
        sql = text(
            f"""
            SELECT p.*,
                   (SELECT COUNT(*) FROM portfolio_holdings h WHERE h.portfolio_id = p.id) AS holding_count,
                   (SELECT COALESCE(SUM(h.weight), 0) FROM portfolio_holdings h WHERE h.portfolio_id = p.id) AS total_weight
            FROM portfolios p{where_sql}
            ORDER BY p.updated_at DESC
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM portfolios WHERE id = CAST(:id AS UUID)"),
                {"id": str(portfolio_id)},
            ).fetchone()
        return self._row(row) if row else None

    def create_portfolio(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO portfolios (name, objective, status)
                    VALUES (:name, :objective, :status)
                    RETURNING *
                    """
                ),
                {
                    "name": str(payload.get("name") or "").strip(),
                    "objective": payload.get("objective"),
                    "status": payload.get("status") or "draft",
                },
            ).fetchone()
        return self._row(row)

    def update_portfolio(self, portfolio_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        allowed = {"name", "objective", "status"}
        updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if "status" in updates and updates["status"] not in VALID_STATUSES:
            raise ValueError(f"invalid status: {updates['status']}")
        if not updates:
            return self.get_portfolio(portfolio_id)
        set_sql = ", ".join(f"{key} = :{key}" for key in updates)
        updates["id"] = str(portfolio_id)
        with self.engine.begin() as conn:
            row = conn.execute(
                text(f"UPDATE portfolios SET {set_sql}, updated_at = NOW() WHERE id = CAST(:id AS UUID) RETURNING *"),
                updates,
            ).fetchone()
        return self._row(row) if row else None

    # ─────────────── 目标配置 ───────────────

    def list_targets(self, portfolio_id: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM portfolio_targets WHERE portfolio_id = CAST(:id AS UUID) ORDER BY created_at"),
                {"id": str(portfolio_id)},
            ).fetchall()
        return [self._row(row) for row in rows]

    def replace_targets(self, portfolio_id: str, targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM portfolio_targets WHERE portfolio_id = CAST(:id AS UUID)"),
                {"id": str(portfolio_id)},
            )
            for item in targets:
                conn.execute(
                    text(
                        """
                        INSERT INTO portfolio_targets (portfolio_id, peer_group_key, peer_group_name, target_weight, note)
                        VALUES (CAST(:portfolio_id AS UUID), :peer_group_key, :peer_group_name, :target_weight, :note)
                        """
                    ),
                    {
                        "portfolio_id": str(portfolio_id),
                        "peer_group_key": str(item.get("peer_group_key") or "").strip(),
                        "peer_group_name": item.get("peer_group_name"),
                        "target_weight": float(item.get("target_weight") or 0),
                        "note": item.get("note"),
                    },
                )
        return self.list_targets(portfolio_id)

    # ─────────────── 持仓 ───────────────

    def list_holdings(self, portfolio_id: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT h.*, f.name AS fund_name
                    FROM portfolio_holdings h
                    LEFT JOIN funds f ON f.wind_code = h.wind_code
                    WHERE h.portfolio_id = CAST(:id AS UUID)
                    ORDER BY h.added_at
                    """
                ),
                {"id": str(portfolio_id)},
            ).fetchall()
        return [self._row(row) for row in rows]

    def get_holding(self, portfolio_id: str, wind_code: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM portfolio_holdings WHERE portfolio_id = CAST(:id AS UUID) AND wind_code = :code"
                ),
                {"id": str(portfolio_id), "code": wind_code},
            ).fetchone()
        return self._row(row) if row else None

    def add_holding(self, portfolio_id: str, wind_code: str, note: Optional[str] = None) -> Dict[str, Any]:
        from sqlalchemy import text

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO portfolio_holdings (portfolio_id, wind_code, note)
                    VALUES (CAST(:portfolio_id AS UUID), :wind_code, :note)
                    ON CONFLICT (portfolio_id, wind_code)
                    DO UPDATE SET note = EXCLUDED.note, updated_at = NOW()
                    RETURNING *
                    """
                ),
                {"portfolio_id": str(portfolio_id), "wind_code": wind_code, "note": note},
            ).fetchone()
        return self._row(row)

    def remove_holding(self, portfolio_id: str, wind_code: str) -> bool:
        from sqlalchemy import text

        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM portfolio_holdings WHERE portfolio_id = CAST(:id AS UUID) AND wind_code = :code"
                ),
                {"id": str(portfolio_id), "code": wind_code},
            )
        return bool(result.rowcount)

    def set_weights(self, portfolio_id: str, items: List[Dict[str, Any]], source: str) -> None:
        from sqlalchemy import text

        if source not in VALID_WEIGHT_SOURCES:
            raise ValueError(f"invalid weight source: {source}")
        with self.engine.begin() as conn:
            for item in items:
                conn.execute(
                    text(
                        """
                        UPDATE portfolio_holdings
                        SET weight = :weight, weight_source = :source, updated_at = NOW()
                        WHERE portfolio_id = CAST(:portfolio_id AS UUID) AND wind_code = :wind_code
                        """
                    ),
                    {
                        "portfolio_id": str(portfolio_id),
                        "wind_code": str(item.get("wind_code") or "").strip(),
                        "weight": float(item.get("weight") or 0),
                        "source": source,
                    },
                )

    # ─────────────── 通用 ───────────────

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        result: Dict[str, Any] = {}
        for key in row._mapping.keys():  # noqa: SLF001
            value = row._mapping[key]  # noqa: SLF001
            if isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8", errors="replace")
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif isinstance(value, (dict, list)):
                value = json.loads(json.dumps(value, default=str))
            result[str(key)] = value
        return result
