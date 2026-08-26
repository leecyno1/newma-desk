from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _copy_min_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    shutil.copytree(PROJECT_ROOT / "scripts", root / "scripts")
    (root / "data" / "datasets").mkdir(parents=True)
    for name in ["requirements.txt", ".env.production-lite.example"]:
        shutil.copy2(PROJECT_ROOT / name, root / name)
    return root


def test_manage_prod_lite_creates_env_and_data_dirs_without_install(tmp_path):
    root = _copy_min_project(tmp_path)
    result = subprocess.run(
        ["bash", "scripts/manage.sh", "prod-lite"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "NO_INSTALL": "1", "SKIP_DB_INIT": "1"},
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout
    assert (root / ".env").exists()
    assert (root / "data" / "datasets").is_dir()
    assert (root / "backups").is_dir()
    body = (root / ".env").read_text(encoding="utf-8")
    assert "AI_MAX_PARALLEL=2" in body


def test_manage_backup_and_restore_roundtrip_requires_confirmation(tmp_path):
    root = _copy_min_project(tmp_path)
    (root / ".env").write_text("HOST=127.0.0.1\nPORT=8001\n", encoding="utf-8")
    (root / "data" / "app.db").write_text("db-v1", encoding="utf-8")
    (root / "data" / "ai_config.json").write_text('{"x":1}', encoding="utf-8")

    backup = subprocess.run(
        ["bash", "scripts/manage.sh", "backup"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=20,
    )
    assert backup.returncode == 0, backup.stdout
    backup_dirs = sorted((root / "backups").glob("backup-*"))
    assert backup_dirs
    backup_dir = backup_dirs[-1]
    assert (backup_dir / "app.db").read_text(encoding="utf-8") == "db-v1"

    (root / "data" / "app.db").write_text("db-v2", encoding="utf-8")
    denied = subprocess.run(
        ["bash", "scripts/manage.sh", "restore", str(backup_dir)],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=20,
    )
    assert denied.returncode != 0
    assert (root / "data" / "app.db").read_text(encoding="utf-8") == "db-v2"

    restored = subprocess.run(
        ["bash", "scripts/manage.sh", "restore", str(backup_dir)],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "CONFIRM_RESTORE": "RESTORE"},
        check=False,
        timeout=20,
    )
    assert restored.returncode == 0, restored.stdout
    assert (root / "data" / "app.db").read_text(encoding="utf-8") == "db-v1"


def test_manage_diagnose_outputs_support_report_without_running_service(tmp_path):
    root = _copy_min_project(tmp_path)
    (root / ".env").write_text("HOST=127.0.0.1\nPORT=65530\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", "scripts/manage.sh", "diagnose"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout
    assert "Dasheng Local Diagnostics" in result.stdout
    assert "health=fail" in result.stdout
    assert "root=" in result.stdout
    assert "recent_log:" in result.stdout


def test_manage_diagnose_repairs_stale_pid_file_in_script():
    source = (PROJECT_ROOT / "scripts" / "manage.sh").read_text(encoding="utf-8")
    assert "诊断发现 PID 文件陈旧" in source
    assert 'echo "$pid_on_port" > "$PID_FILE"' in source


def test_manage_script_wraps_launchd_operations():
    source = (PROJECT_ROOT / "scripts" / "manage.sh").read_text(encoding="utf-8")
    assert "launchd <install|start|stop|restart|status|logs|health|uninstall>" in source
    assert "launchd_svc()" in source
    assert 'bash "$ROOT_DIR/scripts/launchd_8001.sh" "$action"' in source


def test_manage_start_stop_restart_respect_configured_launchd_service():
    manage_source = (PROJECT_ROOT / "scripts" / "manage.sh").read_text(encoding="utf-8")
    launchd_source = (PROJECT_ROOT / "scripts" / "launchd_8001.sh").read_text(encoding="utf-8")

    assert "launchd_service_configured()" in manage_source
    assert "launchd_service_loaded()" in manage_source
    assert 'grep -Fq "<string>${ROOT_DIR}/scripts/run_uvicorn_8001.sh</string>"' in manage_source
    assert "restart_svc()" in manage_source
    assert "restart) restart_svc ;;" in manage_source
    assert 'bash "$ROOT_DIR/scripts/launchd_8001.sh" start' in manage_source
    assert 'bash "$ROOT_DIR/scripts/launchd_8001.sh" stop' in manage_source
    assert 'bash "$ROOT_DIR/scripts/launchd_8001.sh" restart' in manage_source

    assert "start_service()" in launchd_source
    assert "stop_service()" in launchd_source
    assert "start) start_service ;;" in launchd_source
    assert "stop) stop_service ;;" in launchd_source


def test_manage_usage_and_invalid_launchd_return_quickly(tmp_path):
    root = _copy_min_project(tmp_path)
    usage = subprocess.run(
        ["bash", "scripts/manage.sh"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=5,
    )
    assert usage.returncode == 0, usage.stdout
    assert "launchd <install|start|stop|restart|status|logs|health|uninstall>" in usage.stdout

    invalid = subprocess.run(
        ["bash", "scripts/manage.sh", "launchd", "invalid"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=5,
    )
    assert invalid.returncode == 2
    assert "launchd <install|start|stop|restart|status|logs|health|uninstall>" in invalid.stdout
