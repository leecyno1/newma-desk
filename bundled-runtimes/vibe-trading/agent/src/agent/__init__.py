"""Lazy public surface for the native Vibe-Trading Agent.

Importing a lightweight type such as :class:`BaseTool` used to initialize the
entire LLM stack.  Integrated Newma-Desk runtimes do not use that native Agent,
so keep each export behind a module-level lazy lookup.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent.loop import AgentLoop
    from src.agent.memory import WorkspaceMemory
    from src.agent.skills import SkillsLoader
    from src.agent.tools import BaseTool, ToolRegistry

__all__ = ["AgentLoop", "WorkspaceMemory", "SkillsLoader", "BaseTool", "ToolRegistry"]

_EXPORTS = {
    "AgentLoop": ("src.agent.loop", "AgentLoop"),
    "WorkspaceMemory": ("src.agent.memory", "WorkspaceMemory"),
    "SkillsLoader": ("src.agent.skills", "SkillsLoader"),
    "BaseTool": ("src.agent.tools", "BaseTool"),
    "ToolRegistry": ("src.agent.tools", "ToolRegistry"),
}


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
