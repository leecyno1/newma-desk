"""Command-line interface for the seven-cycle platform."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any, TextIO

from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.security import redact_secrets
from seven_cycle_platform.storage.manifest import (
    load_manifest,
    verify_manifest,
)
from seven_cycle_platform.storage.run_context import (
    RUN_ID_PATTERN,
)
from seven_cycle_platform.types import ReleaseStatus

if TYPE_CHECKING:
    from seven_cycle_platform.pipeline.research_foundation import (
        FoundationBuildResult,
        FoundationSources,
    )


DEFAULT_CONFIG_DIR = Path("config/seven_cycle")
DEFAULT_PRODUCT_ROOT = Path("products/seven_cycle")
DEFAULT_INPUT_DIR = Path("inputs/seven_cycle")
DEFAULT_FOUNDATION_PRODUCT_ROOT = Path("products/circle")
DEFAULT_FOUNDATION_CATALOG_ROOT = DEFAULT_FOUNDATION_PRODUCT_ROOT / "catalogs"
DEFAULT_PROJECT_ROOT = Path(".")
DEFAULT_WEB_PROJECT_ROOT = Path("web")
DEFAULT_WEB_ROOT = Path("web/dist")
DEFAULT_SERVICE_STATE_PATH = Path("output/services/circle-service.json")
DEFAULT_SERVICE_LOG_PATH = Path("output/services/circle-service.log")
FOUNDATION_AS_OF = date(2026, 7, 19)
_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def __getattr__(name: str) -> object:
    if name in {"FoundationBuildResult", "FoundationSources"}:
        from seven_cycle_platform.pipeline import research_foundation

        return getattr(research_foundation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def load_cycle_pipeline_input(*args: object, **kwargs: object) -> object:
    from seven_cycle_platform.pipeline.cycles import load_cycle_pipeline_input as load

    return load(*args, **kwargs)


def build_cycles(*args: object, **kwargs: object) -> object:
    from seven_cycle_platform.pipeline.cycles import build_cycles as build

    return build(*args, **kwargs)


def generate_baijiu_2019_report(*args: object, **kwargs: object) -> object:
    from seven_cycle_platform.reports.baijiu_2019 import (
        generate_baijiu_2019_report as generate,
    )

    return generate(*args, **kwargs)


class CLIError(RuntimeError):
    """Expected command failure suitable for concise CLI output."""


class RedactingArgumentParser(argparse.ArgumentParser):
    """Argument parser that redacts dynamic values in error messages."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        redacted_message = redact_secrets(message)
        self.exit(2, f"{self.prog}: error: {redacted_message}\n")


def _parse_iso_date(value: str) -> date:
    if not _ISO_DATE_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("expected date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "expected date in YYYY-MM-DD format"
        ) from error


def _parse_run_id(value: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "run ID does not match the RunContext contract"
        )
    return value


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected port number 1..65535") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("expected port number 1..65535")
    return port


def handle_export_research_inputs(arguments: argparse.Namespace) -> int:
    from seven_cycle_platform.research_inputs import export_research_inputs

    project_root = arguments.project_root.resolve()
    output = arguments.research_output_dir or project_root / "output"
    forecast = arguments.c4_forecast_path or output / "c4_forecast_reproducible_latest.json"
    try:
        inputs = export_research_inputs(
            web_data_dir=arguments.web_data_dir or project_root / "web/public/data",
            research_output_dir=output,
            c4_forecast_path=forecast,
            destination=arguments.destination,
        )
    except (OSError, TypeError, ValueError) as error:
        raise CLIError(f"research input export failed: {error}") from error
    _print_json({"status": "exported", "path": str(inputs.root)})
    return 0


def handle_discover_cycles(arguments: argparse.Namespace) -> int:
    from seven_cycle_platform.cycles.discovery import main as discover

    try:
        discover(
            project_root=arguments.project_root.resolve(),
            output_dir=arguments.output_dir,
        )
    except (OSError, ValueError) as error:
        raise CLIError(str(error)) from error
    return 0


