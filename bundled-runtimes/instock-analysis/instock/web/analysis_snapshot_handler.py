#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Resource handler for registered analysis snapshot metadata."""

from __future__ import annotations

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.web.api_contract import AnalysisApiHandler


class AnalysisSnapshotResourceHandler(AnalysisApiHandler):
    """Return one volatile, process-local Analysis Snapshot resource."""

    def get(self, snapshot_id: str) -> None:
        registry = get_analysis_snapshot_registry()
        snapshot = registry.get(snapshot_id)
        if snapshot is None:
            self.write_error(
                404,
                "analysis_snapshot_not_found",
                "分析快照不存在、已过期，或服务进程已重启",
            )
            return
        self.write_success(snapshot, meta={"registry": registry.stats()})
