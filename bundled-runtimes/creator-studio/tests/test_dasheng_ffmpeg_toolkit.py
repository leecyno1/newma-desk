import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "skills" / "dasheng-ffmpeg-toolkit" / "scripts" / "ffmpeg_toolkit.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_transcode_dry_run_uses_argument_array(tmp_path):
    source = tmp_path / "source clip.mov"
    source.write_bytes(b"not-media-needed-for-dry-run")
    output = tmp_path / "render" / "final clip.mp4"

    result = run_tool("transcode", "--input", str(source), "--output", str(output), "--dry-run")

    assert result.returncode == 0, result.stderr
    command = json.loads(result.stdout)
    assert command[-1] == str(output.resolve())
    assert str(source.resolve()) in command
    assert "libx264" in command


def test_mutating_command_refuses_existing_output(tmp_path):
    source = tmp_path / "source.mov"
    source.write_bytes(b"source")
    output = tmp_path / "final.mp4"
    output.write_bytes(b"existing")

    result = run_tool("clip", "--input", str(source), "--output", str(output), "--start", "0", "--duration", "1", "--dry-run")

    assert result.returncode != 0
    assert "output exists" in result.stderr


def test_output_inside_skill_root_is_rejected(tmp_path):
    source = tmp_path / "source.mov"
    source.write_bytes(b"source")
    forbidden = ROOT / "skills" / "dasheng-ffmpeg-toolkit" / "generated.mp4"

    result = run_tool("transcode", "--input", str(source), "--output", str(forbidden), "--dry-run")

    assert result.returncode != 0
    assert "forbidden root" in result.stderr


def test_clip_end_is_converted_to_duration(tmp_path):
    source = tmp_path / "source.mov"
    source.write_bytes(b"source")
    output = tmp_path / "clip.mp4"

    result = run_tool("clip", "--input", str(source), "--output", str(output), "--start", "2.5", "--end", "5", "--dry-run")

    assert result.returncode == 0, result.stderr
    command = json.loads(result.stdout)
    assert command[command.index("-t") + 1] == "2.5"
