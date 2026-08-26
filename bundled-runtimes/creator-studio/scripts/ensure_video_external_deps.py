#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESERVED_ROOT = PROJECT_ROOT / "vendor" / "reserved"


@dataclass(frozen=True)
class ExternalDependency:
    name: str
    repo: str
    default_path_env: str
    default_path: Path
    package_manager: str
    build_after_install: bool = False


DEPENDENCIES: dict[str, ExternalDependency] = {
    "html-video": ExternalDependency(
        name="html-video",
        repo="https://github.com/nexu-io/html-video.git",
        default_path_env="HTML_VIDEO_ROOT",
        default_path=RESERVED_ROOT / "render" / "html-video",
        package_manager="pnpm",
        build_after_install=True,
    ),
    "html-anything": ExternalDependency(
        name="html-anything",
        repo="https://github.com/nexu-io/html-anything.git",
        default_path_env="HTML_ANYTHING_ROOT",
        default_path=RESERVED_ROOT / "render" / "html-anything",
        package_manager="pnpm",
        build_after_install=False,
    ),
    "text-to-lottie": ExternalDependency(
        name="text-to-lottie",
        repo="https://github.com/diffusionstudio/lottie.git",
        default_path_env="TEXT_TO_LOTTIE_ROOT",
        default_path=RESERVED_ROOT / "video" / "text-to-lottie",
        package_manager="npm",
        build_after_install=False,
    ),
    "claude-real-video": ExternalDependency(
        name="claude-real-video",
        repo="https://github.com/HUANGCHIHHUNGLeo/claude-real-video.git",
        default_path_env="CLAUDE_REAL_VIDEO_ROOT",
        default_path=RESERVED_ROOT / "video" / "claude-real-video",
        package_manager="python",
        build_after_install=False,
    ),
    "video-use": ExternalDependency(
        name="video-use",
        repo="https://github.com/browser-use/video-use.git",
        default_path_env="VIDEO_USE_ROOT",
        default_path=RESERVED_ROOT / "video" / "video-use",
        package_manager="python",
    ),
    "freecut": ExternalDependency(
        name="freecut",
        repo="https://github.com/Moh4696/freecut.git",
        default_path_env="FREECUT_ROOT",
        default_path=RESERVED_ROOT / "video" / "freecut",
        package_manager="python",
    ),
    "video-wrapper": ExternalDependency(
        name="video-wrapper",
        repo="https://github.com/op7418/Video-Wrapper-Skills.git",
        default_path_env="VIDEO_WRAPPER_ROOT",
        default_path=RESERVED_ROOT / "video" / "video-wrapper",
        package_manager="python",
    ),
    "claude-shorts": ExternalDependency(
        name="claude-shorts",
        repo="https://github.com/AgriciDaniel/claude-shorts.git",
        default_path_env="CLAUDE_SHORTS_ROOT",
        default_path=RESERVED_ROOT / "video" / "claude-shorts",
        package_manager="python",
    ),
    "hyperframes": ExternalDependency(
        name="hyperframes",
        repo="https://github.com/heygen-com/hyperframes.git",
        default_path_env="HYPERFRAMES_ROOT",
        default_path=RESERVED_ROOT / "video" / "hyperframes",
        package_manager="bun",
    ),
    "talking-head-editor": ExternalDependency(
        name="talking-head-editor",
        repo="https://github.com/chrislema/videoeditor.git",
        default_path_env="TALKING_HEAD_EDITOR_ROOT",
        default_path=RESERVED_ROOT / "video" / "talking-head-editor",
        package_manager="python",
    ),
}


HTML_VIDEO_MOTION_PACKAGES = ["gsap", "lottie-web"]


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def dependency_path(spec: ExternalDependency) -> Path:
    return Path(os.getenv(spec.default_path_env, str(spec.default_path))).expanduser().resolve()


