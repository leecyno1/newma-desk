import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from vibe_visualization_api.agent_gateway.models import AgentPreferences


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_preferences (
  user_id TEXT PRIMARY KEY,
  default_adapter TEXT NOT NULL,
  module_overrides_json TEXT NOT NULL,
  profile_targets_json TEXT NOT NULL DEFAULT '{}',
  module_profile_overrides_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);
"""


class AgentPreferenceStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path
        self._initialized = False
        self._initialize_lock = threading.Lock()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._database_path, timeout=10) as connection:
                connection.executescript(SCHEMA)
                columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(agent_preferences)"
                    ).fetchall()
                }
                if "profile_targets_json" not in columns:
                    connection.execute(
                        "ALTER TABLE agent_preferences ADD COLUMN "
                        "profile_targets_json TEXT NOT NULL DEFAULT '{}'"
                    )
                if "module_profile_overrides_json" not in columns:
                    connection.execute(
                        "ALTER TABLE agent_preferences ADD COLUMN "
                        "module_profile_overrides_json TEXT NOT NULL DEFAULT '{}'"
                    )
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        self._ensure_initialized()
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def get(self, user_id: str, default_adapter: str) -> AgentPreferences:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT default_adapter, module_overrides_json,
                       profile_targets_json, module_profile_overrides_json,
                       updated_at
                FROM agent_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return AgentPreferences(
                user_id=user_id,
                default_adapter=default_adapter,
                module_overrides={},
                profile_targets={},
                module_profile_overrides={},
                updated_at=None,
            )
        overrides = self._json_object(row["module_overrides_json"])
        profile_targets = self._json_object(row["profile_targets_json"])
        module_profile_overrides = self._json_object(
            row["module_profile_overrides_json"]
        )
        return AgentPreferences(
            user_id=user_id,
            default_adapter=row["default_adapter"],
            module_overrides=overrides,
            profile_targets=profile_targets,
            module_profile_overrides=module_profile_overrides,
            updated_at=row["updated_at"],
        )

    def set(
        self,
        user_id: str,
        default_adapter: str,
        module_overrides: dict[str, str],
        profile_targets: dict[str, str] | None = None,
        module_profile_overrides: dict[str, dict[str, str]] | None = None,
    ) -> AgentPreferences:
        updated_at = datetime.now(UTC).isoformat()
        profile_targets = profile_targets or {}
        module_profile_overrides = module_profile_overrides or {}
        serialized = self._serialize(module_overrides)
        serialized_profiles = self._serialize(profile_targets)
        serialized_module_profiles = self._serialize(module_profile_overrides)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_preferences (
                  user_id, default_adapter, module_overrides_json,
                  profile_targets_json, module_profile_overrides_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  default_adapter = excluded.default_adapter,
                  module_overrides_json = excluded.module_overrides_json,
                  profile_targets_json = excluded.profile_targets_json,
                  module_profile_overrides_json =
                    excluded.module_profile_overrides_json,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    default_adapter,
                    serialized,
                    serialized_profiles,
                    serialized_module_profiles,
                    updated_at,
                ),
            )
        return AgentPreferences(
            user_id=user_id,
            default_adapter=default_adapter,
            module_overrides=module_overrides,
            profile_targets=profile_targets,
            module_profile_overrides=module_profile_overrides,
            updated_at=updated_at,
        )

    def resolve(
        self,
        user_id: str,
        module_id: str | None,
        default_adapter: str,
    ) -> str:
        return self.resolve_profile(
            user_id,
            module_id,
            "deep",
            default_adapter,
        )

    def resolve_profile(
        self,
        user_id: str,
        module_id: str | None,
        profile: str,
        default_target: str,
    ) -> str:
        preferences = self.get(user_id, default_target)
        if module_id is not None:
            selected_profile = preferences.module_profile_overrides.get(
                module_id, {}
            ).get(profile)
            if selected_profile:
                return selected_profile
        if profile == "deep" and module_id is not None:
            selected = preferences.module_overrides.get(module_id)
            if selected:
                return selected
        selected_profile = preferences.profile_targets.get(profile)
        if selected_profile:
            return selected_profile
        return preferences.default_adapter if profile == "deep" else default_target

    def resolve_existing_profile(
        self,
        user_id: str,
        module_id: str | None,
        profile: str,
        default_target: str,
    ) -> str:
        if not self._database_path.is_file():
            return default_target
        return self.resolve_profile(user_id, module_id, profile, default_target)

    @staticmethod
    def _json_object(value: object) -> dict:
        try:
            parsed = json.loads(value) if isinstance(value, str) else {}
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _serialize(value: dict) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
