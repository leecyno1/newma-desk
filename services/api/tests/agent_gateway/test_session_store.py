from vibe_visualization_api.agent_gateway.session_store import (
    AgentModuleSessionStore,
)


def test_agent_module_session_store_isolates_user_agent_and_module(tmp_path) -> None:
    store = AgentModuleSessionStore(tmp_path / "sessions.db")
    first = store.set("alice", "hermes-webui", "market-daily", "session-a")
    store.set("bob", "hermes-webui", "market-daily", "session-b")
    store.set("alice", "hermes-webui", "alpha-zoo", "session-c")

    assert first.upstream_session_id == "session-a"
    assert store.get(
        "alice", "hermes-webui", "market-daily"
    ).upstream_session_id == "session-a"
    assert store.get(
        "bob", "hermes-webui", "market-daily"
    ).upstream_session_id == "session-b"
    assert store.get(
        "alice", "hermes-webui", "alpha-zoo"
    ).upstream_session_id == "session-c"


def test_agent_module_session_store_replaces_and_deletes_mapping(tmp_path) -> None:
    store = AgentModuleSessionStore(tmp_path / "sessions.db")
    original = store.set(
        "local-user", "hermes-webui", "market-daily", "session-a"
    )
    replacement = store.set(
        "local-user", "hermes-webui", "market-daily", "session-b"
    )

    assert replacement.upstream_session_id == "session-b"
    assert replacement.created_at == original.created_at
    assert store.delete("local-user", "hermes-webui", "market-daily") is True
    assert store.get("local-user", "hermes-webui", "market-daily") is None
