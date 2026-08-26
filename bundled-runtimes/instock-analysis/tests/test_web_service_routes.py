import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tornado.testing import AsyncHTTPTestCase

import instock.web.integration_api as integration_api
from instock.web.web_service import Application, application_handlers


ROOT = Path(__file__).resolve().parents[1]


def route_patterns(attached_runtime):
    return {route[0] for route in application_handlers(attached_runtime)}


def test_attached_route_interface_excludes_upstream_and_legacy_aliases():
    patterns = route_patterns(True)

    assert patterns == {
        r"/",
        r"/mods/czsc/?",
        r"/mods/rotation/?",
        r"/mods/industry-chain/?",
        r"/mods/stock-candidates/?",
        r"/mods/stock-research/?",
        r"/mods/strategy-validation/?",
        r"/mods/event-flow/?",
        r"/mods/research-book/?",
        r"/mods/market-workbench/?",
        r"/mods/market-map/?",
        r"/mods/technical-signals/?",
        r"/api/v1/czsc/analyses",
        r"/api/v1/czsc/scans",
        r"/api/v1/czsc/scans/([^/]+)",
        r"/api/v1/rotations/snapshots",
        r"/api/v1/rotations/experiments",
        r"/api/v1/rotations/supply-chain-research",
        r"/api/v1/industry-chain/research",
        r"/api/v1/stock-candidates/snapshots",
        r"/api/v1/stock-research/dossiers",
        r"/api/v1/strategy-validations",
        r"/api/v1/event-flows",
        r"/api/v1/research-books",
        r"/api/v1/market-workbench/snapshots",
        r"/api/v1/market-maps/snapshots",
        r"/api/v1/technical-signals/snapshots",
        r"/api/v1/analysis-history",
        r"/api/v1/analysis-history/([^/]+)",
        r"/api/v1/analysis-snapshots/([^/]+)",
        r"/api/v1/health",
        r"/api/v1/capabilities",
        r"/\.well-known/newma-desk-suite\.json",
        r"/\.well-known/newma-dock-suite\.json",
        r"/\.well-known/vibedesk-suite\.json",
    }


def test_diagnostic_route_interface_preserves_upstream_compatibility():
    legacy_modules = (
        None,
        None,
        SimpleNamespace(GetStockDataHandler=object, GetStockHtmlHandler=object),
        SimpleNamespace(GetDataIndicatorsHandler=object, SaveCollectHandler=object),
        None,
    )
    with patch(
        "instock.web.web_service._legacy_web_modules",
        return_value=legacy_modules,
    ):
        patterns = route_patterns(False)

    assert {
        r"/instock/",
        r"/instock/api_data",
        r"/instock/data",
        r"/instock/data/indicators",
        r"/instock/control/attention",
        r"/czsc_chart",
        r"/api/czsc/analysis",
        r"/api/czsc_chart",
        r"/rotation",
        r"/api/rotation/snapshot",
    }.issubset(patterns)
    assert route_patterns(True).issubset(patterns)


def test_skip_db_environment_selects_attached_runtime():
    with patch.dict(os.environ, {"INSTOCK_SKIP_DB": "1"}):
        application = Application()

    assert application.attached_runtime is True
    assert application.db is None


def test_attached_main_warms_analysis_readiness_before_listening():
    source = (ROOT / "instock" / "web" / "web_service.py").read_text("utf-8")

    warm_position = source.index("warm_analysis_runtime_readiness()")
    listen_position = source.index("http_server.listen(")
    assert warm_position < listen_position


