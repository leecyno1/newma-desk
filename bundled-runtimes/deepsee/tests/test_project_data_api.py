from datetime import datetime
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base
from app.models import Chat, Contact, EmailAccount, EmailMessage, Message, SyncState
from app.routers import data_api
from app.services.data_api_access import ProjectRateLimiter, SCOPES
from app.services import public_data
from app.services.wechat_labels import LABEL_CACHE_KEY

TOKEN = "test-project-key-not-a-real-secret-123"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'data.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "DATA_API_CLIENTS", json.dumps({
        "research": {"token": TOKEN, "scopes": sorted(SCOPES)},
        "news-project": {"token": "news-only-project-key-123456789", "scopes": ["news:read"]},
    }))
    monkeypatch.setattr(settings, "DATA_API_TIMEZONE", "Asia/Shanghai")
    app = FastAPI()
    app.state.data_api_limiter = ProjectRateLimiter()
    app.include_router(data_api.router)

    def get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[data_api.get_db] = get_db
    with factory() as db:
        db.add(Chat(id="room", title="研究群", is_chatroom=True))
        db.add(Contact(id="wx_a", name="昵称", alias="研究员备注", labels={"tags": ["投资"], "label_ids": ["1"]}))
        db.add(Contact(id="wx_b", name="第二人", labels={"label_ids": ["2"]}))
        db.add(SyncState(key=LABEL_CACHE_KEY, value=json.dumps({"account": "owner", "names": {"1": "投资"}, "saved_at": "2026-10-15T01:00:00"})))
        db.add_all([
            Message(id=1, chat_id="room", sender_id="wx_a", timestamp=datetime(2026, 10, 15, 9),
                    type="text", content_text="公司增长 20%", derived={"summary": "增长观点"},
                    meta={"device_key": "never-export-this"}),
            Message(id=2, chat_id="room", sender_id="wx_a", timestamp=datetime(2026, 10, 15, 8),
                    type="image", content_text='<msg><img aeskey="secret-material"/></msg>',
                    derived={"summary": '<img aeskey="secret-material"/>', "category": "提问", "tone": "negative"}),
            Message(id=3, chat_id="room", sender_id="wx_b", timestamp=datetime(2026, 10, 14), type="text", content_text="迟到的消息"),
        ])
        db.add(EmailAccount(id=1, name="邮箱", email_address="me@example.com", imap_host="imap.example.com",
                            smtp_host="smtp.example.com", auth={"password": "mail-secret"}))
        db.add(EmailMessage(id=1, account_id=1, subject="报告", from_addr="sender@example.com",
                            to_addrs=["me@example.com"], body_text="报告正文", meta={"raw": "mail-secret"}))
        db.commit()
    yield TestClient(app), factory, app
    engine.dispose()


def test_auth_fails_closed_and_project_scopes_are_independent(api, monkeypatch):
    client, _, _ = api
    assert client.get("/api/v1/messages").status_code == 401
    assert client.get("/api/v1/messages", headers={"Authorization": "Bearer wrong"}).status_code == 401
    news = {"Authorization": "Bearer news-only-project-key-123456789"}
    denied = client.get("/api/v1/contacts", headers=news)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_scope"
    resources = client.get("/api/v1/capabilities", headers=news).json()["data"]["resources"]
    assert [r["resource"] for r in resources] == ["news"]
    monkeypatch.setattr(settings, "DATA_API_CLIENTS", None)
    assert client.get("/api/v1/messages", headers=HEADERS).status_code == 503


def test_pagination_and_incremental_read_include_late_arrivals(api):
    client, factory, _ = api
    first = client.get("/api/v1/messages?limit=2", headers=HEADERS).json()
    assert [r["id"] for r in first["data"]] == [1, 2]
    second = client.get("/api/v1/messages", params={"limit": 2, "cursor": first["meta"]["next_cursor"]}, headers=HEADERS).json()
    assert [r["id"] for r in second["data"]] == [3]
    assert second["meta"]["has_more"] is False
    with factory() as db:
        db.add(Message(id=4, timestamp=datetime(2020, 1, 1), content_text="晚入库", type="text"))
        db.commit()
    new = client.get("/api/v1/messages?after_id=3", headers=HEADERS).json()
    assert [r["id"] for r in new["data"]] == [4]
    empty = client.get("/api/v1/messages?after_id=4", headers=HEADERS).json()
    assert empty["data"] == [] and empty["meta"]["last_id"] == 4


def test_cursor_cannot_silently_change_filters_or_resource(api):
    client, _, _ = api
    cursor = client.get("/api/v1/messages?limit=1", headers=HEADERS).json()["meta"]["next_cursor"]
    for path, params in [("messages", {"q": "different", "cursor": cursor}),
                         ("contacts", {"cursor": cursor}),
                         ("messages", {"cursor": cursor, "after_id": 1}),
                         ("messages", {"cursor": "not-json"})]:
        assert client.get(f"/api/v1/{path}", params=params, headers=HEADERS).status_code == 422


