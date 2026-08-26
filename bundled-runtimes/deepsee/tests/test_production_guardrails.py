import asyncio
import os
import sys
import tempfile
from datetime import datetime

from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.main import (
    _api_token_auth_enabled,
    _configured_api_tokens,
    _cors_options,
    _extract_api_token,
    _is_api_auth_exempt_path,
)
from app.db import Base
from app.models import EmailAccount, EmailMessage
from app.routers import ai, contacts, email, health as health_router
from app.schemas import EmailAccountIn


class _DummyScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DummyExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar(self):
        if isinstance(self._rows, list):
            return self._rows[0] if self._rows else None
        return self._rows

    def scalars(self):
        return _DummyScalars(self._rows)


class _DummyDb:
    def __init__(self, rows=None, row=None, execute_results=None):
        self._rows = rows or []
        self._row = row
        self._execute_results = list(execute_results or [])
        self.committed = False
        self.refreshed = False

    def execute(self, *_args, **_kwargs):
        if self._execute_results:
            return self._execute_results.pop(0)
        return _DummyExecuteResult(self._rows)

    def get(self, *_args, **_kwargs):
        return self._row

    def commit(self):
        self.committed = True

    def refresh(self, _row):
        self.refreshed = True


class _EmailRow:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _ContactRow:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)



def test_get_ai_config_masks_router_secrets(monkeypatch):
    monkeypatch.setattr(
        ai,
        "load_ai_config",
        lambda: {
            "api_key": "top-secret",
            "api_url": "https://example.com/v1",
            "model": "main-model",
            "tool_model": "tool-model",
            "model_router": {
                "enabled": True,
                "main_channels": [
                    {
                        "id": "main-1",
                        "model": "model-a",
                        "api_url": "https://a.example/v1",
                        "api_key": "secret-a",
                        "weight": 1,
                        "enabled": True,
                    }
                ],
                "tool_channels": [
                    {
                        "id": "tool-1",
                        "model": "tool-a",
                        "api_key": "secret-b",
                        "weight": 1,
                        "enabled": True,
                    }
                ],
            },
        },
    )

    payload = ai.get_ai_config()
    assert payload["has_key"] is True
    assert "api_key" not in payload
    main_channel = payload["model_router"]["main_channels"][0]
    assert main_channel["api_key"] == ""
    assert main_channel["has_api_key"] is True
    tool_channel = payload["model_router"]["tool_channels"][0]
    assert tool_channel["api_key"] == ""
    assert tool_channel["has_api_key"] is True



def test_list_accounts_masks_password_but_keeps_username():
    row = _EmailRow(
        id=1,
        name="test",
        email_address="a@example.com",
        provider="custom",
        imap_host="imap.example.com",
        imap_port=993,
        imap_ssl=True,
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_ssl=True,
        auth={"username": "alice", "password": "secret-pass"},
        enabled=True,
        last_sync_at=None,
    )
    out = email.list_accounts(db=_DummyDb(rows=[row]))
    assert out[0].auth["username"] == "alice"
    assert out[0].auth["password"] == ""
    assert out[0].auth["has_password"] is True



def test_update_account_preserves_existing_password_when_blank():
    row = _EmailRow(
        id=1,
        name="acct",
        email_address="a@example.com",
        provider="custom",
        imap_host="imap.old",
        imap_port=993,
        imap_ssl=True,
        smtp_host="smtp.old",
        smtp_port=465,
        smtp_ssl=True,
        auth={"username": "alice", "password": "kept-secret"},
        enabled=True,
        last_sync_at=None,
    )
    db = _DummyDb(row=row)
    body = EmailAccountIn(
        name="acct",
        email_address="a@example.com",
        provider="custom",
        imap_host="imap.new",
        imap_port=993,
        imap_ssl=True,
        smtp_host="smtp.new",
        smtp_port=465,
        smtp_ssl=True,
        auth={"username": "alice", "password": ""},
        enabled=True,
    )

    out = email.update_account(1, body=body, db=db)
    assert db.committed is True
    assert row.auth["password"] == "kept-secret"
    assert out.auth["password"] == ""
    assert out.auth["has_password"] is True


