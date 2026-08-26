#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_video_upload_package import build_package


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "vendor/publish/social-auto-upload"
PLATFORM_COMMANDS = {
    "xiaohongshu": "xiaohongshu",
    "douyin": "douyin",
    "bilibili": "bilibili",
    "wechat_channels": "tencent",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_text(command: list[str]) -> str:
    return shlex.join(command)


def social_auto_upload_root() -> Path:
    return Path(os.environ.get("SOCIAL_AUTO_UPLOAD_ROOT") or DEFAULT_ROOT).expanduser().resolve()


def resolve_launcher(root: Path) -> tuple[list[str] | None, str]:
    explicit = os.environ.get("SOCIAL_AUTO_UPLOAD_CLI")
    if explicit:
        explicit_path = Path(explicit).expanduser()
        if explicit_path.exists():
            return [str(explicit_path.resolve())], "SOCIAL_AUTO_UPLOAD_CLI"
        return None, "configured_cli_not_found"

    binary = shutil.which("sau")
    if binary:
        return [binary], "PATH"

    venv_binary = root / ".venv" / "bin" / "sau"
    if venv_binary.exists():
        return [str(venv_binary)], "upstream_venv"

    cli_script = root / "sau_cli.py"
    venv_python = root / ".venv" / "bin" / "python"
    if cli_script.exists() and venv_python.exists():
        return [str(venv_python), str(cli_script)], "upstream_venv_python"
    if cli_script.exists():
        return [sys.executable, str(cli_script)], "current_python_fallback"
    return None, "missing_sau_cli"


def trim_output(value: str | None, limit: int = 8000) -> str:
    text = (value or "").strip()
    return text[-limit:]


def run_command(command: list[str], *, cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "timed_out": True,
            "stdout": trim_output(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr": trim_output(exc.stderr if isinstance(exc.stderr, str) else ""),
        }
    except OSError as exc:
        return {
            "returncode": None,
            "timed_out": False,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "returncode": proc.returncode,
        "timed_out": False,
        "stdout": trim_output(proc.stdout),
        "stderr": trim_output(proc.stderr),
    }


def append_optional(command: list[str], flag: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    command.extend([flag, str(value)])


def build_commands(request: dict[str, Any], launcher: list[str]) -> tuple[list[str], list[str], list[str]]:
    platform = str(request.get("platform") or "")
    cli_platform = PLATFORM_COMMANDS.get(platform)
    if not cli_platform:
        raise ValueError(f"unsupported_social_auto_upload_platform:{platform}")

    upload = request.get("upload") or {}
    account = str(upload.get("account_name") or "").strip()
    if not account:
        raise ValueError("missing_social_auto_upload_account_name")

    auth_command = [*launcher, cli_platform, "check", "--account", account]
    login_command = [*launcher, cli_platform, "login", "--account", account, "--headed"]
    command = [
        *launcher,
        cli_platform,
        "upload-video",
        "--account",
        account,
        "--file",
        str(upload["video"]),
        "--title",
        str(upload["title"]),
    ]
    append_optional(command, "--desc", upload.get("description"))
    tags = upload.get("tags") or []
    if tags:
        append_optional(command, "--tags", ",".join(str(tag).lstrip("#") for tag in tags if str(tag).strip()))
    append_optional(command, "--schedule", upload.get("scheduled_at"))
    append_optional(command, "--thumbnail", upload.get("cover"))

    options = upload.get("platform_options") or {}
    if platform == "bilibili":
        tid = options.get("tid") or options.get("category_id")
        if tid in (None, ""):
            raise ValueError("missing_bilibili_tid")
        command.extend(["--tid", str(tid)])
    elif platform == "wechat_channels":
        append_optional(command, "--thumbnail-landscape", options.get("thumbnail_landscape"))
        append_optional(command, "--thumbnail-portrait", options.get("thumbnail_portrait"))
        append_optional(command, "--short-title", options.get("short_title"))
        append_optional(command, "--category", options.get("category"))
        if options.get("draft") is True:
            command.append("--draft")
    elif platform == "douyin":
        append_optional(command, "--declaration", options.get("declaration"))

    if platform != "bilibili":
        command.append("--headless" if upload.get("headless") is True else "--headed")
        if upload.get("debug") is True:
            command.append("--debug")
    return auth_command, login_command, command


def build_result(
    channel_pack: Path,
    *,
    confirm_execute: bool,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    package = build_package(channel_pack)
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": now_iso(),
        "adapter": "social-auto-upload",
        "source_channel_pack": str(channel_pack.resolve()),
        "confirm_execute": confirm_execute,
        "requires_user_confirmation": True,
    }
    if package.get("status") != "ready":
        return {
            **base,
            "success": False,
            "status": "blocked_invalid_channel_pack",
            "will_not_publish": True,
            "errors": package.get("errors") or [],
        }

    request_path = Path(package["outputs"]["social_auto_upload_request"])
    request = read_json(request_path)
    root = social_auto_upload_root()
    launcher, launcher_source = resolve_launcher(root)
    base.update(
        {
            "platform": request.get("platform"),
            "account": (request.get("upload") or {}).get("account_name"),
            "request": str(request_path.resolve()),
            "upstream_root": str(root),
            "launcher_source": launcher_source,
        }
    )
    if not root.exists():
        return {
            **base,
            "success": False,
            "status": "blocked_missing_upstream",
            "will_not_publish": True,
            "error": f"social-auto-upload root not found: {root}",
        }
    if not launcher:
        return {
            **base,
            "success": False,
            "status": "blocked_missing_cli",
            "will_not_publish": True,
            "error": "sau CLI is not installed in PATH or the upstream virtual environment.",
        }

    try:
        auth_command, login_command, upload_command = build_commands(request, launcher)
    except (KeyError, TypeError, ValueError) as exc:
        return {
            **base,
            "success": False,
            "status": "blocked_invalid_upload_request",
            "will_not_publish": True,
            "error": str(exc),
        }

    preview = {
        "auth_check_command": command_text(auth_command),
        "login_command": command_text(login_command),
        "upload_command": command_text(upload_command),
    }
    if not confirm_execute:
        return {
            **base,
            **preview,
            "success": True,
            "status": "ready_for_user_confirmation",
            "will_not_publish": True,
            "verification_status": "needs_manual_verification",
        }

    auth = run_command(auth_command, cwd=root, timeout_seconds=min(timeout_seconds, 120))
    if auth.get("returncode") != 0:
        return {
            **base,
            **preview,
            "success": False,
            "status": "blocked_auth_required",
            "will_not_publish": True,
            "error": "social-auto-upload account login is missing or expired",
            "platform_response": {"auth_check": auth},
        }

    execution = run_command(upload_command, cwd=root, timeout_seconds=timeout_seconds)
    if execution.get("returncode") != 0:
        return {
            **base,
            **preview,
            "success": False,
            "status": "failed",
            "will_not_publish": False,
            "error": "social-auto-upload command failed or timed out",
            "verification_status": "failed",
            "platform_response": {"auth_check": auth, "upload": execution},
        }

    upload = request.get("upload") or {}
    options = upload.get("platform_options") or {}
    if options.get("draft") is True:
        status = "draft"
    elif upload.get("scheduled_at"):
        status = "scheduled"
    else:
        status = "pending_verification"
    return {
        **base,
        **preview,
        "success": True,
        "status": status,
        "will_not_publish": False,
        "verification_status": "needs_manual_verification",
        "platform_response": {"auth_check": auth, "upload": execution},
        "notes": "CLI returned success; platform URL or draft ID must still be recovered before verification.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely preview or execute social-auto-upload for one channel pack.")
    parser.add_argument("--channel-pack", required=True)
    parser.add_argument("--confirm-execute", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = build_result(
        Path(args.channel_pack).expanduser().resolve(),
        confirm_execute=args.confirm_execute,
        timeout_seconds=max(args.timeout_seconds, 1),
    )
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
