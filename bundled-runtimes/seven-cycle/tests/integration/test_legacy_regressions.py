import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

from seven_cycle_platform.security import redact_secrets


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_VERIFIERS = (
    (
        "verify_cycle_research_robustness.py",
        "cycle_research_robustness_verification.md",
    ),
    (
        "verify_cycle_investment_application.py",
        "cycle_investment_application_verification.md",
    ),
)


def _artifact_metadata(path: Path) -> tuple[int, int, int]:
    artifact_stat = path.stat()
    return (
        stat.S_IMODE(artifact_stat.st_mode),
        artifact_stat.st_size,
        artifact_stat.st_mtime_ns,
    )


def _timeout_output(error: subprocess.TimeoutExpired) -> str:
    parts: list[str] = []
    for value in (error.stdout, error.stderr):
        if isinstance(value, bytes):
            parts.append(value.decode(errors="replace"))
        elif isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


@pytest.mark.integration
@pytest.mark.parametrize(("script_name", "artifact_name"), LEGACY_VERIFIERS)
def test_legacy_cycle_verifier_remains_green_and_restores_artifact(
    script_name: str,
    artifact_name: str,
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment.pop("TUSHARE_TOKEN", None)
    artifact = PROJECT_ROOT / "output" / artifact_name
    artifact_existed = artifact.is_file()
    backup = tmp_path / artifact_name
    original_content: bytes | None = None
    original_metadata: tuple[int, int, int] | None = None
    if artifact_existed:
        shutil.copy2(artifact, backup)
        original_content = backup.read_bytes()
        original_metadata = _artifact_metadata(backup)

    completed: subprocess.CompletedProcess[str] | None = None
    execution_failure: str | None = None
    try:
        try:
            completed = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts" / script_name)],
                cwd=PROJECT_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            execution_failure = (
                f"{script_name} timed out:\n{_timeout_output(error)}"
            )
        except OSError as error:
            execution_failure = f"{script_name} could not run: {error}"
    finally:
        if artifact_existed:
            shutil.copy2(backup, artifact)
        else:
            artifact.unlink(missing_ok=True)

    assert artifact.is_file() is artifact_existed
    if artifact_existed:
        assert artifact.read_bytes() == original_content
        assert _artifact_metadata(artifact) == original_metadata

    if execution_failure is not None:
        pytest.fail(redact_secrets(execution_failure), pytrace=False)
    assert completed is not None

    failure_output = redact_secrets(
        "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    )
    assert completed.returncode == 0, (
        f"{script_name} failed with exit code {completed.returncode}:\n"
        f"{failure_output}"
    )
