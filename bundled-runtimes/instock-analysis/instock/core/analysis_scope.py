"""Request-local ownership for analysis results, including worker-thread calls.

The unsigned standalone API is a local, single-user surface. Desk requests use
the user/workspace from a verified Mod session, never from caller identity headers.
This partitions local workspaces; it does not add account authentication to Desk.
"""

from contextvars import ContextVar
import json


analysis_scope: ContextVar[str] = ContextVar("analysis_scope", default="standalone:local")
# Request-only credentials, never persisted in snapshots, caches or Context.
analysis_session: ContextVar[tuple[str, str] | None] = ContextVar("analysis_session", default=None)


def desk_scope(user_id: str, workspace_id: str) -> str:
    if not all(isinstance(value, str) and 1 <= len(value) <= 128 for value in (user_id, workspace_id)):
        raise ValueError("Invalid analysis owner")
    return "desk:" + json.dumps([user_id, workspace_id], ensure_ascii=True, separators=(",", ":"))
