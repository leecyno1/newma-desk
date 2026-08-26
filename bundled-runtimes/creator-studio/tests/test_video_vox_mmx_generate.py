from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("video_vox_mmx_generate", ROOT / "scripts" / "video_vox_mmx_generate.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_normalize_base_url_removes_v1() -> None:
    assert MODULE.normalize_base_url("https://api.minimaxi.com/v1") == "https://api.minimaxi.com"


def test_review_gate_requires_explicit_approval() -> None:
    with pytest.raises(MODULE.GenerationError):
        MODULE.require_approved_review({"decision": "pending", "render_allowed": False})


def test_generate_command_uses_explicit_root_url(tmp_path: Path) -> None:
    command = MODULE.generate_command(
        base_url="https://api.minimaxi.com",
        model="MiniMax-Hailuo-2.3-Fast",
        image=tmp_path / "shot.png",
        prompt="restrained parallax",
        output=tmp_path / "shot.mp4",
    )
    assert command[:3] == ["mmx", "--base-url", "https://api.minimaxi.com"]
    assert "--download" in command
