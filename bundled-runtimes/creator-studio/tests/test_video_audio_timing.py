import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_audio_timing import capped_scene_duration, semantic_tail_allowance


def test_semantic_tail_allowance_varies_by_scene_role() -> None:
    assert semantic_tail_allowance({"beat_class": "logic"}) == 0.35
    assert semantic_tail_allowance({"beat_class": "evidence"}) == 0.45
    assert semantic_tail_allowance({"beat_class": "chapter"}) == 0.50
    assert semantic_tail_allowance({"beat_class": "recap"}) == 0.60


def test_caps_excessive_trailing_silence() -> None:
    scene = {"beat_class": "evidence"}
    assert capped_scene_duration(scene, audio_duration=16.0, trailing_silence=6.0) == 10.45


def test_respects_explicit_minimum_visual_duration() -> None:
    scene = {"beat_class": "chapter", "minimum_duration_sec": 3.3}
    assert capped_scene_duration(scene, audio_duration=2.7, trailing_silence=0.5) == 3.3
