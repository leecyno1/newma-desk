"""
基金净值 Repository
"""
import os
import math
import json
from typing import List, Dict, Any
import logging

try:
    from backend.database import get_database_url
except ModuleNotFoundError:
    from database import get_database_url

logger = logging.getLogger(__name__)

from services.fund_trading_calendar import fund_risk_calendar

_engine = None

# 由受控迁移增加；旧库继续可读写，不能把兼容accum_nav冒充真实累计值。
NAV_PROVENANCE_COLUMNS = {
    'reported_accum_nav': 'numeric(20,10)',
    'announcement_date': 'date',
    'adj_nav_source': 'text',
    'benchmark_code': 'text',
    'benchmark_source': 'text',
}


def nav_storage_columns(conn):
    from sqlalchemy import text
    return {row['name']: row['data_type'] for row in conn.execute(text("""
        SELECT attname AS name, format_type(atttypid, atttypmod) AS data_type
        FROM pg_attribute WHERE attrelid=to_regclass('fund_nav')
          AND attnum>0 AND NOT attisdropped
    """)).mappings()}


def nav_storage_evidence(columns):
    missing = sorted(set(NAV_PROVENANCE_COLUMNS) - set(columns))
    return {
        'status': 'schema_ready' if not missing else 'migration_required',
        'missing_provenance_columns': missing,
        'stored_provenance_columns': sorted(set(NAV_PROVENANCE_COLUMNS) & set(columns)),
        'value_types': {name: columns.get(name) for name in ('nav', 'unit_nav', 'adj_nav', 'reported_accum_nav', 'benchmark_nav')},
        'boundary': '仅表示字段承载能力，不证明历史来源齐备；扩列不能恢复旧值精度，不自动回填或重算。',
    }


def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        pg_url = get_database_url()
        _engine = create_engine(pg_url, pool_pre_ping=True, pool_size=20, max_overflow=30, pool_recycle=3600)
    return _engine


def _clean(v):
    """清理 NaN/Inf"""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


