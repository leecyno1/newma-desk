#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import get_project_root
from prepare_publish_execution import load_upstream_rows, resolve_root


ROOT = get_project_root()
DEFAULT_REGISTRY = ROOT / "configs" / "publish" / "account_registry.json"
DEFAULT_BROWSER_PROFILES = ROOT / "configs" / "publish" / "browser_profiles.json"
DEFAULT_SESSION_ROOT = Path.home() / "Library" / "Application Support" / "NewmaPublishSessions"
LEGACY_SESSION_ROOT = Path.home() / "Library" / "Application Support" / "DashengPublishSessions"
QIANFAN_SUBDIRS = ["db", "logs", "cookies", "cookiesFile", "uploads", "thumbnails", "upload_chunks"]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def registry_path() -> Path:
    return Path(
        os.environ.get("NEWMA_PUBLISH_ACCOUNT_REGISTRY")
        or os.environ.get("DASHENG_PUBLISH_ACCOUNT_REGISTRY")
        or DEFAULT_REGISTRY
    ).expanduser()


def browser_profile_path() -> Path:
    return Path(
        os.environ.get("NEWMA_PUBLISH_BROWSER_PROFILES")
        or os.environ.get("DASHENG_PUBLISH_BROWSER_PROFILES")
        or DEFAULT_BROWSER_PROFILES
    ).expanduser()


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.exists():
        return {"policy": {}, "channels": {}}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {"policy": {}, "channels": {}}


def load_browser_profiles() -> dict[str, Any]:
    path = browser_profile_path()
    if not path.exists():
        return {}
    payload = read_json(path)
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    return profiles if isinstance(profiles, dict) else {}


def session_root(registry: dict[str, Any]) -> Path:
    configured = os.environ.get("NEWMA_PUBLISH_SESSION_ROOT") or os.environ.get("DASHENG_PUBLISH_SESSION_ROOT")
    if not configured:
        configured = str((registry.get("policy") or {}).get("session_root") or "")
    if not configured:
        configured = str(LEGACY_SESSION_ROOT if LEGACY_SESSION_ROOT.exists() and not DEFAULT_SESSION_ROOT.exists() else DEFAULT_SESSION_ROOT)
    return Path(configured).expanduser()


def social_cookie_dir(registry: dict[str, Any]) -> Path:
    return session_root(registry) / "social-auto-upload" / "cookies"


def qianfan_data_dir(registry: dict[str, Any]) -> Path:
    return session_root(registry) / "qianfan-sync"


def social_upstream_root() -> Path | None:
    return resolve_root(load_upstream_rows().get("social-auto-upload"))


def set_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def initialize_session_storage(registry: dict[str, Any]) -> dict[str, Any]:
    state_root = session_root(registry)
    cookie_dir = social_cookie_dir(registry)
    set_private_directory(state_root)
    set_private_directory(cookie_dir.parent)
    set_private_directory(cookie_dir)
    qianfan_root = qianfan_data_dir(registry)
    set_private_directory(qianfan_root)
    for subdir in QIANFAN_SUBDIRS:
        set_private_directory(qianfan_root / subdir)

    upstream = social_upstream_root()
    upstream_cookie_dir = upstream / "cookies" if upstream else None
    result: dict[str, Any] = {
        "session_root": str(state_root),
        "social_cookie_dir": str(cookie_dir),
        "qianfan_data_dir": str(qianfan_root),
        "qianfan_backend_command": (
            f"SAU_DATA_DIR={shlex.quote(str(qianfan_root))} "
            f"{shlex.quote(str(ROOT / 'vendor/reserved/publish/qianfan-sync/backend/.venv/bin/python'))} "
            f"{shlex.quote(str(ROOT / 'vendor/reserved/publish/qianfan-sync/backend/app.py'))}"
        ),
        "upstream_root": str(upstream) if upstream else None,
        "upstream_cookie_link": str(upstream_cookie_dir) if upstream_cookie_dir else None,
        "status": "secure_session_root_ready",
        "migrated_entries": [],
    }
    if not upstream or not upstream.exists():
        result["status"] = "secure_session_root_ready_missing_upstream"
        return result

    if upstream_cookie_dir.is_symlink():
        if upstream_cookie_dir.resolve() == cookie_dir.resolve():
            result["status"] = "secure_session_link_ready"
        else:
            result["status"] = "blocked_unexpected_cookie_symlink"
        return result

    if upstream_cookie_dir.exists() and not upstream_cookie_dir.is_dir():
        result["status"] = "blocked_cookie_path_not_directory"
        return result

    if upstream_cookie_dir.exists():
        for source in sorted(upstream_cookie_dir.iterdir()):
            target = cookie_dir / source.name
            if target.exists():
                result["status"] = "blocked_cookie_migration_conflict"
                result["conflict"] = str(target)
                return result
            shutil.move(str(source), str(target))
            result["migrated_entries"].append(source.name)
        upstream_cookie_dir.rmdir()

    upstream_cookie_dir.symlink_to(cookie_dir, target_is_directory=True)
    result["status"] = "secure_session_link_ready"
    return result


