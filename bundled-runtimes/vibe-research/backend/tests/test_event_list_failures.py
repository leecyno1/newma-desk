from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

import app
import astock


@pytest.mark.parametrize("payload", [{"message": "unavailable"}, {"data": None}, {"data": {}}, {"data": [None]}])
def test_reports_invalid_success_payload_is_http_failure(monkeypatch, payload):
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    monkeypatch.setattr(astock, "_report_session", lambda: SimpleNamespace(get=lambda *a, **k: response))
    result = TestClient(app.app).get("/api/reports", params={"code": "300502", "pages": 1})
    assert result.status_code == 502
    assert "data" not in result.json()


def test_reports_http_failure_is_not_empty_success(monkeypatch):
    def fail():
        raise requests.HTTPError("upstream rejected request")
    response = SimpleNamespace(raise_for_status=fail, json=lambda: {"data": []})
    monkeypatch.setattr(astock, "_report_session", lambda: SimpleNamespace(get=lambda *a, **k: response))
    assert TestClient(app.app).get("/api/reports", params={"code": "300502", "pages": 1}).status_code == 502


def test_explicit_empty_report_list_remains_success(monkeypatch):
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": [], "TotalPage": 0})
    monkeypatch.setattr(astock, "_report_session", lambda: SimpleNamespace(get=lambda *a, **k: response))
    result = TestClient(app.app).get("/api/reports", params={"code": "300502", "pages": 1})
    assert result.status_code == 200
    assert result.json() == {"data": []}
