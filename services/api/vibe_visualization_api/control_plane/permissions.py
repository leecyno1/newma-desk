from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool = False
    action: dict[str, Any] | None = None


def authorize_action(
    manifest: dict[str, object],
    capability: str,
) -> ActionDecision:
    if manifest.get("schemaVersion") == "1.1":
        actions = manifest.get("actions", {})
        if not isinstance(actions, dict):
            return ActionDecision(False, "invalid action declarations")
        declared = actions.get(capability)
        if not isinstance(declared, dict):
            return ActionDecision(False, "action is not declared")
        permission = declared.get("permission")
        permissions = set(manifest.get("permissions", []))
        if not isinstance(permission, str) or permission not in permissions:
            return ActionDecision(False, "action permission is not granted")
        confirmation = declared.get("confirmation", "none")
        return ActionDecision(
            True,
            "explicit action binding",
            confirmation != "none",
            declared,
        )

    permissions = set(manifest.get("permissions", []))
    if capability == "trade.execute":
        return ActionDecision(
            "trade.execute" in permissions,
            "trade confirmation required",
            True,
        )
    declared = set(manifest.get("agentCapabilities", []))
    return ActionDecision(
        capability in declared,
        "agent capability declaration",
    )
