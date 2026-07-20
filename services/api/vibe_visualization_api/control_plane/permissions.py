from dataclasses import dataclass


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool = False


def authorize_action(
    manifest: dict[str, object],
    capability: str,
) -> ActionDecision:
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
