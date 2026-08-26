import asyncio

import httpx
from fastapi import FastAPI, Request

from orchestra_app import engine as engine_module
from orchestra_app.credentials import CredentialBundle
from orchestra_app.engine import AgentScopeEngine
from orchestra_app.models import AgentConnection
from orchestra_app.registry import get_profile


def test_external_http_agent_receives_profile_skills_and_bearer_secret(monkeypatch) -> None:
    app = FastAPI()
    received: dict[str, object] = {}

    @app.post("/research")
    async def research(request: Request) -> dict[str, str]:
        received["authorization"] = request.headers.get("authorization")
        received["payload"] = await request.json()
        return {"output": "外部 Agent 已返回可审计研究结论。"}

    original_client = httpx.AsyncClient

    def local_client(*args, **kwargs):
        return original_client(
            *args,
            **kwargs,
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    monkeypatch.setattr(engine_module.httpx, "AsyncClient", local_client)
    credentials = CredentialBundle(
        openai_api_key="test-openai-key",
        agent_secrets={"agent-secret": "external-bearer-token"},
    )
    engine = AgentScopeEngine(credentials)
    profile = get_profile("MACRO-01").model_copy(
        update={
            "connection": AgentConnection(
                kind="external_http",
                endpoint="http://testserver/research",
                secret_id="agent-secret",
                timeout_seconds=30,
            ),
        },
    )

    async def fake_skill_context(*_args, **_kwargs) -> str:
        return "## Skill context\n\n可审计技能内容"

    monkeypatch.setattr(engine, "_external_skill_context", fake_skill_context)
    events: list[tuple[str, dict[str, object]]] = []

    async def emit(event_type: str, payload: dict[str, object]) -> None:
        events.append((event_type, payload))

    output = asyncio.run(engine.run_agent(profile, "分析存储行业", "research", emit))
    payload = received["payload"]

    assert output == "外部 Agent 已返回可审计研究结论。"
    assert received["authorization"] == "Bearer external-bearer-token"
    assert isinstance(payload, dict)
    assert payload["agent"]["id"] == "MACRO-01"
    assert payload["skills"] == profile.skills
    assert payload["skill_context"].startswith("## Skill context")
    assert any(event_type == "agent.output.delta" for event_type, _ in events)
    assert any(event_type == "agent.tool.completed" for event_type, _ in events)
