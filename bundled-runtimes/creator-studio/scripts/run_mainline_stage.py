#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from canonical_workflow import (
    WorkflowContractError,
    canonical_manifest_path,
    canonical_stage_dir,
    ensure_final_structure_gate,
    ensure_publish_decision_gate,
    ensure_selected_topics_gate,
    ensure_stage_manifest,
    ensure_transwrite_decision_gate,
)
from path_config import get_desktop_root
from project_run_manifest import (
    add_artifact,
    build_manifest,
    load_manifest,
    save_manifest,
    set_stage_status,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


PYTHON = sys.executable
MAINLINE_STAGES = {"intake", "brief", "draft", "transwrite", "publish", "postmortem"}


def default_project_manifest_path(run_id: str) -> Path:
    return get_desktop_root() / run_id / "project_run_manifest.json"


def run_command(args: list[str]) -> None:
    subprocess.run([PYTHON, *args], cwd=str(ROOT), check=True)


def run_json_command(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run([PYTHON, *args], cwd=str(ROOT), check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def resolve_project_manifest_path(args: argparse.Namespace, run_id: str | None) -> Path | None:
    explicit = getattr(args, "project_manifest", None)
    if explicit:
        return Path(explicit).expanduser().resolve()
    if run_id:
        return default_project_manifest_path(run_id).expanduser().resolve()
    return None


def load_or_create_project_manifest(
    *,
    args: argparse.Namespace,
    run_id: str | None,
    title: str | None = None,
    source_materials: list[dict[str, str]] | None = None,
) -> tuple[Path, dict[str, Any]] | tuple[None, None]:
    if getattr(args, "no_project_manifest", False):
        return None, None
    manifest_path = resolve_project_manifest_path(args, run_id)
    if not manifest_path:
        return None, None
    if manifest_path.exists():
        return manifest_path, load_manifest(manifest_path)
    if not run_id:
        return None, None
    manifest = build_manifest(
        title=title or run_id,
        pipeline_id="mainline",
        output_root=manifest_path.parent,
        source_materials=source_materials or [],
        run_id=run_id,
    )
    save_manifest(manifest, manifest_path)
    return manifest_path, manifest


def update_project_manifest_stage(
    *,
    args: argparse.Namespace,
    run_id: str | None,
    stage: str,
    status: str,
    artifact_paths: list[tuple[str, Path]] | None = None,
    notes: str = "",
    title: str | None = None,
    source_materials: list[dict[str, str]] | None = None,
) -> None:
    if stage not in MAINLINE_STAGES:
        return
    manifest_path, manifest = load_or_create_project_manifest(
        args=args,
        run_id=run_id,
        title=title,
        source_materials=source_materials,
    )
    if not manifest_path or not manifest:
        return
    set_stage_status(manifest, stage_name=stage, status=status, notes=notes)
    for artifact_type, artifact_path in artifact_paths or []:
        candidate = Path(artifact_path).expanduser().resolve()
        if candidate.exists():
            add_artifact(manifest, stage_name=stage, artifact_type=artifact_type, path=str(candidate))
    errors = validate_manifest(manifest)
    if errors:
        raise WorkflowContractError(f"project_run_manifest 校验失败：{json.dumps(errors, ensure_ascii=False)}")
    save_manifest(manifest, manifest_path)


def add_project_manifest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-manifest", help="显式指定 project_run_manifest.json；默认写入 ~/Desktop/自媒体创作/<run_id>/")
    parser.add_argument("--no-project-manifest", action="store_true", help="跳过 project_run_manifest 回写。")


def resolve_intake_inputs(run_id: str | None, intake_file: str | None) -> tuple[str, str]:
    if intake_file:
        resolved = Path(intake_file).expanduser().resolve()
        if not resolved.exists():
            raise WorkflowContractError(f"intake 文件不存在：{resolved}")
        if run_id:
            return str(resolved), run_id
        if resolved.parent.name == "raw":
            return str(resolved), resolved.parent.parent.name
        raise WorkflowContractError("提供 --input-file 时必须同时提供 --run-id，或使用 canonical raw/intake_records.json 路径。")
    if not run_id:
        raise WorkflowContractError("brief 阶段必须提供 --run-id 或 --input-file；不再允许猜最新目录。")
    intake_manifest = canonical_manifest_path("intake", run_id)
    ensure_stage_manifest(intake_manifest, "intake")
    intake_path = canonical_stage_dir("intake", run_id) / "raw" / "intake_records.json"
    if not intake_path.exists():
        raise WorkflowContractError(f"缺少 canonical intake_records.json：{intake_path}")
    return str(intake_path), run_id


def resolve_draft_inputs(run_id: str) -> tuple[str, str]:
    brief_manifest = canonical_manifest_path("brief", run_id)
    ensure_stage_manifest(brief_manifest, "brief")
    brief_dir = canonical_stage_dir("brief", run_id)
    selected_topics = brief_dir / "selected_topics.json"
    topic_cards = brief_dir / "topic_cards.json"
    ensure_selected_topics_gate(selected_topics)
    if not topic_cards.exists():
        raise WorkflowContractError(f"缺少 topic_cards.json：{topic_cards}")
    return str(selected_topics), str(topic_cards)


def resolve_transwrite_manifests(
    run_id: str | None,
    draft_manifest: str | None,
    transwrite_decision: str | None,
) -> tuple[str, str]:
    manifest = (
        Path(draft_manifest).expanduser().resolve()
        if draft_manifest
        else canonical_manifest_path("draft", run_id or "")
    )
    ensure_stage_manifest(manifest, "draft")
    ensure_final_structure_gate(manifest.parent / "final_structure_snapshot.json")
    decision_path = (
        Path(transwrite_decision).expanduser().resolve()
        if transwrite_decision
        else canonical_stage_dir("transwrite", run_id or "") / "transwrite_decision.json"
    )
    ensure_transwrite_decision_gate(decision_path)
    return str(manifest), str(decision_path)


def resolve_publish_manifests(
    run_id: str | None,
    transwrite_manifest: str | None,
    publish_decision: str | None,
) -> tuple[str, str]:
    manifest = (
        Path(transwrite_manifest).expanduser().resolve()
        if transwrite_manifest
        else canonical_manifest_path("transwrite", run_id or "")
    )
    ensure_stage_manifest(manifest, "transwrite")
    decision_path = (
        Path(publish_decision).expanduser().resolve()
        if publish_decision
        else canonical_stage_dir("publish", run_id or "") / "publish_decision.json"
    )
    ensure_publish_decision_gate(decision_path)
    return str(manifest), str(decision_path)


def resolve_postmortem_manifest(run_id: str | None, publish_manifest: str | None) -> str:
    manifest = (
        Path(publish_manifest).expanduser().resolve()
        if publish_manifest
        else canonical_manifest_path("publish", run_id or "")
    )
    ensure_stage_manifest(manifest, "publish")
    return str(manifest)


def build_publish_dry_run_report(publish_manifest: dict[str, Any]) -> dict[str, Any]:
    plans: list[dict[str, Any]] = []
    for pack in publish_manifest.get("channel_packs") or []:
        execution_request = pack.get("execution_request")
        if not execution_request:
            plans.append(
                {
                    "topic_id": pack.get("topic_id"),
                    "channel": pack.get("channel"),
                    "status": "blocked_missing_execution_request",
                }
            )
            continue
        plan = run_json_command(
            [
                str(ROOT / "scripts/prepare_publish_execution.py"),
                "--execution-request",
                str(execution_request),
            ]
        )
        plans.append(plan)
    blocked = [plan for plan in plans if str(plan.get("status", "")).startswith("blocked")]
    summary = summarize_publish_preflight(plans)
    return {
        "schema_version": "1.0",
        "run_id": publish_manifest.get("run_id"),
        "stage": "publish",
        "mode": "dry_run",
        "status": "blocked" if blocked else "ready_for_user_confirmation",
        "will_not_publish": True,
        "requires_user_confirmation": True,
        "publish_manifest": publish_manifest.get("manifest_file"),
        "summary": summary,
        "plans": plans,
        "blocked_count": len(blocked),
    }


def summarize_publish_preflight(plans: list[dict[str, Any]]) -> dict[str, Any]:
    channels = []
    for plan in plans:
        route_checks = plan.get("route_checks") or []
        missing_dependencies = [
            {
                "route": check.get("route"),
                "reason": check.get("reason"),
                "skill_path": check.get("skill_path"),
                "upstream_root": check.get("upstream_root"),
                "binary": check.get("binary"),
            }
            for check in route_checks
            if not check.get("available") and str(check.get("reason", "")).startswith("missing")
        ]
        selected_route = plan.get("selected_route")
        selected_type = str(plan.get("selected_route_type") or "")
        channels.append(
            {
                "topic_id": plan.get("topic_id"),
                "title": plan.get("title"),
                "channel": plan.get("channel"),
                "platform": plan.get("platform"),
                "status": plan.get("status"),
                "selected_route": selected_route,
                "selected_route_type": plan.get("selected_route_type"),
                "needs_browser_profile": selected_route == "browser-profile" or "browser" in selected_type,
                "manual_package_only": selected_route == "manual-package" or selected_type == "manual_package",
                "requires_user_confirmation": bool(plan.get("requires_user_confirmation", True)),
                "safe_executor_command": plan.get("safe_executor_command"),
                "confirmed_executor_command": plan.get("confirmed_executor_command"),
                "missing_dependencies": missing_dependencies,
            }
        )
    return {
        "total_channels": len(channels),
        "ready_count": sum(1 for item in channels if item["status"] == "ready_for_user_confirmation"),
        "blocked_count": sum(1 for item in channels if str(item["status"] or "").startswith("blocked")),
        "browser_profile_count": sum(1 for item in channels if item["needs_browser_profile"]),
        "manual_package_count": sum(1 for item in channels if item["manual_package_only"]),
        "missing_dependency_count": sum(len(item["missing_dependencies"]) for item in channels),
        "channels": channels,
    }


def render_publish_preflight_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        f"# Publish 发布前总预检｜{report.get('run_id') or ''}",
        "",
        "本报告由 `publish --dry-run` 生成，只做预检和路线选择，不会触发真实发布。",
        "",
        "## 总览",
        "",
        f"- 渠道数：`{summary.get('total_channels', 0)}`",
        f"- 可进入人工确认：`{summary.get('ready_count', 0)}`",
        f"- 阻塞：`{summary.get('blocked_count', 0)}`",
        f"- 需要持久化浏览器 Profile：`{summary.get('browser_profile_count', 0)}`",
        f"- 人工发布包：`{summary.get('manual_package_count', 0)}`",
        f"- 缺失依赖项：`{summary.get('missing_dependency_count', 0)}`",
        "",
        "## 渠道路线",
        "",
    ]
    for item in summary.get("channels") or []:
        lines.extend(
            [
                f"### {item.get('title') or item.get('topic_id')}｜{item.get('channel')}",
                "",
                f"- 平台：`{item.get('platform')}`",
                f"- 状态：`{item.get('status')}`",
                f"- 选中路线：`{item.get('selected_route') or 'none'}`",
                f"- 路线类型：`{item.get('selected_route_type') or 'none'}`",
                f"- 需要浏览器 Profile：`{item.get('needs_browser_profile')}`",
                f"- 仅人工包：`{item.get('manual_package_only')}`",
                f"- 需要人工确认：`{item.get('requires_user_confirmation')}`",
            ]
        )
        if item.get("safe_executor_command"):
            lines.extend(
                [
                    "",
                    "安全执行预演：",
                    "",
                    "```bash",
                    str(item["safe_executor_command"]),
                    "```",
                ]
            )
        if item.get("confirmed_executor_command"):
            lines.extend(
                [
                    "",
                    "确认后执行：",
                    "",
                    "```bash",
                    str(item["confirmed_executor_command"]),
                    "```",
                ]
            )
        missing = item.get("missing_dependencies") or []
        if missing:
            lines.extend(["", "缺失依赖："])
            for dep in missing:
                details = dep.get("skill_path") or dep.get("upstream_root") or dep.get("binary") or ""
                lines.append(f"- `{dep.get('route')}`：`{dep.get('reason')}` {details}".rstrip())
        lines.append("")
    lines.extend(
        [
            "## 安全边界",
            "",
            "- 本报告不会上传、发布或点击最终发布按钮。",
            "- 任何平台执行前都必须由用户确认账号、标题、封面、正文/视频和平台规则。",
            "- 浏览器型渠道只能使用 `configs/publish/browser_profiles.json` 配置的持久化 Profile。",
        ]
    )
    return "\n".join(lines)


def build_paradigm_command(args: argparse.Namespace) -> list[str]:
    if not args.run_id:
        raise WorkflowContractError("paradigm 阶段必须提供 --run-id。")
    if not args.samples:
        raise WorkflowContractError("paradigm 阶段必须至少提供一个样本文件。")
    command = [
        str(ROOT / "scripts/build_paradigm_profile.py"),
        *args.samples,
        "--run-id",
        args.run_id,
    ]
    if args.profile_name:
        command.extend(["--profile-name", args.profile_name])
    if args.sample_type:
        command.extend(["--sample-type", args.sample_type])
    for scenario in args.scenario:
        command.extend(["--scenario", scenario])
    for channel in args.channel:
        command.extend(["--channel", channel])
    if args.bind_style_dna:
        command.extend(["--bind-style-dna", args.bind_style_dna])
    if args.output_dir:
        command.extend(["--output-dir", args.output_dir])
    if args.no_ai:
        command.append("--no-ai")
    return command


def build_video_train_command(args: argparse.Namespace) -> list[str]:
    command = [
        str(ROOT / "scripts/learn_blogger_video_style_local.py"),
        "--video-dir",
        args.video_dir,
        "--style-id",
        args.style_id,
    ]
    if args.blogger_name:
        command.extend(["--blogger-name", args.blogger_name])
    if args.blogger_platform:
        command.extend(["--blogger-platform", args.blogger_platform])
    if args.output_dir:
        command.extend(["--output-dir", args.output_dir])
    if args.skip_aggregate:
        command.append("--skip-aggregate")
    return command


def build_video_self_learning_command(args: argparse.Namespace) -> list[str]:
    command = [
        str(ROOT / "scripts" / "run_video_creator_self_learning.py"),
        "--config",
        args.config,
    ]
    if args.output_root:
        command.extend(["--output-root", args.output_root])
    for creator_id in args.creator_id:
        command.extend(["--creator-id", creator_id])
    if args.discover_only:
        command.append("--discover-only")
    if args.dry_run:
        command.append("--dry-run")
    if args.backfill_latest:
        command.extend(["--backfill-latest", str(args.backfill_latest)])
    if args.skip_agent:
        command.append("--skip-agent")
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonical Newma Daily mainline stage runner")
    subparsers = parser.add_subparsers(dest="stage", required=True)

    intake = subparsers.add_parser("intake")
    intake.add_argument("--run-id")
    add_project_manifest_args(intake)

    paradigm = subparsers.add_parser("paradigm")
    paradigm.add_argument("samples", nargs="*")
    paradigm.add_argument("--run-id", required=True)
    paradigm.add_argument("--profile-name")
    paradigm.add_argument("--sample-type", default="standard_article")
    paradigm.add_argument("--scenario", action="append", default=[])
    paradigm.add_argument("--channel", action="append", default=[])
    paradigm.add_argument("--bind-style-dna", default="none")
    paradigm.add_argument("--output-dir")
    paradigm.add_argument("--no-ai", action="store_true")

    video_train = subparsers.add_parser("video-train")
    video_train.add_argument("--video-dir", required=True, help="包含样板视频的目录")
    video_train.add_argument("--style-id", required=True, help="输出风格 DNA 的唯一标识")
    video_train.add_argument("--blogger-name", default="")
    video_train.add_argument("--blogger-platform", default="")
    video_train.add_argument("--output-dir", help="默认：~/Desktop/自媒体创作/00_范式学习/视频训练")
    video_train.add_argument("--skip-aggregate", action="store_true")

    video_self_learn = subparsers.add_parser("video-self-learn")
    video_self_learn.add_argument(
        "--config",
        default=str(ROOT / "configs" / "video" / "creator_learning_watchlist.json"),
    )
    video_self_learn.add_argument("--output-root")
    video_self_learn.add_argument("--creator-id", action="append", default=[])
    video_self_learn.add_argument("--discover-only", action="store_true")
    video_self_learn.add_argument("--dry-run", action="store_true")
    video_self_learn.add_argument("--backfill-latest", type=int, default=0)
    video_self_learn.add_argument("--skip-agent", action="store_true")

    brief = subparsers.add_parser("brief")
    brief.add_argument("--run-id")
    brief.add_argument("--input-file")
    brief.add_argument("--manual-topic", action="append", default=[])
    brief.add_argument("--agent-cards-file")
    add_project_manifest_args(brief)

    draft = subparsers.add_parser("draft")
    draft.add_argument("--run-id", required=True)
    draft.add_argument("--output-dir")
    add_project_manifest_args(draft)

    transwrite = subparsers.add_parser("transwrite")
    transwrite.add_argument("--run-id")
    transwrite.add_argument("--draft-manifest")
    transwrite.add_argument("--transwrite-decision")
    transwrite.add_argument("--output-dir")
    add_project_manifest_args(transwrite)

    publish = subparsers.add_parser("publish")
    publish.add_argument("--run-id")
    publish.add_argument("--transwrite-manifest")
    publish.add_argument("--publish-decision")
    publish.add_argument("--output-dir")
    publish.add_argument("--dry-run", action="store_true", help="Build publish packs and prepare per-channel execution plans without publishing.")
    add_project_manifest_args(publish)

    postmortem = subparsers.add_parser("postmortem")
    postmortem.add_argument("--run-id")
    postmortem.add_argument("--publish-manifest")
    postmortem.add_argument("--require-publish-guard", action="store_true", help="Fail unless publish_manifest.publish_guard is present and passed.")
    add_project_manifest_args(postmortem)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--run-id")
    doctor.add_argument("--latest", action="store_true")
    doctor.add_argument("--strict", action="store_true")
    doctor.add_argument("--publish", action="store_true", help="Run publish route readiness doctor without publishing.")
    doctor.add_argument("--publish-manifest", help="Run publish batch guard against a publish_manifest.json without publishing.")
    doctor.add_argument("--channel", action="append", default=[], help="Publish channel to check with --publish; may be repeated.")
    doctor.add_argument("--check-auth", action="store_true", help="With --publish, validate registered CLI account sessions without publishing.")
    doctor.add_argument("--output-json", help="Optional publish doctor JSON report path.")
    doctor.add_argument("--output-md", help="Optional publish doctor Markdown report path.")
    doctor.add_argument("--fail-on-error", action="store_true", help="With --publish-manifest, exit non-zero when Publish Guard does not pass.")

    args = parser.parse_args()

    if args.stage == "intake":
        command = [str(ROOT / "scripts/run_stage1_intake.py")]
        if args.run_id:
            command.extend(["--run-id", args.run_id])
        run_command(command)
        if args.run_id:
            update_project_manifest_stage(
                args=args,
                run_id=args.run_id,
                stage="intake",
                status="complete",
                artifact_paths=[("intake_manifest", canonical_manifest_path("intake", args.run_id))],
                title=args.run_id,
            )
        return

    if args.stage == "paradigm":
        run_command(build_paradigm_command(args))
        return

    if args.stage == "video-train":
        run_command(build_video_train_command(args))
        return

    if args.stage == "video-self-learn":
        run_command(build_video_self_learning_command(args))
        return

    if args.stage == "brief":
        intake_file, run_id = resolve_intake_inputs(args.run_id, args.input_file)
        run_command(
            [
                str(ROOT / "scripts/phase2_rebuilder.py"),
                intake_file,
                str(canonical_stage_dir("brief", run_id)),
                "--run-id",
                run_id,
                *sum([["--manual-topic", topic] for topic in args.manual_topic], []),
                *([] if not args.agent_cards_file else ["--agent-cards-file", args.agent_cards_file]),
            ]
        )
        # 现行 simple 管线的聚类产物由 intake 阶段生成；复制进 brief 目录保证阶段自包含。
        event_clusters_src = canonical_stage_dir("intake", run_id) / "event_clusters.json"
        event_clusters_dst = canonical_stage_dir("brief", run_id) / "event_clusters.json"
        if not event_clusters_dst.exists() and event_clusters_src.exists():
            shutil.copyfile(event_clusters_src, event_clusters_dst)
        update_project_manifest_stage(
            args=args,
            run_id=run_id,
            stage="brief",
            status="pending_review",
            artifact_paths=[
                ("brief_manifest", canonical_manifest_path("brief", run_id)),
                ("selected_topics", canonical_stage_dir("brief", run_id) / "selected_topics.json"),
                ("topic_cards", canonical_stage_dir("brief", run_id) / "topic_cards.json"),
            ],
            title=run_id,
            source_materials=[{"type": "intake_records", "path": intake_file}],
        )
        return

    if args.stage == "draft":
        selected_topics, topic_cards = resolve_draft_inputs(args.run_id)
        command = [
            str(ROOT / "scripts/build_stage3_draft.py"),
            selected_topics,
            topic_cards,
        ]
        if args.output_dir:
            command.extend(["--output-dir", args.output_dir])
        run_command(command)
        draft_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else canonical_stage_dir("draft", args.run_id)
        update_project_manifest_stage(
            args=args,
            run_id=args.run_id,
            stage="draft",
            status="pending_review",
            artifact_paths=[
                ("draft_manifest", draft_dir / "draft_manifest.json"),
                ("final_structure_snapshot", draft_dir / "final_structure_snapshot.json"),
                ("draft_quality_gate", draft_dir / "draft_quality_gate.json"),
            ],
            title=args.run_id,
            source_materials=[
                {"type": "selected_topics", "path": selected_topics},
                {"type": "topic_cards", "path": topic_cards},
            ],
        )
        return

    if args.stage == "transwrite":
        if not args.run_id and not (args.draft_manifest and args.transwrite_decision):
            raise WorkflowContractError("transwrite 阶段必须提供 --run-id，或同时提供 draft_manifest 与 transwrite_decision。")
        draft_manifest, transwrite_decision = resolve_transwrite_manifests(
            args.run_id,
            args.draft_manifest,
            args.transwrite_decision,
        )
        command = [
            str(ROOT / "scripts/build_stage4_transwrite.py"),
            "--draft-manifest",
            draft_manifest,
            "--transwrite-decision",
            transwrite_decision,
        ]
        if args.output_dir:
            command.extend(["--output-dir", args.output_dir])
        run_command(command)
        transwrite_run_id = args.run_id or json.loads(Path(draft_manifest).read_text(encoding="utf-8")).get("run_id")
        transwrite_dir = (
            Path(args.output_dir).expanduser().resolve()
            if args.output_dir
            else canonical_stage_dir("transwrite", str(transwrite_run_id))
        )
        update_project_manifest_stage(
            args=args,
            run_id=str(transwrite_run_id),
            stage="transwrite",
            status="pending_review",
            artifact_paths=[
                ("transwrite_manifest", transwrite_dir / "transwrite_manifest.json"),
                ("transwrite_decision", Path(transwrite_decision)),
            ],
            title=str(transwrite_run_id),
            source_materials=[{"type": "draft_manifest", "path": draft_manifest}],
        )
        return

    if args.stage == "publish":
        if not args.run_id and not (args.transwrite_manifest and args.publish_decision):
            raise WorkflowContractError("publish 阶段必须提供 --run-id，或同时提供 transwrite_manifest 与 publish_decision。")
        transwrite_manifest, publish_decision = resolve_publish_manifests(
            args.run_id,
            args.transwrite_manifest,
            args.publish_decision,
        )
        command = [
            str(ROOT / "scripts/build_stage5_publish.py"),
            "--transwrite-manifest",
            transwrite_manifest,
            "--publish-decision",
            publish_decision,
        ]
        if args.output_dir:
            command.extend(["--output-dir", args.output_dir])
        if not args.dry_run:
            run_command(command)
            publish_run_id = args.run_id or json.loads(Path(transwrite_manifest).read_text(encoding="utf-8")).get("run_id")
            publish_dir = (
                Path(args.output_dir).expanduser().resolve()
                if args.output_dir
                else canonical_stage_dir("publish", str(publish_run_id))
            )
            update_project_manifest_stage(
                args=args,
                run_id=str(publish_run_id),
                stage="publish",
                status="pending_review",
                artifact_paths=[
                    ("publish_manifest", publish_dir / "publish_manifest.json"),
                    ("publish_decision", Path(publish_decision)),
                ],
                title=str(publish_run_id),
                source_materials=[{"type": "transwrite_manifest", "path": transwrite_manifest}],
            )
            return
        publish_manifest = run_json_command(command)
        dry_run_report = build_publish_dry_run_report(publish_manifest)
        report_path = Path(publish_manifest["out_dir"]) / "publish_dry_run_report.json"
        preflight_path = Path(publish_manifest["out_dir"]) / "publish_preflight_report.md"
        write_json(report_path, dry_run_report)
        write_text(preflight_path, render_publish_preflight_markdown(dry_run_report))
        dry_run_report["report_file"] = str(report_path.resolve())
        dry_run_report["preflight_report"] = str(preflight_path.resolve())
        update_project_manifest_stage(
            args=args,
            run_id=str(publish_manifest.get("run_id") or args.run_id or ""),
            stage="publish",
            status="pending_review",
            artifact_paths=[
                ("publish_manifest", Path(publish_manifest["manifest_file"])),
                ("publish_dry_run_report", report_path),
                ("publish_preflight_report", preflight_path),
            ],
            title=str(publish_manifest.get("run_id") or args.run_id or ""),
            source_materials=[{"type": "transwrite_manifest", "path": transwrite_manifest}],
        )
        print(json.dumps(dry_run_report, ensure_ascii=False, indent=2))
        return

    if args.stage == "postmortem":
        if not args.run_id and not args.publish_manifest:
            raise WorkflowContractError("postmortem 阶段必须提供 --run-id 或 --publish-manifest。")
        publish_manifest = resolve_postmortem_manifest(args.run_id, args.publish_manifest)
        command = [
            str(ROOT / "scripts/postmortem_writeback.py"),
            "--publish-manifest",
            publish_manifest,
        ]
        if args.require_publish_guard:
            command.append("--require-publish-guard")
        run_command(command)
        postmortem_run_id = args.run_id or json.loads(Path(publish_manifest).read_text(encoding="utf-8")).get("run_id")
        update_project_manifest_stage(
            args=args,
            run_id=str(postmortem_run_id),
            stage="postmortem",
            status="complete",
            artifact_paths=[("postmortem_manifest", canonical_manifest_path("postmortem", str(postmortem_run_id)))],
            title=str(postmortem_run_id),
            source_materials=[{"type": "publish_manifest", "path": publish_manifest}],
        )
        return

    if args.stage == "doctor":
        if args.publish_manifest:
            command = [
                str(ROOT / "scripts/publish_guard.py"),
                "--publish-manifest",
                args.publish_manifest,
            ]
            if args.output_json:
                command.extend(["--output-json", args.output_json])
            if args.output_md:
                command.extend(["--output-md", args.output_md])
            if args.fail_on_error:
                command.append("--fail-on-error")
            run_command(command)
            return
        if args.publish:
            command = [str(ROOT / "scripts/publish_doctor.py")]
            for channel in args.channel:
                command.extend(["--channel", channel])
            if args.check_auth:
                command.append("--check-auth")
            if args.output_json:
                command.extend(["--output-json", args.output_json])
            if args.output_md:
                command.extend(["--output-md", args.output_md])
            run_command(command)
            return
        command = [str(ROOT / "scripts/workflow_doctor.py")]
        if args.run_id:
            command.extend(["--run-id", args.run_id])
        if args.latest:
            command.append("--latest")
        if args.strict:
            command.append("--strict")
        run_command(command)
        return


if __name__ == "__main__":
    main()
