import asyncio
from types import SimpleNamespace

from agentscope.state import AgentState
from agentscope.tool import Toolkit

from orchestra_app.engine import AgentScopeEngine
from orchestra_app.registry import get_profile, required_skill_names, skill_paths_for


def test_required_skills_are_loaded_through_agentscope_viewer() -> None:
    async def scenario() -> None:
        profile = get_profile("MACRO-01")
        agent = SimpleNamespace(
            toolkit=Toolkit(skills_or_loaders=skill_paths_for(profile)),
            state=AgentState(),
        )
        events: list[tuple[str, dict[str, str]]] = []

        async def emit(event_type: str, payload: dict[str, str]) -> None:
            events.append((event_type, payload))

        engine = object.__new__(AgentScopeEngine)
        context = await engine._activate_required_skills(agent, profile, emit)  # noqa: SLF001
        required = required_skill_names(profile)
        used = [payload["skill"] for event, payload in events if event == "agent.skill.used"]
        registered = [
            payload["skill"] for event, payload in events if event == "agent.skill.registered"
        ]

        assert used == required
        assert set(required).issubset(registered)
        assert all(f"## Skill: {skill}" in context for skill in required)
        assert "优先使用一手官方来源" in context

    asyncio.run(scenario())
