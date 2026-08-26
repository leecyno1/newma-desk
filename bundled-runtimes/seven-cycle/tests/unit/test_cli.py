from datetime import date, datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tomllib
from types import SimpleNamespace

import pytest


VALID_RUN_ID = "2026-06-30-0123456789ab-abcdef012345"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = PROJECT_ROOT / "config" / "seven_cycle"
SYNTHETIC_SECRET = "cli-secret-value-123"


def _cli():
    return importlib.import_module("seven_cycle_platform.cli")


def _publish_test_run(tmp_path: Path):
    from seven_cycle_platform.storage.publisher import publish_run
    from seven_cycle_platform.storage.run_context import RunContext

    input_bytes = b"observations"
    context = RunContext.create(
        as_of=date(2026, 6, 30),
        data_vintage=date(2026, 6, 30),
        model_version="seven-cycle-v1",
        config={"cycles": ["C1", "C2"]},
        input_checksums={
            "inputs/observations.parquet": hashlib.sha256(input_bytes).hexdigest()
        },
        quality_summary={"passed": 1},
        created_at=datetime(2026, 7, 12, 9, 30, tzinfo=timezone.utc),
    )
    product_root = tmp_path / "products" / "seven_cycle"

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / "cycles.json").write_text(
            '{"status":"published"}\n',
            encoding="utf-8",
        )

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
    )
    return product_root, manifest


