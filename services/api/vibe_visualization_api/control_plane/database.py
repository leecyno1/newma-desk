import sqlite3
from pathlib import Path


DDL = """
CREATE TABLE IF NOT EXISTS module_revisions (
  module_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('draft','published','disabled')),
  manifest_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (module_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_module_status ON module_revisions(module_id, status);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  module_id TEXT,
  revision INTEGER,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(DDL)
    except BaseException:
        connection.close()
        raise
    return connection
