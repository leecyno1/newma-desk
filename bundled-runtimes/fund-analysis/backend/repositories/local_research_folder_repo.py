"""Persistence adapters for local research folder indexes and review proposals."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, Dict, List, Optional
from uuid import UUID


def _serialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _document(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    serialized = _serialize(dict(doc))
    serialized["id"] = str(serialized.pop("_id"))
    return serialized


class LocalResearchFolderRepo:
    """Legacy MongoDB adapter retained for old report consumers."""

    def __init__(self, db: Any):
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.local_research_folders.create_index("path", unique=True)
        self.db.local_research_documents.create_index(
            [("folder_id", 1), ("relative_path", 1)], unique=True
        )
        self.db.local_research_documents.create_index("content_hash")
        self.db.research_reports.create_index("fund_ids")

    def create_folder(self, folder: Dict[str, Any]) -> Dict[str, Any]:
        result = self.db.local_research_folders.insert_one(dict(folder))
        return {**_serialize(folder), "id": str(result.inserted_id)}

    def list_folders(self) -> List[Dict[str, Any]]:
        return [_document(item) for item in self.db.local_research_folders.find({}).sort("created_at", -1)]

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        from bson import ObjectId

        return _document(self.db.local_research_folders.find_one({"_id": ObjectId(folder_id)}))

    def update_folder(self, folder_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from bson import ObjectId
        from pymongo import ReturnDocument

        doc = self.db.local_research_folders.find_one_and_update(
            {"_id": ObjectId(folder_id)},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return _document(doc)

    def get_document(self, folder_id: str, relative_path: str) -> Optional[Dict[str, Any]]:
        return _document(self.db.local_research_documents.find_one({
            "folder_id": folder_id,
            "relative_path": relative_path,
        }))

    def find_document_by_hash(
        self,
        content_hash: str,
        exclude_folder_id: Optional[str] = None,
        exclude_relative_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        query: Dict[str, Any] = {"content_hash": content_hash, "report_id": {"$nin": [None, ""]}}
        if exclude_folder_id and exclude_relative_path:
            query["$nor"] = [{"folder_id": exclude_folder_id, "relative_path": exclude_relative_path}]
        return _document(self.db.local_research_documents.find_one(query))

    def upsert_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        from pymongo import ReturnDocument

        doc = self.db.local_research_documents.find_one_and_update(
            {"folder_id": document["folder_id"], "relative_path": document["relative_path"]},
            {"$set": dict(document)},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return _document(doc)

    def create_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        result = self.db.research_reports.insert_one(dict(report))
        return {**_serialize(report), "id": str(result.inserted_id)}

    def update_report(self, report_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from bson import ObjectId
        from pymongo import ReturnDocument

        doc = self.db.research_reports.find_one_and_update(
            {"_id": ObjectId(report_id)},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return _document(doc)

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        from bson import ObjectId

        return _document(self.db.research_reports.find_one({"_id": ObjectId(report_id)}))

    def list_reports_for_fund(self, wind_code: str) -> List[Dict[str, Any]]:
        cursor = self.db.research_reports.find({"fund_ids": wind_code}).sort([
            ("report_date", -1),
            ("updated_at", -1),
        ])
        return [_document(item) for item in cursor]

    def list_reports_for_manager_exact(self, manager_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.db.research_reports.find({
            "$or": [
                {"manager_id": manager_id},
                {"manager_links.manager_id": manager_id},
            ]
        }).sort([
            ("report_date", -1),
            ("updated_at", -1),
        ]).limit(max(1, min(int(limit), 200)))
        return [_document(item) for item in cursor]

    def list_confirmed_manager_ids(self, folder_id: Optional[str] = None) -> List[str]:
        query: Dict[str, Any] = {
            "$or": [
                {"manager_id": {"$nin": [None, ""]}},
                {"manager_links.manager_id": {"$nin": [None, ""]}},
            ]
        }
        if folder_id:
            query["local_folder_id"] = folder_id
        manager_ids = {
            str(item.get("manager_id") or "").strip()
            for item in self.db.research_reports.find(query, {"manager_id": 1, "manager_links": 1})
            if str(item.get("manager_id") or "").strip()
        }
        manager_ids.update(
            str(link.get("manager_id") or "").strip()
            for item in self.db.research_reports.find(query, {"manager_links": 1})
            for link in item.get("manager_links") or []
            if str(link.get("manager_id") or "").strip()
        )
        return sorted(manager_ids)

    def list_manager_review_reports(self, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"review_proposals": {"$elemMatch": {"kind": "manager"}}}
        if folder_id:
            query["local_folder_id"] = folder_id
        return [
            _document(item)
            for item in self.db.research_reports.find(query).sort("updated_at", -1)
        ]

    def list_report_manager_links(self, report_id: str) -> List[Dict[str, Any]]:
        report = self.get_report(report_id) or {}
        links = list(report.get("manager_links") or [])
        manager_id = str(report.get("manager_id") or "").strip()
        if manager_id and not any(str(item.get("manager_id") or "") == manager_id for item in links):
            links.append({
                "manager_id": manager_id,
                "manager_name": report.get("manager_name") or manager_id,
                "source": "legacy_research_reports.manager_id",
            })
        return links

    def set_report_manager_link(
        self,
        report_id: str,
        manager_id: str,
        manager_name: str,
        source: str = "research_memo_review",
        confirmed_at: Optional[str] = None,
    ) -> None:
        from bson import ObjectId

        link = {
            "manager_id": manager_id,
            "manager_name": manager_name,
            "source": source,
            "confirmed_at": confirmed_at,
        }
        self.db.research_reports.update_one(
            {"_id": ObjectId(report_id)},
            {"$pull": {"manager_links": {"manager_id": manager_id}}},
        )
        self.db.research_reports.update_one(
            {"_id": ObjectId(report_id)},
            {"$push": {"manager_links": link}},
        )

    def remove_report_manager_link(self, report_id: str, manager_id: str) -> None:
        from bson import ObjectId

        self.db.research_reports.update_one(
            {"_id": ObjectId(report_id)},
            {"$pull": {"manager_links": {"manager_id": manager_id}}},
        )

    def list_pending_reviews(self, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"review_proposals": {"$elemMatch": {"review_status": "pending"}}}
        if folder_id:
            query["local_folder_id"] = folder_id
        pending: List[Dict[str, Any]] = []
        for report in self.db.research_reports.find(query).sort("updated_at", -1):
            for proposal in report.get("review_proposals", []):
                if proposal.get("review_status") != "pending":
                    continue
                if proposal.get("kind") == "fund" and proposal.get("extraction_source") == "tushare.fund_manager":
                    continue
                pending.append({
                    "report_id": str(report["_id"]),
                    "report_title": report.get("title") or "无标题纪要",
                    "report_date": report.get("report_date"),
                    "report_date_source": report.get("report_date_source"),
                    "report_date_precision": report.get("report_date_precision"),
                    **_serialize(proposal),
                })
        return pending


class PostgresLocalResearchFolderRepo:
    """PostgreSQL-backed local memo index used by the main application."""

    REPORT_FIELDS = {
        "manager_id", "manager_name", "fund_ids", "title", "report_date",
        "report_date_source", "report_date_precision", "source",
        "content", "summary", "key_points", "tags", "viewpoint_topics", "research_domains",
        "classifications", "style_labels",
        "review_proposals", "review_status", "local_folder_id", "local_relative_path",
        "local_source_path", "source_hash", "extraction_status", "extraction_provider",
        "extraction_model", "llm_extraction_status", "llm_extraction_error", "created_at",
        "updated_at",
    }
    JSON_FIELDS = {"key_points", "review_proposals", "last_scan_counts"}

    def __init__(self, engine: Any = None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            try:
                from backend.database import get_engine
            except ModuleNotFoundError:
                from database import get_engine
            self._engine = get_engine()
        return self._engine

    @staticmethod
    def _row(row: Any) -> Optional[Dict[str, Any]]:
        return _serialize(dict(row._mapping)) if row else None

    def _with_manager_links(self, report: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not report:
            return report
        links = self.list_report_manager_links(str(report.get("id") or ""))
        return {
            **report,
            "manager_links": links,
            "manager_ids": [str(item.get("manager_id") or "") for item in links],
            "manager_names": [str(item.get("manager_name") or "") for item in links],
        }

    def _rows_with_manager_links(self, rows: List[Any]) -> List[Dict[str, Any]]:
        reports = [self._row(row) or {} for row in rows]
        if not reports:
            return reports
        from sqlalchemy import bindparam, text

        report_ids = [str(report["id"]) for report in reports]
        sql = text("""
            SELECT link.report_id, link.manager_id, link.manager_name, link.source, link.confirmed_at,
                   manager.company AS manager_company,
                   manager.management_years AS manager_management_years
            FROM research_report_managers link
            LEFT JOIN managers manager ON manager.wind_code = link.manager_id
            WHERE link.report_id IN :report_ids
            ORDER BY link.confirmed_at, link.manager_name
        """).bindparams(bindparam("report_ids", expanding=True))
        with self.engine.connect() as conn:
            links = conn.execute(sql, {"report_ids": report_ids}).fetchall()
        links_by_report: Dict[str, List[Dict[str, Any]]] = {}
        for row in links:
            link = self._row(row) or {}
            links_by_report.setdefault(str(link.pop("report_id")), []).append(link)
        for report in reports:
            manager_links = links_by_report.get(str(report.get("id")), [])
            report["manager_links"] = manager_links
            report["manager_ids"] = [str(item.get("manager_id") or "") for item in manager_links]
            report["manager_names"] = [str(item.get("manager_name") or "") for item in manager_links]
        return reports

    @classmethod
    def _params(cls, fields: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: json.dumps(value, ensure_ascii=False, default=str) if key in cls.JSON_FIELDS else value
            for key, value in fields.items()
        }

    @classmethod
    def _assignments(cls, fields: Dict[str, Any]) -> str:
        return ", ".join(
            f"{key} = CAST(:{key} AS JSONB)" if key in cls.JSON_FIELDS else f"{key} = :{key}"
            for key in fields
        )

    def ensure_indexes(self) -> None:
        try:
            from backend.database import init_database
        except ModuleNotFoundError:
            from database import init_database
        init_database()

    def create_folder(self, folder: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text

        fields = {key: folder.get(key) for key in (
            "path", "name", "status", "last_scan_at", "last_scan_counts", "created_at", "updated_at"
        )}
        sql = f"""
            INSERT INTO local_research_folders ({', '.join(fields)})
            VALUES ({', '.join(f'CAST(:{key} AS JSONB)' if key in self.JSON_FIELDS else f':{key}' for key in fields)})
            RETURNING *
        """
        with self.engine.begin() as conn:
            row = conn.execute(text(sql), self._params(fields)).fetchone()
        return self._with_manager_links(self._row(row)) or {}

    def list_folders(self) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM local_research_folders ORDER BY created_at DESC")).fetchall()
        return [self._row(row) or {} for row in rows]

    def list_reports_for_manager_exact(self, manager_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT report.*
                FROM research_reports report
                WHERE EXISTS (
                       SELECT 1
                       FROM research_report_managers link
                       WHERE link.report_id = report.id
                         AND link.manager_id = :manager_id
                   )
                ORDER BY report.report_date DESC NULLS LAST, report.updated_at DESC
                LIMIT :limit
            """), {
                "manager_id": str(manager_id or "").strip(),
                "limit": max(1, min(int(limit), 200)),
            }).fetchall()
        return self._rows_with_manager_links(rows)

    def list_confirmed_manager_ids(self, folder_id: Optional[str] = None) -> List[str]:
        from sqlalchemy import text

        where = ["1=1"]
        params: Dict[str, Any] = {}
        if folder_id:
            where.append("report.local_folder_id = CAST(:folder_id AS UUID)")
            params["folder_id"] = folder_id
        with self.engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT DISTINCT link.manager_id
                FROM research_report_managers link
                JOIN research_reports report ON report.id = link.report_id
                WHERE {' AND '.join(where)}
                ORDER BY link.manager_id
            """), params).fetchall()
        return [str(row.manager_id) for row in rows if str(row.manager_id or "").strip()]

    def list_manager_review_reports(self, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        where = ["""
            EXISTS (
                SELECT 1
                FROM jsonb_array_elements(COALESCE(report.review_proposals, '[]'::jsonb)) proposal
                WHERE proposal->>'kind' = 'manager'
            )
        """]
        params: Dict[str, Any] = {}
        if folder_id:
            where.append("report.local_folder_id = CAST(:folder_id AS UUID)")
            params["folder_id"] = folder_id
        with self.engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT report.*
                FROM research_reports report
                WHERE {' AND '.join(where)}
                ORDER BY report.updated_at DESC
            """), params).fetchall()
        return self._rows_with_manager_links(rows)

    def list_report_manager_links(self, report_id: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT link.manager_id, link.manager_name, link.source, link.confirmed_at,
                       manager.company AS manager_company,
                       manager.management_years AS manager_management_years
                FROM research_report_managers link
                LEFT JOIN managers manager ON manager.wind_code = link.manager_id
                WHERE link.report_id = CAST(:report_id AS UUID)
                ORDER BY link.confirmed_at, link.manager_name
            """), {"report_id": report_id}).fetchall()
        return [self._row(row) or {} for row in rows]

    def set_report_manager_link(
        self,
        report_id: str,
        manager_id: str,
        manager_name: str,
        source: str = "research_memo_review",
        confirmed_at: Optional[str] = None,
    ) -> None:
        from sqlalchemy import text

        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO research_report_managers (
                    report_id, manager_id, manager_name, source, confirmed_at, updated_at
                ) VALUES (
                    CAST(:report_id AS UUID), :manager_id, :manager_name, :source,
                    COALESCE(CAST(:confirmed_at AS TIMESTAMPTZ), NOW()), NOW()
                )
                ON CONFLICT (report_id, manager_id) DO UPDATE SET
                    manager_name = EXCLUDED.manager_name,
                    source = EXCLUDED.source,
                    confirmed_at = EXCLUDED.confirmed_at,
                    updated_at = NOW()
            """), {
                "report_id": report_id,
                "manager_id": manager_id,
                "manager_name": manager_name,
                "source": source,
                "confirmed_at": confirmed_at,
            })

    def remove_report_manager_link(self, report_id: str, manager_id: str) -> None:
        from sqlalchemy import text

        with self.engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM research_report_managers
                WHERE report_id = CAST(:report_id AS UUID)
                  AND manager_id = :manager_id
            """), {"report_id": report_id, "manager_id": manager_id})

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM local_research_folders WHERE id = CAST(:id AS UUID)"), {"id": folder_id}).fetchone()
        return self._row(row)

    def update_folder(self, folder_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        allowed = {key: value for key, value in fields.items() if key in {
            "path", "name", "status", "last_scan_at", "last_scan_counts", "updated_at"
        }}
        if not allowed:
            return self.get_folder(folder_id)
        sql = f"UPDATE local_research_folders SET {self._assignments(allowed)} WHERE id = CAST(:id AS UUID) RETURNING *"
        with self.engine.begin() as conn:
            row = conn.execute(text(sql), {**self._params(allowed), "id": folder_id}).fetchone()
        return self._row(row)

    def get_document(self, folder_id: str, relative_path: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT * FROM local_research_documents
                WHERE folder_id = CAST(:folder_id AS UUID) AND relative_path = :relative_path
            """), {"folder_id": folder_id, "relative_path": relative_path}).fetchone()
        return self._row(row)

    def find_document_by_hash(
        self,
        content_hash: str,
        exclude_folder_id: Optional[str] = None,
        exclude_relative_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        sql = """
            SELECT * FROM local_research_documents
            WHERE content_hash = :content_hash AND report_id IS NOT NULL
              AND NOT (
                CAST(:exclude_folder_id AS UUID) IS NOT NULL
                AND folder_id = CAST(:exclude_folder_id AS UUID)
                AND relative_path = :exclude_relative_path
              )
            LIMIT 1
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {
                "content_hash": content_hash,
                "exclude_folder_id": exclude_folder_id,
                "exclude_relative_path": exclude_relative_path,
            }).fetchone()
        return self._row(row)

    def upsert_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text

        fields = {key: document.get(key) for key in (
            "folder_id", "relative_path", "source_path", "size", "mtime_ns", "content_hash",
            "report_id", "index_status", "error", "updated_at",
        )}
        sql = """
            INSERT INTO local_research_documents (
                folder_id, relative_path, source_path, size, mtime_ns, content_hash,
                report_id, index_status, error, updated_at
            ) VALUES (
                CAST(:folder_id AS UUID), :relative_path, :source_path, :size, :mtime_ns, :content_hash,
                CAST(:report_id AS UUID), :index_status, :error, :updated_at
            )
            ON CONFLICT (folder_id, relative_path) DO UPDATE SET
                source_path = EXCLUDED.source_path,
                size = EXCLUDED.size,
                mtime_ns = EXCLUDED.mtime_ns,
                content_hash = EXCLUDED.content_hash,
                report_id = EXCLUDED.report_id,
                index_status = EXCLUDED.index_status,
                error = EXCLUDED.error,
                updated_at = EXCLUDED.updated_at
            RETURNING *
        """
        with self.engine.begin() as conn:
            row = conn.execute(text(sql), fields).fetchone()
        return self._row(row) or {}

    def create_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text

        fields = {key: value for key, value in report.items() if key in self.REPORT_FIELDS}
        columns = ", ".join(fields)
        values = ", ".join(
            f"CAST(:{key} AS JSONB)" if key in self.JSON_FIELDS else f":{key}"
            for key in fields
        )
        with self.engine.begin() as conn:
            row = conn.execute(
                text(f"INSERT INTO research_reports ({columns}) VALUES ({values}) RETURNING *"),
                self._params(fields),
            ).fetchone()
        return self._row(row) or {}

    def update_report(self, report_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        allowed = {key: value for key, value in fields.items() if key in self.REPORT_FIELDS and key != "created_at"}
        if not allowed:
            return self.get_report(report_id)
        sql = f"UPDATE research_reports SET {self._assignments(allowed)} WHERE id = CAST(:id AS UUID) RETURNING *"
        with self.engine.begin() as conn:
            row = conn.execute(text(sql), {**self._params(allowed), "id": report_id}).fetchone()
        return self._with_manager_links(self._row(row))

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM research_reports WHERE id = CAST(:id AS UUID)"), {"id": report_id}).fetchone()
        return self._with_manager_links(self._row(row))

    def list_reports(
        self,
        manager_id: Optional[str] = None,
        fund_id: Optional[str] = None,
        folder_id: Optional[str] = None,
        keyword: Optional[str] = None,
        tags: Optional[List[str]] = None,
        viewpoint_topics: Optional[List[str]] = None,
        research_domain: Optional[str] = None,
        source: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "report_date",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        from sqlalchemy import text

        where = ["1=1"]
        params: Dict[str, Any] = {}
        if manager_id:
            where.append("""
                (
                    manager_id = :manager_id
                    OR manager_name = :manager_id
                    OR EXISTS (
                        SELECT 1
                        FROM research_report_managers link
                        WHERE link.report_id = research_reports.id
                          AND (link.manager_id = :manager_id OR link.manager_name = :manager_id)
                    )
                )
            """)
            params["manager_id"] = manager_id
        if fund_id:
            where.append(":fund_id = ANY(COALESCE(fund_ids, ARRAY[]::TEXT[]))")
            params["fund_id"] = fund_id
        if folder_id:
            where.append("""
                EXISTS (
                    SELECT 1
                    FROM local_research_documents document
                    WHERE document.report_id = research_reports.id
                      AND document.folder_id = CAST(:folder_id AS UUID)
                )
            """)
            params["folder_id"] = folder_id
        if keyword:
            where.append("(title ILIKE :keyword OR summary ILIKE :keyword OR content ILIKE :keyword)")
            params["keyword"] = f"%{keyword}%"
        if tags:
            where.append("COALESCE(research_reports.tags, ARRAY[]::TEXT[]) && :tags")
            params["tags"] = tags
        if viewpoint_topics:
            where.append("COALESCE(research_reports.viewpoint_topics, ARRAY[]::TEXT[]) && :viewpoint_topics")
            params["viewpoint_topics"] = viewpoint_topics
        if research_domain:
            where.append(":research_domain = ANY(COALESCE(research_reports.research_domains, ARRAY[]::TEXT[]))")
            params["research_domain"] = research_domain
        if source:
            where.append("source ILIKE :source")
            params["source"] = f"%{source}%"
        if start_date:
            where.append("report_date >= CAST(:start_date AS DATE)")
            params["start_date"] = start_date
        if end_date:
            where.append("report_date <= CAST(:end_date AS DATE)")
            params["end_date"] = end_date

        safe_sort = sort_by if sort_by in {"report_date", "created_at", "updated_at", "title"} else "report_date"
        direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"
        where_sql = " AND ".join(where)
        params.update({
            "limit": max(1, min(int(page_size), 50)),
            "offset": max(0, int(page) - 1) * max(1, min(int(page_size), 50)),
        })
        with self.engine.connect() as conn:
            total = int(conn.execute(text(f"SELECT COUNT(*) FROM research_reports WHERE {where_sql}"), params).scalar() or 0)
            rows = conn.execute(text(f"""
                SELECT * FROM research_reports
                WHERE {where_sql}
                ORDER BY {safe_sort} {direction} NULLS LAST, updated_at DESC
                LIMIT :limit OFFSET :offset
            """), params).fetchall()
        return {"total": total, "reports": self._rows_with_manager_links(rows)}

    def list_reports_for_fund(self, wind_code: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT * FROM research_reports
                WHERE :wind_code = ANY(COALESCE(fund_ids, ARRAY[]::TEXT[]))
                ORDER BY report_date DESC NULLS LAST, updated_at DESC
            """), {"wind_code": wind_code}).fetchall()
        return [self._row(row) or {} for row in rows]

    def list_pending_reviews(self, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        where = "review_proposals @> '[{\"review_status\":\"pending\"}]'::jsonb"
        params: Dict[str, Any] = {}
        if folder_id:
            where += """
                AND EXISTS (
                    SELECT 1
                    FROM local_research_documents document
                    WHERE document.report_id = research_reports.id
                      AND document.folder_id = CAST(:folder_id AS UUID)
                )
            """
            params["folder_id"] = folder_id
        with self.engine.connect() as conn:
            rows = conn.execute(text(f"SELECT * FROM research_reports WHERE {where} ORDER BY updated_at DESC"), params).fetchall()
        pending: List[Dict[str, Any]] = []
        for row in rows:
            report = self._row(row) or {}
            for proposal in report.get("review_proposals") or []:
                if proposal.get("review_status") == "pending":
                    if proposal.get("kind") == "fund" and proposal.get("extraction_source") == "tushare.fund_manager":
                        continue
                    pending.append({
                        "report_id": report.get("id"),
                        "report_title": report.get("title") or "无标题纪要",
                        "report_date": report.get("report_date"),
                        "report_date_source": report.get("report_date_source"),
                        "report_date_precision": report.get("report_date_precision"),
                        **proposal,
                    })
        return pending