def test_list_email_messages_omits_bodies_by_default():
    row = _EmailRow(
        id=9,
        account_id=1,
        external_id="x",
        subject="subject",
        from_addr="from@example.com",
        to_addrs=["to@example.com"],
        cc_addrs=[],
        bcc_addrs=[],
        sent_at=None,
        direction="in",
        snippet="snippet",
        body_text="very long body",
        body_html="<p>very long body</p>",
        flags=[],
        meta=None,
        derived={},
    )
    db = _DummyDb(
        execute_results=[
            _DummyExecuteResult(2),
            _DummyExecuteResult([row]),
        ]
    )
    out = email.list_email_messages(limit=50, offset=0, include_bodies=False, db=db)
    assert out["total"] == 2
    assert out["items"][0].body_text is None
    assert out["items"][0].body_html is None


def test_list_email_messages_counts_real_filtered_rows():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        engine = create_engine(f"sqlite:///{path}", future=True)
        TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        Base.metadata.create_all(engine, tables=[EmailAccount.__table__, EmailMessage.__table__])

        with TestingSession() as db:
            account = EmailAccount(
                name="acct",
                email_address="acct@example.com",
                provider="custom",
                imap_host="imap.example.com",
                imap_port=993,
                imap_ssl=True,
                smtp_host="smtp.example.com",
                smtp_port=465,
                smtp_ssl=True,
                auth={"username": "acct@example.com", "password": "x"},
                enabled=True,
            )
            db.add(account)
            db.flush()
            db.add_all(
                [
                    EmailMessage(
                        account_id=account.id,
                        subject="alpha briefing",
                        from_addr="a@example.com",
                        to_addrs=["acct@example.com"],
                        cc_addrs=[],
                        bcc_addrs=[],
                        sent_at=datetime(2026, 3, 28, 10, 0, 0),
                        direction="in",
                        snippet="alpha first",
                        body_text="alpha first full body",
                        body_html=None,
                        flags=[],
                        meta=None,
                        derived={},
                    ),
                    EmailMessage(
                        account_id=account.id,
                        subject="beta note",
                        from_addr="b@example.com",
                        to_addrs=["acct@example.com"],
                        cc_addrs=[],
                        bcc_addrs=[],
                        sent_at=datetime(2026, 3, 28, 11, 0, 0),
                        direction="in",
                        snippet="beta only",
                        body_text="beta only full body",
                        body_html=None,
                        flags=[],
                        meta=None,
                        derived={},
                    ),
                    EmailMessage(
                        account_id=account.id,
                        subject="alpha followup",
                        from_addr="c@example.com",
                        to_addrs=["acct@example.com"],
                        cc_addrs=[],
                        bcc_addrs=[],
                        sent_at=datetime(2026, 3, 28, 12, 0, 0),
                        direction="in",
                        snippet="alpha second",
                        body_text="alpha second full body",
                        body_html=None,
                        flags=[],
                        meta=None,
                        derived={},
                    ),
                ]
            )
            db.commit()

        with TestingSession() as db:
            out = email.list_email_messages(q="alpha", limit=50, offset=0, include_bodies=False, db=db)
            assert out["total"] == 2
            assert [item.subject for item in out["items"]] == ["alpha followup", "alpha briefing"]
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def test_static_index_contains_summary_detail_modal_hooks():
    html = open(os.path.join(PROJECT_ROOT, "static", "index.html"), "r", encoding="utf-8").read()
    assert "openSummaryDetailModal" in html
    assert "summary-detail-mode" in html


def test_static_index_uses_professional_summary_icons_and_title_dedupe_hook():
    html = open(os.path.join(PROJECT_ROOT, "static", "index.html"), "r", encoding="utf-8").read()
    assert "stripDuplicateSummaryHeading" in html
    assert "summary-title-group" in html
    assert "summary-card-icon" in html
    assert "📈 市场观点总结" not in html
    assert "🎯 会议路演信息" not in html


def test_static_index_contains_summary_divider_and_hover_enhancement_hooks():
    html = open(os.path.join(PROJECT_ROOT, "static", "index.html"), "r", encoding="utf-8").read()
    assert "decorateSummaryHoverItems" in html
    assert ".summary-hover-item" in html
    assert "border-bottom: 1px solid rgba(148, 163, 184, 0.22);" in html


