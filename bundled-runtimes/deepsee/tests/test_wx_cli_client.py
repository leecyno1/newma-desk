from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.wx_cli_client import WxCliClient


def test_wx_cli_runs_from_user_work_dir(monkeypatch, tmp_path):
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["cwd"] = kwargs.get("cwd")
        calls["env_pwd"] = (kwargs.get("env") or {}).get("PWD")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"sessions":[]}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    client = WxCliClient(bin_path="/bin/echo", timeout=1)
    result = client.probe()

    assert result["ok"] is True
    assert calls["cwd"] == str(tmp_path / ".wx-cli")
    assert calls["env_pwd"] == str(tmp_path / ".wx-cli")


def test_wx_cli_probe_reports_missing_init_config(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    client = WxCliClient(bin_path="/bin/echo", timeout=1)
    result = client.probe()

    assert result["ok"] is False
    assert str(tmp_path / ".wx-cli" / "config.json") in result["error"]
    assert result["config_path"] == str(tmp_path / ".wx-cli" / "config.json")


def test_wx_cli_probe_reports_empty_key_store(monkeypatch, tmp_path):
    work_dir = tmp_path / ".wx-cli"
    work_dir.mkdir()
    (work_dir / "config.json").write_text('{"db_dir":"/tmp/wechat"}', encoding="utf-8")
    (work_dir / "all_keys.json").write_text("{}", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout='{"error":"无法解密 session.db"}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    client = WxCliClient(bin_path="/bin/echo", timeout=1)
    result = client.probe()

    assert result["ok"] is False
    assert result["key_count"] == 0
    assert "0 个" in result["error"]
    assert "session.db" in result["error"]