def handle_build_cycle_inputs(arguments: argparse.Namespace) -> int:
    from seven_cycle_platform.legacy.research_cycle_input import (
        ResearchCycleInputRequest,
        build_research_cycle_pipeline_input,
    )
    from seven_cycle_platform.pipeline.cycles import write_cycle_pipeline_input

    root = arguments.project_root.resolve()
    try:
        request = ResearchCycleInputRequest(
            annual_panel_path=root / "data/research_input_annual_long.parquet",
            annual_selection_path=root / "output/research_input_annual_long_selection.csv",
            monthly_panel_path=root / "data/research_input_monthly_macro.parquet",
            monthly_selection_path=root / "output/research_input_monthly_macro_selection.csv",
            config_dir=arguments.config_dir or root / "config/seven_cycle",
            as_of=arguments.as_of,
            state_start=arguments.state_start,
            state_end=arguments.state_end,
            verification_cutoffs=tuple(sorted(set(arguments.verification_cutoffs))),
            max_members_per_category=arguments.max_members_per_category,
            minimum_coverage_pct=arguments.minimum_coverage_pct,
        )
        pipeline_input = build_research_cycle_pipeline_input(request)
        path = write_cycle_pipeline_input(arguments.output_dir.resolve(), pipeline_input)
    except (OSError, TypeError, ValueError, KeyError) as error:
        raise CLIError(f"research cycle input build failed: {error}") from error
    _print_json({
        "annual_members": len(pipeline_input.annual_categories),
        "monthly_members": len(pipeline_input.monthly_categories),
        "observations": len(pipeline_input.observations),
        "path": str(path),
        "state_dates": len(pipeline_input.state_dates),
        "vintage": "pseudo_vintage",
    })
    return 0


def handle_build_research_panels(arguments: argparse.Namespace) -> int:
    from tempfile import TemporaryDirectory
    from seven_cycle_platform.legacy.annual_research_panel import build_panel as build_annual
    from seven_cycle_platform.legacy.monthly_research_panel import build_panel as build_monthly

    root = arguments.project_root.resolve()
    destination = arguments.destination.absolute()
    try:
        if destination.exists() or destination.is_symlink():
            raise ValueError("destination already exists; research panels are never overwritten")
        for name in (
            "data/indicator_panel_annual_very_long_history_year.parquet",
            "data/indicator_panel_monthly.parquet",
            "output/cycle_bandpower_scores_monthly.csv",
        ):
            if not (root / name).is_file():
                raise FileNotFoundError(f"required research input is missing: {root / name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".research-panels-", dir=destination.parent) as temporary:
            staged = Path(temporary) / "prepared"
            annual = build_annual(
                input_root=root, output_root=staged,
                window_start=arguments.annual_start, window_end=arguments.annual_end,
            )
            monthly = build_monthly(
                input_root=root, output_root=staged,
                window_start=arguments.monthly_start.isoformat(),
                window_end=arguments.monthly_end.isoformat(),
            )
            if destination.exists() or destination.is_symlink():
                raise ValueError("destination already exists; research panels are never overwritten")
            staged.rename(destination)
    except (OSError, TypeError, ValueError, KeyError, RuntimeError) as error:
        raise CLIError(f"research panel build failed: {error}") from error
    _print_json({
        "status": "prepared", "path": str(destination),
        "annual_selected": annual["selected"], "monthly_selected": monthly["selected"],
        "annual_window": [arguments.annual_start, arguments.annual_end],
        "monthly_window": [arguments.monthly_start.isoformat(), arguments.monthly_end.isoformat()],
    })
    return 0


def handle_build_c4_research(arguments: argparse.Namespace) -> int:
    from tempfile import TemporaryDirectory

    import pandas as pd

    from seven_cycle_platform.legacy import c4_realtime_bridge
    from seven_cycle_platform.legacy.c4_asset_statistics import (
        build_asset_statistics,
        build_c4_state,
    )

    source = arguments.project_root.resolve() / "output"
    destination = arguments.destination.absolute()
    try:
        if destination.exists() or destination.is_symlink():
            raise ValueError("destination already exists; C4 research is never overwritten")
        inputs = {
            "realtime": source / "c4_pseudo_realtime_prototype_2026-07-19.json",
            "historical": source / "c4_c5_phase_display_prototype_2026-07-19.json",
            "returns": source / "monthly_returns_20y.parquet",
        }
        for path in [*inputs.values(), *([arguments.features] if arguments.features else [])]:
            if not path.is_file():
                raise FileNotFoundError(f"required C4 input is missing: {path}")
        realtime = json.loads(inputs["realtime"].read_text(encoding="utf-8"))
        historical = json.loads(inputs["historical"].read_text(encoding="utf-8"))
        if not realtime["timeline"]:
            raise ValueError("C4 baseline timeline is empty")
        through = pd.Timestamp(arguments.through).to_period("M")
        if through < pd.Period(realtime["timeline"][-1]["date"], freq="M"):
            raise ValueError("through month precedes the C4 baseline; historical truncation is not supported")
        returns = pd.read_parquet(inputs["returns"])
        returns.index = pd.to_datetime(returns.index)
        features = (pd.read_parquet(arguments.features) if arguments.features
                    else c4_realtime_bridge.fetch_c4_features())
        bridge = c4_realtime_bridge.build_bridge(realtime, features, through=str(through))
        statistics = build_asset_statistics(returns, build_c4_state(historical, bridge))
        if not statistics["assets"]:
            raise ValueError("no asset returns overlap the C4 state")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".c4-research-", dir=destination.parent) as temporary:
            prepared = Path(temporary) / "prepared"
            prepared.mkdir()
            for filename, payload in (
                ("c4_realtime_bridge_latest.json", bridge),
                ("c4_asset_statistics_current.json", statistics),
            ):
                (prepared / filename).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8",
                )
            features.to_parquet(prepared / "c4_bridge_features.parquet")
            if destination.exists() or destination.is_symlink():
                raise ValueError("destination already exists; C4 research is never overwritten")
            prepared.rename(destination)
    except (OSError, TypeError, ValueError, KeyError, RuntimeError) as error:
        raise CLIError(f"C4 research build failed: {error}") from error
    _print_json({
        "status": "prepared", "path": str(destination),
        "latest": bridge["latest"], "assets": len(statistics["assets"]),
        "validation": bridge["bridge_validation"],
    })
    return 0


