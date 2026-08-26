"""Safe, template-only backtest jobs for the Desk-integrated Runs interface.

This module deliberately does not accept Python, expressions, file paths, or
loader/engine selection.  A request selects one fixed signal template and a
small validated parameter object; the generated files then run through the
same ``backtest.runner`` entrypoint as the existing backtest tool.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.runner import Runner


logger = logging.getLogger(__name__)

QuickTemplateId = Literal["buy_and_hold", "sma_crossover"]
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled"})
_TEMPLATE_NAMES = {
    "buy_and_hold": "Buy and Hold",
    "sma_crossover": "SMA Crossover",
}


class QuickRunCapacityError(RuntimeError):
    """Raised when the process already has its safe compute slot in use."""


class QuickRunNotFoundError(LookupError):
    """Raised when a requested run directory does not exist."""


class QuickRunConflictError(RuntimeError):
    """Raised when a persisted run cannot be controlled by this process."""


class QuickRunRequest(BaseModel):
    """Small public request surface for a fixed quick-backtest template."""

    model_config = ConfigDict(extra="forbid")

    template_id: QuickTemplateId
    symbol: str = Field(min_length=1, max_length=32)
    start_date: date
    end_date: date
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _SYMBOL_RE.fullmatch(normalized):
            raise ValueError("symbol contains unsupported characters")
        return normalized

    @field_validator("params")
    @classmethod
    def validate_param_shape(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 4:
            raise ValueError("params contains too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("params keys must be non-empty strings")
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError("params values must be JSON numbers")
        return value

    @model_validator(mode="after")
    def validate_date_window(self) -> "QuickRunRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if (self.end_date - self.start_date).days > 3650:
            raise ValueError("date window cannot exceed 10 years")
        return self


class _BuyAndHoldParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    initial_cash: float = Field(default=1_000_000, ge=1_000, le=1_000_000_000)
    commission: float = Field(default=0.001, ge=0, le=0.05)


class _SmaCrossoverParams(_BuyAndHoldParams):
    fast_window: int = Field(default=5, strict=True, ge=2, le=200)
    slow_window: int = Field(default=20, strict=True, ge=3, le=500)

    @model_validator(mode="after")
    def validate_windows(self) -> "_SmaCrossoverParams":
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        return self


class QuickRunStatus(BaseModel):
    """Compact job state shared by create, status, and cancel routes."""

    run_id: str
    status: str
    template_id: QuickTemplateId | None = None
    symbol: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    reason: str | None = None


@dataclass
class _QuickRunJob:
    run_id: str
    run_dir: Path
    request: QuickRunRequest
    task: asyncio.Task[None] | None = None
    status: str = "queued"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_state(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _parse_template_params(request: QuickRunRequest) -> _BuyAndHoldParams:
    if request.template_id == "buy_and_hold":
        return _BuyAndHoldParams.model_validate(request.params)
    return _SmaCrossoverParams.model_validate(request.params)


def _signal_source(
    template_id: QuickTemplateId,
    params: _BuyAndHoldParams,
) -> str:
    if template_id == "buy_and_hold":
        return '''"""Fixed Newma-Desk buy-and-hold template."""

class SignalEngine:
    def generate(self, data_map):
        return {
            symbol: frame["close"].notna().astype(float)
            for symbol, frame in data_map.items()
        }
'''

    sma = _SmaCrossoverParams.model_validate(params.model_dump())
    return f'''"""Fixed Newma-Desk SMA crossover template."""

class SignalEngine:
    FAST_WINDOW = {sma.fast_window}
    SLOW_WINDOW = {sma.slow_window}

    def generate(self, data_map):
        signals = {{}}
        for symbol, frame in data_map.items():
            close = frame["close"]
            fast = close.rolling(self.FAST_WINDOW, min_periods=self.FAST_WINDOW).mean()
            slow = close.rolling(self.SLOW_WINDOW, min_periods=self.SLOW_WINDOW).mean()
            signals[symbol] = fast.gt(slow).fillna(False).astype(float)
        return signals
'''


def _prepare_run_directory(
    runs_dir: Path,
    request: QuickRunRequest,
) -> tuple[str, Path]:
    params = _parse_template_params(request)
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
    run_dir = runs_dir / run_id
    (run_dir / "code").mkdir(parents=True, exist_ok=False)

    source = _signal_source(request.template_id, params)
    normalized_params = params.model_dump(mode="json")
    config = {
        "source": "auto",
        "codes": [request.symbol],
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "interval": "1D",
        "initial_cash": normalized_params["initial_cash"],
        "commission": normalized_params["commission"],
        "engine": "daily",
        "quick_template_id": request.template_id,
        "execution_mode": "paper",
        "execution_policy": "paper-only",
    }
    created_at = _now_iso()
    _write_json_atomic(run_dir / "config.json", config)
    _write_json_atomic(
        run_dir / "req.json",
        {
            "prompt": (
                f"Quick backtest {request.template_id}: {request.symbol} "
                f"{request.start_date.isoformat()} to {request.end_date.isoformat()}"
            ),
            "request": request.model_dump(mode="json"),
            "normalized_params": normalized_params,
        },
    )
    _write_json_atomic(
        run_dir / "design_spec.json",
        {
            "schema_version": "newma-desk.strategy-experiment.v1",
            "strategy_id": f"vibe-trading.{request.template_id.replace('_', '-')}",
            "name": _TEMPLATE_NAMES[request.template_id],
            "template_id": request.template_id,
            "template_version": "1.0.0",
            "symbol": request.symbol,
            "parameters": normalized_params,
            "generator": "newma-desk-fixed-template-v1",
            "execution_mode": "paper",
            "execution_policy": "paper-only",
            "accepts_arbitrary_code": False,
            "signal_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        },
    )
    (run_dir / "code" / "signal_engine.py").write_text(source, encoding="utf-8")
    _write_json_atomic(
        run_dir / "state.json",
        {
            "run_id": run_id,
            "status": "queued",
            "template_id": request.template_id,
            "symbol": request.symbol,
            "created_at": created_at,
        },
    )
    return run_id, run_dir


class QuickRunManager:
    """Own one bounded quick-backtest slot and its cancellable child process."""

    def __init__(
        self,
        runs_dir_provider: Callable[[], Path],
        *,
        runner_factory: Callable[[], Runner] | None = None,
        max_active: int = 1,
    ) -> None:
        self._runs_dir_provider = runs_dir_provider
        self._runner_factory = runner_factory or (lambda: Runner(timeout=300))
        self._max_active = max_active
        self._jobs: dict[str, _QuickRunJob] = {}

    def create(self, request: QuickRunRequest) -> QuickRunStatus:
        active = sum(
            job.status not in _TERMINAL_STATUSES
            for job in self._jobs.values()
        )
        if active >= self._max_active:
            raise QuickRunCapacityError("a quick backtest is already running")

        runs_dir = self._runs_dir_provider()
        runs_dir.mkdir(parents=True, exist_ok=True)
        run_id, run_dir = _prepare_run_directory(runs_dir, request)
        job = _QuickRunJob(run_id=run_id, run_dir=run_dir, request=request)
        self._jobs[run_id] = job
        job.task = asyncio.get_running_loop().create_task(self._run(job))
        job.task.add_done_callback(
            lambda _task, completed_run_id=run_id: self._jobs.pop(
                completed_run_id,
                None,
            )
        )
        return self.status(run_id)

    def status(self, run_id: str) -> QuickRunStatus:
        job = self._jobs.get(run_id)
        run_dir = job.run_dir if job is not None else self._runs_dir_provider() / run_id
        state = _load_state(run_dir / "state.json")
        if state is None:
            raise QuickRunNotFoundError(run_id)
        state.setdefault("run_id", run_id)
        return QuickRunStatus.model_validate(state)

    async def cancel(self, run_id: str) -> QuickRunStatus:
        job = self._jobs.get(run_id)
        if job is None:
            persisted = self.status(run_id)
            if persisted.status in _TERMINAL_STATUSES:
                return persisted
            raise QuickRunConflictError(
                "run belongs to another process and cannot be cancelled safely"
            )
        if job.status in _TERMINAL_STATUSES:
            return self.status(run_id)

        job.status = "cancelling"
        self._update_state(job, status="cancelling")
        if job.task is not None:
            job.task.cancel()
            try:
                await job.task
            except asyncio.CancelledError:
                pass
        if job.status != "cancelled":
            job.status = "cancelled"
            self._update_state(job, status="cancelled", finished_at=_now_iso())
        return self.status(run_id)

    async def shutdown(self) -> None:
        active = [
            job for job in self._jobs.values()
            if job.task is not None and not job.task.done()
        ]
        for job in active:
            job.task.cancel()
        if active:
            await asyncio.gather(
                *(job.task for job in active if job.task is not None),
                return_exceptions=True,
            )

    async def _run(self, job: _QuickRunJob) -> None:
        job.status = "running"
        self._update_state(job, status="running", started_at=_now_iso())
        agent_root = Path(__file__).resolve().parents[2]
        entry_script = agent_root / "backtest" / "runner.py"
        try:
            result = await self._runner_factory().execute_async(
                entry_script,
                job.run_dir,
                cwd=agent_root,
                cli_args=[str(job.run_dir)],
            )
        except asyncio.CancelledError:
            job.status = "cancelled"
            self._update_state(job, status="cancelled", finished_at=_now_iso())
            raise
        except Exception:
            logger.exception("quick backtest failed unexpectedly (run_id=%s)", job.run_id)
            job.status = "failed"
            self._update_state(
                job,
                status="failed",
                finished_at=_now_iso(),
                reason="quick backtest failed; see server logs",
            )
            return

        if result.success and not result.timed_out:
            job.status = "success"
            self._update_state(
                job,
                status="success",
                finished_at=_now_iso(),
                exit_code=result.exit_code,
            )
            return

        fallback_reason = (
            "quick backtest timed out"
            if result.timed_out
            else f"backtest process exited with code {result.exit_code}"
        )
        job.status = "failed"
        self._update_state(
            job,
            status="failed",
            finished_at=_now_iso(),
            exit_code=result.exit_code,
            reason=result.reason or fallback_reason,
        )

    @staticmethod
    def _update_state(job: _QuickRunJob, **updates: Any) -> None:
        current = _load_state(job.run_dir / "state.json") or {
            "run_id": job.run_id,
            "template_id": job.request.template_id,
            "symbol": job.request.symbol,
        }
        current.update(updates)
        _write_json_atomic(job.run_dir / "state.json", current)
