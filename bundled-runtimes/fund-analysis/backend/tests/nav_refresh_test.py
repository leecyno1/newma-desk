"""NAV refresh failures, period endpoints and cache invalidation; no real writes."""
import sys
import asyncio
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routes import data_sync, funds, fund_browser
from services import cache_service


class NavRefreshTests(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.get_nav_series.return_value = [{'date': '2026-09-24', 'nav': 1}]
        self.repo.upsert_nav_series.return_value = True
        self.repo.get_storage_evidence.return_value = {'status': 'migration_required', 'missing_provenance_columns': ['announcement_date']}
        self.source = Mock()
        self.source.get_fund_nav.return_value = [
            {'date': '2026-09-29', 'unit_nav': 1, 'adj_nav': 1.05},
            {'date': '2026-09-30', 'unit_nav': 1.01, 'adj_nav': None},
        ]
        for target, value in (
            ('get_nav_repo', self.repo),
            ('get_fund_repo', Mock(get_fund=Mock(return_value={'name': 'isolated'}))),
            ('get_strict_tushare_service', self.source),
        ):
            p = patch.object(data_sync, target, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        self.invalidate = patch.object(data_sync, 'invalidate_fund_cache').start()
        self.addCleanup(patch.stopall)

    def refresh(self):
        return data_sync.refresh_fund_nav('TEST.OF', data_sync.RefreshNavRequest())

    def test_refresh_preserves_gaps_and_discloses_no_recalculation(self):
        result = self.refresh()
        self.assertEqual(result['latest_nav_date'], '2026-09-30')
        self.assertEqual(result['previous_latest_date'], '2026-09-24')
        self.assertEqual(result['adjusted_observations'], 1)
        self.assertFalse(result['metrics_recalculated'])
        self.assertEqual(result['storage_evidence']['status'], 'migration_required')
        self.repo.upsert_nav_series.assert_called_once_with('TEST.OF', self.source.get_fund_nav.return_value, update_latest=True)
        self.invalidate.assert_called_once_with('TEST.OF')

    def test_empty_source_keeps_inventory_and_cache(self):
        self.source.get_fund_nav.return_value = []
        with self.assertRaises(HTTPException) as failure:
            self.refresh()
        self.assertEqual(failure.exception.status_code, 422)
        self.repo.upsert_nav_series.assert_not_called()
        self.invalidate.assert_not_called()

    def test_write_failure_never_reports_success(self):
        self.repo.upsert_nav_series.return_value = False
        with self.assertRaises(HTTPException) as failure:
            self.refresh()
        self.assertEqual(failure.exception.status_code, 500)
        self.invalidate.assert_not_called()

    def test_source_failure_does_not_write(self):
        self.source.get_fund_nav.side_effect = RuntimeError('isolated failure')
        with self.assertLogs('routes.data_sync', level='ERROR'):
            with self.assertRaises(HTTPException) as failure:
                self.refresh()
        self.assertEqual(failure.exception.status_code, 502)
        self.repo.upsert_nav_series.assert_not_called()

    def test_ranking_write_failure_stops_metric_generation(self):
        from scripts import sync_fund_ranking_metrics as ranking
        rolling = Mock()
        self.source.get_fund_nav.return_value = [{'date': f'2026-09-{i:02}', 'nav': 1} for i in range(1, 22)]
        self.repo.upsert_nav_series.return_value = False
        with patch.object(ranking, 'get_fund_repo', return_value=Mock(get_fund=Mock(return_value={}))), \
             patch.object(ranking, 'get_nav_repo', return_value=self.repo), \
             patch.object(ranking, 'get_metric_snapshot_repo'), \
             patch.object(ranking, 'get_fund_classification_repo', return_value=Mock(get_classification_context=Mock(return_value={'status':'resolved'}))), \
             patch.object(ranking, 'FundNavDataEnrichmentService', return_value=Mock(enrich=Mock(return_value={'nav_series':self.source.get_fund_nav.return_value, 'nav_data_status':'valid'}))):
            result = ranking.sync_one_fund(self.source, rolling, 'TEST.OF', date(2026,9,1), date(2026,9,30))
        self.assertEqual(result['status'], 'failed')
        rolling.calculate_and_save_for_fund.assert_not_called()


class NavReadingTests(unittest.TestCase):
    def test_monthly_and_weekly_use_actual_last_day_and_keep_evidence(self):
        rows = [
            {'date':date(2026,8,28),'nav':1,'adj_nav':2,'benchmark_nav':100},
            {'date':date(2026,8,31),'nav':1.1,'adj_nav':2.1,'benchmark_nav':101},
            {'date':date(2026,9,1),'nav':1.2,'adj_nav':2.2,'benchmark_nav':102},
            {'date':date(2026,9,4),'nav':1.3,'adj_nav':2.3,'benchmark_nav':103},
        ]
        with patch('repositories.get_nav_repo', return_value=Mock(get_nav_series=Mock(return_value=rows))), \
             patch.object(cache_service, 'get_cache', return_value=cache_service.NullCache()):
            monthly = funds.get_fund_nav('TEST.OF','2026-08-01','2026-09-30','monthly')
            weekly = funds.get_fund_nav('TEST.OF','2026-08-01','2026-09-30','weekly')
        self.assertEqual([str(r['date']) for r in monthly['data']], ['2026-08-31','2026-09-04'])
        self.assertEqual(monthly['data'][0]['adj_nav'],2.1)
        self.assertEqual(monthly['data'][1]['benchmark_nav'],103)
        self.assertEqual([str(r['date']) for r in weekly['data']], ['2026-08-28','2026-09-04'])

    def test_sync_invalidates_nav_versions_for_only_selected_fund(self):
        cache = cache_service.MemoryCache()
        for key in ('fund:nav:v2:TEST.OF:a', 'fund:nav:v3:TEST.OF:a', 'fund:nav:v4:TEST.OF:a', 'fund:nav:v4:OTHER.OF:a'):
            cache.set(key, {'value':1})
        with patch.object(cache_service, 'get_cache', return_value=cache):
            cache_service.invalidate_fund_cache('TEST.OF')
        self.assertIsNone(cache.get('fund:nav:v2:TEST.OF:a'))
        self.assertIsNone(cache.get('fund:nav:v3:TEST.OF:a'))
        self.assertIsNone(cache.get('fund:nav:v4:TEST.OF:a'))
        self.assertIsNotNone(cache.get('fund:nav:v4:OTHER.OF:a'))

    def test_invalidation_clears_selected_detail_and_chart_not_other_fund(self):
        cache = cache_service.MemoryCache()
        for key in ('fund:detail:v10:TEST.OF', 'fund:detail:v10:OTHER.OF',
                    'fund:nav-chart:TEST.OF:3y', 'fund:nav-chart:OTHER.OF:3y', 'fund:list:query'):
            cache.set(key, {'value': 1})
        with patch.object(cache_service, 'get_cache', return_value=cache):
            cache_service.invalidate_fund_cache('TEST.OF')
        self.assertIsNone(cache.get('fund:detail:v10:TEST.OF'))
        self.assertIsNone(cache.get('fund:nav-chart:TEST.OF:3y'))
        self.assertIsNone(cache.get('fund:list:query'))
        self.assertIsNotNone(cache.get('fund:detail:v10:OTHER.OF'))
        self.assertIsNotNone(cache.get('fund:nav-chart:OTHER.OF:3y'))


class NavConcurrencyTest(unittest.IsolatedAsyncioTestCase):
    async def test_slow_research_snapshot_does_not_freeze_health_requests(self):
        app = FastAPI()
        app.include_router(funds.router)

        @app.get('/probe')
        async def probe():
            return {'ready': True}

        entered, release = threading.Event(), threading.Event()

        def slow_snapshot(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('Research snapshot blocked event loop')
            return {'fund': {'wind_code': 'TEST.OF'}}

        with patch('services.fund_research_snapshot_service.FundResearchSnapshotService.build', side_effect=slow_snapshot):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated') as client:
                task = asyncio.create_task(client.get('/api/funds/TEST.OF/research-snapshot'))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    response = await asyncio.wait_for(client.get('/probe'), .5)
                    self.assertTrue(response.json()['ready'])
                    self.assertFalse(task.done())
                finally:
                    release.set()
                    result = await task
                self.assertEqual(result.status_code, 200)

    async def test_slow_nav_read_does_not_freeze_health_requests(self):
        app = FastAPI()
        app.include_router(funds.router)

        @app.get('/probe')
        async def probe():
            return {'ready':True}

        entered, release = threading.Event(), threading.Event()

        def slow_query(*args):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('NAV route blocked event loop')
            return [{'date':'2026-09-30','nav':1}]

        with patch('repositories.get_nav_repo', return_value=Mock(get_nav_series=slow_query)), \
             patch.object(cache_service, 'get_cache', return_value=cache_service.NullCache()):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated') as client:
                task = asyncio.create_task(client.get('/api/funds/TEST.OF/nav'))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait,1))
                    response = await asyncio.wait_for(client.get('/probe'),.5)
                    self.assertTrue(response.json()['ready'])
                    self.assertFalse(task.done())
                finally:
                    release.set()
                    result = await task
                self.assertEqual(result.status_code,200)

    async def test_slow_fund_search_does_not_freeze_health_requests(self):
        app = FastAPI()
        app.include_router(fund_browser.router)

        @app.get('/probe')
        async def probe():
            return {'ready':True}

        entered, release = threading.Event(), threading.Event()

        def slow_search(**kwargs):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('Search blocked event loop')
            return {'total':0}

        with patch('services.fund_browser_service.FundBrowserService.browse', side_effect=slow_search):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated') as client:
                task = asyncio.create_task(client.get('/api/fund-browser?keyword=TEST'))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait,1))
                    response = await asyncio.wait_for(client.get('/probe'),.5)
                    self.assertTrue(response.json()['ready'])
                    self.assertFalse(task.done())
                finally:
                    release.set()
                    result = await task
                self.assertEqual(result.status_code,200)


if __name__ == '__main__':
    unittest.main()
