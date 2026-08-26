from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..config import settings


@dataclass(frozen=True)
class WxCliCommandResult:
    ok: bool
    payload: dict[str, Any]
    stdout: str
    stderr: str


class WxCliClient:
    """Thin wrapper around jackwener/wx-cli.

    wx-cli exposes a local CLI/daemon interface rather than an HTTP API.
    Deepsee keeps this wrapper isolated so the rest of the sync pipeline receives normalized dicts.
    """

    def __init__(self, bin_path: str | None = None, timeout: int | None = None):
        self.bin_path = self.resolve_binary(bin_path)
        self.timeout = int(timeout or settings.WX_CLI_TIMEOUT_SECONDS or 45)
        self.work_dir = Path.home() / ".wx-cli"

    @staticmethod
    def resolve_binary(explicit: str | None = None) -> str:
        candidates: list[str] = []
        if explicit or settings.WX_CLI_BIN:
            candidates.append(str(explicit or settings.WX_CLI_BIN))
        root = Path(__file__).resolve().parents[2]
        candidates.extend(
            [
                str(root / ".local" / "wechat-local" / "wx_cli" / "wx"),
                str(root / ".local" / "wechat-local" / "wx_cli" / "wx.exe"),
                str(root / ".local" / "wechat-local" / "wx_cli" / "wx-windows-x86_64.exe"),
                str(root / ".local" / "wechat-local" / "wx_cli" / "wx-macos-arm64"),
                str(root / ".local" / "wechat-local" / "wx_cli" / "wx-macos-x86_64"),
            ]
        )
        marker = root / ".local" / "wechat-local" / "wx_cli" / "BIN_PATH"
        if marker.exists():
            try:
                candidates.insert(0, marker.read_text(encoding="utf-8").strip())
            except Exception:
                pass
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        found = shutil.which("wx") or shutil.which("wx.exe")
        if found:
            return found
        return str(explicit or settings.WX_CLI_BIN or "wx")

    def _run(self, args: list[str]) -> WxCliCommandResult:
        env = os.environ.copy()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        env["PWD"] = str(self.work_dir)
        proc = subprocess.run(
            [self.bin_path, *args],
            cwd=str(self.work_dir),
            capture_output=True,
            text=True,
            timeout=self.timeout,
            env=env,
            check=False,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        payload: dict[str, Any] = {}
        if stdout:
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, dict):
                    payload = parsed
                elif isinstance(parsed, list):
                    payload = {"results": parsed}
            except Exception:
                payload = {"raw": stdout}
        ok = proc.returncode == 0 and bool(payload.get("ok", True))
        return WxCliCommandResult(ok=ok, payload=payload, stdout=stdout, stderr=stderr)

    def _config_path(self) -> Path:
        return self.work_dir / "config.json"

    def _all_keys_path(self) -> Path:
        return self.work_dir / "all_keys.json"

    def _all_keys_count(self) -> int | None:
        path = self._all_keys_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if isinstance(data, dict):
            return len(data)
        if isinstance(data, list):
            return len(data)
        return None

    def _diagnostic_error(self, fallback: str | None = None) -> str:
        config_path = self._config_path()
        if not config_path.exists():
            return f"wx-cli 尚未完成 init，缺少 {config_path}"
        key_count = self._all_keys_count()
        if key_count == 0:
            return "wx-cli init 已完成，但 all_keys.json 没有可用数据库密钥（0 个），因此无法解密 session.db"
        if key_count is None and not self._all_keys_path().exists():
            return f"wx-cli init 未生成密钥文件，缺少 {self._all_keys_path()}"
        if fallback:
            return fallback
        return "wx-cli unavailable"

    def probe(self) -> dict[str, Any]:
        try:
            result = self._run(["sessions", "-n", "1", "--json"])
            error = result.payload.get("error") or result.stderr or None
            return {
                "ok": result.ok,
                "bin": self.bin_path,
                "work_dir": str(self.work_dir),
                "config_path": str(self._config_path()),
                "all_keys_path": str(self._all_keys_path()),
                "key_count": self._all_keys_count(),
                "error": None if result.ok else self._diagnostic_error(error),
                "payload": result.payload if result.ok else None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "bin": self.bin_path,
                "work_dir": str(self.work_dir),
                "config_path": str(self._config_path()),
                "all_keys_path": str(self._all_keys_path()),
                "key_count": self._all_keys_count(),
                "error": self._diagnostic_error(str(exc)),
            }

    def sessions(self, limit: int | None = None) -> list[dict[str, Any]]:
        result = self._run(["sessions", "-n", str(limit or settings.WX_CLI_SESSION_LIMIT or 200), "--json"])
        if not result.ok:
            raise RuntimeError(result.payload.get("error") or result.stderr or "wx-cli sessions failed")
        data = result.payload
        sessions = data.get("sessions") or data.get("results") or []
        return [item for item in sessions if isinstance(item, dict)]

    def history(
        self,
        chat: str,
        *,
        since: date | str | None = None,
        until: date | str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, Any]:
        args = ["history", chat, "-n", str(limit), "--offset", str(offset), "--json"]
        if since:
            args.extend(["--since", since.isoformat() if hasattr(since, "isoformat") else str(since)])
        if until:
            args.extend(["--until", until.isoformat() if hasattr(until, "isoformat") else str(until)])
        result = self._run(args)
        if not result.ok:
            raise RuntimeError(result.payload.get("error") or result.stderr or f"wx-cli history failed: {chat}")
        return result.payload

    @staticmethod
    def parse_timestamp(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value))
            except Exception:
                return None
        text = str(value).strip()
        if not text:
            return None
        try:
            if text.isdigit():
                return datetime.fromtimestamp(float(text))
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except Exception:
            return None
