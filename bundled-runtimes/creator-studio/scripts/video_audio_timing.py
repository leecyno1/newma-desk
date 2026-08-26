#!/usr/bin/env python3
from __future__ import annotations

from typing import Any


def semantic_tail_allowance(scene: dict[str, Any]) -> float:
    beat = str(scene.get("beat_class") or "")
    if beat == "recap":
        return 0.60
    if beat == "chapter":
        return 0.50
    if beat.startswith("evidence"):
        return 0.45
    return 0.35


def capped_scene_duration(
    scene: dict[str, Any],
    *,
    audio_duration: float,
    trailing_silence: float,
) -> float:
    allowance = semantic_tail_allowance(scene)
    excess_silence = max(0.0, trailing_silence - allowance)
    duration = max(0.6, audio_duration - excess_silence)
    minimum = float(scene.get("minimum_duration_sec") or 0)
    return round(max(duration, minimum), 3)
