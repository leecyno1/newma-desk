#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import logging
import os.path
import sys

import tornado.escape
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web

# 在项目运行时，临时将项目路径添加到环境变量
cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)
log_path = os.path.join(cpath_current, 'log')
if not os.path.exists(log_path):
    os.makedirs(log_path)
logging.basicConfig(format='%(asctime)s %(message)s', filename=os.path.join(log_path, 'stock_web.log'))
logging.getLogger().setLevel(logging.ERROR)
import instock.lib.version as version
from instock.web.analysis_snapshot_handler import AnalysisSnapshotResourceHandler
from instock.web.analysis_history_handler import (
    AnalysisHistoryCollectionHandler,
    AnalysisHistoryResourceHandler,
)
from instock.web.czsc_chart_handler import CZSCAnalysisHandler, CZSCChartHandler
from instock.web.czsc_scan_handler import CZSCScanCollectionHandler, CZSCScanResourceHandler
from instock.web.api_contract import apply_security_headers, embed_origins
from instock.web.integration_api import (
    IntegrationCapabilitiesHandler,
    IntegrationHealthHandler,
    NewmaDeskSuiteHandler,
    warm_analysis_runtime_readiness,
)
from instock.web.rotation_handler import RotationExperimentHandler, RotationSnapshotHandler
from instock.web.industry_chain_handler import IndustryChainResearchHandler
from instock.web.supply_chain_handler import SupplyChainResearchHandler
from instock.web.stock_candidates_handler import StockCandidateSnapshotHandler
from instock.web.stock_research_handler import StockResearchDossierHandler
from instock.web.strategy_validation_handler import StrategyValidationHandler
from instock.web.event_flow_handler import EventFlowHandler
from instock.web.research_book_handler import ResearchBookHandler
from instock.web.market_map_handler import MarketMapSnapshotHandler
from instock.web.market_workbench_handler import MarketWorkbenchSnapshotHandler
from instock.web.technical_signal_handler import TechnicalSignalSnapshotHandler

__author__ = 'myh '
__date__ = '2023/3/10 '


class Application(tornado.web.Application):
    def __init__(self, attached_runtime=None):
        if attached_runtime is None:
            attached_runtime = is_attached_runtime()
        self.attached_runtime = bool(attached_runtime)
        handlers = application_handlers(self.attached_runtime)
        settings = dict(  # 配置
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=False,  # True,
            # cookie加密
            cookie_secret=os.environ.get(
                "INSTOCK_COOKIE_SECRET", "027bb1b670eddf0392cdda8709268a17b58b7"
            ),
            debug=os.environ.get("INSTOCK_WEB_DEBUG", "0") == "1",
        )
        super(Application, self).__init__(handlers, **settings)
        if self.attached_runtime:
            self.db = None
        else:
            # The upstream database stack belongs to maintainer diagnostics and
            # must not enter the Newma-Desk attached process import graph.
            torndb, mdb, _, _, _ = _legacy_web_modules()
            self.db = torndb.Connection(**mdb.MYSQL_CONN_TORNDB)


def is_attached_runtime():
    """Return whether Newma-Desk owns this process and its HTTP surface."""

    return os.environ.get("INSTOCK_SKIP_DB", "0").strip() == "1"


def _legacy_web_modules():
    """Load the upstream database-backed web modules only for diagnostics."""

    import instock.lib.database as mdb
    import instock.lib.torndb as torndb
    import instock.web.base as web_base
    import instock.web.dataIndicatorsHandler as data_indicators_handler
    import instock.web.dataTableHandler as data_table_handler

    return torndb, mdb, data_table_handler, data_indicators_handler, web_base


