"""Public synthetic board data; signed contexts are never serialized."""
from concurrent.futures import ThreadPoolExecutor
import json

from instock.core.analysis_scope import analysis_scope, analysis_session, desk_scope
from instock.core.workbench import MarketWorkbenchEngine
from test_market_workbench import FixtureProvider


def test_workbench_all_dependencies_inherit_the_current_request_in_parallel():
    def run(owner):
        scope = analysis_scope.set(desk_scope(owner, 'workspace'))
        session = analysis_session.set(('synthetic-' + owner, 'instance-' + owner))
        seen = []
        class Provider(FixtureProvider):
            def check(self):
                seen.append((analysis_scope.get(), analysis_session.get()))
            def get_market_overview(self):
                self.check(); return super().get_market_overview()
            def get_market_emotion(self):
                self.check(); return super().get_market_emotion()
            def get_market_turnover_top(self, **kwargs):
                self.check(); return super().get_market_turnover_top(**kwargs)
            def get_stock_scan(self, **kwargs):
                self.check(); return super().get_stock_scan(**kwargs)
        try:
            result = MarketWorkbenchEngine(Provider()).analyze(scan_limit=50)
            assert len(seen) == 7
            assert all(value == (desk_scope(owner, 'workspace'), ('synthetic-' + owner, 'instance-' + owner)) for value in seen)
            assert 'synthetic-' not in json.dumps(result)
            assert result['leaderboards']['gainers']
        finally:
            analysis_session.reset(session); analysis_scope.reset(scope)
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(run, ('alice', 'bob')))
    assert analysis_session.get() is None
