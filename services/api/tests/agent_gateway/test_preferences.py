import sqlite3
from pathlib import Path

from vibe_visualization_api.agent_gateway.preferences import AgentPreferenceStore


def test_existing_agent_preferences_table_is_migrated(tmp_path: Path) -> None:
    database_path = tmp_path / "preferences.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE agent_preferences (
              user_id TEXT PRIMARY KEY,
              default_adapter TEXT NOT NULL,
              module_overrides_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO agent_preferences (
              user_id, default_adapter, module_overrides_json, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "alice",
                "codex-cli",
                '{"deepsee-ai-insights":"claude-cli"}',
                "2026-08-18T00:00:00+00:00",
            ),
        )

    preferences = AgentPreferenceStore(database_path).get(
        "alice",
        "gemini-cli",
    )

    assert preferences.default_adapter == "codex-cli"
    assert preferences.module_overrides == {
        "deepsee-ai-insights": "claude-cli"
    }
    assert preferences.profile_targets == {}
    assert preferences.module_profile_overrides == {}
