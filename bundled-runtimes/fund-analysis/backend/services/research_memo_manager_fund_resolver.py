"""Resolve a memo's manager to funds managed on the memo date using real Tushare data."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional


class ResearchMemoManagerFundResolver:
    def __init__(self, data_service: Optional[Any] = None, engine: Optional[Any] = None):
        self._data_service = data_service
        self._engine = engine
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    def resolve(self, manager_name: str, report_date: str, report_title: str = "") -> List[Dict[str, Any]]:
        name = str(manager_name or "").strip()
        as_of_date = self._parse_date(report_date)
        if not name or as_of_date is None:
            return []

        rows = self._manager_rows(name)
        active_codes = []
        for row in rows:
            if str(row.get("name") or "").strip() != name:
                continue
            begin_date = self._parse_date(row.get("begin_date"))
            end_date = self._parse_date(row.get("end_date"))
            if begin_date and begin_date > as_of_date:
                continue
            if end_date and end_date < as_of_date:
                continue
            wind_code = self._wind_code(row.get("ts_code"))
            if wind_code:
                active_codes.append(wind_code)
        return self._local_canonical_funds(active_codes, report_title)

    def _manager_rows(self, manager_name: str) -> List[Dict[str, Any]]:
        if manager_name in self._cache:
            return self._cache[manager_name]
        try:
            service = self._get_data_service()
            frame = service.pro.fund_manager(
                name=manager_name,
                fields="ts_code,name,begin_date,end_date",
            )
            rows = [] if frame is None or frame.empty else frame.to_dict("records")
        except Exception:
            rows = []
        self._cache[manager_name] = rows
        return rows

    def _local_canonical_funds(self, wind_codes: List[str], report_title: str) -> List[Dict[str, Any]]:
        normalized_codes = list(dict.fromkeys(code for code in wind_codes if code))
        if not normalized_codes:
            return []

        from sqlalchemy import text

        sql = """
            SELECT DISTINCT ON (COALESCE(fe.canonical_code, f.wind_code))
                COALESCE(fe.canonical_code, f.wind_code) AS wind_code,
                COALESCE(canonical_fund.name, f.name) AS fund_name,
                f.raw_data->'universe'->>'manager' AS management_company
            FROM funds f
            LEFT JOIN fund_share_classes fsc ON fsc.wind_code = f.wind_code
            LEFT JOIN fund_entities fe ON fe.id = fsc.entity_id
            LEFT JOIN funds canonical_fund ON canonical_fund.wind_code = fe.canonical_code
            WHERE f.wind_code = ANY(:wind_codes)
            ORDER BY COALESCE(fe.canonical_code, f.wind_code), fsc.is_primary DESC NULLS LAST, f.wind_code
        """
        with self._get_engine().connect() as conn:
            rows = [dict(row._mapping) for row in conn.execute(text(sql), {"wind_codes": normalized_codes}).fetchall()]

        title = str(report_title or "")
        company_matched = [
            row for row in rows
            if (alias := self._company_alias(row.get("management_company"))) and alias in title
        ]
        company_aliases = {
            alias for row in rows
            if (alias := self._company_alias(row.get("management_company")))
        }
        if not company_matched and len(company_aliases) > 1:
            return []
        selected = company_matched or rows
        return [{
            "wind_code": row["wind_code"],
            "fund_name": row.get("fund_name"),
            "management_company": row.get("management_company"),
            "source": "tushare.fund_manager",
        } for row in selected]

    def _get_data_service(self):
        if self._data_service is None:
            from services.tushare_service import TushareDataService

            self._data_service = TushareDataService(strict_no_mock=True)
        return self._data_service

    def _get_engine(self):
        if self._engine is None:
            from database import get_engine

            self._engine = get_engine()
        return self._engine

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        text_value = str(value or "").strip().replace("-", "")[:8]
        if len(text_value) != 8 or not text_value.isdigit():
            return None
        try:
            return date(int(text_value[:4]), int(text_value[4:6]), int(text_value[6:8]))
        except ValueError:
            return None

    @staticmethod
    def _wind_code(value: Any) -> str:
        code = str(value or "").strip().upper()
        return code if code.endswith((".OF", ".SH", ".SZ", ".BJ", ".HK")) else ""

    @staticmethod
    def _company_alias(value: Any) -> str:
        company = str(value or "").strip()
        for suffix in ("基金管理股份有限公司", "基金管理有限公司", "资产管理有限公司", "投资管理有限公司", "股份有限公司", "有限公司"):
            if company.endswith(suffix):
                return company[:-len(suffix)]
        return company
