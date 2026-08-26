from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import settings
from .media_collector_store import get_collector_status


_RUN_LOCK = threading.Lock()
_LAST_RUN: dict[str, Any] | None = None
_CURRENT_RUN: dict[str, Any] | None = None


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _collector_dir() -> Path:
    return _project_root() / "media-collector"


def _collector_data_dir() -> Path:
    env = os.getenv("COLLECTOR_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (_project_root() / "data").resolve()


def _runs_dir() -> Path:
    path = _collector_data_dir() / "collector_runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _last_run_path() -> Path:
    return _runs_dir() / "last.json"


def _current_run_path() -> Path:
    return _runs_dir() / "current.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, limit: int = 4000) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[-limit:]


def _script_timeout(timeout_seconds: int | None = None) -> int:
    raw = timeout_seconds if timeout_seconds is not None else settings.__dict__.get("MEDIA_COLLECTOR_TIMEOUT_SECONDS", 240)
    try:
        return max(30, min(1800, int(raw or 240)))
    except Exception:
        return 240


def _run_script(
    name: str,
    script: str,
    *,
    timeout_seconds: int,
    pretty: bool = False,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    collector_dir = _collector_dir()
    script_path = collector_dir / script
    if not script_path.exists():
        return {
            "name": name,
            "ok": False,
            "returncode": 127,
            "error": f"脚本不存在: {script_path}",
            "started_at": _utc_now(),
            "finished_at": _utc_now(),
        }

    started_at = _utc_now()
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if env_overrides:
        env.update(env_overrides)
    args = ["bash", str(script_path)]
    if pretty:
        args.append("--pretty")

    try:
        completed = subprocess.run(
            args,
            cwd=str(collector_dir),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "name": name,
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "stdout": _truncate(completed.stdout),
            "stderr": _truncate(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "ok": False,
            "returncode": 124,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "error": f"采集超时（{timeout_seconds}s）",
            "stdout": _truncate(exc.stdout or ""),
            "stderr": _truncate(exc.stderr or ""),
        }
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "returncode": 1,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "error": str(exc),
        }


def _load_last_run() -> dict[str, Any] | None:
    global _LAST_RUN
    if _LAST_RUN:
        return dict(_LAST_RUN)
    path = _last_run_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _LAST_RUN = data
            return dict(data)
    except Exception:
        return None
    return None


def _set_current_run(payload: dict[str, Any] | None) -> None:
    global _CURRENT_RUN
    _CURRENT_RUN = dict(payload) if isinstance(payload, dict) else None
    path = _current_run_path()
    try:
        if _CURRENT_RUN:
            path.write_text(json.dumps(_CURRENT_RUN, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    except Exception:
        pass


def _load_current_run() -> dict[str, Any] | None:
    if _CURRENT_RUN:
        return dict(_CURRENT_RUN)
    path = _current_run_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else None
    except Exception:
        return None


def get_media_collector_run_state() -> dict[str, Any]:
    last = _load_last_run()
    current = _load_current_run()
    running = _RUN_LOCK.locked() or bool(current and current.get("running"))
    return {
        "running": running,
        "current_run": current if running else None,
        "last_run": last,
        "status": get_collector_status(),
    }


def run_media_collector_once(
    *,
    hot: bool = True,
    search: bool = True,
    authors: bool = True,
    timeout_seconds: int | None = None,
    pretty: bool = False,
) -> dict[str, Any]:
    global _LAST_RUN
    if not _RUN_LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "running": True,
            "message": "自媒体采集正在运行，请稍后查看结果",
            "last_run": _load_last_run(),
            "status": get_collector_status(),
        }

    started_at = _utc_now()
    timeout = _script_timeout(timeout_seconds)
    try:
        data_dir = _collector_data_dir()
        tasks: list[tuple[str, str, dict[str, str]]] = []
        if hot:
            tasks.append(("hot", "collect.sh", {"OUTPUT_BASE": str(data_dir / "hot")}))
        if search:
            tasks.append(("search", "batch_search.sh", {"OUTPUT_BASE": str(data_dir / "search")}))
        if authors:
            tasks.append(("authors", "batch_author_search.sh", {"OUTPUT_BASE": str(data_dir / "authors")}))

        _set_current_run({
            "running": True,
            "started_at": started_at,
            "tasks": [name for name, _, _ in tasks],
            "message": "自媒体采集中",
        })
        results = [
            _run_script(name, script, timeout_seconds=timeout, pretty=pretty, env_overrides=env_overrides)
            for name, script, env_overrides in tasks
        ]
        ok = all(bool(item.get("ok")) for item in results) if results else True
        payload: dict[str, Any] = {
            "ok": ok,
            "running": False,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "tasks": [name for name, _, _ in tasks],
            "results": results,
            "status": get_collector_status(),
        }
        _LAST_RUN = payload
        _last_run_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _set_current_run(None)
        return payload
    finally:
        _set_current_run(None)
        _RUN_LOCK.release()


def start_media_collector_job(
    *,
    hot: bool = True,
    search: bool = True,
    authors: bool = True,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    if bool(get_media_collector_run_state().get("running")):
        return get_media_collector_run_state() | {
            "ok": False,
            "running": True,
            "accepted": False,
            "message": "自媒体采集正在运行，请稍后查看结果",
        }

    started_at = _utc_now()
    tasks = [name for name, enabled in (("hot", hot), ("search", search), ("authors", authors)) if enabled]
    _set_current_run({
        "running": True,
        "started_at": started_at,
        "tasks": tasks,
        "message": "自媒体采集已进入后台",
    })

    thread = threading.Thread(
        target=run_media_collector_once,
        kwargs={
            "hot": hot,
            "search": search,
            "authors": authors,
            "timeout_seconds": timeout_seconds,
        },
        name="media-collector-refresh",
        daemon=True,
    )
    thread.start()
    return get_media_collector_run_state() | {
        "ok": True,
        "running": True,
        "accepted": True,
        "message": "自媒体采集已启动，完成后会自动读取最新数据",
    }
