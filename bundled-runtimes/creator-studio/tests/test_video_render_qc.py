import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import video_render_qc
from video_render_qc import find_luma_pulses


def make_video(path: Path, color: str, duration: float = 1.0) -> None:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=320x180:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_render_qc_rejects_sustained_dark_frame(tmp_path):
    video = tmp_path / "black.mp4"
    report_path = tmp_path / "report.json"
    make_video(video, "black")

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/video_render_qc.py"),
            "--video",
            str(video),
            "--skip-loudness",
            "--output",
            str(report_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1, proc.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "dark_frame_run" in {item["code"] for item in report["failures"]}


def test_render_qc_rejects_scene_plan_duration_drift(tmp_path):
    video = tmp_path / "blue.mp4"
    scene_plan = tmp_path / "scene_plan.json"
    report_path = tmp_path / "report.json"
    make_video(video, "blue")
    scene_plan.write_text(
        json.dumps(
            {
                "lane": "talking_head_video",
                "timeline_alignment": {"mode": "roughcut_edl"},
                "scenes": [
                    {"id": "s1", "start_sec": 0, "end_sec": 2, "duration_sec": 2},
                ],
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/video_render_qc.py"),
            "--video",
            str(video),
            "--scene-plan",
            str(scene_plan),
            "--skip-loudness",
            "--output",
            str(report_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1, proc.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "timeline_duration_drift" in {item["code"] for item in report["failures"]}


def test_luma_pulse_detector_finds_dim_entry_flash_but_not_stable_dark_scene():
    pulse_samples = [
        (0.0, 100.0),
        (0.125, 14.0),
        (0.25, 21.0),
        (0.375, 24.0),
        (0.5, 27.0),
        (0.625, 27.0),
    ]
    stable_dark_samples = [(index * 0.125, 27.0) for index in range(8)]

    assert len(find_luma_pulses(pulse_samples)) == 1
    assert find_luma_pulses(stable_dark_samples) == []


def test_flat_frame_detector_finds_blank_transition_but_not_intentional_flat_scene():
    assert hasattr(video_render_qc, "find_flat_frame_pulses")
    transition_samples = [
        {"time": 0.0, "ymin": 18.0, "ymax": 224.0},
        {"time": 0.125, "ymin": 234.0, "ymax": 234.0},
        {"time": 0.25, "ymin": 22.0, "ymax": 218.0},
    ]
    stable_flat_samples = [
        {"time": index * 0.125, "ymin": 234.0, "ymax": 234.0}
        for index in range(8)
    ]

    assert len(video_render_qc.find_flat_frame_pulses(transition_samples)) == 1
    assert video_render_qc.find_flat_frame_pulses(stable_flat_samples) == []


def test_visual_change_density_rejects_slow_template_slides_but_accepts_benchmark_pacing():
    assert hasattr(video_render_qc, "evaluate_visual_change_density")
    current = video_render_qc.evaluate_visual_change_density(
        duration_sec=36,
        change_times=[3.6, 18.0, 21.6, 25.2, 28.8, 32.4],
        minimum_per_minute=12,
    )
    benchmark = video_render_qc.evaluate_visual_change_density(
        duration_sec=36,
        change_times=[index * 1.2 for index in range(1, 29)],
        minimum_per_minute=12,
    )

    assert current["status"] == "fail"
    assert current["changes_per_minute"] == 10.0
    assert benchmark["status"] == "pass"
    assert benchmark["changes_per_minute"] > 40


def test_merge_change_times_deduplicates_cut_and_motion_events():
    merged = video_render_qc.merge_change_times([1.0, 5.0], [1.1, 3.0, 5.2])

    assert merged == [1.0, 3.0, 5.0]
