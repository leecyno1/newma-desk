#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import get_project_root
from prepare_publish_execution import check_route, choose_route, load_upstream_rows, resolve_root, route_can_be_confirm_executed
from publish_accounts import build_report as build_account_report


ROOT = get_project_root()
BROWSER_PROFILE_CONFIG = ROOT / "configs" / "publish" / "browser_profiles.json"

CHANNEL_ROUTE_TEMPLATES: dict[str, dict[str, Any]] = {
    "wechat_article": {
        "platform": "wechat",
        "route_priority": [
            {"route": "baoyu-post-to-wechat", "type": "skill_draft_push"},
            {"route": "wechat-multi-publisher", "type": "skill_batch_draft_push"},
            {"route": "md2wechat", "type": "preprocess_fallback"},
            {"route": "browser-profile", "type": "browser_confirm_fallback"},
        ],
    },
    "xiaohongshu_video": {
        "platform": "xiaohongshu",
        "route_priority": [
            {"route": "social-auto-upload", "type": "external_uploader_fallback"},
            {"route": "all-in-one", "type": "api_first_cli"},
            {"route": "xhs-skills-spider-xhs", "type": "api_first_skill"},
            {"route": "xiaohongshu-mcp", "type": "mcp_fallback"},
            {"route": "rednote-mcp", "type": "mcp_fallback"},
            {"route": "browser-profile", "type": "browser_confirm_fallback"},
        ],
    },
    "douyin_video": {
        "platform": "douyin",
        "route_priority": [
            {"route": "douyin-upload-skill", "type": "skill_or_api_upload"},
            {"route": "social-auto-upload", "type": "external_uploader_fallback"},
            {"route": "browser-profile", "type": "browser_confirm_fallback"},
        ],
    },
    "bilibili_video": {
        "platform": "bilibili",
        "route_priority": [
            {"route": "social-auto-upload", "type": "external_uploader_fallback"},
            {"route": "bilibili-upload-bridge", "type": "skill_bridge"},
            {"route": "biliup-rs", "type": "external_cli"},
            {"route": "manual-package", "type": "manual_package"},
        ],
    },
    "wechat_channels_video": {
        "platform": "wechat_channels",
        "route_priority": [
            {"route": "social-auto-upload", "type": "external_uploader_fallback"},
            {"route": "browser-profile", "type": "browser_confirm_fallback"},
            {"route": "manual-package", "type": "manual_package"},
        ],
    },
    "weibo_post": {
        "platform": "weibo",
        "route_priority": [
            {"route": "baoyu-post-to-weibo", "type": "browser_confirm"},
        ],
    },
    "x_post": {
        "platform": "x",
        "route_priority": [
            {"route": "baoyu-post-to-x", "type": "browser_or_api_confirm"},
            {"route": "xurl", "type": "external_api_cli_fallback"},
        ],
    },
}

