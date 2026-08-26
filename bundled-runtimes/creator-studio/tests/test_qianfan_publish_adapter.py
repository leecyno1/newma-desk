from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import execute_qianfan_publish as adapter


def write_request(tmp_path: Path) -> Path:
    request = tmp_path / "qianfan_video_request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "dasheng.qianfan_video_request.v1",
                "api_base": "${QIANFAN_API_BASE:-http://127.0.0.1:5409}",
                "run_id": "run-1",
                "task_id": "task-1",
                "content_revision": "rev-1",
                "qianfan_draft_id": 101,
                "platform": "xiaohongshu",
                "account_selector": {"account_name": "account-a"},
                "post_video_payload": {
                    "type": 1,
                    "title": "测试",
                    "fileList": [str(tmp_path / "video.mp4")],
                    "accountList": [],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return request


def test_qianfan_preview_validates_draft_without_enqueue(tmp_path, monkeypatch):
    request = write_request(tmp_path)
    monkeypatch.setattr(adapter, "build_package", lambda _: {"status": "ready", "outputs": {"qianfan_video_request": str(request)}})

    calls = []

    def fake_http(method, url, payload, timeout):
        calls.append((method, url, payload, timeout))
        return {"code": 200, "data": {"valid": True, "errors": [], "account_ids": [7]}}

    result = adapter.build_result(tmp_path / "channel_pack.json", confirm_execute=False, http_client=fake_http)
    assert result["status"] == "ready_for_user_confirmation"
    assert result["will_not_publish"] is True
    assert [call[0] for call in calls] == ["GET"]
    assert calls[0][1].endswith("/api/v2/drafts/101/validate")


def test_qianfan_execute_enqueues_validated_draft_once(tmp_path, monkeypatch):
    request = write_request(tmp_path)
    monkeypatch.setattr(adapter, "build_package", lambda _: {"status": "ready", "outputs": {"qianfan_video_request": str(request)}})
    calls = []

    def fake_http(method, url, payload, timeout):
        calls.append((method, url, payload, timeout))
        if method == "GET":
            return {"code": 200, "data": {"valid": True, "errors": [], "account_ids": [7]}}
        return {"code": 200, "task_ids": [9001], "batch_ids": [8001], "failed": []}

    result = adapter.build_result(tmp_path / "channel_pack.json", confirm_execute=True, http_client=fake_http)
    assert result["success"] is True
    assert result["status"] == "queued_for_publish"
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert calls[1][1].endswith("/api/v2/drafts/batch-publish")
    assert calls[1][2] == {
        "draft_ids": [101],
        "idempotency_keys": ["run-1:task-1:7:rev-1"],
    }

    repeated = adapter.build_result(tmp_path / "channel_pack.json", confirm_execute=True, http_client=fake_http)
    assert repeated["status"] == "already_queued"
    assert [call[0] for call in calls] == ["GET", "POST", "GET"]


def test_qianfan_execute_blocks_invalid_draft(tmp_path, monkeypatch):
    request = write_request(tmp_path)
    monkeypatch.setattr(adapter, "build_package", lambda _: {"status": "ready", "outputs": {"qianfan_video_request": str(request)}})

    def fake_http(method, url, payload, timeout):
        return {"code": 200, "data": {"valid": False, "errors": ["账号未绑定"], "account_ids": []}}

    result = adapter.build_result(tmp_path / "channel_pack.json", confirm_execute=True, http_client=fake_http)
    assert result["status"] == "blocked_qianfan_draft_validation"
    assert result["will_not_publish"] is True
    assert result["errors"] == ["账号未绑定"]
