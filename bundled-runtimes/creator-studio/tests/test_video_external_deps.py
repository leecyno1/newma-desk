import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from ensure_video_external_deps import DEPENDENCIES, inspect_dependency


def test_video_external_dependencies_are_unlocked():
    assert DEPENDENCIES["html-video"].repo == "https://github.com/nexu-io/html-video.git"
    assert DEPENDENCIES["html-anything"].repo == "https://github.com/nexu-io/html-anything.git"
    assert "palmier-pro" not in DEPENDENCIES
    assert "vox-director" not in DEPENDENCIES
    for spec in DEPENDENCIES.values():
        assert "commit" not in spec.__dict__
        assert "tag" not in spec.__dict__
        assert "branch" not in spec.__dict__


def test_inspect_dependency_uses_env_path_without_installing(monkeypatch, tmp_path):
    dep_root = tmp_path / "html-video"
    dep_root.mkdir()
    (dep_root / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@9.15.0"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HTML_VIDEO_ROOT", str(dep_root))

    result = inspect_dependency(DEPENDENCIES["html-video"])

    assert result["status"] == "ready"
    assert result["package_manager"] == "pnpm"
    assert result["path"] == str(dep_root.resolve())
    assert result["motion_libraries"]["required"] == ["gsap", "lottie-web"]
    assert result["motion_libraries"]["ready"] is False
