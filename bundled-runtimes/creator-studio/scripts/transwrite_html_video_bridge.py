#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BridgeError(RuntimeError):
    pass


SUPPORTED_VIDEO_LANES = {"talking_head_video", "explainer_html_video", "vox_explainer_video", "digital_human_video", "commercial_promo_video"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_plan(video_manifest_path: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    manifest = read_json(video_manifest_path)
    if not isinstance(manifest, dict) or manifest.get("lane") not in SUPPORTED_VIDEO_LANES:
        raise BridgeError(f"不是受支持的视频 lane manifest：{video_manifest_path}")
    plan_file = manifest.get("html_video_project_plan")
    if not plan_file:
        raise BridgeError("video lane manifest 缺少 html_video_project_plan")
    plan_path = Path(str(plan_file)).expanduser().resolve()
    if not plan_path.exists():
        raise BridgeError(f"html_video_project_plan 不存在：{plan_path}")
    plan = read_json(plan_path)
    if not isinstance(plan, dict) or plan.get("renderer") != "html-video":
        raise BridgeError(f"html_video_project_plan 格式无效：{plan_path}")
    return manifest, plan_path, plan


def run_cli(cli: str, html_video_root: str, args: list[str]) -> dict[str, Any]:
    command = ["node", cli, *args, "--cwd", html_video_root]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise BridgeError(proc.stderr or proc.stdout or f"html-video command failed: {' '.join(command)}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BridgeError(f"html-video 输出不是 JSON：{proc.stdout[:500]}") from exc
    if isinstance(payload, dict) and payload.get("status") not in (None, "ok"):
        raise BridgeError(f"html-video 返回异常：{payload}")
    return payload


def create_project(plan: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    cli = str(plan["html_video_cli"])
    root = str(plan["html_video_root"])
    vars_file = str(plan["vars_file"])
    template_id = str(plan["template_id"])
    if project_id:
        created = {"status": "ok", "project_id": project_id, "reused": True}
    else:
        created = run_cli(
            cli,
            root,
            [
                "project-create",
                "--name",
                str(plan["project_name"]),
                "--intent",
                str(plan["title"]),
                "--aspect",
                str(plan["aspect"]),
            ],
        )
        project_id = str(created.get("project_id") or "")
    if not project_id:
        raise BridgeError(f"无法取得 html-video project_id：{created}")
    templated = run_cli(cli, root, ["project-set-template", project_id, "--template", template_id])
    variables = run_cli(cli, root, ["project-set-vars", project_id, "--vars-file", vars_file])
    preview = run_cli(cli, root, ["project-preview", project_id])
    return {
        "project_id": project_id,
        "created": created,
        "templated": templated,
        "variables": variables,
        "preview": preview,
    }


def render_project(plan: dict[str, Any], project_id: str) -> dict[str, Any]:
    cli = str(plan["html_video_cli"])
    root = str(plan["html_video_root"])
    output = Path(str(plan["expected_output"])).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = run_cli(cli, root, ["project-render", project_id, "--output", str(output)])
    return {"project_id": project_id, "rendered": rendered, "output": str(output)}


def update_video_manifest(video_manifest_path: Path, updates: dict[str, Any]) -> None:
    manifest = read_json(video_manifest_path)
    if not isinstance(manifest, dict):
        return
    manifest.update(updates)
    write_json(video_manifest_path, manifest)


def build_bridge_result(
    *,
    video_manifest_path: Path,
    execute: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    manifest, plan_path, plan = load_plan(video_manifest_path)
    result: dict[str, Any] = {
        "status": "planned",
        "created_at": now_iso(),
        "video_manifest": str(video_manifest_path.resolve()),
        "plan_file": str(plan_path),
        "plan": plan,
        "execute": execute,
        "topic_id": manifest.get("topic_id"),
    }
    if execute in {"create", "render"}:
        created = create_project(plan, project_id=project_id)
        result["status"] = "previewed"
        result["html_video_project"] = created
        update_video_manifest(
            video_manifest_path,
            {
                "status": "previewed_in_html_video",
                "html_video_project_id": created["project_id"],
                "html_video_preview": created.get("preview", {}).get("html_path"),
            },
        )
    if execute == "render":
        active_project_id = str(result["html_video_project"]["project_id"])
        rendered = render_project(plan, active_project_id)
        result["status"] = "scene_assets_rendered"
        result["html_video_render"] = rendered
        update_video_manifest(
            video_manifest_path,
            {
                "status": "scene_assets_rendered",
                "html_video_project_id": active_project_id,
                "html_video_scene_render": rendered["output"],
                "next_step": "Compose scene assets on the Remotion master timeline, then run full QC.",
            },
        )
    output_path = video_manifest_path.parent / "html_video_execution.json"
    write_json(output_path, result)
    result["execution_file"] = str(output_path.resolve())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or render html-video projects from Newma transwrite manifests.")
    parser.add_argument("--video-manifest", required=True)
    parser.add_argument("--execute", choices=["plan", "create", "render"], default="plan")
    parser.add_argument("--project-id", help="Reuse an existing html-video project id.")
    args = parser.parse_args()
    result = build_bridge_result(
        video_manifest_path=Path(args.video_manifest).expanduser().resolve(),
        execute=args.execute,
        project_id=args.project_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
