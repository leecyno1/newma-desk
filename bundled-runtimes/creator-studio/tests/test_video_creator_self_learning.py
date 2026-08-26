import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_video_creator_self_learning import (  # noqa: E402
    build_paths,
    initial_state,
    load_config,
    safe_slug,
    select_candidates,
)
from install_video_self_learning_schedule import build_plist  # noqa: E402


CONFIG = PROJECT_ROOT / "configs" / "video" / "creator_learning_watchlist.json"


def test_watchlist_has_six_unique_bilibili_creators():
    config = load_config(CONFIG)
    creators = config["creators"]
    ids = [item["creator_id"] for item in creators]

    assert len(creators) == 6
    assert len(ids) == len(set(ids))
    assert all(item["platform"] == "bilibili" for item in creators)
    assert all(item["homepage"].endswith("/video") for item in creators)


def test_video_analysis_is_reserved_for_native_codex_review():
    config = load_config(CONFIG)
    agent = config["analysis"]["agent"]

    assert agent["provider"] == "codex-native"
    assert "command" not in agent
    assert "base_url" not in agent
    assert "text_model" not in agent


def test_bilibili_discovery_uses_persistent_browser_identity():
    config = load_config(CONFIG)
    discovery = config["discovery"]

    assert discovery["cookies_from_browser"] == "chrome"
    assert discovery["impersonate"].startswith("Chrome-")


def test_output_paths_keep_media_outside_repo(tmp_path):
    paths = build_paths(tmp_path / "自媒体创作" / "视频训练" / "每日博主自学习")

    assert "skills" not in str(paths["media_cache"])
    assert paths["notes"].is_relative_to(paths["root"])
    assert paths["profiles"].is_relative_to(paths["root"])


def test_first_run_baselines_without_heavy_analysis():
    state = initial_state()
    creator = {
        "creator_id": "1",
        "label": "demo",
        "homepage": "https://space.bilibili.com/1/video",
        "videos": {},
        "initialized_at": None,
    }
    discovered = [
        {"video_id": "BV1", "timestamp": 2},
        {"video_id": "BV0", "timestamp": 1},
    ]

    candidates, baselined = select_candidates(
        creator,
        discovered,
        bootstrap_mode="baseline_only",
        max_new=2,
        backfill_latest=0,
    )

    assert baselined is True
    assert candidates == []
    assert creator["videos"]["BV1"]["status"] == "baseline_seen"
    assert state["schema_version"] == "dasheng.video_creator_learning_state.v1"


def test_backfill_can_force_a_baselined_video():
    creator = {
        "creator_id": "1",
        "initialized_at": "2026-01-01T00:00:00+08:00",
        "videos": {"BV1": {"status": "baseline_seen"}},
    }
    discovered = [{"video_id": "BV1", "timestamp": 2}, {"video_id": "BV0", "timestamp": 1}]

    candidates, baselined = select_candidates(
        creator,
        discovered,
        bootstrap_mode="baseline_only",
        max_new=2,
        backfill_latest=1,
    )

    assert baselined is False
    assert [item["video_id"] for item in candidates] == ["BV1", "BV0"]


def test_schedule_is_daily_at_22_and_logs_outside_repo(tmp_path):
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    plist = build_plist(CONFIG, config, tmp_path / "每日博主自学习")

    assert plist["StartCalendarInterval"] == {"Hour": 22, "Minute": 0}
    assert plist["RunAtLoad"] is False
    assert str(tmp_path) in plist["StandardOutPath"]
    assert "run_video_creator_self_learning.py" in " ".join(plist["ProgramArguments"])


def test_safe_slug_preserves_chinese_and_removes_path_symbols():
    assert safe_slug("小Lin说 / 第一期") == "小Lin说_第一期"
