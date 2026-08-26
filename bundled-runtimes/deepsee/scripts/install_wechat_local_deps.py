#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEPS_FILE = ROOT / "deps" / "wechat-local-deps.json"
INSTALL_ROOT = ROOT / ".local" / "wechat-local"
VENDORED_CHATLOG_SOURCE = ROOT / "third_party" / "chatlog"


def detect_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        os_key = "darwin"
    elif system == "windows":
        os_key = "windows"
    elif system == "linux":
        os_key = "linux"
    else:
        raise SystemExit(f"unsupported system: {system}")
    if machine in {"arm64", "aarch64"}:
        arch_key = "arm64"
    elif machine in {"x86_64", "amd64", "x64"}:
        arch_key = "amd64"
    else:
        raise SystemExit(f"unsupported arch: {machine}")
    return f"{os_key}-{arch_key}"


def github_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def release_assets(repo: str, release: str) -> list[dict]:
    if release == "latest":
        url = f"https://api.github.com/repos/{repo}/releases/latest"
    else:
        url = f"https://api.github.com/repos/{repo}/releases/tags/{release}"
    data = github_json(url)
    return list(data.get("assets") or [])


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=180) as resp, dest.open("wb") as fh:
        fh.write(resp.read())


def install_asset(tool: str, spec: dict, platform_key: str) -> Path:
    asset_name = (spec.get("assets") or {}).get(platform_key)
    if not asset_name:
        raise SystemExit(f"{tool}: no asset for {platform_key}")
    assets = release_assets(str(spec["repo"]), str(spec.get("release") or "latest"))
    asset = next((item for item in assets if item.get("name") == asset_name), None)
    if not asset:
        names = ", ".join(str(item.get("name")) for item in assets)
        raise SystemExit(f"{tool}: asset {asset_name!r} not found. available: {names}")

    tool_dir = INSTALL_ROOT / tool
    tool_dir.mkdir(parents=True, exist_ok=True)
    raw_dest = tool_dir / asset_name
    print(f"download {tool}: {asset_name}")
    download(str(asset["browser_download_url"]), raw_dest)

    executable = raw_dest
    if raw_dest.suffix.lower() == ".zip":
        with ZipFile(raw_dest) as zf:
            zf.extractall(tool_dir)
        candidates = [
            p
            for p in tool_dir.rglob("*")
            if p.is_file()
            and (
                p.name in {"chatlog", "chatlog.exe", "wx", "wx.exe"}
                or p.name.startswith("chatlog")
                or p.name.startswith("wx-")
            )
        ]
        if candidates:
            executable = sorted(candidates, key=lambda p: len(str(p)))[0]

    if platform.system().lower() != "windows":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    marker = tool_dir / "BIN_PATH"
    marker.write_text(str(executable), encoding="utf-8")
    print(f"installed {tool}: {executable}")
    return executable


def build_vendored_chatlog(platform_key: str) -> Path:
    native_key = detect_key()
    if platform_key != native_key:
        raise RuntimeError(
            f"vendored chatlog builds natively; requested {platform_key}, current platform is {native_key}"
        )
    if not (VENDORED_CHATLOG_SOURCE / "go.mod").exists():
        raise RuntimeError(f"vendored chatlog source missing: {VENDORED_CHATLOG_SOURCE}")
    go_bin = shutil.which("go")
    if not go_bin:
        raise RuntimeError("Go 1.24+ is required to build the vendored chatlog source")

    tool_dir = INSTALL_ROOT / "chatlog_alpha"
    tool_dir.mkdir(parents=True, exist_ok=True)
    executable = tool_dir / ("chatlog.exe" if platform.system().lower() == "windows" else "chatlog")
    env = {**os.environ, "CGO_ENABLED": os.environ.get("CGO_ENABLED", "1")}
    command = [
        go_bin,
        "build",
        "-trimpath",
        "-ldflags",
        "-s -w -X github.com/sjzar/chatlog/pkg/version.Version=vendored-bfb031f",
        "-o",
        str(executable),
        "./main.go",
    ]
    print(f"build chatlog_alpha from vendored source: {VENDORED_CHATLOG_SOURCE}")
    subprocess.run(command, cwd=VENDORED_CHATLOG_SOURCE, env=env, check=True)
    if platform.system().lower() != "windows":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (tool_dir / "BIN_PATH").write_text(str(executable), encoding="utf-8")
    print(f"installed chatlog_alpha: {executable}")
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Deepsee local WeChat dependencies")
    parser.add_argument("--tool", choices=["all", "chatlog_alpha", "wx_cli"], default="all")
    parser.add_argument("--platform", default=detect_key(), help="darwin-arm64/windows-amd64/linux-amd64...")
    args = parser.parse_args()

    deps = json.loads(DEPS_FILE.read_text(encoding="utf-8"))
    selected = deps.items() if args.tool == "all" else [(args.tool, deps[args.tool])]
    installed: dict[str, str] = {}
    for tool, spec in selected:
        try:
            if tool == "chatlog_alpha":
                installed[tool] = str(build_vendored_chatlog(args.platform))
            else:
                installed[tool] = str(install_asset(tool, spec, args.platform))
        except Exception as exc:
            print(f"ERROR {tool}: {exc}", file=sys.stderr)
            if args.tool != "all":
                return 1
    print(json.dumps({"platform": args.platform, "installed": installed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
