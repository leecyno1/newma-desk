import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_scene_plan_edl_mapping_drops_deleted_scenes_without_global_scaling(tmp_path):
    scene_plan = tmp_path / "scene_plan.json"
    edl = tmp_path / "roughcut_edl.json"
    output = tmp_path / "scene_plan.locked.json"
    write_json(
        scene_plan,
        {
            "schema_version": "dasheng.video.scene_plan.v1",
            "lane": "talking_head_video",
            "duration_estimate_sec": 25,
            "scenes": [
                {"id": "before", "title": "删除点之前", "start_sec": 2, "end_sec": 4, "duration_sec": 2, "beat_class": "claim"},
                {"id": "deleted", "title": "已经删除", "start_sec": 11, "end_sec": 14, "duration_sec": 3, "beat_class": "claim"},
                {"id": "tiny", "title": "删除边界残片", "start_sec": 14.9, "end_sec": 15.2, "duration_sec": 0.3, "beat_class": "claim"},
                {"id": "after", "title": "删除点之后", "start_sec": 16, "end_sec": 18, "duration_sec": 2, "beat_class": "claim"},
            ],
        },
    )
    write_json(
        edl,
        {
            "source": "raw.mp4",
            "segments": [
                {"old_start": 0, "old_end": 10},
                {"old_start": 15, "old_end": 25},
            ],
        },
    )

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/video_timeline_edl.py"),
            "--scene-plan",
            str(scene_plan),
            "--edl",
            str(edl),
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    locked = json.loads(output.read_text(encoding="utf-8"))
    assert [scene["id"] for scene in locked["scenes"]] == ["before", "after"]
    assert locked["scenes"][0]["start_sec"] == 2
    assert locked["scenes"][1]["start_sec"] == 11
    assert locked["scenes"][1]["end_sec"] == 13
    assert locked["duration_estimate_sec"] == 20
    assert locked["timeline_alignment"]["mode"] == "roughcut_edl"
    assert locked["timeline_alignment"]["dropped_scene_count"] == 2
    assert "time_scale" not in locked["timeline_alignment"]


def test_director_accepts_original_srt_plus_roughcut_edl(tmp_path):
    output_dir = tmp_path / "自媒体创作" / "director"
    srt = tmp_path / "original.srt"
    edl = tmp_path / "roughcut_edl.json"
    srt.write_text(
        """1
00:00:02,000 --> 00:00:04,000
删除点之前。

2
00:00:11,000 --> 00:00:14,000
这一句已经删除。

3
00:00:16,000 --> 00:00:18,000
删除点之后。
""",
        encoding="utf-8",
    )
    write_json(
        edl,
        {
            "segments": [
                {"old_start": 0, "old_end": 10},
                {"old_start": 15, "old_end": 25},
            ]
        },
    )

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/dasheng_video_director.py"),
            "--lane",
            "talking_head_video",
            "--srt",
            str(srt),
            "--roughcut-edl",
            str(edl),
            "--duration",
            "20",
            "--output-dir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    timeline = json.loads((output_dir / "talking_head_timeline.raw.json").read_text(encoding="utf-8"))
    assert timeline["timeline_alignment"]["mode"] == "roughcut_edl"
    assert timeline["timeline_alignment"]["dropped_caption_count"] == 1
    assert all("已经删除" not in segment["caption"] for segment in timeline["segments"])
    assert timeline["segments"][-1]["start"] == 11
