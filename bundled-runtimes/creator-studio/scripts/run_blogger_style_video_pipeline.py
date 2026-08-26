#!/usr/bin/env python3
"""端到端运行：学习博主风格 -> 应用风格 -> 渲染视频。

Example:
    python3 scripts/run_blogger_style_video_pipeline.py \
        --style-profile ~/Desktop/自媒体创作/00_范式学习/视频训练/xiaolin_finance_v1/style_profile.json \
        --storyboard ~/Desktop/自媒体创作/2026-06-24_xxx/04_转写/storyboard.json \
        --article-html ~/Desktop/自媒体创作/2026-06-24_xxx/03_初稿/article.html \
        --output-dir ~/Desktop/自媒体创作/2026-06-24_xxx/04_转写/blogger_style_video \
        --with-voice
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from canonical_workflow import ensure_runtime_output_dir  # noqa: E402


class PipelineError(RuntimeError):
    pass


def run_py(script: str, *args: str) -> dict[str, Any]:
    cmd = [sys.executable, str(_PROJECT_ROOT / script), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise PipelineError(f"{script} failed:\n{proc.stderr or proc.stdout}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"raw_output": proc.stdout, "status": "ok"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="端到端：应用博主风格并渲染视频")
    parser.add_argument("--style-profile", required=True)
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--article-html", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--template-router", default=str(_PROJECT_ROOT / "configs" / "video" / "html_anything_template_router.json"))
    parser.add_argument("--with-voice", action="store_true", help="生成配音（默认静音预览）")
    parser.add_argument("--voice", default="Chinese (Mandarin)_Radio_Host")
    parser.add_argument("--limit", type=int, help="仅渲染前 N 个场景用于快速测试")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = ensure_runtime_output_dir(Path(args.output_dir).expanduser().resolve(), label="blogger style video output_dir")
    output_dir.mkdir(parents=True, exist_ok=True)

    timeline_path = output_dir / "timeline_style.json"
    scene_pack_dir = output_dir / "scene_pack"
    video_dir = output_dir / "video"

    # Step 1: apply style to timeline
    print("[step 1/3] 应用博主风格到 timeline...")
    apply_result = run_py(
        "scripts/apply_blogger_style_to_timeline.py",
        "--style-profile", str(Path(args.style_profile).expanduser().resolve()),
        "--storyboard", str(Path(args.storyboard).expanduser().resolve()),
        "--article-html", str(Path(args.article_html).expanduser().resolve()),
        "--template-router", str(Path(args.template_router).expanduser().resolve()),
        "--output-timeline", str(timeline_path),
    )
    print(json.dumps(apply_result, ensure_ascii=False, indent=2))

    # Step 2: render timeline to HTML scene pack
    print("[step 2/3] 渲染 HTML Anything 场景包...")
    pack_result = run_py(
        "scripts/render_html_anything_timeline_pack.py",
        "--timeline", str(timeline_path),
        "--output-dir", str(scene_pack_dir),
    )
    print(json.dumps(pack_result, ensure_ascii=False, indent=2))

    # Step 3: record live HTML animation (+ optional voice)
    print("[step 3/3] 录制 HTML 动画并合成最终视频...")
    manifest_path = scene_pack_dir / "scene_pack_manifest.json"
    voice_args: list[str] = []
    if args.with_voice:
        voice_args.extend(["--with-voice", "--voice", args.voice])
    if args.limit:
        voice_args.extend(["--limit", str(args.limit)])

    render_result = run_py(
        "scripts/render_html_anything_scene_pack_animated.py",
        "--manifest", str(manifest_path),
        "--output-dir", str(video_dir),
        *voice_args,
    )
    print(json.dumps(render_result, ensure_ascii=False, indent=2))

    final_report = {
        "status": "ok",
        "output_dir": str(output_dir),
        "timeline": str(timeline_path),
        "scene_pack_dir": str(scene_pack_dir),
        "video_dir": str(video_dir),
        "style_applied": apply_result.get("style_id"),
        "talking_head_policy": "blank_placeholder_for_user_footage",
    }
    report_path = output_dir / "pipeline_report.json"
    report_path.write_text(json.dumps(final_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[done] 报告已保存: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
