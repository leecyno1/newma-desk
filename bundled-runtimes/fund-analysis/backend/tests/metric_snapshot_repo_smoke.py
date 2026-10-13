"""显式启用的真实PostgreSQL临时表验收，外层事务回滚，不写业务指标。"""
import os
import sys
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repositories.metric_snapshot_repo import MetricSnapshotRepo


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
    if os.environ.get('FUND_METRIC_ALLOW_TEMP_TEST') != '1':
        print('SKIP metric storage: set FUND_METRIC_ALLOW_TEMP_TEST=1 for rollback-only temporary tables')
        return
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DBAPIError
    from database import get_database_url, load_shared_database_environment
    load_dotenv(Path(__file__).resolve().parents[2] / '.env.local')
    load_shared_database_environment()
    engine = create_engine(get_database_url())
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text('CREATE TEMP TABLE metric_snapshots (LIKE public.metric_snapshots INCLUDING ALL) ON COMMIT DROP'))
                assert connection.execute(text("SELECT to_regclass('metric_snapshots')=to_regclass('pg_temp.metric_snapshots')")).scalar()
                repo = MetricSnapshotRepo()
                repo._engine = TemporaryEngine(connection)
                record = dict(target_type='fund', target_id='TEMP.METRIC', as_of_date=date(2026, 10, 2),
                              metric_name='annualized_return', metric_value=Decimal('.1'),
                              metric_unit='ratio', window='1y', benchmark_code=None, peer_group_key=None,
                              details={'methodology_version': 'legacy'})
                original = repo.upsert_metric(**record)
                new_record = {**record, 'metric_value': Decimal('.2'), 'details': {'methodology_version': 'new'}}
                updated = repo.upsert_metrics([new_record])[0]
                assert original['id'] == updated['id']
                assert updated['details']['_revision_history'][0]['metric_value'] == '0.10000000'
                assert updated['details']['_revision_history'][0]['details'] == record['details']
                assert connection.execute(text('SELECT count(*) FROM metric_snapshots')).scalar() == 1
                identical = repo.upsert_metrics([new_record])[0]
                assert len(identical['details']['_revision_history']) == 1
                assert identical['updated_at'] == updated['updated_at']

                # 第二条SQL失败时，第一条修订及其历史一起回滚。
                try:
                    repo.upsert_metrics([{**new_record, 'metric_value': Decimal('.3')},
                                         {**record, 'metric_name': 'max_drawdown', 'source_snapshot_id': 'invalid-uuid'}])
                except DBAPIError:
                    pass
                else:
                    raise AssertionError('invalid UUID should roll back the whole panel')
                after_failure = repo.get_latest_panel('fund', 'TEMP.METRIC')
                assert len(after_failure) == 1
                assert after_failure[0]['metric_value'] == '0.20000000'
                assert len(after_failure[0]['details']['_revision_history']) == 1

                latest = repo.upsert_metric(**{**record, 'metric_value': Decimal('.4'), 'details': None})
                assert 'methodology_version' not in latest['details']  # 无版本的改值不能继承新方法标签。
                assert len(latest['details']['_revision_history']) == 2
                assert latest['details']['_revision_history'][1]['details'] == new_record['details']
                assert '_revision_history' not in latest['details']['_revision_history'][1]['details']
                try:
                    repo.upsert_metrics([record, record])
                except ValueError:
                    pass
                else:
                    raise AssertionError('duplicate natural keys must not be silently overwritten')
                assert repo.upsert_metrics([]) == []
                assert len(repo.get_latest_panels('fund', ['TEMP.METRIC'])['TEMP.METRIC']) == 1
                assert len(repo.get_metrics_as_of('fund', 'TEMP.METRIC', record['as_of_date'])) == 1
                print('OK 7 metric storage scenarios: NULL keys, revisions, idempotency, full rollback, unknown method, duplicate batch, read paths')
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