def test_static_index_replaces_primary_ai_toolbar_emojis_with_svg_markup():
    html = open(os.path.join(PROJECT_ROOT, "static", "index.html"), "r", encoding="utf-8").read()
    assert "buildButtonMarkup" in html
    assert "applyThemeToggleMarkup" in html
    assert "🚀 运行分析" not in html
    assert "🖼 一页通" not in html
    assert "📄 导出" not in html
    assert "☀️ 浅色" not in html
    assert "🌙 深色" not in html


def test_static_index_disables_workspace_access_gate_but_keeps_guest_guard_stubs():
    html = open(os.path.join(PROJECT_ROOT, "static", "index.html"), "r", encoding="utf-8").read()
    assert 'id="accessGate"' not in html
    assert 'id="accessConfirmBtn"' not in html
    assert 'id="accessGuestBtn"' not in html
    assert "function canAccessModule(moduleId) {" in html
    assert "return true;" in html
    assert "function guestUseCacheOnly() {" in html
    assert "function shouldSkipGuestModuleLoad(moduleId)" in html
    assert "function isGuestAllowedApiPath(urlLike)" in html
    assert "if (guestUseCacheOnly() && !isGuestAllowedApiPath(url))" in html
    assert "游客模式不可访问此接口" in html
    assert "if (guestUseCacheOnly() && isGuestBlurModule(targetModule))" in html
    assert "if (guestUseCacheOnly()) return;" in html


def test_static_index_contains_background_runtime_panel():
    html = open(os.path.join(PROJECT_ROOT, "static", "index.html"), "r", encoding="utf-8").read()
    assert "后台任务运行状态" in html
    assert "loadBackgroundRuntimeStats" in html
    assert 'id="backgroundRuntimeBody"' in html


def test_static_index_contains_contact_scoring_hooks():
    html = open(os.path.join(PROJECT_ROOT, "static", "index.html"), "r", encoding="utf-8").read()
    assert "refreshContactScoring" in html
    assert "openContactScorecard" in html
    assert "/api/contact-scoring/run" in html
    assert "/scorecard" in html
    assert "市场数据配置" in html
    assert "loadMarketDataConfig" in html
    assert "/api/config/market-data" in html
    assert "期限命中画像" in html
    assert "标的表现榜" in html
    assert "renderContactSummaryPreview" in html
    assert "renderContactSparkline" in html
    assert "renderContactMarketCurve" in html
    assert "评分摘要" in html
    assert "contactSummaryFilter" in html
    assert "contactSortMode" in html
    assert "contactSubScoreMetric" in html
    assert "contactSubScoreWindow" in html
    assert "contactSubScoreFilter" in html
    assert "contactSubScoreTrendFilter" in html
    assert "contactWarningFilter" in html
    assert "applyContactSortMode" in html
    assert "contact-curve-anchor" in html
    assert "核心标的走势" in html
    assert "分期限命中拆解" in html
    assert "事件流" in html
    assert "renderContactEventTimeline" in html
    assert "filterContactEventTimeline" in html
    assert "评分矩阵" in html
    assert "contact-score-compare" in html
    assert "建议动作" in html
    assert "renderContactActionRecommendation" in html
    assert "contactWarningBoard" in html
    assert "renderContactWarningBoard" in html
    assert "/watch?" in html
    assert "toggleContactWatch" in html


def test_static_index_contains_router_batch_test_hooks():
    html = open(os.path.join(PROJECT_ROOT, "static", "index.html"), "r", encoding="utf-8").read()
    assert "testAllRouterModels" in html
    assert "routerBatchTestStatus" in html
    assert "router-status-dot" in html
    assert "/api/ai/test-all-models" in html
    assert "previewRouterRoute" in html
    assert "validateRouterConfigFromUi" in html
    assert "/api/ai/route-preview" in html


def test_list_contacts_omits_labels_unless_requested():
    row = _ContactRow(id="wxid_a", name="Alice", alias="A", rating=88, labels={"tags": ["重点"]})
    db = _DummyDb(rows=[row])
    compact = contacts.list_contacts(include_labels=False, db=db)
    assert compact[0].labels is None

    full = contacts.list_contacts(include_labels=True, db=_DummyDb(rows=[row]))
    assert full[0].labels == {"tags": ["重点"]}