def handle_build_state_research(arguments: argparse.Namespace) -> int:
    from seven_cycle_platform.legacy.state_research import build_state_research

    root = arguments.project_root.resolve()
    try:
        result = build_state_research(
            panel_path=root / "data/indicator_panel_monthly.parquet",
            returns_path=root / "output/monthly_returns_20y.parquet",
            public_signal_dir=arguments.public_signal_dir or root / "data/raw/web_public",
            destination=arguments.destination,
            refresh_public=arguments.refresh_public,
        )
    except (OSError, TypeError, ValueError, KeyError, IndexError, RuntimeError) as error:
        raise CLIError(f"state research build failed: {error}") from error
    _print_json(result)
    return 0


def handle_build_asset_forecast(arguments: argparse.Namespace) -> int:
    from seven_cycle_platform.legacy.asset_cycle_state_forecast import build_asset_forecast

    output = arguments.project_root.resolve() / "output"
    try:
        result = build_asset_forecast(
            returns_path=output / "monthly_returns_20y.parquet",
            state_paths={
                "C4": output / "c4_realtime_bridge_latest.json",
                "C5": output / "c5_liquidity_state_research.json",
                "C7": output / "c7_risk_appetite_state_research.json",
            },
            destination=arguments.destination,
            workers=arguments.workers,
        )
    except (OSError, TypeError, ValueError, KeyError, IndexError, RuntimeError) as error:
        raise CLIError(f"asset forecast build failed: {error}") from error
    _print_json(result)
    return 0


def handle_validate_config(arguments: argparse.Namespace) -> int:
    try:
        bundle = load_registry_bundle(arguments.config_dir)
    except (OSError, ValueError) as error:
        raise CLIError(str(error)) from error

    _print_json(
        {
            "assets": len(bundle.assets),
            "channels": len(bundle.channels),
            "cycles": len(bundle.cycles),
            "indicators": len(bundle.indicators),
            "status": "valid",
        }
    )
    return 0


def _foundation_sources(project_root: Path) -> FoundationSources:
    from seven_cycle_platform.pipeline.research_foundation import FoundationSources

    project_root = project_root.resolve()
    approved_config = (
        project_root / "config" / "seven_cycle" / "approved" / "2026-07-19"
    )
    return FoundationSources(
        project_root=project_root,
        config_dir=approved_config,
        evidence_path=approved_config / "evidence_baseline.yaml",
        historical_path=(
            project_root / "output" / "c4_c5_phase_display_prototype_2026-07-19.json"
        ),
        realtime_path=(
            project_root / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json"
        ),
        forecast_path=(
            project_root / "output" / "c4_forecast_prototype_2026-07-19.json"
        ),
        asset_path=(
            project_root / "output" / "c4_asset_statistics_prototype_2026-07-19.json"
        ),
    )


