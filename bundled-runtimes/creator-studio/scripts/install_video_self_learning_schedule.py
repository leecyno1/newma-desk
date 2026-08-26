#!/usr/bin/env python3
"""Install the daily creator-learning pipeline as a macOS LaunchAgent."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from path_config import get_output_root


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "video" / "creator_learning_watchlist.json"
LABEL = "com.dasheng.video-self-learning"


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_launchctl(args: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/launchctl", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def build_plist(config_path: Path, config: dict, output_root: Path) -> dict:
    schedule = config.get("schedule") or {}
    logs_dir = output_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    script = ROOT / "scripts" / "run_video_creator_self_learning.py"
    path_value = ":".join(
        [
            str(Path(sys.executable).parent),
            str(Path.home() / ".local/bin"),
            str(Path.home() / ".npm-global/bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
        ]
    )
    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(script), "--config", str(config_path)],
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {
            "Hour": int(schedule.get("hour") or 22),
            "Minute": int(schedule.get("minute") or 0),
        },
        "RunAtLoad": False,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "Nice": 10,
        "ThrottleInterval": 300,
        "EnvironmentVariables": {
            "HOME": str(Path.home()),
            "PATH": path_value,
            "TZ": str(schedule.get("timezone") or "Asia/Shanghai"),
            "DASHENG_PROJECT_ROOT": str(ROOT),
        },
        "StandardOutPath": str(logs_dir / "launchd.stdout.log"),
        "StandardErrorPath": str(logs_dir / "launchd.stderr.log"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or inspect the daily Newma video self-learning LaunchAgent.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-root", default="")
    parser.add_argument("--print-only", action="store_true")
    parser.add_argument("--run-now", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    output_root = Path(
        args.output_root
        or config.get("output_root")
        or (get_output_root("video_training") / "每日博主自学习")
    ).expanduser().resolve()
    plist = build_plist(config_path, config, output_root)
    if args.print_only:
        print(plistlib.dumps(plist, fmt=plistlib.FMT_XML).decode("utf-8"))
        return 0

    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents / f"{LABEL}.plist"
    plist_path.write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=False))

    domain = f"gui/{os.getuid()}"
    run_launchctl(["bootout", domain, str(plist_path)], check=False)
    proc = run_launchctl(["bootstrap", domain, str(plist_path)], check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr or proc.stdout or "launchctl bootstrap failed")
    if args.run_now:
        run_launchctl(["kickstart", "-k", f"{domain}/{LABEL}"], check=False)
    verify = run_launchctl(["print", f"{domain}/{LABEL}"], check=False)
    print(
        json.dumps(
            {
                "status": "installed",
                "label": LABEL,
                "plist": str(plist_path),
                "schedule": plist["StartCalendarInterval"],
                "output_root": str(output_root),
                "stdout": plist["StandardOutPath"],
                "stderr": plist["StandardErrorPath"],
                "launchctl_registered": verify.returncode == 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