class NavRepo:
    """基金净值数据访问层"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def get_storage_evidence(self):
        with self.engine.connect() as conn:
            return nav_storage_evidence(nav_storage_columns(conn))

    def upsert_nav_series(
        self,
        wind_code: str,
        nav_data: List[Dict[str, Any]],
        replace_range: bool = False,
        update_latest: bool = False,
    ) -> bool:
        """Upsert 基金净值序列；权威源同步可先替换本次覆盖日期范围。"""
        try:
            from sqlalchemy import text

            if not nav_data:
                return False

            insert_sql = """
            INSERT INTO fund_nav (
                wind_code, trade_date, nav, unit_nav, accum_nav,
                adj_nav, daily_return, benchmark_nav, discount_rate{extra_columns}
            ) VALUES (
                :wind_code, :trade_date, :nav, :unit_nav, :accum_nav,
                :adj_nav, :daily_return, :benchmark_nav, :discount_rate{extra_values}
            )
            ON CONFLICT (wind_code, trade_date) DO UPDATE SET
                nav = EXCLUDED.nav,
                unit_nav = EXCLUDED.unit_nav,
                accum_nav = EXCLUDED.accum_nav,
                adj_nav = EXCLUDED.adj_nav,
                daily_return = EXCLUDED.daily_return,
                benchmark_nav = CASE WHEN :benchmark_provided THEN EXCLUDED.benchmark_nav ELSE fund_nav.benchmark_nav END,
                discount_rate = EXCLUDED.discount_rate{extra_updates}
            """

            valid_dates = sorted(
                str(nav.get("date") or "").strip()
                for nav in nav_data
                if str(nav.get("date") or "").strip()
            )
            with self.engine.begin() as conn:
                columns = nav_storage_columns(conn)
                supported = [name for name in NAV_PROVENANCE_COLUMNS if name in columns]
                updates = []
                for name in supported:
                    if name in ('benchmark_code', 'benchmark_source'):
                        updates.append(f'{name}=CASE WHEN :benchmark_provided THEN EXCLUDED.{name} ELSE fund_nav.{name} END')
                    else:
                        updates.append(f'{name}=EXCLUDED.{name}')
                insert_sql = insert_sql.format(
                    extra_columns=''.join(f', {name}' for name in supported),
                    extra_values=''.join(f', :{name}' for name in supported),
                    extra_updates=''.join(f', {update}' for update in updates),
                )
                if replace_range and valid_dates:
                    conn.execute(text("""
                        DELETE FROM fund_nav
                        WHERE wind_code = :wind_code
                          AND trade_date BETWEEN :start_date AND :end_date
                    """), {
                        "wind_code": wind_code,
                        "start_date": valid_dates[0],
                        "end_date": valid_dates[-1],
                    })
                params = []
                for nav in nav_data:
                    nav_value = _clean(nav.get("unit_nav") if nav.get("unit_nav") is not None else nav.get("nav"))
                    params.append({
                        "wind_code": wind_code,
                        "trade_date": nav.get("date", ""),
                        "nav": nav_value,
                        "unit_nav": nav_value,
                        "accum_nav": _clean(nav.get("accum_nav")),
                        "adj_nav": _clean(nav.get("adj_nav")),
                        "daily_return": _clean(nav.get("daily_return")),
                        "benchmark_nav": _clean(nav.get("benchmark_nav")),
                        "benchmark_provided": "benchmark_nav" in nav,
                        "discount_rate": _clean(nav.get("discount_rate")),
                        **{name: _clean(nav.get(name)) for name in supported},
                    })
                    if params[-1]['adj_nav'] is None and 'adj_nav_source' in supported:
                        params[-1]['adj_nav_source'] = None
                    if params[-1]['benchmark_nav'] is None:
                        for name in ('benchmark_code', 'benchmark_source'):
                            if name in supported:
                                params[-1][name] = None
                # 一批净值和覆盖窗口属于同一事务；任何一行失败都必须回滚。
                conn.execute(text(insert_sql), params)
                if update_latest:
                    latest = max(params, key=lambda row: str(row["trade_date"]))
                    conn.execute(text("""
                        UPDATE funds SET nav = :nav, nav_date = :trade_date,
                            raw_data = COALESCE(raw_data, '{}'::jsonb) ||
                                jsonb_build_object('nav_refresh', CAST(:refresh AS jsonb))
                        WHERE wind_code = :wind_code
                          AND (nav_date IS NULL OR nav_date <= :trade_date)
                    """), {
                        **latest,
                        "refresh": json.dumps({
                            "source": "tushare.fund_nav",
                            "as_of_date": str(latest["trade_date"]),
                            "observations": len(params),
                            "metrics_recalculated": False,
                            "storage_evidence": nav_storage_evidence(columns),
                        }),
                    })
            return True
        except Exception as e:
            logger.error(f"upsert_nav_series error for {wind_code}: {e}")
            return False

    def get_nav_series(
        self,
        wind_code: str,
        start_date: str = None,
        end_date: str = None,
    ) -> List[Dict[str, Any]]:
        """获取净值序列"""
        try:
            from sqlalchemy import text

            where_clauses = ["nav.wind_code = :wind_code"]
            params = {"wind_code": wind_code}

            if start_date:
                where_clauses.append("trade_date >= :start_date")
                params["start_date"] = start_date
            if end_date:
                where_clauses.append("trade_date <= :end_date")
                params["end_date"] = end_date

            where_sql = " AND ".join(where_clauses)

            with self.engine.connect() as conn:
                columns = nav_storage_columns(conn)
                projection = ', '.join(f'nav.{name}' if name in columns else f'NULL AS {name}' for name in NAV_PROVENANCE_COLUMNS)
                sql = f"""
                SELECT nav.trade_date, COALESCE(nav.unit_nav, nav.nav) AS unit_nav,
                       nav.accum_nav, nav.adj_nav, nav.daily_return, nav.benchmark_nav,
                       fund.type AS fund_type, fund.name AS fund_name, {projection}
                FROM fund_nav nav
                LEFT JOIN funds fund ON fund.wind_code = nav.wind_code
                WHERE {where_sql}
                ORDER BY trade_date ASC
                """
                result = conn.execute(text(sql), params)
                return [
                    {
                        "date": str(r.trade_date),
                        "nav": r.unit_nav,
                        "unit_nav": r.unit_nav,
                        "accum_nav": r.accum_nav,
                        "adj_nav": r.adj_nav,
                        "daily_return": r.daily_return,
                        "benchmark_nav": r.benchmark_nav,
                        **{name: str(getattr(r, name)) if name == 'announcement_date' and getattr(r, name) is not None
                           else getattr(r, name) for name in NAV_PROVENANCE_COLUMNS},
                        "risk_calendar": fund_risk_calendar({"type": r.fund_type, "name": r.fund_name}),
                    }
                    for r in result.fetchall()
                ]
        except Exception as e:
            logger.error(f"get_nav_series error for {wind_code}: {e}")
            return []

    def delete_nav(self, wind_code: str) -> bool:
        """删除净值数据"""
        try:
            from sqlalchemy import text
            sql = "DELETE FROM fund_nav WHERE wind_code = :wind_code"
            with self.engine.connect() as conn:
                conn.execute(text(sql), {"wind_code": wind_code})
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"delete_nav error: {e}")
            return False
