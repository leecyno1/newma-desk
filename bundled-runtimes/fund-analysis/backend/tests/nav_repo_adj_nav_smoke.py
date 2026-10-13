"""真实PG会话临时表验证，默认跳过；不初始化、不写公共基金/净值表。"""
import os
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repositories.nav_repo import NavRepo, NAV_PROVENANCE_COLUMNS


class TemporaryEngine:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def begin(self):
        with self.connection.begin_nested():
            yield self.connection

    @contextmanager
    def connect(self):
        yield self.connection


def main():
    if os.environ.get('FUND_NAV_ALLOW_TEMP_TEST') != '1':
        print('SKIP NAV storage: set FUND_NAV_ALLOW_TEMP_TEST=1 for rollback-only temporary tables')
        return
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text
    from database import get_database_url, load_shared_database_environment
    load_dotenv(Path(__file__).resolve().parents[2] / '.env.local', override=False)
    load_shared_database_environment()
    engine = create_engine(get_database_url())
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                # 不复制公共SERIAL默认值，避免临时测试消耗业务表序列。
                conn.execute(text('''CREATE TEMP TABLE fund_nav (
                    wind_code text, trade_date date, nav numeric(10,4), unit_nav numeric(10,4),
                    accum_nav numeric(10,4), adj_nav numeric(12,4), daily_return numeric(12,8),
                    benchmark_nav numeric(10,4), discount_rate numeric(12,8),
                    UNIQUE(wind_code, trade_date)) ON COMMIT DROP'''))
                conn.execute(text('''CREATE TEMP TABLE funds (wind_code text PRIMARY KEY, name text,
                    type text, nav numeric(20,10), nav_date date, raw_data jsonb) ON COMMIT DROP'''))
                for name in ('fund_nav', 'funds'):
                    assert conn.execute(text('SELECT to_regclass(:name)=to_regclass(:temp)'),
                                        {'name': name, 'temp': f'pg_temp.{name}'}).scalar()
                conn.execute(text("INSERT INTO funds (wind_code, name, type) VALUES ('TEMP.NAV', '临时基金', '债券型')"))
                repo = NavRepo()
                repo._engine = TemporaryEngine(conn)
                row = {'date': '2026-09-29', 'unit_nav': Decimal('1.1234567890'),
                       'accum_nav': Decimal('3.1234567890'), 'adj_nav': Decimal('3.1234567890'),
                       'reported_accum_nav': Decimal('2.9876543210'), 'announcement_date': '2026-09-30',
                       'adj_nav_source': 'tushare.fund_nav.adj_nav', 'benchmark_nav': Decimal('100.1234567890'),
                       'benchmark_code': '000300.SH', 'benchmark_source': 'tushare.index_daily.close'}
                assert repo.get_storage_evidence()['status'] == 'migration_required'
                assert repo.upsert_nav_series('TEMP.NAV', [row])
                legacy = repo.get_nav_series('TEMP.NAV')[0]
                assert legacy['adj_nav'] == Decimal('3.1235')
                assert all(legacy[key] is None for key in NAV_PROVENANCE_COLUMNS)

                for name, kind in NAV_PROVENANCE_COLUMNS.items():
                    conn.execute(text(f'ALTER TABLE pg_temp.fund_nav ADD COLUMN {name} {kind}'))
                for name in ('nav', 'unit_nav', 'adj_nav', 'benchmark_nav'):
                    conn.execute(text(f'ALTER TABLE pg_temp.fund_nav ALTER COLUMN {name} TYPE numeric(20,10)'))
                assert repo.get_storage_evidence()['status'] == 'schema_ready'
                assert repo.upsert_nav_series('TEMP.NAV', [row], update_latest=True)
                saved = repo.get_nav_series('TEMP.NAV')[0]
                assert saved['adj_nav'] == row['adj_nav']
                assert saved['unit_nav'] == row['unit_nav']
                assert saved['reported_accum_nav'] == row['reported_accum_nav']
                assert saved['reported_accum_nav'] != saved['accum_nav']
                assert saved['announcement_date'] == '2026-09-30'
                assert saved['benchmark_code'] == row['benchmark_code']
                assert saved['benchmark_source'] == row['benchmark_source']

                no_benchmark = {key: value for key, value in row.items() if not key.startswith('benchmark_')}
                assert repo.upsert_nav_series('TEMP.NAV', [no_benchmark])
                retained = repo.get_nav_series('TEMP.NAV')[0]
                assert all(retained[key] == saved[key] for key in ('benchmark_nav', 'benchmark_code', 'benchmark_source'))
                assert repo.upsert_nav_series('TEMP.NAV', [{**no_benchmark, 'benchmark_nav': None}])
                cleared = repo.get_nav_series('TEMP.NAV')[0]
                assert all(cleared[key] is None for key in ('benchmark_nav', 'benchmark_code', 'benchmark_source'))
                assert repo.upsert_nav_series('TEMP.NAV', [row])
                assert repo.upsert_nav_series('TEMP.NAV', [{**no_benchmark, 'benchmark_nav': 200}])
                unknown = repo.get_nav_series('TEMP.NAV')[0]
                assert unknown['benchmark_nav'] == 200
                assert unknown['benchmark_code'] is None and unknown['benchmark_source'] is None

                changed = {**row, 'adj_nav': Decimal('3.2234567890'), 'announcement_date': '2026-10-01'}
                assert repo.upsert_nav_series('TEMP.NAV', [changed])
                corrected = repo.get_nav_series('TEMP.NAV')[0]
                assert corrected['announcement_date'] == '2026-10-01'
                assert corrected['adj_nav'] == changed['adj_nav']
                assert not repo.upsert_nav_series('TEMP.NAV', [{**row, 'adj_nav': 5},
                    {**row, 'date': '2026-09-30', 'announcement_date': 'invalid-date'}], replace_range=True)
                assert repo.get_nav_series('TEMP.NAV') == [corrected]
                assert repo.upsert_nav_series('TEMP.NAV', [{**no_benchmark, 'adj_nav': None}])
                missing = repo.get_nav_series('TEMP.NAV')[0]
                assert missing['adj_nav'] is None and missing['adj_nav_source'] is None

                fund = conn.execute(text('SELECT nav_date,raw_data FROM funds')).mappings().one()
                assert str(fund['nav_date']) == '2026-09-29'
                assert fund['raw_data']['nav_refresh']['storage_evidence']['status'] == 'schema_ready'
                assert repo.upsert_nav_series('TEMP.NAV', [{**row, 'date': '2026-09-28', 'unit_nav': 8}], update_latest=True)
                assert str(conn.execute(text('SELECT nav_date FROM funds')).scalar()) == '2026-09-29'
                print('OK 9 NAV storage scenarios: legacy compatibility, precision/provenance, benchmark omission, explicit gap, unknown identity, revision, rollback, source clearing, latest NAV')
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