def git_head(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    proc = run(["git", "rev-parse", "--short", "HEAD"], cwd=path)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def package_manager_from_package_json(path: Path) -> str | None:
    package_json = path / "package.json"
    if not package_json.exists():
        return None
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = str(payload.get("packageManager") or "")
    return value.split("@", 1)[0] if value else None


def package_json_dependencies(path: Path) -> dict[str, str]:
    package_json = path / "package.json"
    if not package_json.exists():
        return {}
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    deps = {}
    for key in ["dependencies", "devDependencies", "optionalDependencies"]:
        value = payload.get(key) or {}
        if isinstance(value, dict):
            deps.update({str(k): str(v) for k, v in value.items()})
    return deps


def motion_library_status(path: Path) -> dict[str, Any]:
    deps = package_json_dependencies(path)
    node_modules = path / "node_modules"
    return {
        "required": HTML_VIDEO_MOTION_PACKAGES,
        "package_json": {name: deps.get(name) for name in HTML_VIDEO_MOTION_PACKAGES},
        "files": {
            "gsap": any(node_modules.glob("**/gsap/dist/gsap.min.js")) if node_modules.exists() else False,
            "lottie-web": any(node_modules.glob("**/lottie-web/build/player/lottie_light.min.js")) if node_modules.exists() else False,
        },
        "ready": all(deps.get(name) for name in HTML_VIDEO_MOTION_PACKAGES),
    }


def inspect_dependency(spec: ExternalDependency) -> dict[str, Any]:
    path = dependency_path(spec)
    package_manager = package_manager_from_package_json(path) or spec.package_manager
    pyproject_exists = (path / "pyproject.toml").exists()
    payload = {
        "name": spec.name,
        "repo": spec.repo,
        "path_env": spec.default_path_env,
        "path": str(path),
        "exists": path.exists(),
        "is_git_repo": (path / ".git").exists(),
        "package_json": (path / "package.json").exists(),
        "pyproject_toml": pyproject_exists,
        "package_manager": package_manager,
        "git_head": git_head(path),
        "status": "ready" if path.exists() and ((path / "package.json").exists() or pyproject_exists) else "missing",
    }
    payload["venv_python"] = str(path / ".venv" / "bin" / "python")
    payload["venv_ready"] = (path / ".venv" / "bin" / "python").exists()
    payload["node_modules_ready"] = (path / "node_modules").exists()
    if package_manager == "python":
        payload["dependency_ready"] = payload["venv_ready"]
        if payload["is_git_repo"] and payload["venv_ready"]:
            payload["status"] = "ready"
    elif package_manager in {"npm", "pnpm", "bun"}:
        payload["dependency_ready"] = payload["node_modules_ready"]
    if spec.name == "claude-real-video":
        payload["source_package"] = (path / "src" / "claude_real_video").exists()
    if spec.name == "html-video":
        payload["motion_libraries"] = motion_library_status(path)
    return payload


def ensure_dependency(
    spec: ExternalDependency,
    *,
    mode: str,
    install_node_deps: bool,
) -> dict[str, Any]:
    path = dependency_path(spec)
    actions: list[dict[str, Any]] = []
    path.parent.mkdir(parents=True, exist_ok=True)

    if mode in {"install", "update"} and not path.exists():
        proc = run(["git", "clone", spec.repo, str(path)])
        actions.append({"action": "git_clone", "returncode": proc.returncode, "stderr": proc.stderr[-1200:]})
        if proc.returncode != 0:
            return {**inspect_dependency(spec), "actions": actions, "status": "error"}

    if mode == "update" and (path / ".git").exists():
        proc = run(["git", "pull", "--ff-only"], cwd=path)
        actions.append({"action": "git_pull_ff_only", "returncode": proc.returncode, "stderr": proc.stderr[-1200:]})
        if proc.returncode != 0:
            return {**inspect_dependency(spec), "actions": actions, "status": "error"}

    if install_node_deps and spec.package_manager == "python" and path.exists() and (path / "pyproject.toml").exists():
        python = Path(".venv_media/bin/python")
        python_bin = str(python) if python.exists() else "python3"
        proc = run([python_bin, "-m", "pip", "install", "-e", str(path)])
        actions.append({"action": "pip_install_editable", "returncode": proc.returncode, "stderr": proc.stderr[-1200:]})
        if proc.returncode != 0:
            return {**inspect_dependency(spec), "actions": actions, "status": "error"}

    if install_node_deps and path.exists() and (path / "package.json").exists():
        if spec.name == "html-video":
            motion = motion_library_status(path)
            missing = [name for name in HTML_VIDEO_MOTION_PACKAGES if not motion["package_json"].get(name)]
            if missing:
                proc = run([spec.package_manager, "add", "-w", *missing], cwd=path)
                actions.append({"action": f"{spec.package_manager}_add_motion_libraries", "packages": missing, "returncode": proc.returncode, "stderr": proc.stderr[-1200:]})
                if proc.returncode != 0:
                    return {**inspect_dependency(spec), "actions": actions, "status": "error"}
        proc = run([spec.package_manager, "install"], cwd=path)
        actions.append({"action": f"{spec.package_manager}_install", "returncode": proc.returncode, "stderr": proc.stderr[-1200:]})
        if proc.returncode != 0:
            return {**inspect_dependency(spec), "actions": actions, "status": "error"}
        if spec.build_after_install:
            proc = run([spec.package_manager, "-r", "build"], cwd=path)
            actions.append({"action": f"{spec.package_manager}_recursive_build", "returncode": proc.returncode, "stderr": proc.stderr[-1200:]})
            if proc.returncode != 0:
                return {**inspect_dependency(spec), "actions": actions, "status": "error"}

    inspected = inspect_dependency(spec)
    inspected["actions"] = actions
    return inspected


def select_dependencies(dep: str) -> list[ExternalDependency]:
    if dep == "all":
        return list(DEPENDENCIES.values())
    return [DEPENDENCIES[dep]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check or install Newma video external dependencies without version locking.")
    parser.add_argument("--dep", choices=["all", *sorted(DEPENDENCIES)], default="all")
    parser.add_argument("--mode", choices=["check", "install", "update"], default="check")
    parser.add_argument("--install-node-deps", action="store_true", help="Run package-manager install; html-video also builds after install.")
    parser.add_argument("--output", help="Optional JSON report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = {
        "schema_version": "dasheng.video_external_deps.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version_locking": False,
        "mode": args.mode,
        "dependencies": [
            ensure_dependency(spec, mode=args.mode, install_node_deps=args.install_node_deps)
            for spec in select_dependencies(args.dep)
        ],
    }
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
