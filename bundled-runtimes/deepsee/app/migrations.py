from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class SchemaMigration:
    version: str
    description: str
    apply: Callable[[Engine], None]


def _baseline(_engine: Engine) -> None:
    return None


def _contact_list_indexes(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_contacts_rating ON contacts (rating DESC)"))


MIGRATIONS: tuple[SchemaMigration, ...] = (
    SchemaMigration(
        version="20260623_0001_baseline",
        description="Record Deepsee migration baseline after legacy create_all/backfill schema",
        apply=_baseline,
    ),
    SchemaMigration(
        version="20260624_0002_contact_list_indexes",
        description="Add contact list ordering index for settings/contact pages",
        apply=_contact_list_indexes,
    ),
)


def ensure_schema_migrations_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(64) PRIMARY KEY,
                    description TEXT,
                    applied_at DATETIME NOT NULL
                )
                """
            )
        )


def applied_versions(engine: Engine) -> set[str]:
    ensure_schema_migrations_table(engine)
    inspector = inspect(engine)
    if "schema_migrations" not in inspector.get_table_names():
        return set()
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
    return {str(row[0]) for row in rows}


def pending_migrations(engine: Engine) -> list[SchemaMigration]:
    applied = applied_versions(engine)
    return [migration for migration in MIGRATIONS if migration.version not in applied]


def run_schema_migrations(engine: Engine) -> list[str]:
    ensure_schema_migrations_table(engine)
    applied = applied_versions(engine)
    executed: list[str] = []
    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        migration.apply(engine)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO schema_migrations(version, description, applied_at)
                    VALUES (:version, :description, :applied_at)
                    """
                ),
                {
                    "version": migration.version,
                    "description": migration.description,
                    "applied_at": datetime.utcnow(),
                },
            )
        executed.append(migration.version)
    return executed
