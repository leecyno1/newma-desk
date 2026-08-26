"""Local Circle service supervision with health-based recovery."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True, slots=True)
class LocalServiceConfig:
    host: str
    port: int
    product_root: Path
    catalog_root: Path
    web_root: Path
    state_path: Path
    log_path: Path
    project_root: Path
    health_interval: float = 5.0
    health_failure_limit: int = 3
    startup_grace: float = 15.0
    repair_catalog_on_start: bool = False

    @property
    def health_url(self) -> str:
        return f"http://{self.host}:{self.port}/healthz"

    def normalized(self) -> LocalServiceConfig:
        root = self.project_root.resolve()
        return replace(
            self,
            product_root=(root / self.product_root).resolve()
            if not self.product_root.is_absolute()
            else self.product_root.resolve(),
            catalog_root=(root / self.catalog_root).resolve()
            if not self.catalog_root.is_absolute()
            else self.catalog_root.resolve(),
            web_root=(root / self.web_root).resolve()
            if not self.web_root.is_absolute()
            else self.web_root.resolve(),
            state_path=(root / self.state_path).resolve()
            if not self.state_path.is_absolute()
            else self.state_path.resolve(),
            log_path=(root / self.log_path).resolve()
            if not self.log_path.is_absolute()
            else self.log_path.resolve(),
            project_root=root,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_state(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _fetch_health(
    url: str,
    *,
    timeout: float = 1.5,
    require_ok: bool = True,
) -> dict[str, Any] | None:
    try:
        with urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read())
    except (OSError, TypeError, ValueError, URLError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if require_ok and payload.get("status") != "ok":
        return None
    return payload


def inspect_service(config: LocalServiceConfig) -> dict[str, Any]:
    normalized = config.normalized()
    state = _read_state(normalized.state_path)
    supervisor_pid = int(state.get("supervisor_pid", 0)) if state else 0
    supervisor_alive = _process_alive(supervisor_pid)
    health = _fetch_health(normalized.health_url)
    if supervisor_alive and health is not None:
        status = "running"
    elif supervisor_alive:
        status = "degraded"
    elif health is not None:
        status = "unmanaged"
    else:
        status = "stopped"
    return {
        "health": health,
        "health_url": normalized.health_url,
        "log_path": str(normalized.log_path),
        "state_path": str(normalized.state_path),
        "status": status,
        "supervisor_pid": supervisor_pid if supervisor_alive else None,
    }


def _module_command(action: str, config: LocalServiceConfig) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "seven_cycle_platform.local_service",
        action,
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--product-root",
        str(config.product_root),
        "--catalog-root",
        str(config.catalog_root),
        "--web-root",
        str(config.web_root),
        "--state-path",
        str(config.state_path),
        "--log-path",
        str(config.log_path),
        "--project-root",
        str(config.project_root),
        "--health-interval",
        str(config.health_interval),
        "--health-failure-limit",
        str(config.health_failure_limit),
        "--startup-grace",
        str(config.startup_grace),
    ]
    if config.repair_catalog_on_start:
        command.append("--repair-catalog-on-start")
    return command


def repair_latest_catalog_device_drift(
    product_root: Path,
    catalog_root: Path,
    web_root: Path,
) -> dict[str, object]:
    """Repair the latest catalog only after strict device-drift attestation."""

    from seven_cycle_platform.catalog import (
        build_catalog,
        inspect_catalog_device_identity_drift,
        open_catalog,
    )
    from seven_cycle_platform.deployment import (
        install_catalog_repair_transaction,
        recover_pending_catalog_repair,
        verify_deployment_for_catalog_repair,
    )
    from seven_cycle_platform.storage.manifest import load_manifest, verify_manifest
    from seven_cycle_platform.storage.run_context import (
        RUN_ID_PATTERN,
        canonical_json_bytes,
    )

    normalized_product_root = Path(product_root).resolve(strict=True)
    normalized_catalog_root = Path(catalog_root).resolve(strict=True)
    normalized_web_root = Path(web_root).resolve(strict=True)
    for directory in (
        normalized_product_root,
        normalized_catalog_root,
        normalized_web_root,
    ):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise RuntimeError("catalog repair roots must be real directories")

    recovery = recover_pending_catalog_repair(
        product_root=normalized_product_root,
        catalog_root=normalized_catalog_root,
        web_root=normalized_web_root,
    )

    latest_path = normalized_product_root / "latest.json"
    try:
        latest_stat = latest_path.lstat()
        latest_identity = latest_stat.st_dev, latest_stat.st_ino
        pointer_bytes = latest_path.read_bytes()
        pointer = json.loads(pointer_bytes)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("latest run pointer is invalid") from error
    if (
        not stat.S_ISREG(latest_stat.st_mode)
        or not isinstance(pointer, dict)
        or set(pointer) != {"run_id"}
        or not isinstance(pointer.get("run_id"), str)
        or not RUN_ID_PATTERN.fullmatch(pointer["run_id"])
        or pointer_bytes != canonical_json_bytes(pointer) + b"\n"
        or (latest_path.lstat().st_dev, latest_path.lstat().st_ino)
        != latest_identity
    ):
        raise RuntimeError("latest run pointer is invalid")

    run_id = pointer["run_id"]
    run_dir = normalized_product_root / "runs" / run_id
    manifest = load_manifest(run_dir)
    manifest = verify_manifest(run_dir, expected=manifest)
    catalog_path = normalized_catalog_root / f"{run_id}.duckdb"
    evidence = inspect_catalog_device_identity_drift(
        run_dir,
        catalog_path,
        expected_manifest=manifest,
    )
    if evidence is None:
        if recovery is not None:
            return recovery
        return {"action": "not_needed", "run_id": run_id}
    deployment = verify_deployment_for_catalog_repair(
        product_root=normalized_product_root,
        web_root=normalized_web_root,
        run_id=run_id,
        catalog_checksum=evidence.previous_catalog_checksum,
    )
    candidate_directory = Path(
        tempfile.mkdtemp(
            dir=normalized_catalog_root,
            prefix=f".{run_id}.device-repair.",
        )
    )
    candidate_path = candidate_directory / "catalog.duckdb"
    try:
        result = build_catalog(
            run_dir,
            candidate_path,
            expected_manifest=manifest,
        )
        if result.catalog_checksum != evidence.replacement_catalog_checksum:
            raise RuntimeError(
                "candidate catalog checksum changed after drift verification"
            )
        with open_catalog(
            candidate_path,
            run_dir=run_dir,
            expected_manifest=manifest,
        ):
            pass
        manifest = verify_manifest(run_dir, expected=manifest)
        confirmed_evidence = inspect_catalog_device_identity_drift(
            run_dir,
            catalog_path,
            expected_manifest=manifest,
        )
        if confirmed_evidence != evidence:
            raise RuntimeError(
                "catalog drift evidence changed before transactional repair"
            )
        try:
            latest_stat_now = latest_path.lstat()
            latest_content_now = latest_path.read_bytes()
        except OSError as error:
            raise RuntimeError("latest run pointer changed before repair") from error
        if (
            (latest_stat_now.st_dev, latest_stat_now.st_ino) != latest_identity
            or latest_content_now != pointer_bytes
            or json.loads(latest_content_now).get("run_id") != run_id
        ):
            raise RuntimeError("latest run changed before transactional repair")
        deployment_id = install_catalog_repair_transaction(
            snapshot=deployment,
            catalog_path=catalog_path,
            catalog_identity=(
                evidence.catalog_device,
                evidence.catalog_inode,
            ),
            candidate_catalog_path=candidate_path,
            latest_content=pointer_bytes,
            latest_identity=latest_identity,
            latest_path=latest_path,
            replacement_catalog_checksum=result.catalog_checksum,
        )
        with open_catalog(
            catalog_path,
            run_dir=run_dir,
            expected_manifest=manifest,
        ):
            pass
    finally:
        repair_journal = normalized_product_root / ".catalog-repair-transaction.json"
        if not repair_journal.exists():
            candidate_path.unlink(missing_ok=True)
            try:
                candidate_directory.rmdir()
            except OSError:
                pass
    return {
        "action": "repaired_device_drift",
        "catalog_checksum": result.catalog_checksum,
        "deployment_id": deployment_id,
        "run_id": run_id,
    }


def start_service(
    config: LocalServiceConfig,
    *,
    startup_timeout: float = 30.0,
) -> dict[str, Any]:
    normalized = config.normalized()
    current = inspect_service(normalized)
    if current["status"] == "running":
        return {**current, "action": "already_running"}
    if current["status"] == "unmanaged":
        raise RuntimeError(
            f"{normalized.health_url} is already served by an unmanaged process; "
            "stop it before starting the Circle supervisor"
        )
    if current["supervisor_pid"] is not None:
        raise RuntimeError("Circle supervisor is alive but health is degraded; restart it")

    normalized.log_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.state_path.parent.mkdir(parents=True, exist_ok=True)
    with normalized.log_path.open("ab", buffering=0) as log_file:
        process = subprocess.Popen(
            _module_command("supervise", normalized),
            cwd=normalized.project_root,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    _write_state(
        normalized.state_path,
        {
            "child_pid": None,
            "health_url": normalized.health_url,
            "project_root": str(normalized.project_root),
            "restart_count": 0,
            "started_at": _utc_now(),
            "supervisor_pid": process.pid,
            "updated_at": _utc_now(),
        },
    )

    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        health = _fetch_health(normalized.health_url)
        if health is not None:
            return {
                **inspect_service(normalized),
                "action": "started",
            }
        if process.poll() is not None:
            break
        time.sleep(0.25)

    if process.poll() is None:
        process.terminate()
    raise RuntimeError(
        f"Circle did not become healthy within {startup_timeout:g}s; "
        f"inspect {normalized.log_path}"
    )


def stop_service(
    config: LocalServiceConfig,
    *,
    shutdown_timeout: float = 15.0,
) -> dict[str, Any]:
    normalized = config.normalized()
    state = _read_state(normalized.state_path)
    supervisor_pid = int(state.get("supervisor_pid", 0)) if state else 0
    if not _process_alive(supervisor_pid):
        normalized.state_path.unlink(missing_ok=True)
        return {**inspect_service(normalized), "action": "already_stopped"}
    if state and state.get("project_root") != str(normalized.project_root):
        raise RuntimeError("service state belongs to a different project root")

    os.kill(supervisor_pid, signal.SIGTERM)
    deadline = time.monotonic() + shutdown_timeout
    while time.monotonic() < deadline and _process_alive(supervisor_pid):
        time.sleep(0.1)
    if _process_alive(supervisor_pid):
        os.kill(supervisor_pid, signal.SIGKILL)
    normalized.state_path.unlink(missing_ok=True)
    return {**inspect_service(normalized), "action": "stopped"}


def _terminate_child(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def supervise(config: LocalServiceConfig) -> int:
    normalized = config.normalized()
    stopping = False
    restart_count = 0
    child: subprocess.Popen[bytes] | None = None

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        if child is not None:
            _terminate_child(child)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    try:
        while not stopping:
            child = subprocess.Popen(
                _module_command("serve-child", normalized),
                cwd=normalized.project_root,
                stdin=subprocess.DEVNULL,
            )
            child_started = time.monotonic()
            failed_health_checks = 0
            _write_state(
                normalized.state_path,
                {
                    "child_pid": child.pid,
                    "health_url": normalized.health_url,
                    "project_root": str(normalized.project_root),
                    "restart_count": restart_count,
                    "started_at": _utc_now(),
                    "supervisor_pid": os.getpid(),
                    "updated_at": _utc_now(),
                },
            )
            while not stopping and child.poll() is None:
                time.sleep(normalized.health_interval)
                if time.monotonic() - child_started < normalized.startup_grace:
                    continue
                if _fetch_health(normalized.health_url, require_ok=False) is not None:
                    failed_health_checks = 0
                    continue
                failed_health_checks += 1
                if failed_health_checks >= normalized.health_failure_limit:
                    print(
                        "Circle health check failed repeatedly; restarting server",
                        flush=True,
                    )
                    _terminate_child(child)
                    break
            if stopping:
                break
            restart_count += 1
            time.sleep(min(2.0 * restart_count, 15.0))
    finally:
        if child is not None:
            _terminate_child(child)
        normalized.state_path.unlink(missing_ok=True)
    return 0


def serve_child(config: LocalServiceConfig) -> int:
    import uvicorn

    from seven_cycle_platform.api import create_app

    normalized = config.normalized()
    if normalized.repair_catalog_on_start:
        repair = repair_latest_catalog_device_drift(
            normalized.product_root,
            normalized.catalog_root,
            normalized.web_root,
        )
        print(
            "Circle catalog startup check: "
            + json.dumps(
                repair,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
    app = create_app(
        product_root=normalized.product_root,
        catalog_root=normalized.catalog_root,
        web_root=normalized.web_root,
    )
    uvicorn.run(app, host=normalized.host, port=normalized.port)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("supervise", "serve-child"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--product-root", required=True, type=Path)
    parser.add_argument("--catalog-root", required=True, type=Path)
    parser.add_argument("--web-root", required=True, type=Path)
    parser.add_argument("--state-path", required=True, type=Path)
    parser.add_argument("--log-path", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--health-interval", required=True, type=float)
    parser.add_argument("--health-failure-limit", required=True, type=int)
    parser.add_argument("--startup-grace", required=True, type=float)
    parser.add_argument("--repair-catalog-on-start", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    config = LocalServiceConfig(
        host=arguments.host,
        port=arguments.port,
        product_root=arguments.product_root,
        catalog_root=arguments.catalog_root,
        web_root=arguments.web_root,
        state_path=arguments.state_path,
        log_path=arguments.log_path,
        project_root=arguments.project_root,
        health_interval=arguments.health_interval,
        health_failure_limit=arguments.health_failure_limit,
        startup_grace=arguments.startup_grace,
        repair_catalog_on_start=arguments.repair_catalog_on_start,
    )
    if arguments.action == "supervise":
        return supervise(config)
    return serve_child(config)


if __name__ == "__main__":
    raise SystemExit(main())