def test_list_contacts_includes_score_summary_when_requested(monkeypatch):
    row = _ContactRow(id="wxid_a", name="Alice", alias="A", rating=88, labels={"tags": ["重点"]})
    db = _DummyDb(
        execute_results=[
            _DummyExecuteResult(1),
            _DummyExecuteResult([row]),
        ]
    )
    monkeypatch.setattr(
        contacts,
        "build_contact_score_summaries",
        lambda _db, _ids: {
            "wxid_a": {
                "total_predictions": 6,
                "pending_predictions": 1,
                "top_asset_name": "紫金矿业",
                "hit_rate_1m": 0.75,
            }
        },
    )

    out = contacts.list_contacts(include_labels=False, include_score_summary=True, db=db)
    assert out[0].score_summary["total_predictions"] == 6
    assert out[0].score_summary["top_asset_name"] == "紫金矿业"


def test_list_contacts_skips_score_summary_by_default(monkeypatch):
    row = _ContactRow(id="wxid_a", name="Alice", alias="A", rating=88, labels={"tags": ["重点"]})
    db = _DummyDb(
        execute_results=[
            _DummyExecuteResult(1),
            _DummyExecuteResult([row]),
        ]
    )

    def _unexpected_summary(_db, _ids):
        raise AssertionError("score summaries should be opt-in for the contact list")

    monkeypatch.setattr(contacts, "build_contact_score_summaries", _unexpected_summary)

    out = contacts.list_contacts(include_labels=False, db=db)
    assert out[0].score_summary is None


def test_list_contacts_supports_limit_offset_and_total_header():
    rows = [
        _ContactRow(id="wxid_a", name="Alice", alias="A", rating=88, labels={"tags": ["重点"]}),
        _ContactRow(id="wxid_b", name="Bob", alias="B", rating=77, labels={"tags": ["次重点"]}),
    ]
    db = _DummyDb(
        execute_results=[
            _DummyExecuteResult(2),
            _DummyExecuteResult([rows[1]]),
        ]
    )
    class _Resp:
        headers = {}

    response = _Resp()
    page = contacts.list_contacts(limit=1, offset=1, include_labels=False, response=response, db=db)
    assert len(page) == 1
    assert page[0].id == "wxid_b"
    assert response.headers["X-Total-Count"] == "2"


def test_list_contact_ratings_returns_compact_mapping():
    db = _DummyDb(execute_results=[_DummyExecuteResult([("wxid_a", 88), ("wxid_b", None)])])
    ratings = contacts.list_contact_ratings(db=db)
    assert ratings == {"wxid_a": 88, "wxid_b": 50}



def test_api_token_helpers_enable_workspace_gate_when_required(monkeypatch):
    monkeypatch.setattr("app.main.settings.APP_ENV", "production")
    monkeypatch.setattr("app.main.settings.API_AUTH_REQUIRED", True)
    monkeypatch.setattr("app.main.settings.API_TOKEN", "prod-token")
    assert _api_token_auth_enabled() is True
    assert _configured_api_tokens() == {"prod-token"}
    assert _is_api_auth_exempt_path("/api/health") is True
    assert _is_api_auth_exempt_path("/api/ready") is True
    assert _is_api_auth_exempt_path("/api/access/verify") is True
    assert _is_api_auth_exempt_path("/api/agent/invoke") is True
    assert _is_api_auth_exempt_path("/api/ai/config") is False

    bearer_request = Request({"type": "http", "headers": [(b"authorization", b"Bearer prod-token")]})
    assert _extract_api_token(bearer_request) == "prod-token"

    header_request = Request({"type": "http", "headers": [(b"x-api-token", b"prod-token")]})
    assert _extract_api_token(header_request) == "prod-token"


def test_api_token_auth_stays_disabled_for_local_default(monkeypatch):
    monkeypatch.setattr("app.main.settings.APP_ENV", "development")
    monkeypatch.setattr("app.main.settings.API_AUTH_REQUIRED", False)
    monkeypatch.setattr("app.main.settings.API_TOKEN", "dev-local-token")
    assert _api_token_auth_enabled() is False



def test_cors_options_switch_between_dev_and_prod(monkeypatch):
    monkeypatch.setattr("app.main.settings.APP_ENV", "development")
    monkeypatch.setattr("app.main.settings.CORS_ALLOW_ORIGINS", None)
    dev = _cors_options()
    assert dev is not None
    assert dev["allow_origins"] == ["*"]

    monkeypatch.setattr("app.main.settings.APP_ENV", "production")
    monkeypatch.setattr("app.main.settings.CORS_ALLOW_ORIGINS", "https://a.example, https://b.example")
    prod = _cors_options()
    assert prod is not None
    assert prod["allow_origins"] == ["https://a.example", "https://b.example"]


