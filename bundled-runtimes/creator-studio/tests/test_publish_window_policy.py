from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from publish_window_policy import chrome_window_args, resolve_publish_window, window_environment


def test_publish_window_prefers_first_secondary_display():
    window = resolve_publish_window(
        screens=[
            {"index": 0, "x": 0, "y": 0, "width": 3440, "height": 1410},
            {"index": 1, "x": 1230, "y": -1117, "width": 1728, "height": 1085},
        ]
    )

    assert window["mode"] == "secondary_display"
    assert window["screen_index"] == 1
    assert window["width"] == 1180
    assert window["height"] == 780
    assert window["x"] == 1738
    assert window["y"] == -1077
    assert window["never_maximize"] is True


def test_publish_window_falls_back_to_small_primary_window():
    window = resolve_publish_window(
        screens=[{"index": 0, "x": 0, "y": 0, "width": 1440, "height": 900}]
    )

    assert window["mode"] == "primary_display_fallback"
    assert window["width"] == 1180
    assert window["height"] == 780
    assert window["x"] == 220
    assert window["y"] == 40


def test_publish_window_exports_browser_flags_and_environment():
    window = resolve_publish_window(
        screens=[{"index": 0, "x": 10, "y": 20, "width": 1600, "height": 1000}]
    )

    assert chrome_window_args(window) == ["--window-size=1180,780", "--window-position=390,60"]
    environment = window_environment(window)
    assert environment["DASHENG_PUBLISH_WINDOW_WIDTH"] == "1180"
    assert environment["DASHENG_PUBLISH_WINDOW_HEIGHT"] == "780"
    assert environment["DASHENG_PUBLISH_WINDOW_TARGET"] == "primary_display_fallback"