def parse_env_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and value.strip():
            keys.add(key.strip())
    return keys


def inspect_wechat_api(alias: str) -> dict[str, Any]:
    normalized = alias.upper().replace("-", "_")
    prefix = "" if normalized in {"", "DEFAULT"} else f"WECHAT_{normalized}_"
    app_id_key = f"{prefix}APP_ID" if prefix else "WECHAT_APP_ID"
    secret_key = f"{prefix}APP_SECRET" if prefix else "WECHAT_APP_SECRET"
    sources = [
        ("process_env", {key for key, value in os.environ.items() if value}),
        ("project_env", parse_env_keys(ROOT / ".baoyu-skills" / ".env")),
        ("user_env", parse_env_keys(Path.home() / ".baoyu-skills" / ".env")),
    ]
    for source_name, keys in sources:
        if app_id_key in keys and secret_key in keys:
            return {
                "mode": "official_api",
                "status": "configured_unverified",
                "credential_alias": alias,
                "credential_source": source_name,
                "secret_values_exposed": False,
            }
    return {
        "mode": "official_api",
        "status": "missing_credentials",
        "credential_alias": alias,
        "credential_source": None,
        "secret_values_exposed": False,
    }


def inspect_browser_profile(profile_key: str, profiles: dict[str, Any]) -> dict[str, Any]:
    row = profiles.get(profile_key)
    if not isinstance(row, dict):
        return {
            "mode": "browser_profile",
            "status": "missing_profile_config",
            "profile_key": profile_key,
        }
    profile_dir = Path(str(row.get("profile_dir") or "")).expanduser()
    cookie_db = profile_dir / "Default" / "Cookies"
    state_present = cookie_db.exists() and cookie_db.stat().st_size > 0
    return {
        "mode": "browser_profile",
        "status": "state_present_unverified" if state_present else "login_required",
        "profile_key": profile_key,
        "profile_dir": str(profile_dir),
        "profile_dir_exists": profile_dir.exists(),
        "state_present": state_present,
        "open_command": f"python3 scripts/open_publish_browser.py {profile_key}",
        "cookie_contents_inspected": False,
    }


def resolve_sau_launcher(upstream: Path | None) -> list[str] | None:
    explicit = os.environ.get("SOCIAL_AUTO_UPLOAD_CLI")
    if explicit and Path(explicit).expanduser().exists():
        return [str(Path(explicit).expanduser().resolve())]
    binary = shutil.which("sau")
    if binary:
        return [binary]
    if not upstream:
        return None
    venv_cli = upstream / ".venv" / "bin" / "sau"
    if venv_cli.exists():
        return [str(venv_cli)]
    cli_script = upstream / "sau_cli.py"
    venv_python = upstream / ".venv" / "bin" / "python"
    if cli_script.exists() and venv_python.exists():
        return [str(venv_python), str(cli_script)]
    return None


