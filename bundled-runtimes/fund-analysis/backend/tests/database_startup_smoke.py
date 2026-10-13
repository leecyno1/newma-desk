"""Check-only startup must never call initialization or copy unrelated secrets."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import database
from runtime_config import load_shared_model_environment

connection = MagicMock()
connection.execute.return_value.scalar.return_value = "existing_table"
engine = MagicMock()
engine.connect.return_value.__enter__.return_value = connection
with patch.object(database, "get_engine", return_value=engine), patch.object(database, "init_database") as initialize:
    with patch.object(database, "check_database_health", return_value={"status": "ok"}):
        database.prepare_database("check")
        initialize.assert_not_called()
        assert len(connection.execute.call_args_list) == 5
        assert all(str(call.args[0]).startswith("SELECT") for call in connection.execute.call_args_list)
        connection.execute.return_value.scalar.return_value = None
        try:
            database.prepare_database("check")
            raise AssertionError("missing tables should block startup")
        except RuntimeError:
            pass
        initialize.assert_not_called()
    with patch.object(database, "check_database_health", return_value={"status": "database_unavailable"}):
        try:
            database.prepare_database("check")
            raise AssertionError("database unavailable should block startup")
        except RuntimeError:
            pass
        initialize.assert_not_called()
    try:
        database.prepare_database("typo")
        raise AssertionError("invalid mode should block startup")
    except ValueError:
        pass
    initialize.assert_not_called()
    database.prepare_database("initialize")
    initialize.assert_called_once()

with patch.object(database, "get_engine", side_effect=AssertionError("checked database must not run lazy initialization")):
    assert database.init_database() is True

with patch.dict(os.environ, {"NEWMA_DESK_FUND_DATABASE_ENV_FILE": "/isolated/test.env"}, clear=True):
    with patch("dotenv.dotenv_values", return_value={"DATABASE_URL": "postgresql://literal/${VALUE}", "LLM_API_KEY": "not-to-copy"}) as load:
        database.load_shared_database_environment()
        load.assert_called_once_with("/isolated/test.env", interpolate=False)
        assert os.environ["DATABASE_URL"] == "postgresql://literal/${VALUE}"
        assert "LLM_API_KEY" not in os.environ
    with patch("dotenv.dotenv_values") as load:
        database.load_shared_database_environment()
        load.assert_not_called()
with patch.dict(os.environ, {"NEWMA_DESK_FUND_MODEL_ENV_FILE": "/isolated/model.env", "LLM_MODEL": "explicit"}, clear=True):
    with patch("pathlib.Path.is_file", return_value=True), patch("dotenv.dotenv_values", return_value={"LLM_PROVIDER": "openai-compatible", "LLM_MODEL": "ignored", "LLM_API_KEY": "literal-${VALUE}", "DATABASE_URL": "not-to-copy", "PYTHONPATH": "not-to-copy"}):
        load_shared_model_environment()
        assert os.environ["LLM_MODEL"] == "explicit"
        assert os.environ["LLM_API_KEY"] == "literal-${VALUE}"
        assert os.environ["LLM_PROVIDER"] == "openai-compatible"
        assert "DATABASE_URL" not in os.environ and "PYTHONPATH" not in os.environ
print("PASS check-only startup, lazy initialization suppression, schema failure and separately allowlisted database/model configuration")