def _publish_foundation_release(
    *,
    project_root: Path,
    product_root: Path,
    catalog_root: Path | None,
) -> tuple[FoundationBuildResult, Any, bool]:
    from seven_cycle_platform.pipeline.research_foundation import (
        FoundationBuildResult,
        build_research_foundation,
    )

    reused = False
    try:
        result = build_research_foundation(
            sources=_foundation_sources(project_root),
            product_root=product_root,
            as_of=FOUNDATION_AS_OF,
        )
    except FileExistsError:
        try:
            candidates: list[FoundationBuildResult] = []
            for run_dir in sorted((product_root / "runs").iterdir()):
                if not run_dir.is_dir() or not RUN_ID_PATTERN.fullmatch(run_dir.name):
                    continue
                manifest = load_manifest(run_dir)
                if (
                    manifest.as_of != FOUNDATION_AS_OF
                    or manifest.model_version != "research-foundation-v1"
                ):
                    continue
                verify_manifest(run_dir, expected=manifest)
                candidates.append(
                    FoundationBuildResult(run_id=manifest.run_id, run_dir=run_dir)
                )
            if len(candidates) != 1:
                raise ValueError("expected exactly one reusable foundation run")
            result = candidates[0]
            reused = True
        except (OSError, TypeError, ValueError) as error:
            raise CLIError(f"existing foundation run could not be reused: {error}") from error
    except (OSError, TypeError, ValueError) as error:
        raise CLIError(str(error)) from error

    try:
        from seven_cycle_platform.catalog import build_catalog

        manifest = load_manifest(result.run_dir)
        normalized_catalog_root = catalog_root or product_root / "catalogs"
        catalog = build_catalog(
            result.run_dir,
            normalized_catalog_root / f"{result.run_id}.duckdb",
            expected_manifest=manifest,
        )
    except (OSError, TypeError, ValueError) as error:
        raise CLIError(f"catalog publication failed: {error}") from error
    return result, catalog, reused


