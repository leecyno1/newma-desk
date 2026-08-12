import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_descriptor_path() -> Path:
    return _default_project_root() / "config" / "external-mod-runtimes.json"


@lru_cache(maxsize=4)
def load_runtime_descriptor(
    descriptor_path: Path | None = None,
) -> dict[str, Any]:
    path = (descriptor_path or _default_descriptor_path()).resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schemaVersion") != "1.0":
        raise ValueError("unsupported external Mod runtime descriptor")
    if not isinstance(value.get("roots"), list) or not isinstance(
        value.get("runtimes"), list
    ):
        raise ValueError("invalid external Mod runtime descriptor")
    return value


def _runtime_by_id(descriptor: Mapping[str, Any], runtime_id: str) -> Mapping[str, Any]:
    for runtime in descriptor["runtimes"]:
        if isinstance(runtime, dict) and runtime.get("id") == runtime_id:
            return runtime
    raise KeyError(f"unknown external Mod runtime: {runtime_id}")


def _configured_env(env: Mapping[str, str], name: str) -> str:
    prefixes = ("NEWMA_DESK_", "NEWMA_DOCK_", "VIBEDESK_")
    suffix = next(
        (name.removeprefix(prefix) for prefix in prefixes if name.startswith(prefix)),
        None,
    )
    if suffix is None:
        return env.get(name, "").strip()
    for prefix in prefixes:
        configured = env.get(f"{prefix}{suffix}", "").strip()
        if configured:
            return configured
    return ""


def _resolve_roots(
    descriptor: Mapping[str, Any],
    *,
    project_root: Path,
    home: Path,
    env: Mapping[str, str],
) -> dict[str, Path]:
    roots = {"repo": project_root.resolve()}
    for root in descriptor["roots"]:
        if not isinstance(root, dict):
            raise ValueError("runtime root must be an object")
        root_id = str(root["id"])
        configured = _configured_env(env, str(root["env"]))
        if configured:
            path = Path(configured).expanduser()
            roots[root_id] = (
                path if path.is_absolute() else project_root / path
            ).resolve()
            continue
        fallback = root.get("fallback")
        if not isinstance(fallback, dict):
            raise ValueError("runtime root fallback must be an object")
        relative = Path(str(fallback["path"])).expanduser()
        if fallback.get("type") == "repo-relative":
            roots[root_id] = (project_root / relative).resolve()
        elif fallback.get("type") == "home-relative":
            roots[root_id] = (home / relative).resolve()
        else:
            raise ValueError("unsupported runtime root fallback")
    return roots


def resolve_runtime_workspace(
    runtime_id: str,
    workspace_name: str,
    *,
    descriptor_path: Path | None = None,
    project_root: Path | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    descriptor = load_runtime_descriptor(descriptor_path)
    runtime = _runtime_by_id(descriptor, runtime_id)
    workspaces = runtime.get("workspaces")
    if not isinstance(workspaces, dict) or workspace_name not in workspaces:
        raise KeyError(f"unknown {runtime_id} workspace: {workspace_name}")
    workspace = workspaces[workspace_name]
    if not isinstance(workspace, dict):
        raise ValueError("runtime workspace must be an object")
    root = (project_root or _default_project_root()).resolve()
    environment = os.environ if env is None else env
    configured = _configured_env(environment, str(workspace["env"]))
    if configured:
        path = Path(configured).expanduser()
        return (path if path.is_absolute() else root / path).resolve()
    roots = _resolve_roots(
        descriptor,
        project_root=root,
        home=(home or Path.home()).resolve(),
        env=environment,
    )
    candidates = workspace.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("runtime workspace candidates are required")
    resolved: list[Path] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("runtime workspace candidate must be an object")
        root_path = roots.get(str(candidate["root"]))
        if root_path is None:
            raise ValueError("runtime workspace candidate references an unknown root")
        path = (root_path / str(candidate["path"])).resolve()
        resolved.append(path)
        if path.exists():
            return path
    return resolved[0]


def resolve_runtime_origin(
    runtime_id: str,
    endpoint_name: str,
    *,
    descriptor_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    descriptor = load_runtime_descriptor(descriptor_path)
    runtime = _runtime_by_id(descriptor, runtime_id)
    endpoints = runtime.get("endpoints")
    if not isinstance(endpoints, dict) or endpoint_name not in endpoints:
        raise KeyError(f"unknown {runtime_id} endpoint: {endpoint_name}")
    endpoint = endpoints[endpoint_name]
    if not isinstance(endpoint, dict):
        raise ValueError("runtime endpoint must be an object")
    environment = os.environ if env is None else env
    value = _configured_env(environment, str(endpoint["env"])) or str(
        endpoint["defaultOrigin"]
    )
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("runtime endpoint must be an HTTP(S) origin")
    return f"{parsed.scheme}://{parsed.netloc}"


def default_external_origins(
    *,
    descriptor_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    descriptor = load_runtime_descriptor(descriptor_path)
    origins: list[str] = []
    for runtime in descriptor["runtimes"]:
        for endpoint_name in runtime.get("endpoints", {}):
            origin = resolve_runtime_origin(
                str(runtime["id"]),
                str(endpoint_name),
                descriptor_path=descriptor_path,
                env=env,
            )
            if origin not in origins:
                origins.append(origin)
    return origins