def test_attached_runtime_import_excludes_legacy_database_stack():
    source = """
import json
import sys
import instock.web.web_service

blocked = (
    'pymysql',
    'sqlalchemy',
    'talib',
    'czsc',
    'instock.web.base',
    'instock.web.dataTableHandler',
    'instock.web.dataIndicatorsHandler',
)
print(json.dumps([name for name in blocked if name in sys.modules]))
"""
    environment = os.environ.copy()
    environment["INSTOCK_SKIP_DB"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []


class AttachedApplicationRouteTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application(attached_runtime=True)

    def test_root_redirects_to_canonical_market_workbench(self):
        response = self.fetch("/", follow_redirects=False)

        assert response.code == 302
        assert response.headers["Location"] == "/mods/market-workbench"

    def test_upstream_and_unversioned_routes_are_not_exposed(self):
        for path in (
            "/instock/",
            "/instock/api_data",
            "/instock/data",
            "/instock/data/indicators",
            "/instock/control/attention",
            "/czsc_chart",
            "/rotation",
            "/api/czsc/analysis",
            "/api/czsc_chart",
            "/api/rotation/snapshot",
        ):
            response = self.fetch(path, raise_error=False)
            assert response.code == 404, path

    def test_mod_pages_and_discovery_remain_available(self):
        for path in ("/mods/czsc", "/mods/rotation", "/mods/industry-chain", "/mods/stock-candidates", "/mods/stock-research", "/mods/strategy-validation", "/mods/event-flow", "/mods/research-book", "/mods/market-workbench", "/mods/market-map", "/mods/technical-signals"):
            response = self.fetch(path)
            assert response.code == 200
            assert b'id="sidebar"' not in response.body
            assert b'href="/czsc_chart' not in response.body
            assert b'href="/rotation' not in response.body

        rotation = self.fetch("/mods/rotation")
        assert b'href="/mods/czsc"' in rotation.body
        assert b'id="rotation-candidate-link"' in rotation.body

        candidates = self.fetch("/mods/stock-candidates")
        assert "筛选条件".encode("utf-8") in candidates.body
        assert b"analysis.stock-candidates" in candidates.body
        assert b'id="candidate-profile"' in candidates.body
        assert b'id="candidate-industry"' in candidates.body
        assert b'id="candidate-event-flow"' in candidates.body
        assert b"/mods/stock-research" in candidates.body

        research = self.fetch("/mods/stock-research")
        assert b"Company Research Dossier" in research.body
        assert b"analysis.stock-research" in research.body
        assert b'id="dossier-event-flow"' in research.body
        assert b'id="dossier-industry-chain-snapshot"' in research.body
        assert b'id="dossier-events"' in research.body
        assert b'id="dossier-industry-chain"' in research.body
        assert b'id="dossier-handoff"' in research.body

        validation = self.fetch("/mods/strategy-validation")
        assert b"Strategy Validation" in validation.body
        assert b"analysis.strategy-validation" in validation.body

        event_flow = self.fetch("/mods/event-flow")
        assert b"Event & Flow Radar" in event_flow.body
        assert b"analysis.event-flow" in event_flow.body
        assert b'id="event-research-link"' in event_flow.body

        research_book = self.fetch("/mods/research-book")
        assert "研究组合".encode("utf-8") in research_book.body
        assert b"analysis.research-book" in research_book.body

        market_workbench = self.fetch("/mods/market-workbench")
        assert b"MARKET OVERVIEW" in market_workbench.body
        assert b"analysis.market-workbench" in market_workbench.body
        assert b'id="market-map-chart"' not in market_workbench.body
        assert "大盘云图".encode("utf-8") in market_workbench.body
        assert b'href="/mods/market-map"' in market_workbench.body
        assert b"/mods/stock-research" in market_workbench.body
        assert b'id="stock-suite-history-button"' in market_workbench.body
        assert b'id="stock-suite-history-fab"' in market_workbench.body
        assert b'id="stock-suite-history"' in market_workbench.body

        market_map = self.fetch("/mods/market-map")
        assert b"MARKET MAP / A-SHARE" in market_map.body
        assert b"analysis.market-map" in market_map.body
        assert b'id="market-map-chart"' in market_map.body
        assert "多榜 Top500".encode("utf-8") in market_map.body
        assert "不是市值 Top500".encode("utf-8") in market_map.body
        assert b"/mods/stock-research" in market_map.body
        assert b"security.selected" in market_map.body

        technical_signals = self.fetch("/mods/technical-signals")
        assert "选股中心".encode("utf-8") in technical_signals.body
        assert "趋势突破".encode("utf-8") in technical_signals.body
        assert "低波动成长".encode("utf-8") in technical_signals.body
        assert "基本面成长".encode("utf-8") in technical_signals.body
        assert "低估值流动性".encode("utf-8") in technical_signals.body
        assert "清空条件".encode("utf-8") in technical_signals.body
        assert b"analysis.technical-signals" in technical_signals.body
        assert b"/mods/stock-research" in technical_signals.body

        with patch.object(
            integration_api,
            "_native_analysis_runtime_readiness",
            return_value={
                "status": "ready",
                "reason": None,
                "exit_code": 0,
                "isolation": "subprocess",
            },
        ):
            health_response = self.fetch("/api/v1/health")
        health = json.loads(health_response.body)["data"]
        assert health["runtime"]["mode"] == "newma-desk-attached"

        suite_response = self.fetch("/.well-known/newma-desk-suite.json")
        suite = json.loads(suite_response.body)
        assert suite["id"] == "instock-suite"
