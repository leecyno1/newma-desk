from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vibe_visualization_api.finance_pilots.models import (
    PilotAuditStatus,
    PilotRuntimeStatus,
)


CLEAN_DEPENDENCY_AUDIT = "no-known-vulnerabilities"


class FinancePilotDescriptorError(ValueError):
    """Raised when the checked-in pilot descriptor cannot be trusted."""


def _enabled(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _configured_env(environment: Mapping[str, str], name: str) -> str:
    prefixes = ("NEWMA_DESK_", "NEWMA_DOCK_", "VIBEDESK_")
    suffix = next(
        (name.removeprefix(prefix) for prefix in prefixes if name.startswith(prefix)),
        None,
    )
    if suffix is None:
        return environment.get(name, "").strip()
    return next(
        (
            configured
            for prefix in prefixes
            if (configured := environment.get(f"{prefix}{suffix}", "").strip())
        ),
        "",
    )


class FinancePilotPolicy:
    def __init__(
        self,
        descriptor_path: Path,
        *,
        project_root: Path,
        environment: Mapping[str, str] | None = None,
    ):
        self._descriptor_path = descriptor_path.expanduser().resolve()
        self._project_root = project_root.expanduser().resolve()
        self._environment = os.environ if environment is None else environment
        self._descriptor = self._load_descriptor()

    def _load_descriptor(self) -> dict[str, Any]:
        value = json.loads(self._descriptor_path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("schemaVersion") != "1.0"
            or not isinstance(value.get("pilots"), list)
        ):
            raise FinancePilotDescriptorError(
                "unsupported external finance pilot descriptor"
            )
        return value

    def _pilot(self, pilot_id: str) -> Mapping[str, Any]:
        for pilot in self._descriptor["pilots"]:
            if isinstance(pilot, Mapping) and pilot.get("id") == pilot_id:
                return pilot
        raise KeyError(f"unknown finance pilot: {pilot_id}")

    def pilot_ids(self) -> list[str]:
        return [
            str(pilot["id"])
            for pilot in self._descriptor["pilots"]
            if isinstance(pilot, Mapping) and pilot.get("id")
        ]

    def _workspace(self, pilot: Mapping[str, Any]) -> Path:
        workspace = pilot.get("workspace")
        if not isinstance(workspace, Mapping):
            raise FinancePilotDescriptorError("pilot workspace is missing")
        configured = _configured_env(
            self._environment,
            str(workspace.get("env") or ""),
        )
        if configured:
            path = Path(configured).expanduser()
            return (path if path.is_absolute() else self._project_root / path).resolve()
        candidates = workspace.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise FinancePilotDescriptorError("pilot workspace candidates are missing")
        resolved = [(self._project_root / str(value)).resolve() for value in candidates]
        return next((path for path in resolved if path.exists()), resolved[0])

    def status(self, pilot_id: str) -> PilotRuntimeStatus:
        pilot = self._pilot(pilot_id)
        activation = pilot.get("activation")
        audit = pilot.get("audit")
        runtime = pilot.get("runtime")
        capabilities = pilot.get("capabilities")
        if not all(
            isinstance(value, Mapping)
            for value in (activation, audit, runtime, capabilities)
        ):
            raise FinancePilotDescriptorError("pilot policy fields are missing")
        requested = _enabled(
            _configured_env(self._environment, str(activation.get("env") or ""))
        )
        dependency_audit = str(audit.get("dependencyAudit") or "missing")
        workspace = self._workspace(pilot)
        origin = str(runtime.get("origin") or "")
        reasons: list[str] = []
        if not requested:
            reasons.append("activation-not-requested")
        if dependency_audit != CLEAN_DEPENDENCY_AUDIT:
            reasons.append(f"dependency-audit:{dependency_audit}")
        if not workspace.exists():
            reasons.append("workspace-missing")
        blocking = [reason for reason in reasons if reason != "activation-not-requested"]
        state = "disabled" if not requested else "blocked" if blocking else "eligible"
        return PilotRuntimeStatus(
            pilot_id=str(pilot["id"]),
            label=str(pilot.get("label") or pilot["id"]),
            mode=str(pilot["mode"]),
            state=state,
            requested=requested,
            activatable=requested and not blocking,
            reasons=reasons,
            audit=PilotAuditStatus(
                revision=str(audit.get("revision") or ""),
                tag=str(audit.get("tag")) if audit.get("tag") else None,
                reviewed_at=(
                    str(audit.get("reviewedAt")) if audit.get("reviewedAt") else None
                ),
                dependency_audit=dependency_audit,
            ),
            workspace=str(workspace),
            workspace_exists=workspace.exists(),
            origin=origin,
            capabilities=[
                str(value)
                for value in capabilities.get("allow", [])
                if isinstance(value, str)
            ],
        )

    def statuses(self) -> list[PilotRuntimeStatus]:
        return [self.status(pilot_id) for pilot_id in self.pilot_ids()]

    def sanitized_environment(self, pilot_id: str) -> dict[str, str]:
        pilot = self._pilot(pilot_id)
        isolation = pilot.get("isolation")
        if not isinstance(isolation, Mapping):
            raise FinancePilotDescriptorError("pilot isolation policy is missing")
        allowlist = isolation.get("environmentAllowlist")
        if not isinstance(allowlist, list):
            raise FinancePilotDescriptorError("pilot environment allowlist is missing")
        return {
            name: self._environment[name]
            for value in allowlist
            if isinstance(value, str)
            if (name := value) in self._environment
        }
