from __future__ import annotations

from contextlib import contextmanager
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.engine import Engine
from .config import settings
import os


class Base(DeclarativeBase):
    pass


def ensure_dirs():
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        # path like sqlite:///./data/app.db
        path = url.split("sqlite:///")[-1]
        dir_ = os.path.dirname(os.path.abspath(path))
        if dir_ and not os.path.exists(dir_):
            os.makedirs(dir_, exist_ok=True)


ensure_dirs()
# Improve SQLite robustness under concurrent access: enable WAL, busy timeout,
# and cross-thread connections. For non-SQLite, keep defaults.
if settings.DATABASE_URL.startswith("sqlite"):
    engine: Engine = create_engine(
        settings.DATABASE_URL,
        future=True,
        connect_args={
            "check_same_thread": False,  # allow usage across threads
            "timeout": 30,               # seconds
        },
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-redef]
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")  # ms
            cursor.close()
        except Exception:
            # pragma best-effort
            try:
                cursor.close()
            except Exception:
                pass
else:
    engine: Engine = create_engine(settings.DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    from . import models  # noqa
    from .migrations import run_schema_migrations

    Base.metadata.create_all(bind=engine)
    run_schema_migrations(engine)
    create_fts_objects()
    ensure_email_message_columns()
    ensure_contact_scoring_columns()


def create_fts_objects():
    """Create FTS5 virtual table and triggers for messages if not exists."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    content_text, sender_name, talker_name, content='messages', content_rowid='id'
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, content_text, sender_name, talker_name)
                    VALUES (new.id, new.content_text, new.sender_name, new.talker_name);
                END;
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content_text, sender_name, talker_name)
                    VALUES('delete', old.id, old.content_text, old.sender_name, old.talker_name);
                END;
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content_text, sender_name, talker_name)
                    VALUES('delete', old.id, old.content_text, old.sender_name, old.talker_name);
                    INSERT INTO messages_fts(rowid, content_text, sender_name, talker_name)
                    VALUES (new.id, new.content_text, new.sender_name, new.talker_name);
                END;
                """
            )
        )


def ensure_email_message_columns():
    """Ensure email_messages table has derived column for cached AI features."""
    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(email_messages)"))}
            if "derived" not in columns:
                conn.execute(text("ALTER TABLE email_messages ADD COLUMN derived TEXT"))
    else:
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE email_messages ADD COLUMN derived JSON"))
        except Exception:
            pass


def ensure_contact_scoring_columns():
    """Best-effort schema backfill for contact scoring tables on SQLite deployments."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        event_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(contact_prediction_events)"))}
        for name, ddl in (
            ("topic_key", "ALTER TABLE contact_prediction_events ADD COLUMN topic_key VARCHAR(255)"),
            ("event_kind", "ALTER TABLE contact_prediction_events ADD COLUMN event_kind VARCHAR(32)"),
            ("is_actionable", "ALTER TABLE contact_prediction_events ADD COLUMN is_actionable BOOLEAN"),
            ("signal_strength", "ALTER TABLE contact_prediction_events ADD COLUMN signal_strength FLOAT"),
            ("source_type", "ALTER TABLE contact_prediction_events ADD COLUMN source_type VARCHAR(32)"),
            ("event_cluster_id", "ALTER TABLE contact_prediction_events ADD COLUMN event_cluster_id VARCHAR(128)"),
        ):
            if name not in event_columns:
                conn.execute(text(ddl))

        snapshot_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(contact_score_snapshots)"))}
        for name, ddl in (
            ("accuracy_score", "ALTER TABLE contact_score_snapshots ADD COLUMN accuracy_score FLOAT"),
            ("service_value_score", "ALTER TABLE contact_score_snapshots ADD COLUMN service_value_score FLOAT"),
            ("direction_accuracy_score", "ALTER TABLE contact_score_snapshots ADD COLUMN direction_accuracy_score FLOAT"),
            ("excess_return_score", "ALTER TABLE contact_score_snapshots ADD COLUMN excess_return_score FLOAT"),
            ("risk_alert_score", "ALTER TABLE contact_score_snapshots ADD COLUMN risk_alert_score FLOAT"),
            ("consistency_score", "ALTER TABLE contact_score_snapshots ADD COLUMN consistency_score FLOAT"),
        ):
            if name not in snapshot_columns:
                conn.execute(text(ddl))
