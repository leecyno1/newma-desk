#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Resource handler for registered analysis snapshot metadata."""

from __future__ import annotations

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.web.api_contract import AnalysisApiHandler


class AnalysisSnapshotResourceHandler(AnalysisApiHandler):
    """Return a same-scope snapshot from memory or retained analysis history."""

    def get(self, snapshot_id: str) -> None:
        registry = get_analysis_snapshot_registry()
        snapshot = registry.get(snapshot_id)
        if snapshot is None:
            self.write_error(
                404,
                "analysis_snapshot_not_found",
                "当前范围没有可用快照或保留历史，请返回来源模块重新分析",
            )
            return
        self.write_success(snapshot, meta={"registry": registry.stats(),
            "reference_policy": "same_scope_memory_or_retained_history",
            "freshness_basis": "original_analysis_time_not_retrieval_time"})
