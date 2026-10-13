"""只读预览净值来源字段及精度迁移方案；无apply入口、不执行业务DDL。"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repositories.nav_repo import NAV_PROVENANCE_COLUMNS, nav_storage_columns, nav_storage_evidence


def build_plan(columns):
    if not columns:
        raise ValueError('fund_nav表不存在，不能为未知数据库生成迁移方案')
    precision_changes = []
    for name in ('nav', 'unit_nav', 'adj_nav', 'benchmark_nav'):
        current = columns.get(name, '')
        match = re.fullmatch(r'numeric\((\d+),(\d+)\)', current)
        if not match or int(match[2]) >= 10:
            continue
        proposed = f'numeric({max(20, int(match[1])-int(match[2])+10)},10)'
        precision_changes.append({'column': name, 'current_type': current, 'proposed_type': proposed,
                                  'sql': f'ALTER TABLE public.fund_nav ALTER COLUMN {name} TYPE {proposed};'})
    return {
        'storage_evidence': nav_storage_evidence(columns),
        'provenance_column_sql': [f'ALTER TABLE public.fund_nav ADD COLUMN {name} {kind};'
                                  for name, kind in NAV_PROVENANCE_COLUMNS.items() if name not in columns],
        'precision_changes_requiring_review': precision_changes,
        'shared_writer_gate': {
            'status': 'not_verified',
            'required_contract': ['所有共享writer须先升级或暂停，不能只更新数值却保留旧来源。',
                                  '净值整批失败须回滚，逐点来源和数值一起保存。',
                                  '指标修订和失效清理须保留历史，不自动运行DDL。'],
        },
        'deployment_order': [
            '确认共享库独立writer、备份、维护窗口与锁/表重写成本；本脚本不执行变更。',
            '先部署兼容新旧schema的写入/读取代码到所有writer，或暂停未升级writer。',
            '再增加可空来源列；旧行保留NULL，不从基金级标签推断逐点来源。',
            '确认所有writer均保持值与来源同步；未提供的来源保留未知。',
            '精度变更另行评审，不能靠扩列恢复旧舍入值；授权后定向重取官方净值。',
            '按显式基金/日期范围核对来源、公告日及基准，再小批重算，保留旧指标。',
        ],
        'boundary': '只读计划，不改accum_nav旧兼容语义，不回填、不重算；schema就绪不等于证据就绪。',
    }


def main():
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text
    from database import get_database_url, load_shared_database_environment
    load_dotenv(Path(__file__).resolve().parents[2] / '.env.local', override=False)
    load_shared_database_environment()
    engine = create_engine(get_database_url(), execution_options={'postgresql_readonly': True})
    try:
        with engine.connect() as conn:
            if conn.execute(text('SHOW transaction_read_only')).scalar() != 'on':
                raise RuntimeError('数据库连接未强制只读')
            print(json.dumps({'read_only': True, **build_plan(nav_storage_columns(conn))}, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
