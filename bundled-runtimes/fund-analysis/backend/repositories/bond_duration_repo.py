"""中债分期限指数与债基估算久期 Repository。"""

import json
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class BondDurationRepo:
    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def upsert_index_points(self, definition: Dict[str, Any], indicator: str, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        from sqlalchemy import text

        sql = text("""
            INSERT INTO bond_index_series (
                series_key, index_group, index_name, index_id, period_code,
                period_label, indicator, trade_date, value, source,
                source_url, fetched_at
            ) VALUES (
                :series_key, :index_group, :index_name, :index_id, :period_code,
                :period_label, :indicator, :trade_date, :value, :source,
                :source_url, NOW()
            )
            ON CONFLICT (series_key, indicator, trade_date) DO UPDATE SET
                value = EXCLUDED.value,
                index_name = EXCLUDED.index_name,
                source = EXCLUDED.source,
                source_url = EXCLUDED.source_url,
                fetched_at = NOW()
        """)
        payload = [{**definition, "indicator": indicator, **row} for row in rows]
        with self.engine.begin() as conn:
            conn.execute(sql, payload)
        return len(payload)

    def list_index_series(
        self,
        series_keys: List[str],
        indicator: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not series_keys:
            return {}
        from sqlalchemy import text

        sql = text("""
            SELECT series_key, index_group, index_name, index_id, period_code,
                   period_label, indicator, trade_date, value, source, source_url
            FROM bond_index_series
            WHERE series_key = ANY(:series_keys)
              AND indicator = :indicator
              AND (:start_date IS NULL OR trade_date >= CAST(:start_date AS DATE))
              AND (:end_date IS NULL OR trade_date <= CAST(:end_date AS DATE))
            ORDER BY series_key, trade_date
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {
                "series_keys": series_keys,
                "indicator": indicator,
                "start_date": start_date,
                "end_date": end_date,
            }).fetchall()
        grouped: Dict[str, List[Dict[str, Any]]] = {key: [] for key in series_keys}
        for row in rows:
            item = self._serialize(dict(row._mapping))
            grouped.setdefault(str(item["series_key"]), []).append(item)
        return grouped

    def latest_indicator_values(
        self,
        series_keys: List[str],
        indicator: str,
        as_of_date: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        if not series_keys:
            return {}
        from sqlalchemy import text

        sql = text("""
            SELECT DISTINCT ON (series_key)
                   series_key, index_group, index_name, index_id, period_code,
                   period_label, indicator, trade_date, value, source, source_url
            FROM bond_index_series
            WHERE series_key = ANY(:series_keys)
              AND indicator = :indicator
              AND (:as_of_date IS NULL OR trade_date <= CAST(:as_of_date AS DATE))
            ORDER BY series_key, trade_date DESC
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {
                "series_keys": series_keys,
                "indicator": indicator,
                "as_of_date": as_of_date,
            }).fetchall()
        return {
            str(row.series_key): self._serialize(dict(row._mapping))
            for row in rows
        }

    def index_inventory(self) -> Dict[str, Any]:
        from sqlalchemy import text

        sql = text("""
            SELECT indicator, COUNT(DISTINCT series_key) AS series_count,
                   COUNT(*) AS observations, MIN(trade_date) AS start_date,
                   MAX(trade_date) AS end_date
            FROM bond_index_series
            GROUP BY indicator
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        indicators = {
            str(row.indicator): self._serialize(dict(row._mapping))
            for row in rows
        }
        return {
            "status": "ready" if all(int((indicators.get(key) or {}).get("series_count") or 0) >= 20 for key in ("wealth", "duration")) else "incomplete",
            "indicators": indicators,
        }

    def upsert_estimate(self, row: Dict[str, Any]) -> None:
        from sqlalchemy import text

        sql = text("""
            INSERT INTO fund_bond_duration_estimates (
                wind_code, as_of_date, window_weeks, data_start, data_end,
                observations, estimated_duration, duration_bucket, r_squared,
                tracking_error, selected_series, weights, group_diagnostics,
                methodology_version, status, source, missing_items, calculated_at
            ) VALUES (
                :wind_code, :as_of_date, :window_weeks, :data_start, :data_end,
                :observations, :estimated_duration, :duration_bucket, :r_squared,
                :tracking_error, CAST(:selected_series AS jsonb), CAST(:weights AS jsonb),
                CAST(:group_diagnostics AS jsonb), :methodology_version, :status,
                :source, CAST(:missing_items AS jsonb), NOW()
            )
            ON CONFLICT (wind_code, as_of_date, window_weeks) DO UPDATE SET
                data_start = EXCLUDED.data_start,
                data_end = EXCLUDED.data_end,
                observations = EXCLUDED.observations,
                estimated_duration = EXCLUDED.estimated_duration,
                duration_bucket = EXCLUDED.duration_bucket,
                r_squared = EXCLUDED.r_squared,
                tracking_error = EXCLUDED.tracking_error,
                selected_series = EXCLUDED.selected_series,
                weights = EXCLUDED.weights,
                group_diagnostics = EXCLUDED.group_diagnostics,
                methodology_version = EXCLUDED.methodology_version,
                status = EXCLUDED.status,
                source = EXCLUDED.source,
                missing_items = EXCLUDED.missing_items,
                calculated_at = NOW()
        """)
        payload = dict(row)
        for key in ("selected_series", "weights", "group_diagnostics", "missing_items"):
            payload[key] = json.dumps(payload.get(key) or [], ensure_ascii=False)
        with self.engine.begin() as conn:
            conn.execute(sql, payload)

    def latest_estimate(self, wind_code: str, window_weeks: int = 104) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text("""
            SELECT *
            FROM fund_bond_duration_estimates
            WHERE wind_code = :wind_code AND window_weeks = :window_weeks
            ORDER BY as_of_date DESC, calculated_at DESC
            LIMIT 1
        """)
        with self.engine.connect() as conn:
            row = conn.execute(sql, {
                "wind_code": wind_code,
                "window_weeks": window_weeks,
            }).fetchone()
        return self._serialize(dict(row._mapping)) if row else None

    @staticmethod
    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("value", "estimated_duration", "r_squared", "tracking_error"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        for key in ("trade_date", "start_date", "end_date", "as_of_date", "data_start", "data_end", "calculated_at"):
            if row.get(key) is not None:
                row[key] = row[key].isoformat()
        return row