def application_handlers(attached_runtime):
    """Build the HTTP interface for either Desk attachment or maintainer diagnosis.

    The attached interface deliberately excludes the upstream InStock site and
    all unversioned aliases. Those routes remain available only when maintainers
    run the upstream-compatible diagnostic mode with its database dependency.
    """

    attached_handlers = [
        (r"/mods/czsc/?", CZSCChartPageHandler),
        (r"/mods/rotation/?", RotationPageHandler),
        (r"/mods/industry-chain/?", IndustryChainPageHandler),
        (r"/mods/stock-candidates/?", StockCandidatesPageHandler),
        (r"/mods/stock-research/?", StockResearchPageHandler),
        (r"/mods/strategy-validation/?", StrategyValidationPageHandler),
        (r"/mods/event-flow/?", EventFlowPageHandler),
        (r"/mods/research-book/?", ResearchBookPageHandler),
        (r"/mods/market-workbench/?", MarketWorkbenchPageHandler),
        (r"/mods/market-map/?", MarketMapPageHandler),
        (r"/mods/technical-signals/?", TechnicalSignalsPageHandler),
        (r"/api/v1/czsc/analyses", CZSCAnalysisHandler),
        (r"/api/v1/czsc/scans", CZSCScanCollectionHandler),
        (r"/api/v1/czsc/scans/([^/]+)", CZSCScanResourceHandler),
        (r"/api/v1/rotations/snapshots", RotationSnapshotHandler),
        (r"/api/v1/rotations/experiments", RotationExperimentHandler),
        (r"/api/v1/rotations/supply-chain-research", SupplyChainResearchHandler),
        (r"/api/v1/industry-chain/research", IndustryChainResearchHandler),
        (r"/api/v1/stock-candidates/snapshots", StockCandidateSnapshotHandler),
        (r"/api/v1/stock-research/dossiers", StockResearchDossierHandler),
        (r"/api/v1/strategy-validations", StrategyValidationHandler),
        (r"/api/v1/event-flows", EventFlowHandler),
        (r"/api/v1/research-books", ResearchBookHandler),
        (r"/api/v1/market-workbench/snapshots", MarketWorkbenchSnapshotHandler),
        (r"/api/v1/market-maps/snapshots", MarketMapSnapshotHandler),
        (r"/api/v1/technical-signals/snapshots", TechnicalSignalSnapshotHandler),
        (r"/api/v1/analysis-history", AnalysisHistoryCollectionHandler),
        (r"/api/v1/analysis-history/([^/]+)", AnalysisHistoryResourceHandler),
        (r"/api/v1/analysis-snapshots/([^/]+)", AnalysisSnapshotResourceHandler),
        (r"/api/v1/health", IntegrationHealthHandler),
        (r"/api/v1/capabilities", IntegrationCapabilitiesHandler),
        (r"/\.well-known/newma-desk-suite\.json", NewmaDeskSuiteHandler),
        (r"/\.well-known/newma-dock-suite\.json", NewmaDeskSuiteHandler),
        (r"/\.well-known/vibedesk-suite\.json", NewmaDeskSuiteHandler),
    ]
    if attached_runtime:
        return [
            (r"/", tornado.web.RedirectHandler, {
                "url": "/mods/market-workbench",
                "permanent": False,
            }),
            *attached_handlers,
        ]

    _, _, data_table_handler, data_indicators_handler, _ = _legacy_web_modules()
    return [
        # 上游站点与非版本化入口仅用于维护者诊断和源码兼容。
        (r"/", HomeHandler),
        (r"/instock/", HomeHandler),
        (r"/instock/api_data", data_table_handler.GetStockDataHandler),
        (r"/instock/data", data_table_handler.GetStockHtmlHandler),
        (r"/instock/data/indicators", data_indicators_handler.GetDataIndicatorsHandler),
        (r"/instock/control/attention", data_indicators_handler.SaveCollectHandler),
        (r"/czsc_chart", CZSCChartPageHandler),
        (r"/api/czsc/analysis", CZSCAnalysisHandler),
        (r"/api/czsc_chart", CZSCChartHandler),
        (r"/rotation", RotationPageHandler),
        (r"/api/rotation/snapshot", RotationSnapshotHandler),
        *attached_handlers,
    ]


# 首页handler。
class HomeHandler(tornado.web.RequestHandler):
    def get(self):
        _, _, _, _, web_base = _legacy_web_modules()
        self.render("index.html",
                    stockVersion=version.__version__,
                    leftMenu=web_base.GetLeftMenu(self.request.uri))


class CZSCChartPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("czsc_chart.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-czsc",
                    vibedeskParentOrigins=",".join(embed_origins()))


class RotationPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("rotation.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-rotation",
                    vibedeskParentOrigins=",".join(embed_origins()))


class IndustryChainPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("industry_chain.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-industry-chain",
                    vibedeskParentOrigins=",".join(embed_origins()))


class StockCandidatesPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("stock_candidates.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-stock-candidates",
                    vibedeskParentOrigins=",".join(embed_origins()))


class StockResearchPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("stock_research.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-stock-research",
                    vibedeskParentOrigins=",".join(embed_origins()))


class StrategyValidationPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("strategy_validation.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-strategy-validation",
                    vibedeskParentOrigins=",".join(embed_origins()))


class EventFlowPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("event_flow.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-event-flow",
                    vibedeskParentOrigins=",".join(embed_origins()))


class ResearchBookPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("research_book.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-research-book",
                    vibedeskParentOrigins=",".join(embed_origins()))


class MarketWorkbenchPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("market_workbench.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-market-workbench",
                    vibedeskParentOrigins=",".join(embed_origins()))


class MarketMapPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("market_map.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-market-map",
                    vibedeskParentOrigins=",".join(embed_origins()))


class TechnicalSignalsPageHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        apply_security_headers(self)

    def get(self):
        self.render("technical_signals.html",
                    stockVersion=version.__version__,
                    vibedeskModId="instock-technical-signals",
                    vibedeskParentOrigins=",".join(embed_origins()))


def main():
    # tornado.options.parse_command_line()
    tornado.options.options.logging = None

    attached_runtime = is_attached_runtime()
    if attached_runtime:
        # Complete the isolated native probe before exposing the health socket.
        # A failed probe remains cached so health can return an immediate 503.
        warm_analysis_runtime_readiness()
    http_server = tornado.httpserver.HTTPServer(Application(attached_runtime))
    host = os.environ.get("INSTOCK_WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("INSTOCK_WEB_PORT", "9988"))
    if not 1 <= port <= 65535:
        raise ValueError("INSTOCK_WEB_PORT 必须位于 1 到 65535 之间")
    http_server.listen(port, address=host)

    print(f"服务已启动，web地址 : http://{host}:{port}/")
    logging.error(f"服务已启动，web地址 : http://{host}:{port}/")

    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
