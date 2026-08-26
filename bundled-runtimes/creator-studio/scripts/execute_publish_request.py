#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_publish_payload import build_package
from execute_qianfan_publish import build_result as execute_qianfan_publish
from execute_social_auto_upload import build_result as execute_social_auto_upload
from prepare_publish_execution import build_plan, write_json
from record_publish_result import record_result
from skill_invoker import SKILL_SEARCH_PATHS, SkillInvoker

ROOT = Path(__file__).resolve().parents[1]
WECHAT_API_ROUTE = "baoyu-post-to-wechat"


CONFIRM_EXECUTABLE_ROUTE_TYPES = {"skill_draft_push", "qianfan_local_api", "external_uploader_fallback"}

AUTO_SKILL_ROUTES = {
    "baoyu-post-to-wechat",
    "wechat-multi-publisher",
    "md2wechat",
    "baoyu-post-to-weibo",
    "baoyu-post-to-x",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def resolve_channel_pack(plan: dict[str, Any]) -> Path:
    request = read_json(Path(plan["source_execution_request"]))
    channel_pack = request.get("channel_pack")
    if not channel_pack or str(channel_pack).startswith("<"):
        raise SystemExit("execution_request 缺少真实 channel_pack 路径，不能执行。")
    return Path(str(channel_pack)).expanduser().resolve()


def build_dry_run_response(
    plan: dict[str, Any],
    payload_report: dict[str, Any] | None = None,
    external_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "mode": "dry_run",
        "will_not_publish": True,
        "requires_user_confirmation": True,
        "status": plan.get("status"),
        "selected_route": plan.get("selected_route"),
        "selected_route_type": plan.get("selected_route_type"),
        "prepared_commands": plan.get("prepared_commands") or [],
        "publish_payload": (payload_report or {}).get("publish_payload"),
        "external_preview": external_preview,
        "next_step": "Review payload and rerun with --confirm-execute only for supported skill routes.",
    }


def load_project_env() -> dict[str, str]:
    """读项目 .env 的 KEY=VALUE（不覆盖 os.environ）。"""
    values: dict[str, str] = {}
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def locate_wechat_api_script() -> Path | None:
    """在 skill 搜索路径中找 baoyu-post-to-wechat 的确定性推草稿脚本。"""
    for base in [*SKILL_SEARCH_PATHS, ROOT / "skills"]:
        candidate = Path(base).expanduser() / "baoyu-post-to-wechat" / "scripts" / "wechat-api.ts"
        if candidate.is_file():
            return candidate
    return None


def execute_wechat_api_direct(
    channel_pack: dict[str, Any], payload: dict[str, Any], pack_dir: Path
) -> dict[str, Any] | None:
    """baoyu-post-to-wechat 路由的确定性执行：直接跑 wechat-api.ts 推草稿（不经 LLM）。

    返回 None 表示脚本不可用（回落 SkillInvoker 路由）。
    """
    script = locate_wechat_api_script()
    if script is None:
        return None
    inner = payload.get("payload") or {}
    html_path = str(inner.get("content_html") or "")
    if not html_path or not Path(html_path).expanduser().is_file():
        return {
            "success": False,
            "status": "failed",
            "error": f"content_html 缺失或不存在：{html_path}",
        }
    env_map = load_project_env()
    app_id = os.environ.get("WECHAT_APP_ID") or env_map.get("WECHAT_APP_ID") or ""
    app_secret = os.environ.get("WECHAT_APP_SECRET") or env_map.get("WECHAT_APP_SECRET") or ""
    if not app_id or not app_secret:
        return {
            "success": False,
            "status": "failed",
            "error": "缺少 WECHAT_APP_ID / WECHAT_APP_SECRET（环境变量或项目 .env）",
        }
    bun = shutil.which("bun")
    if bun:
        command = [bun, str(script), html_path]
    else:
        command = ["npx", "-y", "bun", str(script), html_path]
    if inner.get("title"):
        command += ["--title", str(inner["title"])]
    if inner.get("summary"):
        command += ["--summary", str(inner["summary"])]
    cover = str(inner.get("cover_path") or "")
    if cover and Path(cover).expanduser().is_file():
        command += ["--cover", cover]
    env = {**os.environ, "WECHAT_APP_ID": app_id, "WECHAT_APP_SECRET": app_secret}
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
            cwd=str(pack_dir),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "status": "failed",
            "error": "wechat-api.ts 执行超时（300s）",
            "command": command,
        }
    result: dict[str, Any] = {
        "success": completed.returncode == 0,
        "status": "succeeded" if completed.returncode == 0 else "failed",
        "command": command,
        "exit_code": completed.returncode,
        "stdout": (completed.stdout or "")[-4000:],
        "stderr": (completed.stderr or "")[-4000:],
    }
    if completed.returncode == 0:
        try:
            parsed = json.loads(completed.stdout)
            if isinstance(parsed, dict):
                result.update(
                    {
                        "media_id": parsed.get("media_id"),
                        "draft_id": parsed.get("media_id"),
                        "title": parsed.get("title"),
                        "platform": "wechat_article",
                    }
                )
        except json.JSONDecodeError:
            pass
    else:
        result["error"] = (completed.stderr or completed.stdout or "wechat-api.ts failed").strip()[-500:]
    return result