def _build_web_distribution(web_project_root: Path) -> Path:
    package_path = web_project_root / "package.json"
    if not package_path.is_file():
        raise CLIError("web project is missing package.json")
    completed = subprocess.run(
        ["npm", "run", "build"],
        cwd=web_project_root,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        diagnostics = redact_secrets(completed.stderr or completed.stdout)
        raise CLIError(f"web build failed: {diagnostics.strip()}")
    web_root = web_project_root / "dist"
    if not (web_root / "index.html").is_file():
        raise CLIError("web build completed without dist/index.html")
    return web_root


def _write_deployment_manifest(
    *,
    product_root: Path,
    catalog_checksum: str,
    run_id: str,
    deployment_as_of: date,
    web_root: Path,
) -> tuple[Path, str]:
    from seven_cycle_platform.deployment import write_deployment_manifest

    try:
        return write_deployment_manifest(
            product_root=product_root,
            catalog_checksum=catalog_checksum,
            run_id=run_id,
            deployment_as_of=deployment_as_of,
            web_root=web_root,
        )
    except (OSError, TypeError, ValueError) as error:
        raise CLIError(f"deployment metadata publication failed: {error}") from error


def handle_build(arguments: argparse.Namespace) -> int:
    try:
        load_registry_bundle(arguments.config_dir)
    except (OSError, ValueError) as error:
        raise CLIError(str(error)) from error
    inputs = None
    if arguments.research_bundle_dir is not None:
        from seven_cycle_platform.research_inputs import load_research_inputs

        try:
            inputs = load_research_inputs(arguments.research_bundle_dir)
        except (OSError, TypeError, ValueError) as error:
            raise CLIError(f"research input snapshot is invalid: {error}") from error
        asset_forecast_path = inputs.asset_forecast_path
        asset_statistics_path = inputs.asset_statistics_path
        c4_forecast_path = inputs.c4_forecast_path
    else:
        research_output = arguments.research_output_dir or arguments.project_root / "output"
        asset_forecast_path = research_output / "asset_cycle_state_forecast.json"
        asset_statistics_path = research_output / "c4_asset_statistics_current.json"
        c4_forecast_path = research_output / "c4_forecast_reproducible_latest.json"
        if not c4_forecast_path.exists():
            c4_forecast_path = arguments.project_root / "output" / "c4_forecast_prototype_2026-07-19.json"
    missing = [str(path) for path in (asset_forecast_path, asset_statistics_path, c4_forecast_path) if not path.is_file()]
    if missing:
        raise CLIError(
            "research build inputs missing: " + ", ".join(missing)
            + "; supply --research-output-dir from the matching research snapshot"
        )
    foundation, _, reused_foundation = _publish_foundation_release(
        project_root=arguments.project_root,
        product_root=arguments.product_root,
        catalog_root=arguments.catalog_root,
    )
    web_root = _build_web_distribution(arguments.web_project_root)
    try:
        if inputs is not None:
            inputs.install_web_data(web_root)
        from seven_cycle_platform.catalog import build_catalog
        from seven_cycle_platform.pipeline.circle_deployment import (
            build_circle_deployment,
        )

        deployment = build_circle_deployment(
            product_root=arguments.product_root,
            foundation_run_dir=foundation.run_dir,
            web_data_dir=web_root / "data",
            asset_forecast_path=asset_forecast_path,
            asset_statistics_path=asset_statistics_path,
            c4_forecast_path=c4_forecast_path,
            as_of=arguments.as_of,
        )
        deployment_manifest = load_manifest(deployment.run_dir)
        normalized_catalog_root = (
            arguments.catalog_root or arguments.product_root / "catalogs"
        )
        catalog = build_catalog(
            deployment.run_dir,
            normalized_catalog_root / f"{deployment.run_id}.duckdb",
            expected_manifest=deployment_manifest,
        )
    except (OSError, TypeError, ValueError) as error:
        raise CLIError(f"deployment publication failed: {error}") from error
    deployment_path, deployment_id = _write_deployment_manifest(
        product_root=arguments.product_root,
        catalog_checksum=catalog.catalog_checksum,
        run_id=deployment.run_id,
        deployment_as_of=arguments.as_of,
        web_root=web_root,
    )
    _print_json(
        {
            "catalog": redact_secrets(str(catalog.path)),
            "deployment": redact_secrets(str(deployment_path)),
            "deployment_id": deployment_id,
            "reused_deployment": deployment.reused,
            "reused_foundation": reused_foundation,
            "run_id": deployment.run_id,
            "status": "ready",
            "web": redact_secrets(str(web_root)),
        }
    )
    return 0


def handle_build_foundation(arguments: argparse.Namespace) -> int:
    result, catalog, reused = _publish_foundation_release(
        project_root=arguments.project_root,
        product_root=arguments.product_root,
        catalog_root=arguments.catalog_root,
    )

    _print_json(
        {
            "catalog": redact_secrets(str(catalog.path)),
            "catalog_products": catalog.product_count,
            "reused": reused,
            "run_id": result.run_id,
            "path": redact_secrets(str(result.run_dir)),
            "status": "live",
        }
    )
    return 0


def handle_build_cycles(arguments: argparse.Namespace) -> int:
    try:
        bundle = load_registry_bundle(arguments.config_dir)
        pipeline_input = load_cycle_pipeline_input(arguments.input_dir)
        result = build_cycles(
            pipeline_input,
            registry_bundle=bundle,
            product_root=arguments.product_root,
            as_of=arguments.as_of,
            strict_vintage=arguments.strict_vintage,
        )
    except (OSError, TypeError, ValueError) as error:
        raise CLIError(str(error)) from error

    if result.status is ReleaseStatus.BLOCKED:
        failed_checks = sorted(
            finding.check for finding in result.findings if finding.status == "FAIL"
        )
        _print_json(
            {
                "checks": len(result.findings),
                "failed_checks": failed_checks,
                "run_id": result.run_id,
                "status": result.status.value,
            },
            file=sys.stderr,
        )
        return 1

    if result.manifest is None or result.publication_path is None:
        raise CLIError("cycle build returned no published manifest")
    _print_json(
        {
            "checks": len(result.findings),
            "files": len(result.manifest.product_checksums) + 1,
            "path": redact_secrets(str(result.publication_path)),
            "reused": result.reused,
            "run_id": result.run_id,
            "status": result.status.value,
        }
    )
    return 0


def handle_verify(arguments: argparse.Namespace) -> int:
    from seven_cycle_platform.verification.cycles import (
        CycleAcceptanceError,
        verify_published_cycle_run,
    )

    run_dir = arguments.product_root / "runs" / arguments.run_id
    is_m2_run = any(
        (run_dir / filename).exists()
        for filename in (
            "cycle_model_versions.json",
            "quality_findings.parquet",
            "verification_plan.json",
        )
    )
    if is_m2_run:
        try:
            acceptance = verify_published_cycle_run(run_dir)
        except (CycleAcceptanceError, OSError, ValueError) as error:
            raise CLIError(f"M2 acceptance verification failed: {error}") from error
        _print_json(
            {
                "checks_verified": acceptance.checks_verified,
                "files_verified": acceptance.files_verified,
                "run_id": acceptance.manifest.run_id,
                "status": "valid",
                "verification": "m2_acceptance",
            }
        )
        return 0

    try:
        expected_manifest = load_manifest(run_dir)
        manifest = verify_manifest(run_dir, expected=expected_manifest)
    except (OSError, ValueError) as error:
        raise CLIError(f"run self-consistency verification failed: {error}") from error

    _print_json(
        {
            "external_authenticity": "not_verified",
            "files_verified": len(manifest.product_checksums),
            "run_id": manifest.run_id,
            "status": "valid",
            "verification": "run_self_consistency",
        }
    )
    return 0


def handle_report_baijiu_2019(arguments: argparse.Namespace) -> int:
    try:
        result = generate_baijiu_2019_report(
            arguments.product_root,
            arguments.run_id,
        )
    except (OSError, TypeError, ValueError) as error:
        raise CLIError(str(error)) from error
    _print_json(
        {
            "json_path": redact_secrets(str(result.json_path)),
            "markdown_path": redact_secrets(str(result.markdown_path)),
            "requested_run_id": result.requested_run_id,
            "reused": result.reused,
            "source_runs": result.source_runs,
            "status": "ready",
        }
    )
    return 0


def handle_serve(arguments: argparse.Namespace) -> int:
    """Run the local read-only API without opening it during CLI parsing."""

    try:
        import uvicorn

        from seven_cycle_platform.api import create_app
        from seven_cycle_platform.local_service import (
            repair_latest_catalog_device_drift,
        )

        if arguments.repair_catalog_on_start:
            repair_latest_catalog_device_drift(
                arguments.product_root,
                arguments.catalog_root,
                arguments.web_root,
            )

        app = create_app(
            product_root=arguments.product_root,
            catalog_root=arguments.catalog_root,
            web_root=arguments.web_root,
        )
        uvicorn.run(app, host=arguments.host, port=arguments.port)
    except Exception as error:
        raise CLIError(f"local API could not start: {error}") from error
    return 0


def handle_service(arguments: argparse.Namespace) -> int:
    """Manage the supervised local Circle service."""

    from seven_cycle_platform.local_service import (
        LocalServiceConfig,
        inspect_service,
        start_service,
        stop_service,
    )

    config = LocalServiceConfig(
        host=arguments.host,
        port=arguments.port,
        product_root=arguments.product_root,
        catalog_root=arguments.catalog_root,
        web_root=arguments.web_root,
        state_path=arguments.state_path,
        log_path=arguments.log_path,
        project_root=arguments.project_root,
        repair_catalog_on_start=arguments.repair_catalog_on_start,
    )
    try:
        if arguments.action == "status":
            result = inspect_service(config)
        elif arguments.action == "stop":
            result = stop_service(config)
        elif arguments.action == "restart":
            stop_service(config)
            result = start_service(config, startup_timeout=arguments.startup_timeout)
            result["action"] = "restarted"
        else:
            result = start_service(config, startup_timeout=arguments.startup_timeout)
    except (OSError, RuntimeError, ValueError) as error:
        raise CLIError(str(error)) from error
    _print_json(result)
    return 0


def _print_json(
    payload: dict[str, object],
    *,
    file: TextIO | None = None,
) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stdout if file is None else file,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = RedactingArgumentParser(prog="seven-cycle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export-research-inputs", help="export paired browser/API derived research data",
    )
    export_parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    export_parser.add_argument("--web-data-dir", type=Path)
    export_parser.add_argument("--research-output-dir", type=Path)
    export_parser.add_argument("--c4-forecast-path", type=Path)
    export_parser.add_argument("--destination", type=Path, required=True)
    export_parser.set_defaults(handler=handle_export_research_inputs)

    discovery_parser = subparsers.add_parser(
        "discover-cycles", help="run research discovery from local input panels",
    )
    discovery_parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT,
        help="input root with data/ panels and output/ selection metadata; defaults to cwd",
    )
    discovery_parser.add_argument(
        "--output-dir", type=Path,
        help="result directory; defaults to PROJECT_ROOT/output",
    )
    discovery_parser.set_defaults(handler=handle_discover_cycles)

    panels_parser = subparsers.add_parser(
        "build-research-panels", help="prepare governed annual/monthly panels from explicit raw inputs",
    )
    panels_parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    panels_parser.add_argument("--destination", type=Path, required=True)
    panels_parser.add_argument("--annual-start", type=int, required=True)
    panels_parser.add_argument("--annual-end", type=int, required=True)
    panels_parser.add_argument("--monthly-start", type=_parse_iso_date, required=True)
    panels_parser.add_argument("--monthly-end", type=_parse_iso_date, required=True)
    panels_parser.set_defaults(handler=handle_build_research_panels)

    c4_parser = subparsers.add_parser(
        "build-c4-research", help="build paired validated C4 bridge and asset statistics",
    )
    c4_parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    c4_parser.add_argument("--destination", type=Path, required=True)
    c4_parser.add_argument("--through", type=_parse_iso_date, required=True)
    c4_features = c4_parser.add_mutually_exclusive_group(required=True)
    c4_features.add_argument("--features", type=Path, help="local monthly C4 feature parquet")
    c4_features.add_argument(
        "--fetch-features", action="store_true", help="explicitly fetch PMI/PPI using configured Tushare",
    )
    c4_parser.set_defaults(handler=handle_build_c4_research)

    state_parser = subparsers.add_parser(
        "build-state-research", help="build paired C5/C7 state research and historical asset associations",
    )
    state_parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    state_parser.add_argument("--destination", type=Path, required=True)
    state_signals = state_parser.add_mutually_exclusive_group()
    state_signals.add_argument("--public-signal-dir", type=Path, help="existing four FRED CSV inputs")
    state_signals.add_argument("--refresh-public", action="store_true", help="explicitly fetch FRED into the new output")
    state_parser.set_defaults(handler=handle_build_state_research)

    forecast_parser = subparsers.add_parser(
        "build-asset-forecast", help="build paired asset forecasts and synchronous reference",
    )
    forecast_parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    forecast_parser.add_argument("--destination", type=Path, required=True)
    forecast_parser.add_argument("--workers", type=int, default=1)
    forecast_parser.set_defaults(handler=handle_build_asset_forecast)

    cycle_inputs_parser = subparsers.add_parser(
        "build-cycle-inputs",
        help="convert local research panels to an offline pseudo-vintage cycle input bundle",
    )
    cycle_inputs_parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT,
        help="input root with data/ panels and output/ selection metadata; defaults to cwd",
    )
    cycle_inputs_parser.add_argument(
        "--config-dir", type=Path,
        help="registry directory; defaults to PROJECT_ROOT/config/seven_cycle",
    )
    cycle_inputs_parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="destination directory; an existing cycle input file is never overwritten",
    )
    for option in ("--as-of", "--state-start", "--state-end"):
        cycle_inputs_parser.add_argument(option, type=_parse_iso_date, required=True)
    cycle_inputs_parser.add_argument(
        "--verification-cutoff", type=_parse_iso_date, action="append",
        dest="verification_cutoffs", required=True,
    )
    cycle_inputs_parser.add_argument("--max-members-per-category", type=int, default=5)
    cycle_inputs_parser.add_argument("--minimum-coverage-pct", type=float, default=0.0)
    cycle_inputs_parser.set_defaults(handler=handle_build_cycle_inputs)

    validate_parser = subparsers.add_parser("validate-config")
    validate_parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
    )
    validate_parser.set_defaults(handler=handle_validate_config)

    build_command = subparsers.add_parser("build")
    build_command.add_argument("--as-of", type=_parse_iso_date, required=True)
    build_command.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
    )
    build_command.add_argument(
        "--product-root",
        type=Path,
        default=DEFAULT_FOUNDATION_PRODUCT_ROOT,
    )
    build_command.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_PROJECT_ROOT,
    )
    build_command.add_argument("--catalog-root", type=Path)
    research_inputs_group = build_command.add_mutually_exclusive_group()
    research_inputs_group.add_argument(
        "--research-output-dir",
        type=Path,
        help="directory of research output JSON inputs; defaults to PROJECT_ROOT/output",
    )
    research_inputs_group.add_argument(
        "--research-bundle-dir", type=Path,
        help="exported paired research snapshot; replaces all five built browser data files",
    )
    build_command.add_argument(
        "--web-project-root",
        type=Path,
        default=DEFAULT_WEB_PROJECT_ROOT,
    )
    build_command.set_defaults(handler=handle_build)

    build_foundation_command = subparsers.add_parser("build-foundation")
    build_foundation_command.add_argument(
        "--as-of",
        type=_parse_iso_date,
        required=True,
    )
    build_foundation_command.add_argument(
        "--product-root",
        type=Path,
        default=DEFAULT_FOUNDATION_PRODUCT_ROOT,
    )
    build_foundation_command.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_PROJECT_ROOT,
    )
    build_foundation_command.add_argument("--catalog-root", type=Path)
    build_foundation_command.set_defaults(handler=handle_build_foundation)

    build_cycles_command = subparsers.add_parser("build-cycles")
    build_cycles_command.add_argument(
        "--as-of",
        type=_parse_iso_date,
        required=True,
    )
    build_cycles_command.add_argument(
        "--strict-vintage",
        action="store_true",
    )
    build_cycles_command.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
    )
    build_cycles_command.add_argument(
        "--product-root",
        type=Path,
        default=DEFAULT_PRODUCT_ROOT,
    )
    build_cycles_command.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
    )
    build_cycles_command.set_defaults(handler=handle_build_cycles)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--run-id", type=_parse_run_id, required=True)
    verify_parser.add_argument(
        "--product-root",
        type=Path,
        default=DEFAULT_PRODUCT_ROOT,
    )
    verify_parser.set_defaults(handler=handle_verify)

    baijiu_report_parser = subparsers.add_parser("report-baijiu-2019")
    baijiu_report_parser.add_argument(
        "--run-id",
        type=_parse_run_id,
        required=True,
    )
    baijiu_report_parser.add_argument(
        "--product-root",
        type=Path,
        default=DEFAULT_PRODUCT_ROOT,
    )
    baijiu_report_parser.set_defaults(handler=handle_report_baijiu_2019)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument(
        "--port",
        type=_parse_port,
        metavar="PORT",
        default=8008,
    )
    serve_parser.add_argument(
        "--product-root",
        type=Path,
        default=DEFAULT_FOUNDATION_PRODUCT_ROOT,
    )
    serve_parser.add_argument(
        "--catalog-root",
        type=Path,
        default=DEFAULT_FOUNDATION_CATALOG_ROOT,
    )
    serve_parser.add_argument(
        "--web-root",
        type=Path,
        default=DEFAULT_WEB_ROOT,
    )
    serve_parser.add_argument(
        "--repair-catalog-on-start",
        action="store_true",
        help=(
            "strictly rebuild a catalog only when verified filesystem device "
            "identity drift is the sole mismatch"
        ),
    )
    serve_parser.set_defaults(handler=handle_serve)

    service_parser = subparsers.add_parser("service")
    service_parser.add_argument(
        "action",
        choices=("start", "stop", "restart", "status"),
    )
    service_parser.add_argument("--host", default="127.0.0.1")
    service_parser.add_argument(
        "--port",
        type=_parse_port,
        metavar="PORT",
        default=4174,
    )
    service_parser.add_argument(
        "--product-root",
        type=Path,
        default=DEFAULT_FOUNDATION_PRODUCT_ROOT,
    )
    service_parser.add_argument(
        "--catalog-root",
        type=Path,
        default=DEFAULT_FOUNDATION_CATALOG_ROOT,
    )
    service_parser.add_argument(
        "--web-root",
        type=Path,
        default=DEFAULT_WEB_ROOT,
    )
    service_parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_SERVICE_STATE_PATH,
    )
    service_parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_SERVICE_LOG_PATH,
    )
    service_parser.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_PROJECT_ROOT,
    )
    service_parser.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
    )
    service_parser.add_argument(
        "--repair-catalog-on-start",
        action="store_true",
        help=(
            "strictly rebuild a catalog only when verified filesystem device "
            "identity drift is the sole mismatch"
        ),
    )
    service_parser.set_defaults(handler=handle_service)

    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parse_args(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else 1
    try:
        return arguments.handler(arguments)
    except CLIError as error:
        message = redact_secrets(str(error))
        print(f"error: {message}", file=sys.stderr)
        return 1
