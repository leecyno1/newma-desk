"""Version timeline for immutable AI analysis records."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    return value


def _record(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


class PostgresAnalysisReportRepo:
    """PostgreSQL adapter used by the analysis history module."""

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        from database import get_engine

        sql = text(
            """
            SELECT id, target_type, target_id, report_type, content,
                   data_sources, generation_params, created_at
            FROM ai_analysis_reports
            WHERE id = CAST(:report_id AS UUID)
            LIMIT 1
            """
        )
        with get_engine().connect() as conn:
            row = conn.execute(sql, {"report_id": report_id}).fetchone()
        return dict(row._mapping) if row else None

    def list_versions(
        self,
        target_type: str,
        target_id: str,
        report_type: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        from database import get_engine

        sql = text(
            """
            SELECT id, target_type, target_id, report_type, content,
                   data_sources, generation_params, created_at
            FROM ai_analysis_reports
            WHERE target_type = :target_type
              AND target_id = :target_id
              AND report_type = :report_type
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        )
        with get_engine().connect() as conn:
            rows = conn.execute(
                sql,
                {
                    "target_type": target_type,
                    "target_id": target_id,
                    "report_type": report_type,
                    "limit": max(1, min(int(limit), 100)),
                },
            ).fetchall()
        return [dict(row._mapping) for row in rows]


class AnalysisHistoryService:
    """Turn immutable analysis records into a user-readable version timeline."""

    def __init__(self, repo: Optional[Any] = None):
        self.repo = repo or PostgresAnalysisReportRepo()

    def timeline_for_report(self, report_id: str, limit: int = 50) -> Dict[str, Any]:
        current = self.repo.get_report(report_id)
        if not current:
            raise ValueError("analysis_report_not_found")

        records = self.repo.list_versions(
            str(current.get("target_type") or ""),
            str(current.get("target_id") or ""),
            str(current.get("report_type") or ""),
            limit,
        )
        ordered = sorted(
            records,
            key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")),
        )
        revisions = []
        previous: Optional[Dict[str, Any]] = None
        current_revision = 0
        for revision_number, record in enumerate(ordered, start=1):
            item = self._timeline_item(record, revision_number, previous, report_id)
            revisions.append(item)
            if item["is_current"]:
                current_revision = revision_number
            previous = record

        return {
            "target_type": current.get("target_type"),
            "target_id": current.get("target_id"),
            "report_type": current.get("report_type"),
            "current_report_id": str(report_id),
            "current_revision": current_revision,
            "total_revisions": len(revisions),
            "revisions": list(reversed(revisions)),
        }

    def _timeline_item(
        self,
        record: Dict[str, Any],
        revision_number: int,
        previous: Optional[Dict[str, Any]],
        current_report_id: str,
    ) -> Dict[str, Any]:
        params = _record(record.get("generation_params"))
        previous_params = _record(previous.get("generation_params")) if previous else {}
        mode = str(params.get("mode") or "unknown")
        mode_label = self._mode_label(mode)
        question = str(params.get("question") or "").strip()
        provider = str(params.get("provider") or "").strip()
        model = str(params.get("model") or "").strip()
        summary_parts = []
        if previous is None:
            summary_parts.append("首次保存基金评价分析")
        else:
            previous_mode = str(previous_params.get("mode") or "unknown")
            if previous_mode != mode:
                summary_parts.append(
                    f"生成方式由{self._mode_label(previous_mode)}变为{mode_label}"
                )
            if question and question != str(previous_params.get("question") or "").strip():
                summary_parts.append(f"关注问题：{question}")
            previous_runtime = (
                str(previous_params.get("provider") or "").strip(),
                str(previous_params.get("model") or "").strip(),
            )
            if (provider, model) != previous_runtime and (provider or model):
                summary_parts.append(f"模型：{' · '.join(item for item in (provider, model) if item)}")
        if not summary_parts:
            summary_parts.append("使用更新后的基金、评价、归因或纪要证据重新分析")

        return {
            "id": str(record.get("id") or ""),
            "revision": revision_number,
            "is_current": str(record.get("id") or "") == str(current_report_id),
            "created_at": _json_value(record.get("created_at")),
            "mode": mode,
            "mode_label": mode_label,
            "provider": provider or None,
            "model": model or None,
            "question": question,
            "change_summary": "；".join(summary_parts),
        }

    @staticmethod
    def _mode_label(mode: str) -> str:
        if mode == "llm_evaluation_evidence":
            return "模型综合评价"
        if "deterministic" in mode:
            return "本地证据评价"
        return "分析记录"
