import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "build_stage4_transwrite",
    ROOT / "scripts" / "build_stage4_transwrite.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def decision_row(podcast: dict | None = None) -> dict:
    row = {
        "topic_id": "topic-demo",
        "lanes": ["wechat_article", "podcast"],
    }
    if podcast is not None:
        row["podcast"] = podcast
    return {"topics": [row]}


def test_podcast_lane_is_disabled_without_explicit_opt_in() -> None:
    rows = MODULE.normalize_topic_rows(decision_row({"provider": "minimax"}))
    assert rows[0]["lanes"] == ["wechat_article"]


def test_podcast_lane_requires_enabled_true() -> None:
    rows = MODULE.normalize_topic_rows(
        decision_row({"enabled": True, "provider": "minimax"})
    )
    assert rows[0]["lanes"] == ["wechat_article", "podcast"]
