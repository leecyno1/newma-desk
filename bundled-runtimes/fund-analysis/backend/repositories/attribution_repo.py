"""基金业绩归因历史存储。"""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class AttributionRepo:
    def __init__(self, engine: Optional[Any] = None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def save_bundle(self, bundle: Dict[str, Any]) -> bool:
        from sqlalchemy import text

        fund = bundle.get("fund") or {}
        brinson = bundle.get("brinson") or {}
        returns = brinson.get("returns") or {}
        effects = {
            item.get("name"): item.get("value")
            for item in brinson.get("effects") or []
            if item.get("name")
        }
        wind_code = str(fund.get("wind_code") or "").strip()
        quarter = str(bundle.get("quarter") or "").strip()
        benchmark = str(bundle.get("benchmark") or "").strip()
        if not wind_code or not quarter or not benchmark:
            return False

        sql = text("""
            INSERT INTO performance_attributions (
                fund_id, wind_code, benchmark_id, quarter, holding_quarter, status,
                total_return, benchmark_return, active_return,
                allocation_effect, selection_effect, interaction_effect, residual,
                evidence, updated_at
            ) VALUES (
                (SELECT id::text FROM funds WHERE wind_code = :wind_code),
                :wind_code, :benchmark_id, :quarter, :holding_quarter, :status,
                :total_return, :benchmark_return, :active_return,
                :allocation_effect, :selection_effect, :interaction_effect, :residual,
                CAST(:evidence AS jsonb), CURRENT_TIMESTAMP
            )
            ON CONFLICT (wind_code, quarter) DO UPDATE SET
                fund_id = EXCLUDED.fund_id,
                benchmark_id = EXCLUDED.benchmark_id,
                holding_quarter = EXCLUDED.holding_quarter,
                status = EXCLUDED.status,
                total_return = EXCLUDED.total_return,
                benchmark_return = EXCLUDED.benchmark_return,
                active_return = EXCLUDED.active_return,
                allocation_effect = EXCLUDED.allocation_effect,
                selection_effect = EXCLUDED.selection_effect,
                interaction_effect = EXCLUDED.interaction_effect,
                residual = EXCLUDED.residual,
                evidence = EXCLUDED.evidence,
                updated_at = CURRENT_TIMESTAMP
        """)
        with self.engine.begin() as conn:
            conn.execute(sql, {
                "wind_code": wind_code,
                "benchmark_id": benchmark,
                "quarter": quarter,
                "holding_quarter": bundle.get("holding_snapshot_quarter"),
                "status": brinson.get("status") or bundle.get("status"),
                "total_return": returns.get("fund"),
                "benchmark_return": returns.get("benchmark"),
                "active_return": returns.get("active"),
                "allocation_effect": effects.get("allocation"),
                "selection_effect": effects.get("selection"),
                "interaction_effect": effects.get("interaction"),
                "residual": effects.get("residual"),
                "evidence": json.dumps(bundle, ensure_ascii=False, default=str),
            })
        return True

    def get_bundle(self, wind_code: str, quarter: str) -> Optional[Dict[str, Any]]:
        """读取某一季度保存的完整归因证据。"""
        from sqlalchemy import text

        sql = text("""
            SELECT quarter, holding_quarter, benchmark_id, status, evidence, updated_at
            FROM performance_attributions
            WHERE wind_code = :wind_code AND quarter = :quarter
            LIMIT 1
        """)
        with self.engine.connect() as conn:
            row = conn.execute(sql, {
                "wind_code": str(wind_code or "").strip().upper(),
                "quarter": str(quarter or "").strip().upper(),
            }).fetchone()
        if not row:
            return None

        data = dict(row._mapping)
        evidence = data.get("evidence")
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except json.JSONDecodeError:
                return None
        if not isinstance(evidence, dict):
            return None

        bundle = dict(evidence)
        bundle.setdefault("quarter", data.get("quarter"))
        bundle.setdefault("holding_snapshot_quarter", data.get("holding_quarter"))
        bundle.setdefault("benchmark", data.get("benchmark_id"))
        bundle.setdefault("status", data.get("status"))
        return {"bundle": bundle, "updated_at": self._serialize(data.get("updated_at"))}

    def list_history(self, wind_code: str, limit: int = 8) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text("""
            SELECT
                wind_code, benchmark_id, quarter, holding_quarter, status,
                total_return, benchmark_return, active_return,
                allocation_effect, selection_effect, interaction_effect, residual,
                evidence, created_at, updated_at
            FROM performance_attributions
            WHERE wind_code = :wind_code
            ORDER BY quarter DESC, updated_at DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(
                sql,
                {"wind_code": wind_code, "limit": max(1, min(int(limit), 40))},
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row._mapping)
            if isinstance(item.get("evidence"), str):
                try:
                    item["evidence"] = json.loads(item["evidence"])
                except json.JSONDecodeError:
                    item["evidence"] = None
            result.append(self._serialize(item))
        return result

    @classmethod
    def _serialize(cls, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: cls._serialize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._serialize(item) for item in value]
        return value