def skill_name_for_route(route: str | None, payload: dict[str, Any]) -> str | None:
    if not route:
        return None
    if route in AUTO_SKILL_ROUTES:
        return payload.get("payload", {}).get("skill") or route
    return None


def route_can_be_confirm_executed(plan: dict[str, Any]) -> bool:
    route = str(plan.get("selected_route") or "")
    route_type = str(plan.get("selected_route_type") or "")
    if route_type == "skill_draft_push":
        return True
    if route == "qianfan-local-api" and route_type == "qianfan_local_api":
        return True
    return route == "social-auto-upload" and route_type == "external_uploader_fallback"


def normalize_skill_result(result: dict[str, Any], *, selected_route: str | None) -> dict[str, Any]:
    return {
        "success": result.get("success", False),
        "status": result.get("status"),
        "platform": result.get("platform"),
        "platform_url": result.get("platform_url") or result.get("url"),
        "platform_post_id": result.get("platform_post_id") or result.get("post_id"),
        "draft_id": result.get("draft_id") or result.get("msg_id") or result.get("draft_id_or_url"),
        "verification_status": result.get("verification_status"),
        "account": result.get("account"),
        "screenshot": result.get("screenshot") or result.get("screenshot_path"),
        "error": result.get("error"),
        "platform_response": result,
        "notes": f"recorded_from_route:{selected_route}",
    }


