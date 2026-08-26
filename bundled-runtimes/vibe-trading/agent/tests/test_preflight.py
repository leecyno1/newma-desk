"""Tests for startup preflight checks."""

from __future__ import annotations

import sys

import requests

from src import preflight


def _configure_llm_preflight(monkeypatch) -> None:
    """Install a minimal OpenAI-compatible provider environment for preflight tests."""
    import src.providers.llm as llm

    monkeypatch.setenv("LANGCHAIN_PROVIDER", "openai")
    monkeypatch.setenv("LANGCHAIN_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setattr(llm, "_ensure_dotenv", lambda: None)
    monkeypatch.setattr(llm, "_sync_provider_env", lambda: None)
    monkeypatch.setattr(
        llm,
        "provider_diagnostics",
        lambda: {
            "base_url": "https://example.test/v1",
            "timeout_seconds": 120,
            "max_retries": 2,
            "proxy": {},
        },
    )


def test_llm_preflight_probe_does_not_follow_redirects(monkeypatch) -> None:
    """A redirect response still proves the HTTPS provider base is reachable."""
    _configure_llm_preflight(monkeypatch)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs: object) -> object:
        calls.append((url, kwargs))
        response = requests.Response()
        response.status_code = 307
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    result = preflight._check_llm_provider()

    assert result.status == "ready"
    assert calls == [
        (
            "https://example.test",
            {
                "timeout": 10,
                "allow_redirects": False,
            },
        )
    ]


def test_integrated_runtime_delegates_llm_preflight_to_desk(monkeypatch) -> None:
    import src.providers.llm as llm

    monkeypatch.setenv("NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME", "1")
    monkeypatch.setattr(llm, "_ensure_dotenv", lambda: None)

    result = preflight._check_llm_provider()

    assert result.name == "VibeDesk Agent Gateway"
    assert result.status == "ready"
    assert "Desk-level Agent settings" in result.message


def test_llm_preflight_probe_reports_request_errors(monkeypatch) -> None:
    """Request failures remain critical errors for the LLM provider check."""
    _configure_llm_preflight(monkeypatch)

    def fake_get(url: str, **kwargs: object) -> object:
        del url, kwargs
        raise requests.Timeout("timed out")

    monkeypatch.setattr(requests, "get", fake_get)

    result = preflight._check_llm_provider()

    assert result.status == "error"
    assert result.critical is True
    assert "Timeout: timed out" in result.message


def test_akshare_check_uses_spec_without_import(monkeypatch) -> None:
    """AKShare's package import is heavy; preflight should only check discovery."""
    monkeypatch.delitem(sys.modules, "akshare", raising=False)
    monkeypatch.setattr(preflight, "find_spec", lambda name: object() if name == "akshare" else None)

    result = preflight._check_akshare()

    assert result.status == "ready"
    assert result.message == "installed"
    assert "akshare" not in sys.modules


def test_global_stock_data_preflight_checks_skill_primary_routes(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Response:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, **kwargs: object) -> Response:
        calls.append((url, kwargs))
        if "sinajs" in url:
            return Response('var hq_str_gb_aapl="Apple,200";')
        return Response('v_r_hk00700="100~Tencent~00700";')

    monkeypatch.setattr(requests, "get", fake_get)

    result = preflight._check_global_stock_data()

    assert result.name == "global-stock-data"
    assert result.status == "ready"
    assert "US/Sina" in result.message
    assert "HK/Tencent" in result.message
    assert calls == [
        (
            "https://hq.sinajs.cn/list=gb_aapl",
            {
                "headers": {"Referer": "https://finance.sina.com.cn/"},
                "timeout": 10,
            },
        ),
        (
            "https://qt.gtimg.cn/q=r_hk00700",
            {"headers": None, "timeout": 10},
        ),
    ]


def test_global_stock_data_preflight_reports_partial_availability(monkeypatch) -> None:
    class Response:
        text = 'v_r_hk00700="100~Tencent~00700";'

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, **kwargs: object) -> Response:
        del kwargs
        if "sinajs" in url:
            raise requests.Timeout("blocked")
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    result = preflight._check_global_stock_data()

    assert result.status == "ready"
    assert "HK/Tencent" in result.message
    assert "fallback required: US/Sina Timeout" in result.message
    assert "degraded" in result.impact


def test_global_stock_data_preflight_errors_when_all_primary_routes_fail(monkeypatch) -> None:
    def fake_get(url: str, **kwargs: object) -> object:
        del url, kwargs
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", fake_get)

    result = preflight._check_global_stock_data()

    assert result.status == "error"
    assert "US/Sina ConnectionError" in result.message
    assert "HK/Tencent ConnectionError" in result.message


def test_akshare_check_skips_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(preflight, "find_spec", lambda name: None)

    result = preflight._check_akshare()

    assert result.status == "skipped"
    assert result.message == "package not installed"


def test_content_filter_threshold_check(monkeypatch) -> None:
    """Content Filter Threshold row must appear in preflight output."""
    monkeypatch.setenv("CONTENT_FILTER_WARNING_THRESHOLD", "0.10")

    result = preflight._check_content_filter_threshold()

    assert result.name == "Content Filter Threshold"
    assert result.status == "ready"
    assert "10%" in result.message
    assert "CONTENT_FILTER_WARNING_THRESHOLD" in result.message


def test_content_filter_threshold_default(monkeypatch) -> None:
    """Default threshold is 5% when env var is unset."""
    monkeypatch.delenv("CONTENT_FILTER_WARNING_THRESHOLD", raising=False)

    result = preflight._check_content_filter_threshold()

    assert result.name == "Content Filter Threshold"
    assert result.status == "ready"
    assert "5%" in result.message