def _console_process(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_path = str(PROJECT_ROOT / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_path
        if not existing_pythonpath
        else os.pathsep.join((source_path, existing_pythonpath))
    )
    console_script = Path(sys.executable).with_name("seven-cycle")
    if console_script.is_file():
        command = [str(console_script)]
    else:
        command = [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from seven_cycle_platform.cli import main; "
                "raise SystemExit(main(sys.argv[1:]))"
            ),
        ]
    return subprocess.run(
        [*command, *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _plain_checkout_python(tmp_path: Path) -> tuple[str, dict[str, str]]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    candidates = [Path(sys.executable)]
    for directory in environment.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidates.extend([Path(directory) / "python", Path(directory) / "python3"])

    seen: set[Path] = set()
    probe = (
        "import importlib.util; import pydantic, yaml; "
        "raise SystemExit("
        "0 if importlib.util.find_spec('seven_cycle_platform') is None else 1"
        ")"
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved in seen or not os.access(resolved, os.X_OK):
            continue
        seen.add(resolved)
        completed = subprocess.run(
            [str(resolved), "-c", probe],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode == 0:
            return str(resolved), environment
    raise AssertionError(
        "no plain Python with runtime dependencies and no installed package found"
    )


def test_parser_requires_a_subcommand() -> None:
    cli = _cli()

    with pytest.raises(SystemExit) as error_info:
        cli.parse_args([])

    assert error_info.value.code == 2


def test_validate_config_parses_defaults_and_selects_handler() -> None:
    cli = _cli()

    arguments = cli.parse_args(["validate-config"])

    assert arguments.command == "validate-config"
    assert arguments.config_dir == Path("config/seven_cycle")
    assert arguments.handler is cli.handle_validate_config


def test_validate_config_accepts_an_explicit_config_directory() -> None:
    cli = _cli()

    arguments = cli.parse_args(["validate-config", "--config-dir", "custom/registry"])

    assert arguments.config_dir == Path("custom/registry")


def test_build_parses_iso_date_defaults_and_selects_handler() -> None:
    cli = _cli()

    arguments = cli.parse_args(["build", "--as-of", "2026-07-12"])

    assert arguments.command == "build"
    assert arguments.as_of == date(2026, 7, 12)
    assert arguments.config_dir == Path("config/seven_cycle")
    assert arguments.product_root == Path("products/circle")
    assert arguments.project_root == Path(".")
    assert arguments.catalog_root is None
    assert arguments.web_project_root == Path("web")
    assert arguments.handler is cli.handle_build


def test_build_accepts_explicit_future_extension_paths() -> None:
    cli = _cli()

    arguments = cli.parse_args(
        [
            "build",
            "--as-of",
            "2026-07-12",
            "--config-dir",
            "custom/registry",
            "--product-root",
            "custom/products",
            "--project-root",
            "custom/project",
            "--catalog-root",
            "custom/catalogs",
            "--web-project-root",
            "custom/web",
        ]
    )

    assert arguments.config_dir == Path("custom/registry")
    assert arguments.product_root == Path("custom/products")
    assert arguments.project_root == Path("custom/project")
    assert arguments.catalog_root == Path("custom/catalogs")
    assert arguments.web_project_root == Path("custom/web")


def test_build_foundation_parses_approved_defaults_and_selects_handler() -> None:
    cli = _cli()

    arguments = cli.parse_args(["build-foundation", "--as-of", "2026-07-19"])

    assert arguments.command == "build-foundation"
    assert arguments.as_of == date(2026, 7, 19)
    assert arguments.product_root == Path("products/circle")
    assert arguments.project_root == Path(".")
    assert arguments.handler is cli.handle_build_foundation


def test_serve_defaults_to_circle_release_and_built_web() -> None:
    cli = _cli()

    arguments = cli.parse_args(["serve"])

    assert arguments.product_root == Path("products/circle")
    assert arguments.catalog_root == Path("products/circle/catalogs")
    assert arguments.web_root == Path("web/dist")
    assert arguments.handler is cli.handle_serve


def test_service_defaults_to_supervised_circle_port() -> None:
    cli = _cli()

    arguments = cli.parse_args(["service", "start"])

    assert arguments.action == "start"
    assert arguments.host == "127.0.0.1"
    assert arguments.port == 4174
    assert arguments.product_root == Path("products/circle")
    assert arguments.catalog_root == Path("products/circle/catalogs")
    assert arguments.web_root == Path("web/dist")
    assert arguments.state_path == Path("output/services/circle-service.json")
    assert arguments.log_path == Path("output/services/circle-service.log")
    assert arguments.project_root == Path(".")
    assert arguments.repair_catalog_on_start is False
    assert arguments.handler is cli.handle_service


def test_serve_and_service_accept_explicit_catalog_startup_repair() -> None:
    cli = _cli()

    serve = cli.parse_args(["serve", "--repair-catalog-on-start"])
    service = cli.parse_args(
        ["service", "restart", "--repair-catalog-on-start"]
    )

    assert serve.repair_catalog_on_start is True
    assert service.repair_catalog_on_start is True


def test_build_cycles_parses_documented_shape_and_boolean_strict_flag() -> None:
    cli = _cli()

    arguments = cli.parse_args(
        ["build-cycles", "--as-of", "2026-07-12", "--strict-vintage"]
    )

    assert arguments.command == "build-cycles"
    assert arguments.as_of == date(2026, 7, 12)
    assert arguments.strict_vintage is True
    assert arguments.config_dir == Path("config/seven_cycle")
    assert arguments.product_root == Path("products/seven_cycle")
    assert arguments.input_dir == Path("inputs/seven_cycle")
    assert arguments.handler is cli.handle_build_cycles


def test_build_cycles_accepts_explicit_paths_and_defaults_to_non_strict() -> None:
    cli = _cli()

    arguments = cli.parse_args(
        [
            "build-cycles",
            "--as-of",
            "2026-07-12",
            "--config-dir",
            "custom/registry",
            "--product-root",
            "custom/products",
            "--input-dir",
            "custom/inputs",
        ]
    )

    assert arguments.strict_vintage is False
    assert arguments.config_dir == Path("custom/registry")
    assert arguments.product_root == Path("custom/products")
    assert arguments.input_dir == Path("custom/inputs")


@pytest.mark.parametrize("value", ["not-a-date", "2026-02-30", "20260712"])
def test_build_cycles_rejects_invalid_iso_dates(value: str) -> None:
    cli = _cli()

    with pytest.raises(SystemExit) as error_info:
        cli.parse_args(["build-cycles", "--as-of", value])

    assert error_info.value.code == 2


def test_build_cycles_requires_as_of() -> None:
    cli = _cli()

    with pytest.raises(SystemExit) as error_info:
        cli.parse_args(["build-cycles", "--strict-vintage"])

    assert error_info.value.code == 2


@pytest.mark.parametrize("value", ["not-a-date", "2026-02-30", "20260712"])
def test_build_rejects_invalid_iso_dates(value: str) -> None:
    cli = _cli()

    with pytest.raises(SystemExit) as error_info:
        cli.parse_args(["build", "--as-of", value])

    assert error_info.value.code == 2


def test_build_requires_as_of() -> None:
    cli = _cli()

    with pytest.raises(SystemExit) as error_info:
        cli.parse_args(["build"])

    assert error_info.value.code == 2


def test_verify_parses_run_id_defaults_and_selects_handler() -> None:
    cli = _cli()

    arguments = cli.parse_args(["verify", "--run-id", VALID_RUN_ID])

    assert arguments.command == "verify"
    assert arguments.run_id == VALID_RUN_ID
    assert arguments.product_root == Path("products/seven_cycle")
    assert arguments.handler is cli.handle_verify


def test_verify_accepts_an_explicit_product_root() -> None:
    cli = _cli()

    arguments = cli.parse_args(
        [
            "verify",
            "--run-id",
            VALID_RUN_ID,
            "--product-root",
            "custom/products",
        ]
    )

    assert arguments.product_root == Path("custom/products")


def test_baijiu_report_parses_run_and_product_root() -> None:
    cli = _cli()

    arguments = cli.parse_args(
        [
            "report-baijiu-2019",
            "--run-id",
            VALID_RUN_ID,
            "--product-root",
            "custom/products",
        ]
    )

    assert arguments.command == "report-baijiu-2019"
    assert arguments.run_id == VALID_RUN_ID
    assert arguments.product_root == Path("custom/products")
    assert arguments.handler is cli.handle_report_baijiu_2019


def test_baijiu_report_rejects_invalid_run_id() -> None:
    cli = _cli()

    with pytest.raises(SystemExit) as error_info:
        cli.parse_args(["report-baijiu-2019", "--run-id", "../invalid-run"])

    assert error_info.value.code == 2


def test_verify_requires_run_id() -> None:
    cli = _cli()

    with pytest.raises(SystemExit) as error_info:
        cli.parse_args(["verify"])

    assert error_info.value.code == 2


@pytest.mark.parametrize(
    "run_id",
    [
        "../2026-06-30-0123456789ab-abcdef012345",
        "2026-06-30/0123456789ab/abcdef012345",
        "2026-06-30-0123456789AB-abcdef012345",
        "2026-06-30-0123456789ab-abcdef01234",
        "arbitrary-run-id",
    ],
)
def test_verify_rejects_run_ids_outside_the_run_context_shape(
    run_id: str,
) -> None:
    cli = _cli()

    with pytest.raises(SystemExit) as error_info:
        cli.parse_args(["verify", "--run-id", run_id])

    assert error_info.value.code == 2


def test_cli_uses_the_public_run_id_pattern() -> None:
    cli = _cli()
    from seven_cycle_platform.storage.run_context import RUN_ID_PATTERN

    assert cli.RUN_ID_PATTERN is RUN_ID_PATTERN


def test_validate_config_executes_against_the_real_registry(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()

    exit_code = cli.main(["validate-config", "--config-dir", str(REGISTRY_DIR)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == (
        '{"assets":11,"channels":8,"cycles":7,"indicators":38,"status":"valid"}\n'
    )
    assert captured.err == ""


def test_build_creates_one_deployment_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    import seven_cycle_platform.catalog as catalog_module
    import seven_cycle_platform.pipeline.circle_deployment as deployment_module

    product_root = tmp_path / "products"
    product_root.mkdir()
    run_id = VALID_RUN_ID
    run_dir = product_root / "runs" / run_id
    catalog_path = product_root / "catalogs" / f"{run_id}.duckdb"
    catalog_path.parent.mkdir()
    catalog_path.write_bytes(b"catalog")
    web_root = tmp_path / "web" / "dist"
    (web_root / "data").mkdir(parents=True)
    (web_root / "index.html").write_text("<title>Circle</title>", encoding="utf-8")
    (web_root / "data" / "market.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "_publish_foundation_release",
        lambda **_: (
            cli.FoundationBuildResult(run_id=run_id, run_dir=run_dir),
            SimpleNamespace(path=catalog_path),
            False,
        ),
    )
    monkeypatch.setattr(cli, "_build_web_distribution", lambda _: web_root)
    monkeypatch.setattr(
        deployment_module,
        "build_circle_deployment",
        lambda **_: SimpleNamespace(run_id=run_id, run_dir=run_dir, reused=False),
    )
    monkeypatch.setattr(cli, "load_manifest", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        catalog_module,
        "build_catalog",
        lambda *_args, **_kwargs: SimpleNamespace(
            path=catalog_path,
            catalog_checksum="c" * 64,
        ),
    )

    exit_code = cli.main(
        [
            "build",
            "--as-of",
            "2026-07-21",
            "--config-dir",
            str(REGISTRY_DIR),
            "--product-root",
            str(product_root),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["run_id"] == run_id
    assert payload["status"] == "ready"
    assert payload["reused_deployment"] is False
    assert payload["reused_foundation"] is False
    deployment = json.loads((product_root / "deployment.json").read_text())
    assert deployment["api_run_id"] == run_id
    assert deployment["deployment_as_of"] == "2026-07-21"
    assert deployment["deployment_id"] == payload["deployment_id"]
    assert json.loads((web_root / "data" / "deployment.json").read_text()) == deployment
    assert captured.err == ""


def test_build_reports_config_failure_before_deployment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    missing_registry = tmp_path / "missing-registry"

    exit_code = cli.main(
        [
            "build",
            "--as-of",
            "2026-07-12",
            "--config-dir",
            str(missing_registry),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Registry directory does not exist" in captured.err
    assert "Traceback" not in captured.err


def test_build_foundation_command_publishes_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    product_root = tmp_path / "products"

    exit_code = cli.main(
        [
            "build-foundation",
            "--as-of",
            "2026-07-19",
            "--product-root",
            str(product_root),
            "--project-root",
            str(PROJECT_ROOT),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "catalog": str(
            product_root / "catalogs" / f"{payload['run_id']}.duckdb"
        ),
        "catalog_products": 5,
        "path": str(product_root / "runs" / payload["run_id"]),
        "reused": False,
        "run_id": payload["run_id"],
        "status": "live",
    }
    assert Path(payload["catalog"]).is_file()

    reused_exit_code = cli.main(
        [
            "build-foundation",
            "--as-of",
            "2026-07-19",
            "--product-root",
            str(product_root),
            "--project-root",
            str(PROJECT_ROOT),
        ]
    )
    reused_payload = json.loads(capsys.readouterr().out)
    assert reused_exit_code == 0
    assert reused_payload["run_id"] == payload["run_id"]
    assert reused_payload["reused"] is True

    verify_exit_code = cli.main(
        [
            "verify",
            "--run-id",
            payload["run_id"],
            "--product-root",
            str(product_root),
        ]
    )

    verification = json.loads(capsys.readouterr().out)
    assert verify_exit_code == 0
    assert verification == {
        "external_authenticity": "not_verified",
        "files_verified": 5,
        "run_id": payload["run_id"],
        "status": "valid",
        "verification": "run_self_consistency",
    }


def test_build_cycles_success_prints_compact_deterministic_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    from seven_cycle_platform.types import ReleaseStatus

    run_id = "2026-07-12-0123456789ab-abcdef012345"
    publication_path = tmp_path / "products" / "runs" / run_id
    pipeline_input = object()
    registry_bundle = object()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        cli,
        "load_cycle_pipeline_input",
        lambda input_dir: pipeline_input,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "load_registry_bundle",
        lambda config_dir: registry_bundle,
    )

    def fake_build_cycles(value, **kwargs):
        calls.append({"value": value, **kwargs})
        return SimpleNamespace(
            status=ReleaseStatus.LIVE,
            run_id=run_id,
            reused=False,
            publication_path=publication_path,
            findings=(object(), object(), object()),
            manifest=SimpleNamespace(
                product_checksums={f"file-{index}": "digest" for index in range(7)}
            ),
        )

    monkeypatch.setattr(cli, "build_cycles", fake_build_cycles, raising=False)

    exit_code = cli.main(
        [
            "build-cycles",
            "--as-of",
            "2026-07-12",
            "--strict-vintage",
            "--config-dir",
            str(tmp_path / "registry"),
            "--product-root",
            str(tmp_path / "products"),
            "--input-dir",
            str(tmp_path / "inputs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == (
        '{"checks":3,"files":8,'
        f'"path":"{publication_path}","reused":false,'
        f'"run_id":"{run_id}","status":"live"}}\n'
    )
    assert captured.err == ""
    assert calls == [
        {
            "value": pipeline_input,
            "registry_bundle": registry_bundle,
            "product_root": tmp_path / "products",
            "as_of": date(2026, 7, 12),
            "strict_vintage": True,
        }
    ]


def test_build_cycles_blocked_returns_operational_code_without_latest_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    from seven_cycle_platform.types import ReleaseStatus

    monkeypatch.setattr(
        cli,
        "load_cycle_pipeline_input",
        lambda input_dir: object(),
        raising=False,
    )
    monkeypatch.setattr(cli, "load_registry_bundle", lambda config_dir: object())
    monkeypatch.setattr(
        cli,
        "build_cycles",
        lambda *args, **kwargs: SimpleNamespace(
            status=ReleaseStatus.BLOCKED,
            run_id="2026-07-12-0123456789ab-abcdef012345",
            reused=False,
            publication_path=None,
            manifest=None,
            findings=(
                SimpleNamespace(check="cutoff_reconstruction", status="PASS"),
                SimpleNamespace(check="schema_contract", status="FAIL"),
                SimpleNamespace(check="no_lookahead", status="PASS"),
            ),
        ),
        raising=False,
    )

    exit_code = cli.main(
        [
            "build-cycles",
            "--as-of",
            "2026-07-12",
            "--input-dir",
            str(tmp_path / "inputs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        '{"checks":3,"failed_checks":["schema_contract"],'
        '"run_id":"2026-07-12-0123456789ab-abcdef012345",'
        '"status":"blocked"}\n'
    )
    assert "Traceback" not in captured.err


def test_build_cycles_expected_input_failure_is_redacted_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    monkeypatch.setenv("TUSHARE_TOKEN", SYNTHETIC_SECRET)
    monkeypatch.setattr(cli, "load_registry_bundle", lambda config_dir: object())

    def fail_loading(input_dir: Path) -> None:
        raise ValueError(f"invalid input token={SYNTHETIC_SECRET}")

    monkeypatch.setattr(
        cli,
        "load_cycle_pipeline_input",
        fail_loading,
        raising=False,
    )

    exit_code = cli.main(
        [
            "build-cycles",
            "--as-of",
            "2026-07-12",
            "--input-dir",
            str(tmp_path / "inputs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert SYNTHETIC_SECRET not in captured.err
    assert "[REDACTED]" in captured.err
    assert "Traceback" not in captured.err


def test_build_cycles_success_redacts_secret_values_in_publication_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    from seven_cycle_platform.types import ReleaseStatus

    monkeypatch.setenv("TUSHARE_TOKEN", SYNTHETIC_SECRET)
    monkeypatch.setattr(
        cli,
        "load_cycle_pipeline_input",
        lambda input_dir: object(),
        raising=False,
    )
    monkeypatch.setattr(cli, "load_registry_bundle", lambda config_dir: object())
    monkeypatch.setattr(
        cli,
        "build_cycles",
        lambda *args, **kwargs: SimpleNamespace(
            status=ReleaseStatus.LIVE,
            run_id="2026-07-12-0123456789ab-abcdef012345",
            reused=False,
            publication_path=tmp_path / SYNTHETIC_SECRET / "published",
            manifest=SimpleNamespace(product_checksums={}),
            findings=(),
        ),
        raising=False,
    )

    exit_code = cli.main(["build-cycles", "--as-of", "2026-07-12"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert SYNTHETIC_SECRET not in captured.out
    assert "[REDACTED]" in captured.out


def test_verify_checks_a_real_published_run_self_consistency(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    product_root, manifest = _publish_test_run(tmp_path)

    exit_code = cli.main(
        [
            "verify",
            "--run-id",
            manifest.run_id,
            "--product-root",
            str(product_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == (
        '{"external_authenticity":"not_verified","files_verified":1,'
        f'"run_id":"{manifest.run_id}","status":"valid",'
        '"verification":"run_self_consistency"}\n'
    )
    assert captured.err == ""


def test_verify_rejects_a_tampered_published_run_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    product_root, manifest = _publish_test_run(tmp_path)
    product_path = product_root / "runs" / manifest.run_id / "cycles.json"
    product_path.write_text('{"status":"tampered"}\n', encoding="utf-8")

    exit_code = cli.main(
        [
            "verify",
            "--run-id",
            manifest.run_id,
            "--product-root",
            str(product_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "run self-consistency verification failed" in captured.err
    assert "checksums" in captured.err
    assert "Traceback" not in captured.err


def test_verify_missing_run_returns_operational_failure_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()

    exit_code = cli.main(
        [
            "verify",
            "--run-id",
            VALID_RUN_ID,
            "--product-root",
            str(tmp_path / "missing-products"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "run self-consistency verification failed" in captured.err
    assert "Traceback" not in captured.err


def test_expected_cli_errors_are_redacted_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    monkeypatch.setenv("TUSHARE_TOKEN", SYNTHETIC_SECRET)
    secret_path = tmp_path / SYNTHETIC_SECRET / "missing-registry"

    exit_code = cli.main(["validate-config", "--config-dir", str(secret_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert SYNTHETIC_SECRET not in captured.err
    assert "[REDACTED]" in captured.err
    assert "Traceback" not in captured.err


def test_baijiu_report_errors_are_redacted_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    monkeypatch.setenv("TUSHARE_TOKEN", SYNTHETIC_SECRET)

    def fail_report(product_root: Path, run_id: str) -> None:
        raise ValueError(f"report failure token={SYNTHETIC_SECRET}")

    monkeypatch.setattr(cli, "generate_baijiu_2019_report", fail_report)

    exit_code = cli.main(
        [
            "report-baijiu-2019",
            "--run-id",
            VALID_RUN_ID,
            "--product-root",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert SYNTHETIC_SECRET not in captured.err
    assert "[REDACTED]" in captured.err
    assert "Traceback" not in captured.err


def test_console_entrypoint_preserves_operational_and_usage_exit_codes() -> None:
    operational = _console_process(
        [
            "build",
            "--as-of",
            "2026-07-12",
            "--config-dir",
            "missing-registry",
        ]
    )
    usage = _console_process(["build"])

    assert operational.returncode == 1
    assert "Registry directory does not exist" in operational.stderr
    assert usage.returncode == 2
    assert "--as-of" in usage.stderr


def test_main_returns_redacted_argparse_errors_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli()
    monkeypatch.setenv("TUSHARE_TOKEN", SYNTHETIC_SECRET)

    exit_code = cli.main([SYNTHETIC_SECRET])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert SYNTHETIC_SECRET not in captured.err
    assert "[REDACTED]" in captured.err
    assert "Traceback" not in captured.err


def test_pyproject_registers_the_seven_cycle_console_script() -> None:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert project["project"]["scripts"]["seven-cycle"] == (
        "seven_cycle_platform.cli:main"
    )


def test_pyproject_registers_the_integration_marker() -> None:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    markers = project["tool"]["pytest"]["ini_options"]["markers"]
    assert any(marker.startswith("integration:") for marker in markers)


def test_pyproject_registers_src_pythonpath() -> None:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert project["tool"]["pytest"]["ini_options"]["pythonpath"] == ["src"]


def test_pipeline_wrapper_delegates_argv_without_pipeline_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli()
    calls: list[list[str] | None] = []

    def fake_main(argv=None) -> int:
        calls.append(argv)
        return 7

    monkeypatch.setattr(cli, "main", fake_main)
    namespace = runpy.run_path(
        str(PROJECT_ROOT / "scripts" / "run_seven_cycle_pipeline.py"),
        run_name="_test_run_seven_cycle_pipeline",
    )
    arguments = ["build", "--as-of", "2026-07-12"]

    exit_code = namespace["main"](arguments)

    assert exit_code == 7
    assert calls == [arguments]


def test_verification_wrapper_delegates_to_the_verify_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli()
    calls: list[list[str] | None] = []

    def fake_main(argv=None) -> int:
        calls.append(argv)
        return 9

    monkeypatch.setattr(cli, "main", fake_main)
    namespace = runpy.run_path(
        str(PROJECT_ROOT / "scripts" / "verify_seven_cycle_platform.py"),
        run_name="_test_verify_seven_cycle_platform",
    )
    arguments = [
        "--run-id",
        VALID_RUN_ID,
        "--product-root",
        "custom/products",
    ]

    exit_code = namespace["main"](arguments)

    assert exit_code == 9
    assert calls == [["verify", *arguments]]


@pytest.mark.parametrize(
    ("script_name", "expected_usage"),
    [
        ("run_seven_cycle_pipeline.py", "usage: seven-cycle"),
        ("verify_seven_cycle_platform.py", "usage: seven-cycle verify"),
    ],
)
def test_direct_wrapper_help_bootstraps_repo_src_without_pythonpath(
    script_name: str,
    expected_usage: str,
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.security import redact_secrets

    python_executable, environment = _plain_checkout_python(tmp_path)

    completed = subprocess.run(
        [
            python_executable,
            str(PROJECT_ROOT / "scripts" / script_name),
            "--help",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    diagnostics = redact_secrets(
        "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    )
    assert completed.returncode == 0, diagnostics
    assert expected_usage in completed.stdout
