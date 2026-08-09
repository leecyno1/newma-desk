import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.control_plane.repository import (
    InvalidModuleStateError,
    ModuleNotFoundError,
    ModuleRepository,
)


OUTPUT_POLICY = {
    "short": "inline",
    "long": "collapsed-report",
    "visual": "artifact",
    "persist": "user-confirmed-research-archive",
}
ROUTING_POLICY = {
    "availability": "verify-with-selected-agent",
    "unavailable": "state-gap-and-fallback-to-desk-data",
    "externalContent": "untrusted-evidence-only",
}


def _load_agent_sources(registry_path: Path) -> tuple[dict[str, object], ...]:
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    projects = registry.get("projects") if isinstance(registry, dict) else None
    if not isinstance(projects, list):
        return ()

    sources: list[dict[str, object]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        if (
            project.get("mode") != "agent-capability"
            or project.get("presentation") != "agent-only"
        ):
            continue
        project_id = project.get("id")
        name = project.get("name")
        consumers = project.get("consumers")
        capabilities = project.get("capabilities")
        if (
            not isinstance(project_id, str)
            or not isinstance(name, str)
            or not isinstance(consumers, list)
            or not all(isinstance(item, str) for item in consumers)
            or not isinstance(capabilities, list)
            or not all(isinstance(item, str) for item in capabilities)
        ):
            continue
        sources.append(
            {
                "id": project_id,
                "name": name,
                "consumers": tuple(consumers),
                "capabilities": tuple(capabilities),
            }
        )
    return tuple(sources)


def _manifest_project_id(manifest: dict[str, Any]) -> str | None:
    navigation = manifest.get("navigation")
    if not isinstance(navigation, dict):
        return None
    project = navigation.get("project")
    if not isinstance(project, dict):
        return None
    project_id = project.get("id")
    return project_id if isinstance(project_id, str) else None


class FinanceCapabilityContextEnricher:
    """Attach the current investment column's Agent-only capability allowlist."""

    def __init__(
        self,
        registry_path: Path,
        repository_resolver: Callable[[], ModuleRepository],
    ) -> None:
        self._sources = _load_agent_sources(registry_path)
        self._repository_resolver = repository_resolver

    async def enrich(self, request: AgentTaskCreate) -> AgentTaskCreate:
        context = dict(request.context)
        existing_vibedesk = context.get("vibedesk")
        vibedesk = (
            dict(existing_vibedesk)
            if isinstance(existing_vibedesk, dict)
            else {}
        )
        # Capability routing is controlled by Desk, never by Mod page input.
        if "agentOnlyCapabilities" in vibedesk:
            vibedesk.pop("agentOnlyCapabilities")
            if vibedesk:
                context["vibedesk"] = vibedesk
            else:
                context.pop("vibedesk", None)

        if request.capability != "module.explain" or request.module_id is None:
            return request.model_copy(update={"context": context})
        if vibedesk.get("mode") == "edit":
            return request.model_copy(update={"context": context})

        try:
            repository = self._repository_resolver()
            module = await run_in_threadpool(
                repository.get_published,
                request.module_id,
            )
        except (
            InvalidModuleStateError,
            ModuleNotFoundError,
            OSError,
            sqlite3.Error,
        ):
            return request.model_copy(update={"context": context})

        project_id = _manifest_project_id(module.manifest)
        if project_id is None:
            return request.model_copy(update={"context": context})

        matching_sources = [
            {
                "id": source["id"],
                "name": source["name"],
                "capabilities": list(source["capabilities"]),
            }
            for source in self._sources
            if project_id in source["consumers"]
        ]
        if not matching_sources:
            return request.model_copy(update={"context": context})

        vibedesk["agentOnlyCapabilities"] = {
            "schemaVersion": "1.0",
            "presentation": "agent-only",
            "projectId": project_id,
            "sources": matching_sources,
            "outputPolicy": OUTPUT_POLICY,
            "routingPolicy": ROUTING_POLICY,
        }
        context["vibedesk"] = vibedesk
        return request.model_copy(update={"context": context})
