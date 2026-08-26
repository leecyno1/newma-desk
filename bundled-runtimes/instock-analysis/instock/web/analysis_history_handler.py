#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP resources for complete analysis result history."""

from __future__ import annotations

from instock.core.analysis_history import get_analysis_history_registry
from instock.web.api_contract import AnalysisApiHandler


class AnalysisHistoryCollectionHandler(AnalysisApiHandler):
    def get(self) -> None:
        module_id = self.get_argument("moduleId", "").strip()
        if not module_id:
            self.write_error(400, "missing_module_id", "moduleId 不能为空")
            return
        try:
            limit = int(self.get_argument("limit", "30"))
        except ValueError:
            self.write_error(400, "invalid_limit", "limit 必须是整数")
            return
        registry = get_analysis_history_registry()
        records = registry.list(module_id, limit=limit)
        self.write_success(records, meta={"history": registry.stats()})


class AnalysisHistoryResourceHandler(AnalysisApiHandler):
    def get(self, history_id: str) -> None:
        registry = get_analysis_history_registry()
        record = registry.get(history_id)
        if record is None:
            self.write_error(404, "analysis_history_not_found", "历史记录不存在或已过期")
            return
        self.write_success(record, meta={"history": registry.stats()})
