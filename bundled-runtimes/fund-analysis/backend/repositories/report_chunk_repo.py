"""
调研报告切片 Repository
"""
import json
import logging
import os
from uuid import UUID
from datetime import date, datetime
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_database_url
except ModuleNotFoundError:
    from database import get_database_url

logger = logging.getLogger(__name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        pg_url = get_database_url()
        _engine = create_engine(pg_url, pool_pre_ping=True, pool_size=20, max_overflow=30, pool_recycle=3600)
    return _engine


def _json(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _row_to_dict(row) -> Dict[str, Any]:
    data = dict(row._mapping)
    for key, value in list(data.items()):
        if isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
        elif isinstance(value, UUID):
            data[key] = str(value)
    return data


class ReportChunkRepo:
    """调研报告切片访问层。"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def create_test_report(self, title: str = "test report") -> str:
        """为 smoke test 创建最小报告记录。"""
        from sqlalchemy import text
        from database import init_database

        init_database()
        sql = """
            INSERT INTO research_reports (title, report_date, source, content, fund_ids, tags)
            VALUES (:title, CURRENT_DATE, 'smoke-test', '', ARRAY[]::TEXT[], ARRAY[]::TEXT[])
            RETURNING id
        """
        with self.engine.connect() as conn:
            report_id = str(conn.execute(text(sql), {"title": title}).scalar())
            conn.commit()
        return report_id

    def replace_chunks(self, report_id: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """替换某篇报告的全部切片。"""
        from sqlalchemy import text
        from database import init_database

        init_database()
        delete_sql = "DELETE FROM research_report_chunks WHERE report_id = CAST(:report_id AS UUID)"
        insert_sql = """
            INSERT INTO research_report_chunks (
                report_id, chunk_index, content, token_count, embedding_id, entities, metadata
            ) VALUES (
                CAST(:report_id AS UUID), :chunk_index, :content, :token_count, :embedding_id,
                CAST(:entities AS JSONB), CAST(:metadata AS JSONB)
            )
            RETURNING *
        """
        inserted: List[Dict[str, Any]] = []
        with self.engine.connect() as conn:
            conn.execute(text(delete_sql), {"report_id": report_id})
            for index, chunk in enumerate(chunks):
                row = conn.execute(text(insert_sql), {
                    "report_id": report_id,
                    "chunk_index": chunk.get("chunk_index", index),
                    "content": chunk.get("content", ""),
                    "token_count": chunk.get("token_count"),
                    "embedding_id": chunk.get("embedding_id"),
                    "entities": _json(chunk.get("entities")),
                    "metadata": _json(chunk.get("metadata")),
                }).fetchone()
                inserted.append(_row_to_dict(row))
            conn.commit()
        return inserted

    def list_by_report(self, report_id: str) -> List[Dict[str, Any]]:
        """按报告 ID 获取切片。"""
        from sqlalchemy import text

        sql = """
            SELECT * FROM research_report_chunks
            WHERE report_id = CAST(:report_id AS UUID)
            ORDER BY chunk_index ASC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"report_id": report_id}).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_by_embedding_id(self, embedding_id: str) -> Optional[Dict[str, Any]]:
        """按 Qdrant point id 查找切片元数据。"""
        from sqlalchemy import text

        sql = """
            SELECT * FROM research_report_chunks
            WHERE embedding_id = :embedding_id
            LIMIT 1
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {"embedding_id": embedding_id}).fetchone()
        return _row_to_dict(row) if row else None