def execute_request(
    execution_request_path: Path,
    *,
    confirm_execute: bool,
    invoker: SkillInvoker | None = None,
) -> dict[str, Any]:
    plan = build_plan(execution_request_path)
    channel_pack = resolve_channel_pack(plan)
    payload_report = build_package(channel_pack)
    payload = read_json(Path(payload_report["publish_payload"]))
    if payload_report.get("status") == "blocked":
        return {
            "schema_version": "1.0",
            "created_at": now_iso(),
            "mode": "dry_run" if not confirm_execute else "execute",
            "status": "blocked_platform_form_validation",
            "will_not_publish": True,
            "selected_route": plan.get("selected_route"),
            "publish_payload": payload_report.get("publish_payload"),
            "platform_form_validation": payload_report.get("platform_form_validation"),
            "errors": payload_report.get("errors") or [],
            "warnings": payload_report.get("warnings") or [],
        }
    if not confirm_execute:
        preview = None
        if plan.get("selected_route") == "qianfan-local-api":
            preview = execute_qianfan_publish(channel_pack, confirm_execute=False)
        elif plan.get("selected_route") == "social-auto-upload":
            preview = execute_social_auto_upload(channel_pack, confirm_execute=False)
        return build_dry_run_response(plan, payload_report, preview)
    if plan.get("status") != "ready_for_user_confirmation":
        return {
            "schema_version": "1.0",
            "created_at": now_iso(),
            "mode": "execute",
            "status": "blocked",
            "will_not_publish": True,
            "error": f"route_not_ready:{plan.get('status')}",
            "plan": plan,
        }
    selected_route = plan.get("selected_route")
    if not route_can_be_confirm_executed(plan):
        return {
            "schema_version": "1.0",
            "created_at": now_iso(),
            "mode": "execute",
            "status": "blocked_manual_or_external_route",
            "will_not_publish": True,
            "selected_route": selected_route,
            "selected_route_type": plan.get("selected_route_type"),
            "prepared_commands": plan.get("prepared_commands") or [],
            "error": "Selected route requires browser/manual/MCP/external API or CLI confirmation; not executed by this script.",
        }
    if selected_route == "social-auto-upload":
        result = execute_social_auto_upload(channel_pack, confirm_execute=True)
        if str(result.get("status") or "").startswith("blocked_"):
            return {
                "schema_version": "1.0",
                "created_at": now_iso(),
                "mode": "execute",
                "status": result.get("status"),
                "selected_route": selected_route,
                "will_not_publish": result.get("will_not_publish", True),
                "external_result": result,
            }
        normalized = normalize_skill_result(result, selected_route=selected_route)
        record = record_result(channel_pack, normalized, source=f"execute_publish_request:{selected_route}")
        return {
            "schema_version": "1.0",
            "created_at": now_iso(),
            "mode": "execute",
            "status": "executed_and_recorded",
            "selected_route": selected_route,
            "publish_payload": payload_report["publish_payload"],
            "external_result": result,
            "record": record,
            "verification_required": True,
        }
    if selected_route == "qianfan-local-api":
        result = execute_qianfan_publish(channel_pack, confirm_execute=True)
        if str(result.get("status") or "").startswith("blocked_"):
            return {
                "schema_version": "1.0",
                "created_at": now_iso(),
                "mode": "execute",
                "status": result.get("status"),
                "selected_route": selected_route,
                "will_not_publish": result.get("will_not_publish", True),
                "external_result": result,
            }
        normalized = normalize_skill_result(result, selected_route=selected_route)
        record = record_result(channel_pack, normalized, source=f"execute_publish_request:{selected_route}")
        return {
            "schema_version": "1.0",
            "created_at": now_iso(),
            "mode": "execute",
            "status": "queued_and_recorded",
            "selected_route": selected_route,
            "publish_payload": payload_report["publish_payload"],
            "external_result": result,
            "record": record,
            "verification_required": True,
        }
    if selected_route not in AUTO_SKILL_ROUTES:
        return {
            "schema_version": "1.0",
            "created_at": now_iso(),
            "mode": "execute",
            "status": "blocked_manual_or_external_route",
            "will_not_publish": True,
            "selected_route": selected_route,
            "selected_route_type": plan.get("selected_route_type"),
        }
    skill_name = skill_name_for_route(selected_route, payload)
    if not skill_name:
        return {
            "schema_version": "1.0",
            "created_at": now_iso(),
            "mode": "execute",
            "status": "blocked_missing_skill_name",
            "will_not_publish": True,
            "selected_route": selected_route,
        }
    # baoyu-post-to-wechat：优先确定性脚本直跑（不经 LLM），脚本不可用才回落 SkillInvoker。
    # 显式注入 invoker（单测依赖注入）时视为调用方接管执行，跳过直跑。
    direct_result: dict[str, Any] | None = None
    if selected_route == WECHAT_API_ROUTE and invoker is None:
        direct_result = execute_wechat_api_direct(channel_pack, payload, channel_pack.parent)
        if direct_result is not None:
            result = direct_result
            normalized = normalize_skill_result(result, selected_route=selected_route)
            record = record_result(channel_pack, normalized, source=f"execute_publish_request:{selected_route}:direct")
            if not normalized.get("success"):
                return {
                    "schema_version": "1.0",
                    "created_at": now_iso(),
                    "mode": "execute",
                    "status": "skill_execution_failed",
                    "will_not_publish": True,
                    "selected_route": selected_route,
                    "skill": skill_name,
                    "publish_payload": payload_report["publish_payload"],
                    "skill_result": result,
                    "record": record,
                    "error": normalized.get("error") or "wechat-api.ts execution failed",
                }
            return {
                "schema_version": "1.0",
                "created_at": now_iso(),
                "mode": "execute",
                "status": "executed_and_recorded",
                "selected_route": selected_route,
                "skill": skill_name,
                "execution_path": "direct_script",
                "publish_payload": payload_report["publish_payload"],
                "skill_result": result,
                "record": record,
                "final_publish_requires_confirmation": True,
            }
    result = (invoker or SkillInvoker()).invoke(skill_name, payload)
    normalized = normalize_skill_result(result, selected_route=selected_route)
    record = record_result(channel_pack, normalized, source=f"execute_publish_request:{selected_route}")
    if not normalized.get("success"):
        return {
            "schema_version": "1.0",
            "created_at": now_iso(),
            "mode": "execute",
            "status": "skill_execution_failed",
            "will_not_publish": True,
            "selected_route": selected_route,
            "skill": skill_name,
            "publish_payload": payload_report["publish_payload"],
            "skill_result": result,
            "record": record,
            "error": normalized.get("error") or "skill execution failed",
        }
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "mode": "execute",
        "status": "executed_and_recorded",
        "selected_route": selected_route,
        "skill": skill_name,
        "publish_payload": payload_report["publish_payload"],
        "skill_result": result,
        "record": record,
        "final_publish_requires_confirmation": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely execute a publish execution_request.json. Defaults to dry-run.")
    parser.add_argument("--execution-request", required=True)
    parser.add_argument("--confirm-execute", action="store_true", help="Actually invoke supported local skill routes.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    result = execute_request(Path(args.execution_request).expanduser().resolve(), confirm_execute=args.confirm_execute)
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
