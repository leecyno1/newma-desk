from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from .storage import PostgresStore


TABLES = (
    "users",
    "portfolios",
    "user_tokens",
    "sessions",
    "portfolio_transactions",
    "portfolio_marks",
    "portfolio_nav_snapshots",
    "runs",
    "events",
    "artifacts",
    "evidence",
    "secrets",
    "jobs",
)


def migrate_sqlite_to_postgres(
    sqlite_path: str | Path,
    postgres_dsn: str,
) -> dict[str, Any]:
    source_path = Path(sqlite_path).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite数据库不存在：{source_path}")

    target = PostgresStore(postgres_dsn)
    report: dict[str, Any] = {
        "source": str(source_path),
        "target": target.location,
        "tables": {},
    }
    try:
        with sqlite3.connect(source_path) as source:
            source.row_factory = sqlite3.Row
            target._connection.execute("BEGIN")  # noqa: SLF001
            try:
                for table in TABLES:
                    columns = [
                        row["name"]
                        for row in source.execute(f"PRAGMA table_info({table})").fetchall()
                    ]
                    if not columns:
                        report["tables"][table] = {"source": 0, "inserted": 0, "target": 0}
                        continue
                    order_by = " ORDER BY created_at" if "created_at" in columns else ""
                    rows = source.execute(f"SELECT * FROM {table}{order_by}").fetchall()
                    placeholders = ", ".join("?" for _ in columns)
                    column_sql = ", ".join(columns)
                    inserted = 0
                    for row in rows:
                        cursor = target._connection.execute(  # noqa: SLF001
                            f"INSERT INTO {table}({column_sql}) VALUES ({placeholders}) "
                            "ON CONFLICT DO NOTHING",
                            tuple(row[column] for column in columns),
                        )
                        inserted += max(0, cursor.rowcount)
                    target_count = target._connection.execute(  # noqa: SLF001
                        f"SELECT COUNT(*) AS count FROM {table}",
                    ).fetchone()["count"]
                    report["tables"][table] = {
                        "source": len(rows),
                        "inserted": inserted,
                        "target": int(target_count),
                    }
                target._connection.commit()  # noqa: SLF001
            except Exception:
                target._connection.rollback()  # noqa: SLF001
                raise
    finally:
        target.close()
    report["inserted"] = sum(item["inserted"] for item in report["tables"].values())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="将Orchestra SQLite数据迁移到PostgreSQL。")
    parser.add_argument("--sqlite", required=True, help="源orchestra.db路径")
    parser.add_argument("--postgres", required=True, help="目标PostgreSQL DSN")
    args = parser.parse_args()
    print(
        json.dumps(
            migrate_sqlite_to_postgres(args.sqlite, args.postgres),
            ensure_ascii=False,
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