def test_verify_access_token_requires_match_when_configured(monkeypatch):
    monkeypatch.setattr("app.routers.health.settings.API_TOKEN", "iv19whot")
    ok_req = Request({"type": "http", "headers": [(b"x-api-token", b"iv19whot")]})
    assert asyncio.run(health_router.verify_access_token(ok_req)) == {"status": "ok", "configured": True}


def test_verify_access_token_returns_config_unset(monkeypatch):
    monkeypatch.setattr("app.routers.health.settings.API_TOKEN", "")
    req = Request({"type": "http", "headers": []})
    assert asyncio.run(health_router.verify_access_token(req)) == {"status": "ok", "configured": False}


def test_background_runtime_endpoint_returns_runtime_snapshot(monkeypatch):
    monkeypatch.setattr(
        health_router,
        "get_background_runtime_snapshot",
        lambda: {
            "chatlog_sync": {
                "name": "chatlog_sync",
                "enabled": True,
                "running": False,
                "runs": 3,
                "failures": 0,
                "last_success_at": "2026-04-13T12:00:00+00:00",
                "last_error": None,
            },
            "email_sync": {
                "name": "email_sync",
                "enabled": False,
                "running": False,
                "runs": 0,
                "failures": 0,
                "last_success_at": None,
                "last_error": None,
            },
        },
    )
    payload = asyncio.run(health_router.background_runtime())
    assert payload["status"] == "ok"
    assert payload["total"] == 2
    assert payload["enabled"] == 1
    assert payload["runtime"]["chatlog_sync"]["runs"] == 3


def test_ai_router_batch_connectivity_endpoint(monkeypatch):
    monkeypatch.setattr(
        ai,
        "load_ai_config",
        lambda: {
            "api_url": "https://base.example/v1",
            "api_key": "base-key",
            "model": "base-main",
            "tool_model": "base-tool",
            "model_router": {
                "enabled": True,
                "main_channels": [
                    {"id": "main-a", "model": "model-a", "api_url": "https://a.example/v1", "api_key": "ka", "enabled": True},
                ],
                "mid_channels": [
                    {"id": "mid-a", "model": "model-mid", "api_url": "https://m.example/v1", "api_key": "km", "enabled": True},
                ],
                "tool_channels": [
                    {"id": "tool-a", "model": "model-tool", "api_url": "https://t.example/v1", "api_key": "kt", "enabled": True},
                ],
            },
        },
    )

    def _fake_post(url, headers, payload, timeout=180):  # noqa: ARG001
        class _Resp:
            status_code = 200
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "连接成功"}}]}

        return _Resp()

    monkeypatch.setattr("app.services.llm_client._post_with_backoff", _fake_post)
    payload = ai.test_all_router_models()
    assert payload["status"] == "ok"
    assert payload["summary"]["total"] >= 3
    assert payload["summary"]["ok"] >= 3
    assert payload["lanes"]["main"][0]["status"] == "ok"
    assert payload["lanes"]["mid"][0]["status"] == "ok"
    assert payload["lanes"]["tool"][0]["status"] == "ok"


def test_ai_route_preview_uses_resolved_targets_without_secrets(monkeypatch):
    monkeypatch.setattr(
        ai,
        "load_ai_config",
        lambda: {
            "api_url": "https://base.example/v1",
            "api_key": "base-key",
            "model": "base-main",
            "tool_model": "base-tool",
            "model_router": {
                "enabled": True,
                "prefer_router": True,
                "main_channels": [
                    {"id": "main-a", "model": "model-a", "api_url": "https://a.example/v1", "api_key": "ka", "enabled": True},
                ],
                "main_module_channels": {"market": ["main-a"], "default": ["main-a"]},
            },
        },
    )

    payload = ai.route_preview(route_kind="main", route_key="market")

    assert payload["status"] == "ok"
    assert payload["route_kind"] == "main"
    assert payload["route_key"] == "market"
    assert payload["targets"][0]["channel_id"] == "main-a"
    assert payload["targets"][0]["model"] == "model-a"
    assert payload["targets"][0]["has_api_key"] is True
    assert "api_key" not in payload["targets"][0]
