"""Regression test for P08 (R1) — .env resolution must be observable.

A stale / shadowed .env silently won the config for the whole process with
zero diagnostic, costing hours. _ensure_dotenv now emits one behavior-
preserving INFO line naming the resolved slot via a redacted symbolic
label (or "none") plus the resolved provider/model/base. The absolute
path, OS username, and API key are never logged (CWE-209).
"""

from __future__ import annotations

import getpass
import logging
import os
from pathlib import Path

import pytest

import src.providers.llm as llm

LOGGER = "src.providers.llm"


@pytest.fixture
def fresh(monkeypatch):
    # Drop the once-per-process latch so the resolver actually runs.
    monkeypatch.setattr(llm, "_dotenv_loaded", False)


def test_logs_redacted_label_not_path(tmp_path, fresh, monkeypatch, caplog):
    """The resolved slot is logged as a symbolic label; the absolute path
    and OS username never appear (CWE-209)."""
    env = tmp_path / ".env"
    env.write_text("FOO=bar\n", encoding="utf-8")
    monkeypatch.setattr(llm, "_ENV_CANDIDATES", [env])
    monkeypatch.setattr(llm, "_ENV_LABELS", ("<TEST_SLOT>",))
    with caplog.at_level(logging.INFO, logger=LOGGER):
        llm._ensure_dotenv()
    msg = "\n".join(r.getMessage() for r in caplog.records)
    assert "dotenv resolved from" in msg
    assert "<TEST_SLOT>" in msg  # redacted slot label is logged
    assert str(env) not in msg  # absolute path never logged
    assert str(tmp_path) not in msg
    assert getpass.getuser() not in msg  # OS username never leaks
    assert "sk-" not in msg  # key must never be logged


def test_redact_env_source_maps_real_candidates():
    """_redact_env_source maps fixed candidates to stable leak-free
    labels, None to the no-file sentinel, and any unknown path to a
    generic placeholder (never the real path)."""
    # The home slot never collides with AGENT_DIR / CWD -> exact mapping.
    assert llm._redact_env_source(llm._ENV_CANDIDATES[0]) == llm._ENV_LABELS[0]
    # Every fixed candidate resolves to a known redacted label. When CWD
    # == AGENT_DIR the earlier slot legitimately wins (matches the
    # first-match order of _ensure_dotenv) — still leak-free.
    for candidate in llm._ENV_CANDIDATES:
        result = llm._redact_env_source(candidate)
        assert result in llm._ENV_LABELS
        assert str(candidate) not in result
    assert llm._redact_env_source(None) == "none (no .env file found)"
    unknown = Path("/some/secret/home/user/.env")
    assert llm._redact_env_source(unknown) == "<.env>"
    assert str(unknown) not in llm._redact_env_source(unknown)


def test_logs_none_when_no_env_found(tmp_path, fresh, monkeypatch, caplog):
    monkeypatch.setattr(llm, "_ENV_CANDIDATES", [tmp_path / "does-not-exist.env"])
    with caplog.at_level(logging.INFO, logger=LOGGER):
        llm._ensure_dotenv()
    msg = "\n".join(r.getMessage() for r in caplog.records)
    assert "none (no .env file found)" in msg


def test_logs_redacted_base_url_without_credentials(tmp_path, fresh, monkeypatch, caplog):
    monkeypatch.setattr(llm, "_ENV_CANDIDATES", [tmp_path / "does-not-exist.env"])
    monkeypatch.setenv("OPENAI_BASE_URL", "https://sk-secret@example.com:8443/v1?api_key=sk-hidden")
    with caplog.at_level(logging.INFO, logger=LOGGER):
        llm._ensure_dotenv()
    msg = "\n".join(r.getMessage() for r in caplog.records)
    assert "base=https://example.com:8443" in msg
    assert "sk-secret" not in msg
    assert "sk-hidden" not in msg
    assert "api_key" not in msg


def test_latch_still_skips_second_call(tmp_path, fresh, monkeypatch, caplog):
    """Behavior preserved: still loads once per process (no log on re-entry)."""
    monkeypatch.setattr(llm, "_ENV_CANDIDATES", [tmp_path / "nope.env"])
    llm._ensure_dotenv()
    with caplog.at_level(logging.INFO, logger=LOGGER):
        llm._ensure_dotenv()  # latched -> early return, no new log
    assert not [r for r in caplog.records if "dotenv resolved" in r.getMessage()]


def test_later_dotenv_can_fill_empty_user_level_value(tmp_path, fresh, monkeypatch, caplog):
    """Project-local credentials should fill an empty user env placeholder."""
    user_env = tmp_path / "user.env"
    project_env = tmp_path / "project.env"
    user_env.write_text(
        "LANGCHAIN_PROVIDER=openai\nTUSHARE_TOKEN=\nOPENAI_BASE_URL=https://user.example/v1\n",
        encoding="utf-8",
    )
    project_env.write_text(
        "TUSHARE_TOKEN=project-token\nOPENAI_BASE_URL=https://project.example/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm, "_ENV_CANDIDATES", [user_env, project_env])
    monkeypatch.setattr(llm, "_ENV_LABELS", ("<USER_ENV>", "<PROJECT_ENV>"))
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        llm._ensure_dotenv()

    assert "dotenv resolved from <USER_ENV> + <PROJECT_ENV>" in "\n".join(
        r.getMessage() for r in caplog.records
    )
    assert os.environ["LANGCHAIN_PROVIDER"] == "openai"
    assert os.environ["OPENAI_BASE_URL"] == "https://user.example/v1"
    assert os.environ["TUSHARE_TOKEN"] == "project-token"


def test_loading_dotenv_invalidates_preexisting_config_cache(tmp_path, fresh, monkeypatch):
    """Values loaded after an early config read must be visible immediately."""
    from src.config.accessor import get_env_config, reset_env_config

    env = tmp_path / ".env"
    env.write_text(
        "LANGCHAIN_PROVIDER=openai\n"
        "LANGCHAIN_MODEL_NAME=gpt-test\n"
        "OPENAI_BASE_URL=https://example.test/v1\n"
        "TUSHARE_TOKEN=test-token\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm, "_ENV_CANDIDATES", [env])
    monkeypatch.setattr(llm, "_ENV_LABELS", ("<TEST_ENV>",))
    for name in (
        "LANGCHAIN_PROVIDER",
        "LANGCHAIN_MODEL_NAME",
        "OPENAI_BASE_URL",
        "TUSHARE_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    reset_env_config()
    stale = get_env_config()
    assert stale.llm.langchain_model_name == ""
    assert stale.data.tushare_token == ""

    llm._ensure_dotenv()

    refreshed = get_env_config()
    assert refreshed is not stale
    assert refreshed.llm.langchain_provider == "openai"
    assert refreshed.llm.langchain_model_name == "gpt-test"
    assert refreshed.data.tushare_token == "test-token"
