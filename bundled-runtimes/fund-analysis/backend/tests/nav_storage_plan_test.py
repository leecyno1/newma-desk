"""迁移计划纯计算验收，不连接数据库。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repositories.nav_repo import NAV_PROVENANCE_COLUMNS
from scripts.preview_nav_storage_migration import build_plan


class NavStoragePlanTests(unittest.TestCase):
    def test_missing_fields_and_low_precision(self):
        plan = build_plan({'nav': 'numeric(10,4)', 'unit_nav': 'numeric(10,4)', 'adj_nav': 'numeric(12,4)', 'benchmark_nav': 'numeric(10,4)'})
        self.assertEqual(len(plan['provenance_column_sql']), 5)
        self.assertEqual(len(plan['precision_changes_requiring_review']), 4)
        self.assertEqual(plan['storage_evidence']['status'], 'migration_required')
        self.assertEqual(plan['shared_writer_gate']['status'], 'not_verified')

    def test_ready_schema_is_not_asked_to_migrate_again(self):
        plan = build_plan({**NAV_PROVENANCE_COLUMNS, 'nav': 'numeric(20,10)'})
        self.assertEqual(plan['provenance_column_sql'], [])
        self.assertEqual(plan['precision_changes_requiring_review'], [])

    def test_never_downgrade_precision_or_integer_capacity(self):
        plan = build_plan({'nav': 'numeric(30,12)', 'unit_nav': 'numeric(25,4)', 'adj_nav': 'numeric'})
        changes = plan['precision_changes_requiring_review']
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['proposed_type'], 'numeric(31,10)')

    def test_unknown_table_does_not_generate_ddl(self):
        with self.assertRaises(ValueError):
            build_plan({})


if __name__ == '__main__':
    unittest.main()
