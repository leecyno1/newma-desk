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


def test_qianfan_dry_run_never_calls_local_api(tmp_path, monkeypatch):
    request = write_request(tmp_path)
    monkeypatch.setattr(adapter, "build_package", lambda _: {"status": "ready", "outputs": {"qianfan_video_request": str(request)}})

    called = False

    def fail_http(*args):
        nonlocal called
        called = True
        raise AssertionError("dry-run must not call Qianfan")

    result = adapter.build_result(tmp_path / "channel_pack.json", confirm_execute=False, http_client=fail_http)
    assert result["status"] == "ready_for_user_confirmation"
    assert result["will_not_publish"] is True
    assert called is False


def test_qianfan_execute_resolves_named_account_and_posts_video(tmp_path, monkeypatch):
    request = write_request(tmp_path)
    monkeypatch.setattr(adapter, "build_package", lambda _: {"status": "ready", "outputs": {"qianfan_video_request": str(request)}})
    calls = []

    def fake_http(method, url, payload, timeout):
        calls.append((method, url, payload, timeout))
        if method == "GET":
            return {"data": [[7, 1, "/sessions/xhs/account-a.json", "account-a", "正常", None]]}
        return {"code": 200, "msg": "ok"}

    result = adapter.build_result(tmp_path / "channel_pack.json", confirm_execute=True, http_client=fake_http)
    assert result["success"] is True
    assert result["status"] == "pending_verification"
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert calls[1][2]["accountList"] == ["/sessions/xhs/account-a.json"]


def test_qianfan_execute_blocks_ambiguous_unmapped_slot(tmp_path, monkeypatch):
    request = write_request(tmp_path)
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["account_selector"] = {"account_name": "slot-1"}
    request.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(adapter, "build_package", lambda _: {"status": "ready", "outputs": {"qianfan_video_request": str(request)}})

    def fake_http(method, url, payload, timeout):
        return {"data": [[7, 1, "/sessions/xhs/real.json", "real-account", "正常", None]]}

    result = adapter.build_result(tmp_path / "channel_pack.json", confirm_execute=True, http_client=fake_http)
    assert result["status"] == "blocked_qianfan_account_mapping"
    assert result["will_not_publish"] is True
