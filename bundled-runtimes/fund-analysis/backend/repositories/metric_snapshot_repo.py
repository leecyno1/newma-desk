"""
指标快照 Repository
"""
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_database_url
except ModuleNotFoundError:
    from database import get_database_url

logger = logging.getLogger(__name__)

_engine = None
INVALID_METRIC_ARCHIVE_SOURCE = 'desk.metric_invalidation'
NAV_METRIC_WINDOWS = ('3m', '6m', '1y', '3y', '5y', 'manager_tenure')
NAV_METRIC_NAMES = (
    'total_return', 'annualized_return', 'max_drawdown', 'annualized_volatility',
    'sharpe_ratio', 'calmar_ratio', 'sortino_ratio', 'downside_risk', 'var_95', 'var_99',
    'tracking_error', 'information_ratio', 'excess_return', 'tracking_difference', 'benchmark_return',
    'daily_return_mean', 'daily_return_std', 'positive_return_ratio', 'monthly_win_rate',
    'record_breaking_days_ratio', 'start_nav', 'end_nav', 'observations', 'active_return_mean',
    'tenure_days', 'metric_coverage_days', 'tenure_coverage_ratio',
    'seven_day_annualized_yield', 'income_per_10000', 'benchmark_yield_spread',
)


def archive_invalid_nav_metrics(conn, fund_code, validation):
    """在调用方事务中先归档后移出活跃指标；缓存更新失败时一起回滚。"""
    from sqlalchemy import text
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:kind), hashtext(:target))'),
                 {'kind': 'fund', 'target': fund_code})
    conn.execute(text('SELECT wind_code FROM funds WHERE wind_code=:fund_code FOR UPDATE'), {'fund_code': fund_code})
    row = conn.execute(text("""
        WITH affected AS MATERIALIZED (
            SELECT * FROM metric_snapshots
            WHERE target_type='fund' AND target_id=:fund_code
              AND (metric_window=ANY(:windows) OR metric_name=ANY(:names)
                   OR details->>'nav_basis'='adj_nav')
            FOR UPDATE
        ), archived AS (
            INSERT INTO data_source_snapshots
                (source, dataset, status, coverage_start, coverage_end, finished_at, record_count, metadata)
            SELECT :source, :dataset, 'success', MIN(as_of_date), MAX(as_of_date), clock_timestamp(), COUNT(*),
                jsonb_build_object('archive_version', 1, 'fund_code', :fund_code,
                    'reason', 'invalid_nav', 'validation', CAST(:validation AS jsonb),
                    'metric_snapshots', jsonb_agg(to_jsonb(affected) || jsonb_build_object('metric_value', metric_value::text)),
                    'prior_evaluation', (SELECT jsonb_build_object('performance_data', performance_data,
                        'risk_metrics', risk_metrics) FROM funds WHERE wind_code=:fund_code))
            FROM affected HAVING COUNT(*)>0
            RETURNING id, record_count
        ), removed AS (
            DELETE FROM metric_snapshots active USING affected
            WHERE active.id=affected.id AND EXISTS (SELECT 1 FROM archived)
            RETURNING active.id
        )
        SELECT id, record_count, (SELECT COUNT(*) FROM removed) AS removed_count FROM archived
    """), {'fund_code': fund_code, 'windows': list(NAV_METRIC_WINDOWS), 'names': list(NAV_METRIC_NAMES),
           'source': INVALID_METRIC_ARCHIVE_SOURCE, 'dataset': f'fund.invalid_metrics:{fund_code}',
           'validation': _json(validation)}).mappings().first()
    if row and row['record_count'] != row['removed_count']:
        raise RuntimeError('失效指标归档与移出数量不一致，事务必须回滚')
    return {'archive_id': str(row['id']) if row else None, 'archived_metrics': row['record_count'] if row else 0}


def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        pg_url = get_database_url()
        _engine = create_engine(pg_url, pool_pre_ping=True, pool_size=20, max_overflow=30, pool_recycle=3600)
    return _engine


