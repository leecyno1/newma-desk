"""失效指标归档/移出/派生字段清理的真实PG临时表验收，外层全部回滚。"""
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metric_snapshot_repo_smoke import TemporaryEngine
from repositories.metric_snapshot_repo import MetricSnapshotRepo
from services.scoring_engine import FundScoringEngine
from scripts import sync_fund_ranking_metrics as ranking


def main():
    if os.environ.get('FUND_METRIC_ALLOW_TEMP_TEST') != '1':
        print('SKIP metric invalidation archives: set FUND_METRIC_ALLOW_TEMP_TEST=1 for rollback-only temporary tables')
        return
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DBAPIError
    from database import get_database_url, load_shared_database_environment
    load_dotenv(Path(__file__).resolve().parents[2] / '.env.local', override=False)
    load_shared_database_environment()
    engine = create_engine(get_database_url())
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                for name in ('metric_snapshots', 'data_source_snapshots'):
                    conn.execute(text(f'CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL) ON COMMIT DROP'))
                conn.execute(text('''CREATE TEMP TABLE funds (wind_code text PRIMARY KEY,
                    performance_data jsonb, risk_metrics jsonb, raw_data jsonb, updated_at timestamp) ON COMMIT DROP'''))
                for name in ('metric_snapshots', 'data_source_snapshots', 'funds'):
                    assert conn.execute(text('SELECT to_regclass(:name)=to_regclass(:temp)'),
                                        {'name': name, 'temp': f'pg_temp.{name}'}).scalar()
                conn.execute(text('''INSERT INTO funds VALUES ('TEMP.ARCHIVE',
                    CAST(:performance AS jsonb), CAST(:risk AS jsonb), '{}', now())'''),
                    {'performance': '{"annualized_return_5y":0.2,"expense_ratio":0.005}',
                     'risk': '{"max_drawdown_5y":-0.1,"note":"keep"}'})
                repo = MetricSnapshotRepo()
                repo._engine = TemporaryEngine(conn)
                base = dict(target_type='fund', target_id='TEMP.ARCHIVE', as_of_date=date(2026, 9, 30),
                            metric_name='annualized_return', metric_value=Decimal('.12345678'),
                            metric_unit='ratio', window='1y', details={'methodology_version': 'test'})
                original = repo.upsert_metric(**base)
                repo.upsert_metric(**{**base, 'metric_value': Decimal('.23456789')})
                repo.upsert_metrics([
                    {**base, 'window': '5y'}, {**base, 'window': 'manager_tenure'},
                    {**base, 'window': 'latest', 'metric_name': 'seven_day_annualized_yield'},
                    {**base, 'window': 'custom7d'}, {**base, 'as_of_date': date(2026, 9, 29)},
                    {**base, 'window': 'latest', 'metric_name': 'aum'},
                    {**base, 'window': 'latest', 'metric_name': 'expense_ratio'},
                    {**base, 'window': 'latest', 'metric_name': 'benchmark_annualized_rate'},
                    {**base, 'target_id': 'OTHER.ARCHIVE'},
                ])
                with patch.object(ranking, 'get_engine', return_value=repo.engine), \
                     patch('services.cache_service.invalidate_fund_cache') as invalidate_cache:
                    result = ranking.invalidate_nav_derived_evaluation_facts('TEMP.ARCHIVE', {'status': 'invalid', 'issues': ['test']})
                    assert result['archived_metrics'] == 6
                    invalidate_cache.assert_called_once_with('TEMP.ARCHIVE')
                    active = repo.get_latest_panel('fund', 'TEMP.ARCHIVE')
                    assert {row['metric_name'] for row in active} == {'aum', 'expense_ratio', 'benchmark_annualized_rate'}
                    assert FundScoringEngine().score_fund_from_metric_snapshots('TEMP.ARCHIVE', repo)['overall_score'] is None
                    assert len(repo.get_latest_panel('fund', 'OTHER.ARCHIVE')) == 1
                    archive = repo.get_invalidation_archive('TEMP.ARCHIVE', result['archive_id'])
                    assert archive['record_count'] == 6
                    archived = archive['metadata']['metric_snapshots']
                    revised = next(row for row in archived if row['id'] == str(original['id']))
                    assert revised['metric_value'] == '0.23456789'
                    assert revised['details']['_revision_history'][0]['metric_value'] == '0.12345678'
                    assert archive['metadata']['prior_evaluation']['performance_data']['annualized_return_5y'] == .2
                    assert repo.get_invalidation_archive('OTHER.ARCHIVE', result['archive_id']) is None
                    summaries = repo.list_invalidation_archives('TEMP.ARCHIVE', 10)
                    assert len(summaries) == 1 and 'metric_snapshots' not in summaries[0]
                    fund = conn.execute(text('SELECT * FROM funds')).mappings().one()
                    assert fund['performance_data'] == {'expense_ratio': .005}
                    assert fund['risk_metrics'] == {'note': 'keep'}
                    assert fund['raw_data']['ranking_metrics']['archive_id'] == result['archive_id']
                    repeat = ranking.invalidate_nav_derived_evaluation_facts('TEMP.ARCHIVE', {'status': 'invalid'})
                    assert repeat['archived_metrics'] == 0
                    assert repeat['archive_id'] == result['archive_id']
                    assert len(repo.list_invalidation_archives('TEMP.ARCHIVE')) == 1

                    repo.upsert_metric(**base)
                    for table, clause in (
                        ('data_source_snapshots', "source <> 'desk.metric_invalidation'"),
                        ('funds', "raw_data#>>'{ranking_metrics,status}' IS DISTINCT FROM 'invalid_nav'"),
                    ):
                        conn.execute(text(f'ALTER TABLE pg_temp.{table} ADD CONSTRAINT fail_archive_test CHECK ({clause}) NOT VALID'))
                        invalidate_cache.reset_mock()
                        before = repo.get_latest_panel('fund', 'TEMP.ARCHIVE')
                        try:
                            ranking.invalidate_nav_derived_evaluation_facts('TEMP.ARCHIVE', {'status': 'invalid'})
                        except DBAPIError:
                            pass
                        else:
                            raise AssertionError(f'{table} failure must abort the whole invalidation')
                        assert repo.get_latest_panel('fund', 'TEMP.ARCHIVE') == before
                        assert len(repo.list_invalidation_archives('TEMP.ARCHIVE')) == 1
                        invalidate_cache.assert_not_called()
                        conn.execute(text(f'ALTER TABLE pg_temp.{table} DROP CONSTRAINT fail_archive_test'))
                print('OK 6 invalidation scenarios: full archive/revisions, static and other-fund preservation, scoped reads, repeat, archive failure rollback, fund update failure rollback')
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
