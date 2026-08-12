#!/usr/bin/env python3
"""Validate production Compose profiles and resource guardrails."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "deploy" / "server"


def render(compose_file: str, env_file: str) -> dict:
    command = [
        "docker",
        "compose",
        "--env-file",
        str(SERVER / env_file),
        "-f",
        str(SERVER / compose_file),
        "--profile",
        "*",
        "config",
        "--no-env-resolution",
        "--no-path-resolution",
        "--format",
        "json",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def validate_guardrails(label: str, config: dict, issues: list[str]) -> None:
    for name, service in config.get("services", {}).items():
        prefix = f"{label}:{name}"
        try:
            memory_limit = int(service.get("mem_limit", 0))
        except (TypeError, ValueError):
            memory_limit = 0
        if memory_limit <= 0:
            issues.append(f"{prefix} has no positive mem_limit")
        if int(service.get("pids_limit", 0) or 0) <= 0:
            issues.append(f"{prefix} has no positive pids_limit")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            issues.append(f"{prefix} is missing no-new-privileges:true")


def validate_profiles(
    label: str,
    config: dict,
    expected: dict[str, set[str]],
    issues: list[str],
) -> None:
    services = config.get("services", {})
    for name, required_profiles in expected.items():
        if name not in services:
            issues.append(f"{label}:{name} is missing")
            continue
        actual_profiles = set(services[name].get("profiles", []))
        missing = sorted(required_profiles - actual_profiles)
        if missing:
            issues.append(
                f"{label}:{name} is missing profiles: {', '.join(missing)}"
            )


def validate_newma_webui_route(config: dict, issues: list[str]) -> None:
    api = config.get("services", {}).get("api", {})
    extra_hosts = api.get("extra_hosts", {})
    if isinstance(extra_hosts, list):
        has_host_gateway = any(
            str(entry).startswith(
                ("host.docker.internal:", "host.docker.internal=")
            )
            for entry in extra_hosts
        )
    else:
        has_host_gateway = "host.docker.internal" in extra_hosts
    if not has_host_gateway:
        issues.append("core:api cannot resolve the Docker host WebUI listener")

    env_text = (SERVER / ".env.server.example").read_text(encoding="utf-8")
    if "NEWMA_DESK_HERMES_WEBUI_BASE_URL=" not in env_text:
        issues.append("core:.env.server.example is missing the Desk -> WebUI route")


def main() -> int:
    if shutil.which("docker") is None:
        print("docker CLI with the Compose plugin is required", file=sys.stderr)
        return 2

    try:
        core = render("docker-compose.yml", ".env.server.example")
        external = render("docker-compose.external.yml", ".env.external.example")
        integrations = render(
            "docker-compose.integrations.yml", ".env.external.example"
        )
    except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr.strip(), file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1

    issues: list[str] = []
    validate_guardrails("core", core, issues)
    validate_guardrails("external", external, issues)
    validate_guardrails("integrations", integrations, issues)
    validate_profiles(
        "core",
        core,
        {
            "api": {"core", "ops"},
            "desk": {"core"},
            "gateway": {"core"},
            "register-mods": {"ops"},
        },
        issues,
    )
    validate_newma_webui_route(core, issues)
    validate_profiles(
        "integrations",
        integrations,
        {
            "deepsee": {"optional-integrations", "deepsee"},
            "seven-cycle": {"optional-integrations", "seven-cycle"},
            "instock": {"optional-integrations", "instock"},
            "orchestra-postgres": {"optional-integrations", "orchestra"},
            "orchestra-redis": {"optional-integrations", "orchestra"},
            "orchestra-api": {"optional-integrations", "orchestra"},
            "orchestra-web": {"optional-integrations", "orchestra"},
        },
        issues,
    )

    if issues:
        for issue in issues:
            print(f"ERROR {issue}", file=sys.stderr)
        return 1
    print("Compose profiles and resource guardrails passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
