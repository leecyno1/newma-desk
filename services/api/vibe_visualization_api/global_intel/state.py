"""Read-only inspection and explicit creation of a new, empty domain database."""
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


FORECAST_TABLES = {
    "global_topic_forecasts": {"id", "topic_id", "created_at", "factors_json", "result_json"},
    "global_topic_scoped_forecasts": {"id", "user_id", "workspace_id", "topic_id", "created_at", "factors_json", "result_json"},
}
DOMAIN_TABLES = {*FORECAST_TABLES, "global_topic_observations", "global_topic_events", "sqlite_sequence"}


def initialize_state(database: Path) -> None:
    """Publish a complete empty schema without replacing any existing target."""
    from ..global_topics.store import SCHEMA

    if not database.is_absolute():
        raise ValueError("数据库必须使用绝对路径")
    if os.path.lexists(database):
        raise FileExistsError("目标已存在；不会覆盖、迁移或认领旧记录")
    # Same-directory staging keeps publication atomic; mkstemp uses owner-only permissions.
    fd, name = tempfile.mkstemp(prefix=".global-init-", suffix=".sqlite3", dir=database.parent)
    staged = Path(name)
    try:
        os.close(fd)
        with closing(sqlite3.connect(staged)) as connection:
            connection.executescript(SCHEMA)
        # Unlike replace/rename, link fails if another initializer created the target.
        os.link(staged, database)
    finally:
        staged.unlink()


def inspect_state(database: Path) -> dict:
    if not database.is_file():
        return {"status": "missing", "dedicated": None, "counts": {}}
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts, missing = {}, []
            for table, required in FORECAST_TABLES.items():
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if not required <= columns:
                    missing.append(table)
                else:
                    counts[table] = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            return {"status": "incomplete" if missing else "ready", "dedicated": not bool(tables - DOMAIN_TABLES),
                    "counts": counts, "missingTables": missing}
    except sqlite3.Error:
        return {"status": "unreadable", "dedicated": None, "counts": {}}
