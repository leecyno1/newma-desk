from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_no_human_video_standard_defaults_to_horizontal_and_keeps_adaptations() -> None:
    standard = (ROOT / "docs/technical/no-human-square-video-production-standard.md").read_text(encoding="utf-8")
    sop = (ROOT / "skills/dasheng-media-sop/SKILL.md").read_text(encoding="utf-8")
    bridge = (ROOT / "skills/dasheng-html-video-bridge/SKILL.md").read_text(encoding="utf-8")
    explainer = (ROOT / "skills/dasheng-video-explainer-html/SKILL.md").read_text(encoding="utf-8")

    assert "1920x1080" in standard
    assert "1080x1080" in standard
    assert "1080x1920" in standard
    assert "live HTML Video" in standard
    assert "Remotion" in standard
    assert "/v1/v1/" in standard
    assert "no-human-square-video-production-standard.md" in sop
    assert "no-human-square-video-production-standard.md" in bridge
    assert "no-human-square-video-production-standard.md" in explainer
