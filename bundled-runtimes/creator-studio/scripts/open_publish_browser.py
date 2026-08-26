#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from path_config import get_project_root
from publish_window_policy import chrome_window_args, resolve_publish_window


ROOT = get_project_root()
CONFIG_PATH = ROOT / "configs" / "publish" / "browser_profiles.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def known_profile_keys() -> list[str]:
    payload = read_json(CONFIG_PATH)
    profiles = payload.get("profiles") or {}
    return sorted(profiles) if isinstance(profiles, dict) else []


def resolve_profile(channel: str, *, url: str | None = None) -> dict[str, Any]:
    payload = read_json(CONFIG_PATH)
    profiles = payload.get("profiles") or {}
    if channel not in profiles:
        known = ", ".join(sorted(profiles))
        raise SystemExit(f"unknown channel profile: {channel}. Known: {known}")
    row = profiles[channel]
    chrome = Path(str(payload.get("chrome_binary") or "")).expanduser()
    profile_dir = Path(str(row["profile_dir"])).expanduser()
    entry_url = url or str(row.get("entry_url") or "")
    profile = {
        "channel": channel,
        "platform": str(row.get("platform") or channel),
        "chrome_binary": str(chrome),
        "profile_dir": str(profile_dir),
        "entry_url": entry_url,
        "window": resolve_publish_window(payload.get("window_policy") if isinstance(payload, dict) else None),
    }
    if row.get("debug_port"):
        profile["debug_port"] = str(row["debug_port"])
    return profile


def platform_profile_keys(platform: str) -> list[str]:
    payload = read_json(CONFIG_PATH)
    profiles = payload.get("profiles") or {}
    if not isinstance(profiles, dict):
        return []
    return sorted(
        key for key, row in profiles.items()
        if isinstance(row, dict) and str(row.get("platform") or "").strip() == platform
    )


def open_profile(channel: str, *, url: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    profile = resolve_profile(channel, url=url)
    profile_dir = Path(profile["profile_dir"])
    profile_dir.mkdir(parents=True, exist_ok=True)
    chrome_binary = profile["chrome_binary"]
    window = profile["window"]
    window_args = chrome_window_args(window)
    if Path(chrome_binary).exists() and Path(chrome_binary).name.lower() == "google chrome":
        command = [
            "open",
            "-g",
            "-na",
            chrome_binary,
            "--args",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            *window_args,
            profile["entry_url"],
        ]
    else:
        command = [
            chrome_binary,
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            *window_args,
            profile["entry_url"],
        ]
    if profile.get("debug_port"):
        insert_at = command.index(profile["entry_url"])
        command.insert(insert_at, f"--remote-debugging-port={profile['debug_port']}")
    profile["command"] = " ".join(command)
    if dry_run:
        return profile
    subprocess.Popen(command)
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Open a persistent Newma Publish browser profile.")
    parser.add_argument("channel", nargs="?", choices=known_profile_keys())
    parser.add_argument("--platform", help="List all profile keys for a platform and exit.")
    parser.add_argument("--url", help="Override the configured entry URL.")
    parser.add_argument("--dry-run", action="store_true", help="Print the browser command without launching.")
    args = parser.parse_args()
    if args.platform:
        print(json.dumps({"platform": args.platform, "profiles": platform_profile_keys(args.platform)}, ensure_ascii=False, indent=2))
        return
    if not args.channel:
        parser.error("channel is required unless --platform is used")
    print(json.dumps(open_profile(args.channel, url=args.url, dry_run=args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
