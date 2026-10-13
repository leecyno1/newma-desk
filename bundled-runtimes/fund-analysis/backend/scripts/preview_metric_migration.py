"""只读预览指定基金的旧指标缺口与新口径计算候选；不抓取数据、不保存或迁移。"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_trading_calendar import fund_risk_calendar
from services.metric_factory import MetricFactory
from services.scoring_engine import FundScoringEngine


def preview_fund(code, fund, nav_rows, panel, as_of):
    """纯计算预览，生产评分和迁移清单使用同一证据门槛。"""
    scoring = FundScoringEngine()
    _, _, old_audit = scoring._snapshot_evidence(panel)
    factory = MetricFactory()
    candidates, windows = [], []
    for window in ('1y', '3y', '5y'):
        records = factory.build_metric_records('fund', code, as_of, nav_rows, window=window)
        candidates.extend({**record, 'metric_window': record['window']} for record in records)
        values = {record['metric_name']: float(record['metric_value']) for record in records}
        evidence = records[0]['details'] if records else {}
        windows.append({'window': window, 'candidate_count': len(records),
                        'status': 'candidate' if records else 'insufficient_evidence',
                        'actual_start_date': evidence.get('window_start_date'),
                        'actual_end_date': evidence.get('window_end_date'),
                        'methodology_version': evidence.get('methodology_version'),
                        'calendar_status': evidence.get('calendar_status'),
                        'annualized_return': values.get('annualized_return'),
                        'max_drawdown': values.get('max_drawdown'),
                        'annualized_volatility': values.get('annualized_volatility')})
    metrics, _, proposed_audit = scoring._snapshot_evidence(candidates)
    return {'fund_code': code, 'fund_name': fund['name'], 'as_of_date': as_of,
            'stored_panel': old_audit, 'candidate_windows': windows,
            'candidate_missing_score_metrics': scoring._missing_metric_names(metrics),
            'candidate_rules': proposed_audit['rules'],
            'benchmark_policy': '库存benchmark_nav缺代码/来源，预览不生成相对基准指标。',
            'boundary': '候选仅用于迁移核验，不是已保存结果或完整评分；沿用库存精度及工厂2%无风险利率假设。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codes', nargs='+', required=True, help='显式基金代码，最多20只')
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    codes = list(dict.fromkeys(code.strip().upper() for code in args.codes if code.strip()))
    if not codes or len(codes) > 20 or args.as_of > date.today():
        parser.error('请指定1—20只基金，评价日不能在未来')

    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text
    from database import load_shared_database_environment, get_database_url

    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / '.env.local', override=False)
    load_shared_database_environment()
    engine = create_engine(get_database_url(), execution_options={'postgresql_readonly': True})
    try:
        with engine.connect() as conn:
            if conn.execute(text('SHOW transaction_read_only')).scalar() != 'on':
                raise RuntimeError('数据库连接未处于强制只读模式')
            columns = [dict(row) for row in conn.execute(text("""
                SELECT column_name, data_type, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name='fund_nav'
                ORDER BY ordinal_position
            """)).mappings()]
            present = {row['column_name'] for row in columns}
            provenance_missing = sorted({'reported_accum_nav', 'announcement_date', 'adj_nav_source',
                                         'benchmark_code', 'benchmark_source'} - present)
            results = []
            for code in codes:
                fund = conn.execute(text('SELECT wind_code,name,type FROM funds WHERE wind_code=:code'), {'code': code}).mappings().first()
                if not fund:
                    raise ValueError(f'基金不存在：{code}')
                nav_rows = [dict(row) for row in conn.execute(text("""
                    SELECT trade_date AS date, adj_nav, accum_nav, unit_nav, benchmark_nav
                    FROM fund_nav WHERE wind_code=:code AND trade_date BETWEEN :start AND :end
                    ORDER BY trade_date
                """), {'code': code, 'start': args.as_of-timedelta(days=1840), 'end': args.as_of}).mappings()]
                for row in nav_rows:
                    row['risk_calendar'] = fund_risk_calendar(fund)
                # 排除评价日之后才生成的面板；不借未来的latest覆盖历史截止日。
                panel = [dict(row) for row in conn.execute(text("""
                    SELECT DISTINCT ON (metric_name, metric_window, benchmark_code, peer_group_key) *
                    FROM metric_snapshots WHERE target_type='fund' AND target_id=:code AND as_of_date<=:end
                    ORDER BY metric_name, metric_window, benchmark_code, peer_group_key, as_of_date DESC, updated_at DESC, id DESC
                """), {'code': code, 'end': args.as_of}).mappings()]
                preview = preview_fund(code, fund, nav_rows, panel, args.as_of)
                duplicate_keys = [dict(row) for row in conn.execute(text("""
                    SELECT as_of_date, metric_name, metric_window, benchmark_code, peer_group_key, count(*) AS row_count
                    FROM metric_snapshots WHERE target_type='fund' AND target_id=:code AND as_of_date<=:end
                    GROUP BY as_of_date, metric_name, metric_window, benchmark_code, peer_group_key
                    HAVING count(*)>1 ORDER BY as_of_date DESC, metric_name LIMIT 50
                """), {'code': code, 'end': args.as_of}).mappings()]
                preview['snapshot_key_issues'] = {'duplicate_groups_in_sample': len(duplicate_keys),
                                                  'sample_limit': 50, 'examples': duplicate_keys[:5],
                                                  'policy': '只提示，不删除旧重复行；Desk修订保留在details._revision_history，独立上游写入仍需协调。'}
                results.append(preview)
            print(json.dumps({'read_only': True, 'nav_columns': columns,
                              'missing_provenance_columns': provenance_missing, 'funds': results},
                             ensure_ascii=False, default=str, allow_nan=False))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
