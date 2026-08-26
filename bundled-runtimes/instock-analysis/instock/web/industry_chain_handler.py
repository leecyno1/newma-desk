#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP adapter for the standalone industry-chain research Module."""

from __future__ import annotations

import json
import logging

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.research import IndustryChainResearchEngine, IndustryChainResearchError
from instock.web.api_contract import AnalysisApiHandler


class IndustryChainResearchHandler(AnalysisApiHandler):
    """Validate and rank one Desk-supplied point-in-time industry-chain packet."""

    def post(self) -> None:
        if not self.request.body:
            self.write_error(400, "empty_research_packet", "产业链研究包不能为空")
            return
        try:
            payload = json.loads(self.request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.write_error(400, "invalid_json", "产业链研究包必须是有效 JSON 对象")
            return
        if not isinstance(payload, dict):
            self.write_error(400, "invalid_research_packet", "产业链研究包必须是 JSON 对象")
            return

        try:
            result = IndustryChainResearchEngine().analyze(payload)
            get_analysis_snapshot_registry().register(result["snapshot"])
            self.write_analysis_success(
                result,
                module_id="industry-chain",
                title=f"{result.get('theme') or '产业链'} · 产业链研究",
                parameters={
                    "theme": result.get("theme"),
                    "market": result.get("market"),
                    "asOf": result.get("as_of"),
                },
            )
        except IndustryChainResearchError as exc:
            self.write_error(400, "invalid_research_packet", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("产业链研究接口异常")
            self.write_error(500, "internal_error", "产业链研究服务异常")


# Keep the old class import usable for attached-runtime clients during migration.
IndustryChainHandler = IndustryChainResearchHandler
