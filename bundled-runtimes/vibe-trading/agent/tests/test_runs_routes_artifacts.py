"""Run artifact readers should degrade without hiding corrupt local data."""

from __future__ import annotations

import logging
from pathlib import Path

from src.api.runs_routes import _load_csv_to_dict, _load_json_file


def test_json_artifact_reader_logs_invalid_json(
    tmp_path: Path,
    caplog,
) -> None:
    artifact = tmp_path / "state.json"
    artifact.write_text("{broken", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="src.api.runs_routes"):
        result = _load_json_file(artifact)

    assert result is None
    assert "Unable to read JSON artifact" in caplog.text
    assert str(artifact) in caplog.text


def test_json_artifact_reader_rejects_non_object_payload(
    tmp_path: Path,
    caplog,
) -> None:
    artifact = tmp_path / "state.json"
    artifact.write_text("[]", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="src.api.runs_routes"):
        result = _load_json_file(artifact)

    assert result is None
    assert "Ignoring non-object JSON artifact" in caplog.text


def test_csv_artifact_reader_logs_io_failures(
    tmp_path: Path,
    caplog,
) -> None:
    artifact = tmp_path / "metrics.csv"
    artifact.mkdir()

    with caplog.at_level(logging.WARNING, logger="src.api.runs_routes"):
        result = _load_csv_to_dict(artifact)

    assert result == []
    assert "Unable to read CSV artifact" in caplog.text
