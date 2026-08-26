"""Regression tests for ``--swarm-run`` argument handling."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_swarm_run_rejects_extra_tokens(capsys: pytest.CaptureFixture[str]) -> None:
    """Extra vars tokens must fail explicitly instead of being dropped."""
    from cli._legacy import EXIT_USAGE_ERROR, main

    with patch("cli._legacy.cmd_swarm_run_live") as run:
        rc = main(["--swarm-run", "investment_committee", '{"k":"v"}', "dropped"])

    out = capsys.readouterr().out
    assert rc == EXIT_USAGE_ERROR
    assert "unexpected extra token(s)" in out
    assert "dropped" in out
    assert """--swarm-run PRESET '{"k":"v"}'""" in out
    run.assert_not_called()


def test_swarm_run_invalid_json_reports_offending_string(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid vars JSON should include the bad input and parser detail."""
    from cli._legacy import EXIT_USAGE_ERROR, main

    bad_vars = "{k:v}"
    with patch("cli._legacy.cmd_swarm_run_live") as run:
        rc = main(["--swarm-run", "investment_committee", bad_vars])

    out = capsys.readouterr().out
    assert rc == EXIT_USAGE_ERROR
    assert bad_vars in out
    assert "Expecting property name enclosed in double quotes" in out
    assert """--swarm-run PRESET '{"k":"v"}'""" in out
    assert "shell quoting" in out
    run.assert_not_called()


def test_swarm_run_one_arg_dispatches_without_vars() -> None:
    """A preset without vars remains valid for backwards compatibility."""
    from cli._legacy import EXIT_SUCCESS, main

    with patch("cli._legacy.cmd_swarm_run_live", return_value=0) as run:
        rc = main(["--swarm-run", "investment_committee"])

    assert rc == EXIT_SUCCESS
    run.assert_called_once_with("investment_committee", None)


def test_swarm_run_two_args_dispatches_with_vars() -> None:
    """A preset plus one JSON vars token dispatches unchanged."""
    from cli._legacy import EXIT_SUCCESS, main

    vars_json = '{"ticker":"AAPL"}'
    with patch("cli._legacy.cmd_swarm_run_live", return_value=0) as run:
        rc = main(["--swarm-run", "investment_committee", vars_json])

    assert rc == EXIT_SUCCESS
    run.assert_called_once_with("investment_committee", vars_json)
