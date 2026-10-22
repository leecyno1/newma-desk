import json
from unittest.mock import patch
from types import SimpleNamespace

import pytest
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application
from instock.core.market_data_provider import NewmaDeskMarketDataProvider, MarketDataError
from instock.web.stock_research_handler import StockStatementEvidenceHandler, StockStatementAnnouncementsHandler


def test_statement_provider_uses_registered_capability_and_rejects_wrong_identity(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    calls = []
    result = {"symbol": "300502", "announcementId": "AN202608240006746577", "contentOrigin": "pdf-text", "facts": []}
    def request(capability, path, parameters):
        calls.append((capability, path, parameters))
        return result
    monkeypatch.setattr(provider, "_invoke_json_capability", request)
    assert provider.get_statement_evidence("300502.SZ", result["announcementId"]) == result
    assert calls == [("research.statement-evidence", "/equity-research/statement-evidence", {"code": "300502", "announcementId": result["announcementId"]})]
    result["symbol"] = "600519"
    with pytest.raises(MarketDataError, match="身份"):
        provider.get_statement_evidence("300502", result["announcementId"])


class StatementRouteTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application([(r"/api/v1/stock-research/statement-evidence", StockStatementEvidenceHandler),
                            (r"/api/v1/stock-research/statement-announcements", StockStatementAnnouncementsHandler)])

    def test_announcement_lookup_is_read_only_and_validates_security(self):
        provider=SimpleNamespace(get_statement_announcements=lambda symbol:{'symbol':symbol,'source':'cninfo','items':[]})
        with patch('instock.web.stock_research_handler.get_market_data_provider',return_value=provider):
            response=self.fetch('/api/v1/stock-research/statement-announcements?symbol=300502')
            assert response.code==200 and json.loads(response.body)['data']['symbol']=='300502'
            assert self.fetch('/api/v1/stock-research/statement-announcements?symbol=bad').code==400

    def test_read_only_route_and_invalid_request(self):
        calls = []
        def read(code, announcement):
            calls.append((code, announcement))
            return {"symbol": code, "announcementId": announcement, "facts": []}
        with patch("instock.web.stock_research_handler.get_market_data_provider", return_value=SimpleNamespace(get_statement_evidence=read)):
            response = self.fetch("/api/v1/stock-research/statement-evidence?symbol=300502&announcementId=AN202608240006746577")
            assert response.code == 200
            assert json.loads(response.body)["data"]["facts"] == []
            assert self.fetch("/api/v1/stock-research/statement-evidence?symbol=bad").code == 400
        assert len(calls) == 1

    def test_failure_is_not_reported_as_empty_success(self):
        def read(*_): raise MarketDataError("来源暂不可读")
        with patch("instock.web.stock_research_handler.get_market_data_provider", return_value=SimpleNamespace(get_statement_evidence=read)):
            response = self.fetch("/api/v1/stock-research/statement-evidence?symbol=300502&announcementId=AN202608240006746577")
        assert response.code == 502
        assert json.loads(response.body)["error"]["code"] == "statement_evidence_unavailable"


def test_unavailable_statement_offers_recovery_without_transport_details(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    def fail(*args):
        raise MarketDataError("HTTP 502 from http://internal-service/private-path")
    monkeypatch.setattr(provider, "_invoke_json_capability", fail)
    with pytest.raises(MarketDataError, match="打开原公告") as caught:
        provider.get_statement_evidence("300502", "AN202608240006746577")
    assert "internal-service" not in str(caught.value)
    assert "无需重新生成" in str(caught.value)


def test_cninfo_provider_retains_source_identity(monkeypatch):
    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8911/api/research")
    result={'symbol':'300502','announcementId':'1225499406','announcementSource':'cninfo','contentOrigin':'pdf-text','facts':[]}
    def request(capability,path,parameters):
        assert capability=='research.statement-evidence' and parameters['source']=='cninfo'
        return result
    monkeypatch.setattr(provider,'_invoke_json_capability',request)
    assert provider.get_statement_evidence('300502','1225499406',source='cninfo')['announcementSource']=='cninfo'
    result['announcementSource']='eastmoney'
    with pytest.raises(MarketDataError,match='身份'):
        provider.get_statement_evidence('300502','1225499406',source='cninfo')


def test_rejected_statement_guides_reselection_without_retrying(monkeypatch):
    import requests

    provider = NewmaDeskMarketDataProvider("http://127.0.0.1:18913/api")
    calls = []
    def request(*args, **kwargs):
        calls.append(args)
        response = requests.Response()
        response.status_code = 422
        response.url = "http://internal-service/private-path"
        return response
    monkeypatch.setattr(provider, "_request_capability", request)

    with pytest.raises(MarketDataError, match="证券身份或财报格式校验") as caught:
        provider.get_statement_evidence("300502", "1225475868", source="cninfo")
    assert len(calls) == 1
    assert "重新选择" in str(caught.value)
    assert "internal-service" not in str(caught.value)


def test_official_report_lookup_uses_data_capability(monkeypatch):
    provider=NewmaDeskMarketDataProvider('http://127.0.0.1:8911/api/research')
    def request(capability,path,parameters):
        assert capability=='research.statement-announcements' and parameters=={'code':'300502'}
        return {'symbol':'300502','source':'cninfo','items':[]}
    monkeypatch.setattr(provider,'_invoke_json_capability',request)
    assert provider.get_statement_announcements('300502.SZ')['source']=='cninfo'