def _json(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _row_to_dict(row) -> Dict[str, Any]:
    data = dict(row._mapping)
    for key, value in list(data.items()):
        if isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
        elif isinstance(value, Decimal):
            data[key] = str(value)
    return data


class MetricSnapshotRepo:
    """指标快照访问层。"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def list_invalidation_archives(self, fund_code: str, limit: int = 10):
        from sqlalchemy import text
        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, coverage_start, coverage_end, finished_at, record_count,
                    metadata->'validation' AS validation
                FROM data_source_snapshots WHERE source=:source AND dataset=:dataset
                ORDER BY finished_at DESC, id DESC LIMIT :limit
            """), {'source': INVALID_METRIC_ARCHIVE_SOURCE, 'dataset': f'fund.invalid_metrics:{fund_code}',
                   'limit': limit}).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_invalidation_archive(self, fund_code: str, archive_id):
        from sqlalchemy import text
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT * FROM data_source_snapshots WHERE id=CAST(:id AS uuid)
                  AND source=:source AND dataset=:dataset
            """), {'id': str(archive_id), 'source': INVALID_METRIC_ARCHIVE_SOURCE,
                   'dataset': f'fund.invalid_metrics:{fund_code}'}).fetchone()
        return _row_to_dict(row) if row else None

    def upsert_metric(
        self,
        target_type: str,
        target_id: str,
        as_of_date: date,
        metric_name: str,
        metric_value: Decimal,
        metric_unit: Optional[str] = None,
        window: Optional[str] = None,
        benchmark_code: Optional[str] = None,
        peer_group_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.upsert_metrics([{
            'target_type': target_type, 'target_id': target_id, 'as_of_date': as_of_date,
            'metric_name': metric_name, 'metric_value': metric_value, 'metric_unit': metric_unit,
            'window': window, 'benchmark_code': benchmark_code, 'peer_group_key': peer_group_key,
            'source_snapshot_id': source_snapshot_id, 'details': details,
        }])[0]

    def upsert_metrics(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """整批指标同一事务；同键修订保留旧内容，不隐式初始化数据库。"""
        from sqlalchemy import text

        if not records:
            return []
        keys = ('target_type', 'target_id', 'as_of_date', 'metric_name', 'window', 'benchmark_code', 'peer_group_key')
        natural_keys = [tuple(str(record.get(key)) if record.get(key) is not None else None for key in keys) for record in records]
        if len(set(natural_keys)) != len(natural_keys):
            raise ValueError('同一批指标存在重复窗口/基准/同类键，未保存')
        insert_sql = """
            INSERT INTO metric_snapshots (
                target_type, target_id, as_of_date, metric_name, metric_value,
                metric_unit, metric_window, benchmark_code, peer_group_key,
                source_snapshot_id, details
            ) VALUES (
                :target_type, :target_id, :as_of_date, :metric_name, :metric_value,
                :metric_unit, :window, :benchmark_code, :peer_group_key,
                CASE WHEN :source_snapshot_id IS NULL THEN NULL ELSE CAST(:source_snapshot_id AS UUID) END,
                CAST(:details AS JSONB)
            )
            RETURNING *
        """
        find_sql = """
            SELECT * FROM metric_snapshots
            WHERE target_type=:target_type AND target_id=:target_id AND as_of_date=:as_of_date
              AND metric_name=:metric_name AND metric_window IS NOT DISTINCT FROM :window
              AND benchmark_code IS NOT DISTINCT FROM :benchmark_code
              AND peer_group_key IS NOT DISTINCT FROM :peer_group_key
            ORDER BY updated_at DESC, id DESC LIMIT 1 FOR UPDATE
        """
        update_sql = """
            UPDATE metric_snapshots SET metric_value=:metric_value, metric_unit=:metric_unit,
                source_snapshot_id=CASE WHEN :source_snapshot_id IS NULL THEN NULL ELSE CAST(:source_snapshot_id AS UUID) END,
                details=CAST(:details AS JSONB), updated_at=clock_timestamp()
            WHERE id=CAST(:id AS UUID) RETURNING *
        """
        saved = []
        with self.engine.begin() as conn:
            # 空键的旧UNIQUE约束不拦重复，Desk写入按对象串行；独立上游仍须另行协调。
            for target_type, target_id in sorted({(record['target_type'], record['target_id']) for record in records}):
                conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:kind), hashtext(:target))'),
                             {'kind': target_type, 'target': target_id})
            for record in records:
                params = {key: record.get(key) for key in (*keys, 'metric_unit', 'source_snapshot_id')}
                value = Decimal(str(record['metric_value']))
                if not value.is_finite():
                    raise ValueError('指标数值不是有限值，整批未保存')
                params['metric_value'] = value.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                incoming = json.loads(_json(record.get('details')) or '{}')
                incoming.pop('_revision_history', None)
                existing = conn.execute(text(find_sql), params).fetchone()
                if existing:
                    previous = _row_to_dict(existing)
                    old_details = dict(previous.get('details') or {})
                    history = list(old_details.pop('_revision_history', []))
                    unchanged = (Decimal(previous['metric_value']) == params['metric_value']
                                 and previous.get('metric_unit') == params['metric_unit']
                                 and str(previous.get('source_snapshot_id') or '') == str(params['source_snapshot_id'] or '')
                                 and old_details == incoming)
                    if unchanged:
                        saved.append(previous)
                        continue
                    history.append({key: previous.get(key) for key in ('metric_value', 'metric_unit', 'source_snapshot_id', 'updated_at')} | {
                        'details': previous.get('details') if previous.get('details') is None else old_details,
                    })
                    incoming['_revision_history'] = history
                    params.update(id=previous['id'], details=_json(incoming))
                    row = conn.execute(text(update_sql), params).fetchone()
                else:
                    params['details'] = _json(incoming) if record.get('details') is not None else None
                    row = conn.execute(text(insert_sql), params).fetchone()
                saved.append(_row_to_dict(row))
        return saved

    def get_latest_panel(self, target_type: str, target_id: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = """
            SELECT DISTINCT ON (metric_name, metric_window, benchmark_code, peer_group_key) *
            FROM metric_snapshots
            WHERE target_type = :target_type AND target_id = :target_id
            ORDER BY metric_name, metric_window, benchmark_code, peer_group_key, as_of_date DESC, updated_at DESC, id DESC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "target_type": target_type,
                "target_id": target_id,
            }).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_latest_panels(self, target_type: str, target_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        from sqlalchemy import text

        safe_target_ids = [str(target_id).strip() for target_id in target_ids if str(target_id or "").strip()]
        if not safe_target_ids:
            return {}

        sql = """
            SELECT DISTINCT ON (target_id, metric_name, metric_window, benchmark_code, peer_group_key) *
            FROM metric_snapshots
            WHERE target_type = :target_type AND target_id = ANY(:target_ids)
            ORDER BY target_id, metric_name, metric_window, benchmark_code, peer_group_key, as_of_date DESC, updated_at DESC, id DESC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "target_type": target_type,
                "target_ids": safe_target_ids,
            }).fetchall()
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            item = _row_to_dict(row)
            result.setdefault(str(item.get("target_id")), []).append(item)
        return result

    def get_metrics_as_of(
        self,
        target_type: str,
        target_id: str,
        as_of_date: date,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = """
            SELECT * FROM metric_snapshots
            WHERE target_type = :target_type
              AND target_id = :target_id
              AND as_of_date = :as_of_date
            ORDER BY metric_name, metric_window NULLS FIRST
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "target_type": target_type,
                "target_id": target_id,
                "as_of_date": as_of_date,
            }).fetchall()
        return [_row_to_dict(row) for row in rows]
