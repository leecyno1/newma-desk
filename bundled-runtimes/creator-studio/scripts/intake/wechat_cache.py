"""微信采集缓存读写模块。

将微信相关缓存逻辑从 run_stage1_intake.py 中独立出来，降低主文件体积并便于测试。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    """自动向上查找包含 CLAUDE.md 的目录作为项目根目录。"""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists():
            return parent
    raise RuntimeError("Cannot detect project root: CLAUDE.md not found")


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(ts: datetime) -> str:
    return ts.isoformat()


def _dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_cache_dir(root: Path | None = None) -> Path:
    """获取缓存目录。"""
    cache_dir = (root or _project_root()) / ".cache" / "intake"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def save_wechat_cache(
    channels: dict[str, Any],
    latest_articles: dict[str, Any],
    curated_articles: dict[str, dict[str, Any]],
    root: Path | None = None,
) -> None:
    """保存微信采集缓存。"""
    try:
        cache_dir = _get_cache_dir(root)
        cache_data = {
            "timestamp": _iso(_now()),
            "channels": channels,
            "latest_articles": latest_articles,
            "curated_articles": curated_articles,
        }
        _dump_json(cache_dir / "wechat_last_success.json", cache_data)
    except Exception as e:
        print(f"Warning: Failed to save wechat cache: {e}")


def load_wechat_cache(
    root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]] | None:
    """加载微信采集缓存；超过 7 天的缓存会被丢弃。"""
    try:
        cache_dir = _get_cache_dir(root)
        cache_file = cache_dir / "wechat_last_success.json"
        if not cache_file.exists():
            return None

        cache_data = json.loads(cache_file.read_text(encoding="utf-8"))

        cache_time = datetime.fromisoformat(cache_data.get("timestamp", ""))
        if (_now() - cache_time).days > 7:
            print("Warning: Wechat cache is older than 7 days, ignoring")
            return None

        return (
            cache_data.get("channels", {"data": {"total": 0, "list": []}}),
            cache_data.get("latest_articles", {"data": {"total": 0, "list": []}}),
            cache_data.get("curated_articles", {}),
        )
    except Exception as e:
        print(f"Warning: Failed to load wechat cache: {e}")
        return None