def inspect_social_account(
    registry: dict[str, Any],
    cli_platform: str,
    account_name: str,
    *,
    check_auth: bool,
) -> dict[str, Any]:
    upstream = social_upstream_root()
    cookie_file = social_cookie_dir(registry) / f"{cli_platform}_{account_name}.json"
    launcher = resolve_sau_launcher(upstream)
    login_command = [*(launcher or ["sau"]), cli_platform, "login", "--account", account_name]
    if cli_platform != "bilibili":
        login_command.append("--headed")
    result: dict[str, Any] = {
        "mode": "social_auto_upload",
        "status": "state_present_unverified" if cookie_file.exists() else "login_required",
        "cli_platform": cli_platform,
        "account_name": account_name,
        "session_file": str(cookie_file),
        "session_file_exists": cookie_file.exists(),
        "login_command": shlex.join(login_command),
        "cookie_contents_exposed": False,
        "auth_checked": check_auth,
    }
    if not check_auth:
        return result
    if not launcher or not upstream or not upstream.exists():
        result["status"] = "missing_cli"
        return result
    command = [*launcher, cli_platform, "check", "--account", account_name]
    try:
        completed = subprocess.run(
            command,
            cwd=str(upstream),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        result["status"] = "auth_check_failed"
        return result
    result["status"] = "valid" if completed.returncode == 0 else "invalid"
    result["check_returncode"] = completed.returncode
    return result


def build_slot_report(
    registry: dict[str, Any],
    channel: str,
    channel_row: dict[str, Any],
    slot_name: str,
    slot: dict[str, Any],
    profiles: dict[str, Any],
    *,
    check_auth: bool,
) -> dict[str, Any]:
    auth: list[dict[str, Any]] = []
    modes = [str(mode) for mode in slot.get("auth_modes") or []]
    if "official_api" in modes:
        auth.append(inspect_wechat_api(str(slot.get("credential_alias") or "default")))
    if "browser_profile" in modes:
        auth.append(inspect_browser_profile(str(slot.get("browser_profile") or channel), profiles))
    if "social_auto_upload" in modes:
        auth.append(
            inspect_social_account(
                registry,
                str(channel_row.get("cli_platform") or channel_row.get("platform") or ""),
                str(slot.get("cli_account_name") or slot_name),
                check_auth=check_auth,
            )
        )
    statuses = {str(item.get("status")) for item in auth}
    if "valid" in statuses or "configured_unverified" in statuses:
        status = "available"
    elif "state_present_unverified" in statuses:
        status = "state_present_unverified"
    elif statuses and statuses <= {"login_required", "missing_credentials", "invalid", "missing_cli", "missing_profile_config"}:
        status = "login_required"
    else:
        status = "attention_required"
    return {
        "channel": channel,
        "platform": channel_row.get("platform"),
        "slot": slot_name,
        "label": slot.get("label") or slot_name,
        "default": bool(slot.get("default")),
        "status": status,
        "auth": auth,
    }


def parse_channels(raw_channels: list[str] | None, registry: dict[str, Any]) -> list[str]:
    available = registry.get("channels") or {}
    if not raw_channels:
        return list(available)
    channels: list[str] = []
    for raw in raw_channels:
        for item in raw.split(","):
            channel = item.strip()
            if not channel:
                continue
            if channel in available:
                channels.append(channel)
    return channels


def logical_account_reports(registry: dict[str, Any], account_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_index = {
        (str(row.get("channel")), str(row.get("slot"))): str(row.get("status"))
        for row in account_rows
    }
    reports: list[dict[str, Any]] = []
    for logical_id, logical in (registry.get("logical_accounts") or {}).items():
        routes = logical.get("routes") if isinstance(logical, dict) else {}
        route_rows = [
            {
                "channel": channel,
                "slot": slot,
                "status": status_index.get((str(channel), str(slot)), "not_checked"),
            }
            for channel, slot in (routes or {}).items()
        ]
        statuses = {row["status"] for row in route_rows}
        if route_rows and statuses <= {"available", "state_present_unverified"}:
            status = "ready_or_state_present"
        elif any(value == "login_required" for value in statuses):
            status = "login_required"
        else:
            status = "attention_required"
        reports.append(
            {
                "logical_account": logical_id,
                "label": logical.get("label") if isinstance(logical, dict) else logical_id,
                "matrix_role": logical.get("matrix_role") if isinstance(logical, dict) else None,
                "status": status,
                "routes": route_rows,
            }
        )
    return reports


def build_report(
    channels: list[str] | None = None,
    *,
    slots: list[str] | None = None,
    check_auth: bool = False,
    initialize: bool = False,
) -> dict[str, Any]:
    registry = load_registry()
    profiles = load_browser_profiles()
    selected_channels = parse_channels(channels, registry)
    selected_slots = set(slots or [])
    initialization = initialize_session_storage(registry) if initialize else None
    account_rows: list[dict[str, Any]] = []
    for channel in selected_channels:
        channel_row = (registry.get("channels") or {}).get(channel) or {}
        for slot_name, slot in (channel_row.get("slots") or {}).items():
            if selected_slots and slot_name not in selected_slots:
                continue
            account_rows.append(
                build_slot_report(
                    registry,
                    channel,
                    channel_row,
                    slot_name,
                    slot,
                    profiles,
                    check_auth=check_auth,
                )
            )
    auth_rows = [auth for account in account_rows for auth in account.get("auth") or []]
    logical_rows = logical_account_reports(registry, account_rows)
    return {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "mode": "publish_account_center",
        "registry": str(registry_path()),
        "session_root": str(session_root(registry)),
        "check_auth": check_auth,
        "will_not_publish": True,
        "initialization": initialization,
        "accounts": account_rows,
        "logical_accounts": logical_rows,
        "summary": {
            "account_slot_count": len(account_rows),
            "logical_account_count": len(logical_rows),
            "available_count": sum(1 for row in account_rows if row.get("status") == "available"),
            "state_present_unverified_count": sum(1 for row in account_rows if row.get("status") == "state_present_unverified"),
            "login_required_count": sum(1 for row in account_rows if row.get("status") == "login_required"),
            "cli_valid_count": sum(1 for row in auth_rows if row.get("mode") == "social_auto_upload" and row.get("status") == "valid"),
            "cli_invalid_count": sum(1 for row in auth_rows if row.get("mode") == "social_auto_upload" and row.get("status") == "invalid"),
        },
        "safety": {
            "does_not_publish": True,
            "does_not_open_browser": True,
            "does_not_export_cookies": True,
            "does_not_expose_cookie_contents": True,
            "auth_check_delegates_to_upstream": check_auth,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Publish account slots without logging in or publishing.")
    parser.add_argument("--channel", action="append", help="Channel to inspect; repeat or comma-separate.")
    parser.add_argument("--slot", action="append", help="Account slot to inspect; repeat for multiple slots.")
    parser.add_argument("--check-auth", action="store_true", help="Delegate login validation to the upstream CLI.")
    parser.add_argument("--init", action="store_true", help="Create secure session storage and link the upstream cookie directory.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    report = build_report(args.channel, slots=args.slot, check_auth=args.check_auth, initialize=args.init)
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
