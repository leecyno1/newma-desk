#!/usr/bin/env python3
from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from path_config import get_project_root


CONFIG_PATH = get_project_root() / "configs" / "publish" / "browser_profiles.json"
DEFAULT_POLICY = {
    "mode": "secondary_display_preferred",
    "width": 1180,
    "height": 780,
    "margin": 40,
    "anchor": "top_right",
    "launch_in_background": True,
    "never_maximize": True,
    "fallback": "primary_display_top_right_small_window",
}


def load_window_policy(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    policy = dict(DEFAULT_POLICY)
    if not config_path.exists():
        return policy
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    configured = payload.get("window_policy") or {}
    if isinstance(configured, dict):
        policy.update(configured)
    return policy


def discover_macos_screens() -> list[dict[str, int]]:
    if platform.system() != "Darwin":
        return []
    script = (
        'ObjC.import("AppKit"); '
        'JSON.stringify($.NSScreen.screens.js.map((s,i)=>{'
        'const f=s.visibleFrame; return {index:i,x:Number(f.origin.x),y:Number(f.origin.y),'
        'width:Number(f.size.width),height:Number(f.size.height)};}));'
    )
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if result.returncode != 0:
            return []
        rows = json.loads(result.stdout.strip() or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []
    screens = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            screens.append({key: int(row[key]) for key in ("index", "x", "y", "width", "height")})
        except (KeyError, TypeError, ValueError):
            continue
    return screens


def resolve_publish_window(
    policy: dict[str, Any] | None = None,
    *,
    screens: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    merged = dict(DEFAULT_POLICY)
    merged.update(policy or load_window_policy())
    available = list(discover_macos_screens() if screens is None else screens)
    if not available:
        available = [{"index": 0, "x": 0, "y": 0, "width": 1440, "height": 900}]

    target = available[1] if len(available) > 1 else available[0]
    margin = max(0, int(merged.get("margin") or 0))
    max_width = max(320, int(target["width"]) - margin * 2)
    max_height = max(320, int(target["height"]) - margin * 2)
    width = min(max(640, int(merged.get("width") or 1180)), max_width)
    height = min(max(520, int(merged.get("height") or 780)), max_height)

    if str(merged.get("anchor") or "top_right") == "top_left":
        x = int(target["x"]) + margin
    else:
        x = int(target["x"]) + int(target["width"]) - width - margin
    y = int(target["y"]) + margin

    return {
        "mode": "secondary_display" if len(available) > 1 else "primary_display_fallback",
        "screen_index": int(target["index"]),
        "screen_count": len(available),
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "anchor": str(merged.get("anchor") or "top_right"),
        "launch_in_background": bool(merged.get("launch_in_background", True)),
        "never_maximize": bool(merged.get("never_maximize", True)),
        "fallback": str(merged.get("fallback") or DEFAULT_POLICY["fallback"]),
    }


def window_environment(window: dict[str, Any]) -> dict[str, str]:
    return {
        "DASHENG_PUBLISH_WINDOW_X": str(window["x"]),
        "DASHENG_PUBLISH_WINDOW_Y": str(window["y"]),
        "DASHENG_PUBLISH_WINDOW_WIDTH": str(window["width"]),
        "DASHENG_PUBLISH_WINDOW_HEIGHT": str(window["height"]),
        "DASHENG_PUBLISH_WINDOW_TARGET": str(window["mode"]),
    }


def chrome_window_args(window: dict[str, Any]) -> list[str]:
    return [
        f"--window-size={window['width']},{window['height']}",
        f"--window-position={window['x']},{window['y']}",
    ]
