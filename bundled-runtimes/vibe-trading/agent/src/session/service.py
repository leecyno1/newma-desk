"""Session lifecycle orchestration for message flow, attempt creation, and execution scheduling.

V5: Uses AgentLoop instead of the fixed pipeline behind the generate skill.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from src.config.accessor import get_env_config
from src.session.events import EventBus
from src.session.models import (
    Attempt,
    AttemptStatus,
    Message,
    Session,
)
from src.session.search import get_shared_index
from src.session.store import SessionStore

if TYPE_CHECKING:
    from src.agent.loop import AgentLoop

# Dedicated thread pool limited to four concurrent agents to avoid exhausting the default executor.
_AGENT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent")


def _agent_run_timeout_seconds() -> int:
    """Return a hard wall-clock timeout for web/API session attempts."""
    return max(1, get_env_config().agent_tuning.vibe_trading_agent_timeout_seconds)


def _stale_attempt_seconds() -> int:
    return max(60, _agent_run_timeout_seconds())


class SessionService:
    """Session lifecycle service.

    Attributes:
        store: Session persistence store.
        event_bus: SSE event bus.
        runs_dir: Root runs directory.
    """

    def __init__(
        self,
        store: SessionStore,
        event_bus: EventBus,
        runs_dir: Path,
    ) -> None:
        """Initialize the session service.

        Args:
            store: Session persistence store.
            event_bus: SSE event bus.
            runs_dir: Root runs directory.
        """
        self.store = store
        self.event_bus = event_bus
        self.runs_dir = runs_dir
        self._active_loops: Dict[str, "AgentLoop"] = {}
        self._search_index = get_shared_index()

    def create_session(self, title: str = "", config: Optional[Dict[str, Any]] = None) -> Session:
        """Create a new session.

        Args:
            title: Session title.
            config: Session configuration.

        Returns:
            The newly created Session.
        """
        session = Session(title=title, config=config or {})
        self.store.create_session(session)
        self._search_index.index_session(session.session_id, title)
        self.event_bus.emit(session.session_id, "session.created", {"session_id": session.session_id, "title": title})
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return a session by ID."""
        session = self.store.get_session(session_id)
        if session:
            self._recover_stale_attempt(session)
        return session

    def list_sessions(self, limit: int = 50) -> list[Session]:
        """List all sessions."""
        sessions = self.store.list_sessions(limit)
        for session in sessions:
            self._recover_stale_attempt(session)
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        self.event_bus.clear(session_id)
        return self.store.delete_session(session_id)

    async def send_message(
        self,
        session_id: str,
        content: str,
        role: str = "user",
        *,
        include_shell_tools: bool = False,
    ) -> Dict[str, Any]:
        """Send a message to a session and trigger execution.

        Args:
            session_id: Session ID.
            content: Message content.
            role: Message role.
            include_shell_tools: Whether this attempt may use shell tools.

        Returns:
            Dictionary containing message_id and attempt_id.
        """
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        message = Message(session_id=session_id, role=role, content=content)
        self.store.append_message(message)
        self._search_index.index_message(session_id, role, content)
        self.event_bus.emit(session_id, "message.received", {"message_id": message.message_id, "role": role, "content": content})

        if role != "user":
            return {"message_id": message.message_id}

        attempt = Attempt(session_id=session_id, parent_attempt_id=session.last_attempt_id, prompt=content)
        self.store.create_attempt(attempt)
        session.config["include_shell_tools"] = include_shell_tools
        session.last_attempt_id = attempt.attempt_id
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self.store.update_session(session)
        self.event_bus.emit(session_id, "attempt.created", {"attempt_id": attempt.attempt_id, "prompt": content})

        asyncio.create_task(self._run_attempt(session, attempt, include_shell_tools=include_shell_tools))
        return {"message_id": message.message_id, "attempt_id": attempt.attempt_id}

    def get_messages(self, session_id: str, limit: int = 100) -> list[Message]:
        """Return the message history."""
        session = self.store.get_session(session_id)
        if session:
            self._recover_stale_attempt(session)
        return self.store.get_messages(session_id, limit)

    def cancel_current(self, session_id: str) -> bool:
        """Cancel the currently running AgentLoop for a session.

        Args:
            session_id: Session ID.

        Returns:
            Whether cancellation succeeded. True means an active loop existed and received a cancel signal.
        """
        loop = self._active_loops.get(session_id)
        if loop is None:
            return False
        loop.cancel()
        return True

    async def _run_attempt(self, session: Session, attempt: Attempt, *, include_shell_tools: bool = False) -> None:
        """Execute an Attempt in the background."""
        attempt.mark_running()
        self.store.update_attempt(attempt)
        self.event_bus.emit(session.session_id, "attempt.started", {"attempt_id": attempt.attempt_id})

        try:
            messages = self.store.get_messages(session.session_id)
            result = await self._run_with_agent(
                attempt,
                messages=messages,
                include_shell_tools=include_shell_tools,
                session_config=dict(session.config),
            )
            if result.get("status") == "success":
                attempt.mark_completed(summary=result.get("content", ""))
            else:
                attempt.mark_failed(error=result.get("reason", "unknown"))
            attempt.run_dir = result.get("run_dir")

            self.store.update_attempt(attempt)
            reply_metadata = {}
            if attempt.run_dir:
                reply_metadata["run_id"] = Path(attempt.run_dir).name
            reply_metadata["status"] = attempt.status.value
            if attempt.metrics:
                reply_metadata["metrics"] = attempt.metrics

            reply = Message(
                session_id=session.session_id, role="assistant",
                content=self._format_result_message(attempt),
                linked_attempt_id=attempt.attempt_id,
                metadata=reply_metadata,
            )
            self.store.append_message(reply)
            self._search_index.index_message(session.session_id, "assistant", reply.content)
            self.event_bus.emit(
                session.session_id,
                "attempt.completed" if attempt.status == AttemptStatus.COMPLETED else "attempt.failed",
                {"attempt_id": attempt.attempt_id, "status": attempt.status.value,
                 "summary": attempt.summary, "error": attempt.error, "run_dir": attempt.run_dir},
            )

        except Exception as exc:
            attempt.mark_failed(error=str(exc))
            self.store.update_attempt(attempt)
            self.event_bus.emit(session.session_id, "attempt.failed", {"attempt_id": attempt.attempt_id, "error": str(exc)})

    async def _run_with_agent(
        self,
        attempt: Attempt,
        messages: list = None,
        *,
        include_shell_tools: bool = False,
        session_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an attempt with the V5 AgentLoop.

        Args:
            attempt: Current execution attempt.
            messages: Session message history.
            include_shell_tools: Whether the registry may include shell tools.
            session_config: Optional session-level config overrides. MCP server
                definitions under the ``mcpServers`` key are merged on top of
                the user config file via ``load_runtime_agent_config`` so each
                session can extend or override the global MCP server list.

        Returns:
            Result dictionary containing status, run_dir, run_id, metrics, and related fields.
        """
        from src.tools import build_registry
        from src.providers.chat import ChatLLM
        from src.agent.loop import AgentLoop
        from src.memory.persistent import PersistentMemory
        from src.config.loader import load_runtime_agent_config, sanitize_session_overrides

        llm = ChatLLM()
        pm = PersistentMemory()

        session_id = attempt.session_id
        attempt_id = attempt.attempt_id
        loop = asyncio.get_running_loop()

        safe_overrides = sanitize_session_overrides(session_config) if session_config else session_config
        agent_config = load_runtime_agent_config(overrides=safe_overrides)

        def event_callback(event_type: str, data: Dict[str, Any]) -> None:
            """Forward AgentLoop events to the SSE event bus."""
            data["attempt_id"] = attempt_id
            self.event_bus.emit(session_id, event_type, data)

        def _mcp_collision_warn(msg: str) -> None:
            """Forward MCP server-name collision warnings to the operator event channel."""
            self.event_bus.emit(session_id, "mcp.warning", {"attempt_id": attempt_id, "message": msg})

        registry = await loop.run_in_executor(
            _AGENT_EXECUTOR,
            lambda: build_registry(
                persistent_memory=pm,
                include_shell_tools=include_shell_tools,
                agent_config=agent_config,
                session_id=session_id,
                event_callback=event_callback,
                warn_callback=_mcp_collision_warn,
            ),
        )

        agent = AgentLoop(
            registry=registry,
            llm=llm,
            event_callback=event_callback,
            max_iterations=50,
            persistent_memory=pm,
        )
        self._active_loops[session_id] = agent

        # Build the message history context.
        history = self._convert_messages_to_history(messages) if messages else None

        try:
            future = loop.run_in_executor(
                _AGENT_EXECUTOR,
                lambda: agent.run(
                    user_message=attempt.prompt,
                    history=history,
                    session_id=session_id,
                ),
            )
            try:
                result = await asyncio.wait_for(future, timeout=_agent_run_timeout_seconds())
            except asyncio.TimeoutError:
                agent.cancel()
                raise TimeoutError(
                    f"agent run timed out after {_agent_run_timeout_seconds()} seconds"
                ) from None
        finally:
            self._active_loops.pop(session_id, None)

        # Load metrics from the run output when available.
        if result.get("run_dir"):
            metrics = self._load_metrics(Path(result["run_dir"]))
            if metrics:
                result["metrics"] = metrics

        return result

    @staticmethod
    def _convert_messages_to_history(messages: list) -> list[Dict[str, Any]]:
        """Convert Session messages into OpenAI-format history.

        Keeps the readable ``[prev_run: {run_id}]`` marker instead of removing it
        completely, and trims by character budget instead of a hard six-message cap
        so the LLM can still see previous artifact paths and strategy content during
        iterative updates.

        Args:
            messages: Session message list without the current turn.

        Returns:
            OpenAI-format messages trimmed from the newest items within the token budget.
        """
        import re
        from pathlib import Path

        def _shorten_run_dir(match: re.Match) -> str:
            path_str = match.group(0).replace("Run directory:", "").strip()
            run_id = Path(path_str).name if path_str else ""
            return f"[prev_run: {run_id}]" if run_id else ""

        history = []
        for msg in messages[:-1]:
            role = msg.role if hasattr(msg, "role") else msg.get("role", "user")
            content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            if not content.strip() or role not in ("user", "assistant"):
                continue
            content = re.sub(r"Run directory:\s*\S+", _shorten_run_dir, content).strip()
            if content:
                history.append({"role": role, "content": content})

        # Trim from the newest messages within a character budget of roughly 3000 tokens.
        MAX_HISTORY_CHARS = 12000
        total_chars = 0
        trimmed: list = []
        for msg in reversed(history):
            msg_len = len(msg.get("content", ""))
            if total_chars + msg_len > MAX_HISTORY_CHARS:
                break
            trimmed.append(msg)
            total_chars += msg_len
        return list(reversed(trimmed))

    @staticmethod
    def _load_metrics(run_dir: Path) -> Optional[Dict[str, Any]]:
        """Load metrics.csv from a run directory."""
        import csv
        metrics_path = run_dir / "artifacts" / "metrics.csv"
        if not metrics_path.exists():
            return None
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
                if rows:
                    return {k: float(v) for k, v in rows[0].items() if v}
        except Exception:
            pass
        return None

    def _recover_stale_attempt(self, session: Session) -> None:
        """Finalize a stale persisted attempt after process restart or timeout."""
        attempt_id = session.last_attempt_id
        if not attempt_id or session.session_id in self._active_loops:
            return
        attempt = self.store.get_attempt(session.session_id, attempt_id)
        if not attempt or attempt.status != AttemptStatus.RUNNING:
            return

        run_dir = Path(attempt.run_dir) if attempt.run_dir else self._find_run_dir_for_attempt(session, attempt)
        if run_dir is not None:
            state_path = run_dir / "state.json"
            state: dict[str, Any] = {}
            if state_path.exists():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    state = {}
            state_status = str(state.get("status") or "").lower()
            if state_status == "success":
                attempt.run_dir = str(run_dir)
                attempt.metrics = self._load_metrics(run_dir)
                attempt.mark_completed(summary=self._recover_summary(run_dir))
                self.store.update_attempt(attempt)
                self._append_recovered_assistant_message(session, attempt)
                self.event_bus.emit(
                    session.session_id,
                    "attempt.completed",
                    {
                        "attempt_id": attempt.attempt_id,
                        "status": attempt.status.value,
                        "summary": attempt.summary,
                        "error": attempt.error,
                        "run_dir": attempt.run_dir,
                    },
                )
                return
            if state_status == "failed":
                attempt.run_dir = str(run_dir)
                attempt.mark_failed(error=str(state.get("reason") or "stale run failed"))
                self.store.update_attempt(attempt)
                self._append_recovered_assistant_message(session, attempt)
                self.event_bus.emit(
                    session.session_id,
                    "attempt.failed",
                    {"attempt_id": attempt.attempt_id, "error": attempt.error},
                )
                return

        if not self._attempt_is_stale(attempt):
            return
        reason = f"attempt timed out after {_stale_attempt_seconds()} seconds"
        if run_dir is not None:
            attempt.run_dir = str(run_dir)
        attempt.mark_failed(error=reason)
        self.store.update_attempt(attempt)
        self._append_recovered_assistant_message(session, attempt)
        self.event_bus.emit(
            session.session_id,
            "attempt.failed",
            {"attempt_id": attempt.attempt_id, "error": reason},
        )

    def _find_run_dir_for_attempt(self, session: Session, attempt: Attempt) -> Optional[Path]:
        """Find a run directory by matching session id and prompt."""
        matches: list[tuple[float, Path]] = []
        for req_path in self.runs_dir.glob("*/req.json"):
            try:
                payload = json.loads(req_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            context = payload.get("context") or {}
            if context.get("session_id") != session.session_id:
                continue
            if str(payload.get("prompt") or "") != attempt.prompt:
                continue
            run_dir = req_path.parent
            try:
                mtime = req_path.stat().st_mtime
            except OSError:
                mtime = 0.0
            matches.append((mtime, run_dir))
        if not matches:
            return None
        matches.sort(reverse=True)
        return matches[0][1]

    def _recover_summary(self, run_dir: Path) -> str:
        trace_path = run_dir / "trace.jsonl"
        if trace_path.exists():
            try:
                for raw in reversed(trace_path.read_text(encoding="utf-8").splitlines()):
                    if not raw.strip():
                        continue
                    event = json.loads(raw)
                    if event.get("type") == "answer":
                        content = str(event.get("content") or "").strip()
                        if content:
                            return content
            except (OSError, json.JSONDecodeError):
                pass
        run_card = run_dir / "run_card.json"
        if run_card.exists():
            try:
                data = json.loads(run_card.read_text(encoding="utf-8"))
                metrics = data.get("metrics") or {}
                backtest = data.get("backtest") or {}
                codes = ", ".join(str(c) for c in backtest.get("codes", []))
                source = ", ".join(str(s) for s in data.get("data_sources", []))
                return (
                    "## Backtest Completed\n\n"
                    f"- Symbols: {codes or 'n/a'}\n"
                    f"- Period: {backtest.get('start_date', 'n/a')} to {backtest.get('end_date', 'n/a')}\n"
                    f"- Data source: {source or backtest.get('source', 'n/a')}\n"
                    f"- total_return: {metrics.get('total_return', 'n/a')}\n"
                    f"- sharpe: {metrics.get('sharpe', 'n/a')}\n"
                    f"- max_drawdown: {metrics.get('max_drawdown', 'n/a')}\n"
                    f"- trade_count: {metrics.get('trade_count', 'n/a')}\n\n"
                    f"Run directory: {run_dir}"
                )
            except (OSError, json.JSONDecodeError):
                pass
        return f"Recovered completed run: {run_dir}"

    def _append_recovered_assistant_message(self, session: Session, attempt: Attempt) -> None:
        messages = self.store.get_messages(session.session_id, limit=1000)
        if any(m.linked_attempt_id == attempt.attempt_id and m.role == "assistant" for m in messages):
            return
        metadata: Dict[str, Any] = {"status": attempt.status.value}
        if attempt.run_dir:
            metadata["run_id"] = Path(attempt.run_dir).name
        if attempt.metrics:
            metadata["metrics"] = attempt.metrics
        reply = Message(
            session_id=session.session_id,
            role="assistant",
            content=self._format_result_message(attempt),
            linked_attempt_id=attempt.attempt_id,
            metadata=metadata,
        )
        self.store.append_message(reply)
        self._search_index.index_message(session.session_id, "assistant", reply.content)

    @staticmethod
    def _attempt_is_stale(attempt: Attempt) -> bool:
        try:
            created_at = datetime.fromisoformat(attempt.created_at)
        except ValueError:
            return True
        if created_at.tzinfo is None:
            age = datetime.now() - created_at
        else:
            age = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)
        return age > timedelta(
            seconds=_stale_attempt_seconds(),
        )

    @staticmethod
    def _format_result_message(attempt: Attempt) -> str:
        """Format the final execution result message."""
        if attempt.status == AttemptStatus.COMPLETED:
            return attempt.summary or "Strategy execution completed."
        return f"Execution failed: {attempt.error or 'unknown error'}"