ACCOUNT_OPERATIONS_SKILLS = {
    "wechat_article": "wechat-account-launch-expert",
    "xiaohongshu_video": "xiaohongshu-account-launch-expert",
    "douyin_video": "douyin-account-launch-expert",
    "wechat_channels_video": "channels-account-launch-expert",
    "x_post": "x-twitter-cold-start-expert",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def browser_profiles() -> dict[str, Any]:
    if not BROWSER_PROFILE_CONFIG.exists():
        return {}
    payload = read_json(BROWSER_PROFILE_CONFIG)
    profiles = payload.get("profiles")
    return profiles if isinstance(profiles, dict) else {}


def browser_profile_for_channel(channel: str, profiles: dict[str, Any]) -> dict[str, Any] | None:
    profile = profiles.get(channel)
    if not isinstance(profile, dict):
        return None
    profile_dir = profile.get("profile_dir")
    return {
        "platform": profile.get("platform"),
        "profile_key": channel,
        "profile_dir": str(Path(str(profile_dir)).expanduser()) if profile_dir else None,
        "entry_url": profile.get("entry_url"),
        "open_command": f"python3 scripts/open_publish_browser.py {channel}",
    }


def profile_keys_for_platform(platform: str, profiles: dict[str, Any]) -> list[str]:
    return sorted(
        key for key, profile in profiles.items()
        if isinstance(profile, dict) and str(profile.get("platform") or "") == platform
    )


def build_dummy_request(channel: str, profiles: dict[str, Any]) -> dict[str, Any]:
    template = CHANNEL_ROUTE_TEMPLATES[channel]
    browser_profile = browser_profile_for_channel(channel, profiles)
    route_priority = []
    for route in template["route_priority"]:
        route_copy = dict(route)
        if route_copy.get("route") == "browser-profile" and browser_profile:
            route_copy["open_command"] = browser_profile["open_command"]
        route_priority.append(route_copy)
    return {
        "schema_version": "1.0",
        "topic_id": "doctor",
        "title": f"{channel} publish doctor",
        "channel": channel,
        "platform": template["platform"],
        "status": "ready_for_user_confirmation",
        "requires_user_confirmation": True,
        "channel_pack": "<doctor-only-no-channel-pack>",
        "inputs": {
            "artifacts": {},
            "publish_metadata": {},
            "browser_profile": browser_profile,
        },
        "route_priority": route_priority,
    }


def inspect_browser_profile(channel: str, profiles: dict[str, Any]) -> dict[str, Any]:
    profile = browser_profile_for_channel(channel, profiles)
    if not profile:
        return {
            "configured": False,
            "reason": "missing_browser_profile_config",
            "open_command": None,
            "entry_url": None,
            "profile_dir": None,
        }
    profile_dir = Path(str(profile["profile_dir"])).expanduser() if profile.get("profile_dir") else None
    return {
        "configured": True,
        "reason": "profile_configured",
        "profile_key": profile.get("profile_key"),
        "open_command": profile.get("open_command"),
        "entry_url": profile.get("entry_url"),
        "profile_dir": str(profile_dir) if profile_dir else None,
        "profile_dir_exists": bool(profile_dir and profile_dir.exists()),
    }


def inspect_account_operations(channel: str, rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    upstream_skill = ACCOUNT_OPERATIONS_SKILLS.get(channel)
    if not upstream_skill:
        return {
            "applicable": False,
            "available": False,
            "reason": "no_account_operations_mapping",
            "bridge_skill": "dasheng-publish-operations-bridge",
            "upstream_skill": None,
            "upstream_root": None,
            "upstream_skill_path": None,
        }
    root = resolve_root(rows.get("agent-skills-launch-pack"))
    skill_path = root / "skills" / upstream_skill / "SKILL.md" if root else None
    bridge_path = ROOT / "skills" / "dasheng-publish-operations-bridge" / "SKILL.md"
    upstream_available = bool(skill_path and skill_path.exists())
    bridge_available = bridge_path.exists()
    if upstream_available and bridge_available:
        reason = "bridge_and_upstream_skill_found"
    elif not bridge_available:
        reason = "missing_publish_operations_bridge"
    else:
        reason = "missing_agent_skills_launch_pack_skill"
    return {
        "applicable": True,
        "available": upstream_available and bridge_available,
        "reason": reason,
        "bridge_skill": "dasheng-publish-operations-bridge",
        "bridge_skill_path": str(bridge_path),
        "upstream_registry_name": "agent-skills-launch-pack",
        "upstream_skill": upstream_skill,
        "upstream_root": str(root) if root else None,
        "upstream_skill_path": str(skill_path) if skill_path else None,
    }


def build_channel_report(channel: str, rows: dict[str, dict[str, Any]], profiles: dict[str, Any]) -> dict[str, Any]:
    request = build_dummy_request(channel, profiles)
    route_checks = [check_route(route, rows, request) for route in request["route_priority"]]
    selected = choose_route(route_checks)
    browser_profile = inspect_browser_profile(channel, profiles)
    account_operations = inspect_account_operations(channel, rows)
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
    selected_route = selected.get("route") if selected else None
    selected_type = selected.get("type") if selected else None
    status = "ready_for_user_confirmation" if selected else "blocked_missing_executor"
    return {
        "channel": channel,
        "platform": request["platform"],
        "status": status,
        "selected_route": selected_route,
        "selected_route_type": selected_type,
        "requires_user_confirmation": True,
        "will_not_publish": True,
        "confirm_execute_supported": route_can_be_confirm_executed(selected),
        "available_browser_profiles": profile_keys_for_platform(str(request["platform"]), profiles),
        "browser_profile": browser_profile,
        "account_operations": account_operations,
        "route_checks": route_checks,
        "missing_dependencies": missing_dependencies,
        "prepared_commands": selected.get("commands") if selected else [],
    }


def build_report(channels: list[str], *, check_auth: bool = False) -> dict[str, Any]:
    rows = load_upstream_rows()
    profiles = browser_profiles()
    channel_reports = [build_channel_report(channel, rows, profiles) for channel in channels]
    account_report = build_account_report(channels, check_auth=check_auth)
    accounts_by_channel: dict[str, list[dict[str, Any]]] = {}
    for account in account_report.get("accounts") or []:
        accounts_by_channel.setdefault(str(account.get("channel")), []).append(account)
    for channel_report in channel_reports:
        account_slots = accounts_by_channel.get(str(channel_report.get("channel")), [])
        channel_report["account_slots"] = account_slots
        if check_auth and channel_report.get("selected_route") == "social-auto-upload":
            selected_account = next((row for row in account_slots if row.get("default")), None)
            if selected_account is None and account_slots:
                selected_account = account_slots[0]
            social_auth = next(
                (
                    item for item in (selected_account or {}).get("auth") or []
                    if item.get("mode") == "social_auto_upload"
                ),
                None,
            )
            channel_report["selected_account_slot"] = (selected_account or {}).get("slot")
            channel_report["selected_account_auth_status"] = (social_auth or {}).get("status") or "missing_account_registration"
            if not social_auth or social_auth.get("status") != "valid":
                channel_report["status"] = "blocked_auth_required"
                channel_report["confirm_execute_supported"] = False
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "mode": "publish_doctor",
        "will_not_publish": True,
        "requires_user_confirmation": True,
        "check_auth": check_auth,
        "channels": channel_reports,
        "summary": {
            "total_channels": len(channel_reports),
            "ready_count": sum(1 for item in channel_reports if item["status"] == "ready_for_user_confirmation"),
            "blocked_count": sum(1 for item in channel_reports if str(item["status"]).startswith("blocked")),
            "missing_dependency_count": sum(len(item["missing_dependencies"]) for item in channel_reports),
            "browser_profile_configured_count": sum(1 for item in channel_reports if item["browser_profile"].get("configured")),
            "operations_applicable_count": sum(1 for item in channel_reports if item["account_operations"].get("applicable")),
            "operations_ready_count": sum(1 for item in channel_reports if item["account_operations"].get("available")),
            "operations_missing_count": sum(
                1
                for item in channel_reports
                if item["account_operations"].get("applicable") and not item["account_operations"].get("available")
            ),
            "account_slot_count": account_report["summary"]["account_slot_count"],
            "account_login_required_count": account_report["summary"]["login_required_count"],
            "cli_auth_valid_count": account_report["summary"]["cli_valid_count"],
            "cli_auth_invalid_count": account_report["summary"]["cli_invalid_count"],
        },
        "safety": {
            "does_not_publish": True,
            "does_not_read_cookies": not check_auth,
            "does_not_export_cookies": True,
            "does_not_expose_cookie_contents": True,
            "does_not_open_browser": True,
            "auth_check_delegates_to_upstream": check_auth,
            "checks_only": [
                "local skill SKILL.md presence",
                "external upstream root presence",
                "external account operations skill presence",
                "CLI binary presence",
                "persistent browser profile configuration",
                "non-secret account slot registry",
            ],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Publish Doctor｜发布通路体检",
        "",
        "本报告只检查发布通路可用性，不打开浏览器、不读取 cookies、不触发真实发布。",
        "",
        "## 总览",
        "",
        f"- 渠道数：`{summary['total_channels']}`",
        f"- 可进入人工确认：`{summary['ready_count']}`",
        f"- 阻塞：`{summary['blocked_count']}`",
        f"- 缺失依赖项：`{summary['missing_dependency_count']}`",
        f"- 已配置浏览器 Profile：`{summary['browser_profile_configured_count']}`",
        f"- 可用账号运营 Skill：`{summary['operations_ready_count']}/{summary['operations_applicable_count']}`",
        f"- 注册账号槽：`{summary['account_slot_count']}`",
        f"- 需要登录账号槽：`{summary['account_login_required_count']}`",
        f"- CLI 登录有效/失效：`{summary['cli_auth_valid_count']}/{summary['cli_auth_invalid_count']}`",
        "",
        "## 渠道明细",
        "",
    ]
    for channel in report["channels"]:
        profile = channel["browser_profile"]
        operations = channel["account_operations"]
        account_slots = channel.get("account_slots") or []
        lines.extend(
            [
                f"### {channel['channel']}",
                "",
                f"- 平台：`{channel['platform']}`",
                f"- 状态：`{channel['status']}`",
                f"- 选中路线：`{channel.get('selected_route') or 'none'}`",
                f"- 路线类型：`{channel.get('selected_route_type') or 'none'}`",
                f"- 浏览器 Profile：`{profile.get('reason')}`",
                f"- 可用账号槽：`{', '.join(channel.get('available_browser_profiles') or []) or 'none'}`",
                f"- 当前 Profile key：`{profile.get('profile_key') or 'none'}`",
                f"- Profile 目录：`{profile.get('profile_dir') or 'none'}`",
                f"- Profile 已创建：`{profile.get('profile_dir_exists', False)}`",
                f"- 打开命令：`{profile.get('open_command') or 'none'}`",
                f"- 默认账号槽：`{channel.get('selected_account_slot') or 'none'}`",
                f"- 默认账号认证：`{channel.get('selected_account_auth_status') or 'not_checked'}`",
                f"- 运营桥接：`{operations.get('reason')}`",
                f"- 运营上游 Skill：`{operations.get('upstream_skill') or 'none'}`",
                f"- 运营 Skill 路径：`{operations.get('upstream_skill_path') or 'none'}`",
            ]
        )
        if account_slots:
            lines.extend(["", "账号槽："])
            for account in account_slots:
                auth_status = ", ".join(
                    f"{item.get('mode')}={item.get('status')}" for item in account.get("auth") or []
                )
                lines.append(f"- `{account.get('slot')}` {account.get('label')}：`{account.get('status')}` ({auth_status})")
        missing = channel.get("missing_dependencies") or []
        if missing:
            lines.extend(["", "缺失依赖："])
            for dep in missing:
                details = dep.get("skill_path") or dep.get("upstream_root") or dep.get("binary") or ""
                lines.append(f"- `{dep.get('route')}`：`{dep.get('reason')}` {details}".rstrip())
        lines.append("")
    return "\n".join(lines)


def parse_channels(raw_channels: list[str] | None) -> list[str]:
    if not raw_channels:
        return list(CHANNEL_ROUTE_TEMPLATES)
    channels: list[str] = []
    for raw in raw_channels:
        for item in raw.split(","):
            channel = item.strip()
            if not channel:
                continue
            if channel not in CHANNEL_ROUTE_TEMPLATES:
                raise SystemExit(f"Unsupported publish doctor channel: {channel}")
            channels.append(channel)
    return channels


def main() -> None:
    parser = argparse.ArgumentParser(description="Check publish route readiness without publishing.")
    parser.add_argument("--channel", action="append", help="Channel to check; may be repeated or comma-separated.")
    parser.add_argument("--output-json", help="Optional JSON report path.")
    parser.add_argument("--output-md", help="Optional Markdown report path.")
    parser.add_argument("--check-auth", action="store_true", help="Delegate CLI account login validation without publishing.")
    args = parser.parse_args()

    report = build_report(parse_channels(args.channel), check_auth=args.check_auth)
    if args.output_json:
        write_json(Path(args.output_json).expanduser().resolve(), report)
    if args.output_md:
        write_text(Path(args.output_md).expanduser().resolve(), render_markdown(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