def test_export_has_remarks_utc_and_no_protocol_or_credentials(api):
    client, _, _ = api
    response = client.get("/api/v1/messages", headers=HEADERS)
    rows = response.json()["data"]
    assert rows[0]["sender_name"] == "研究员备注"
    assert rows[0]["chat_name"] == "研究群"
    assert rows[0]["occurred_at"] == "2026-10-15T01:00:00Z"
    assert rows[1]["text"] == "[image]" and rows[1]["category"] is None
    assert "secret-material" not in response.text and "never-export-this" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]
    emails = client.get("/api/v1/emails", headers=HEADERS)
    assert emails.json()["data"][0]["text"] == "报告正文"
    assert "mail-secret" not in emails.text and "auth" not in emails.json()["data"][0]


def test_time_and_literal_search_filters(api):
    client, _, _ = api
    rows = client.get("/api/v1/messages", params={"since": "2026-10-15T00:30:00Z", "until": "2026-10-15T02:00:00Z"}, headers=HEADERS).json()["data"]
    assert [r["id"] for r in rows] == [1]
    assert client.get("/api/v1/messages?since=2026-10-15T00:00:00", headers=HEADERS).status_code == 422
    rows = client.get("/api/v1/messages", params={"q": "%"}, headers=HEADERS).json()["data"]
    assert [r["id"] for r in rows] == [1]


def test_contacts_labels_and_details(api):
    client, _, _ = api
    rows = client.get("/api/v1/contacts?q=备注", headers=HEADERS).json()["data"]
    assert [r["id"] for r in rows] == ["wx_a"]
    assert rows[0]["labels"] == ["投资"]
    labels = client.get("/api/v1/labels", headers=HEADERS).json()
    assert labels["name_source"] == "local_cache"
    assert labels["data"] == [{"id": "1", "name": "投资", "member_count": 1}, {"id": "2", "name": None, "member_count": 1}]
    assert client.get("/api/v1/contacts/missing", headers=HEADERS).status_code == 404
    assert client.get("/api/v1/messages/1", headers=HEADERS).json()["data"]["id"] == 1
    assert client.get("/api/v1/emails/1", headers=HEADERS).status_code == 200
    assert client.get("/api/v1/chats", headers=HEADERS).json()["data"][0]["is_group"] is True


def test_rate_limit_and_validation(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(settings, "DATA_API_CLIENTS", json.dumps({"small": {"token": TOKEN, "scopes": ["messages:read"], "requests_per_minute": 1}}))
    assert client.get("/api/v1/messages", headers=HEADERS).status_code == 200
    limited = client.get("/api/v1/messages", headers=HEADERS)
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0


def test_openapi_is_versioned_typed_and_read_only(api):
    client, _, _ = api
    spec = client.get("/api/v1/openapi.json", headers=HEADERS).json()
    assert spec["info"]["version"] == "1.1.0"
    assert all(path.startswith("/api/v1/") for path in spec["paths"])
    assert all(set(methods) == {"get"} for methods in spec["paths"].values())
    assert spec["components"]["securitySchemes"]["ProjectApiKey"]["scheme"] == "bearer"
    assert client.get("/api/v1/messages?limit=201", headers=HEADERS).status_code == 422


def test_snapshots_are_bounded_filtered_and_do_not_export_paths(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(public_data, "SNAPSHOT_LIMIT", 2)
    monkeypatch.setattr(public_data, "snapshot_rows", lambda *_: [
        {"id": str(i), "title": f"记录{i}", "time": f"2026-10-1{i}T09:00:00", "path": "/secret/internal/path",
         "content": "正文", "meta": {"key": "secret"}} for i in (1, 2, 3)
    ])
    response = client.get("/api/v1/articles?source=news&limit=1", headers=HEADERS)
    payload = response.json()
    assert payload["data"][0]["id"] == "news:3"
    assert payload["meta"]["truncated"] is True and payload["meta"]["next_offset"] == 1
    assert "/secret" not in response.text
    assert client.get("/api/v1/articles?source=news&offset=1", headers=HEADERS).json()["data"][0]["id"] == "news:2"


def test_local_adapters_do_not_collect_or_call_models(api, monkeypatch, tmp_path):
    client, _, _ = api
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEWS_DATASET_DIR", str(tmp_path / "datasets"))
    monkeypatch.setenv("COLLECTOR_DATA_DIR", str(tmp_path / "collector"))
    monkeypatch.setenv("MEDIA_PROJECT_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("WE_MP_RSS_DB", str(tmp_path / "absent.db"))
    monkeypatch.setenv("MP_REMOTE_ENABLED", "1")
    monkeypatch.setenv("MINUTES_DIRS", str(tmp_path / "minutes"))
    import requests
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: pytest.fail("must not fetch upstream"))
    for source in ("news", "media", "mp"):
        result = client.get(f"/api/v1/articles?source={source}", headers=HEADERS)
        assert result.status_code == 200, result.text
    assert client.get("/api/v1/meetings", headers=HEADERS).status_code == 200


def test_legacy_auth_does_not_demand_admin_token_for_project_api(api, monkeypatch):
    from app.main import create_app
    _, factory, _ = api
    monkeypatch.setattr(settings, "API_AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "API_TOKEN", "admin-only-token")
    app = create_app()

    def get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[data_api.get_db] = get_db
    client = TestClient(app)
    assert client.get("/api/v1/messages", headers=HEADERS).status_code == 200
    assert client.get("/api/messages", headers=HEADERS).status_code == 401
