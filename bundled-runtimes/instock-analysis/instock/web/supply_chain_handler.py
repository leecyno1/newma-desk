#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP adapter for host-supplied supply-chain research packets."""

from __future__ import annotations

import json
import logging

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.research import SupplyChainResearchEngine, SupplyChainResearchError
from instock.web.api_contract import AnalysisApiHandler


class SupplyChainResearchHandler(AnalysisApiHandler):
    """Validate and rank one point-in-time research packet.

    The adapter never fetches evidence itself.  Newma-Desk remains responsible
    for data access and Agent orchestration; this process only performs the
    deterministic part of the workflow.
    """

    def post(self) -> None:
        if not self.request.body:
            self.write_error(400, "empty_research_packet", "供应链研究包不能为空")
            return
        try:
            payload = json.loads(self.request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.write_error(400, "invalid_json", "供应链研究包必须是有效 JSON 对象")
            return
        if not isinstance(payload, dict):
            self.write_error(400, "invalid_research_packet", "供应链研究包必须是 JSON 对象")
            return

        try:
            result = SupplyChainResearchEngine().analyze(payload)
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
        except SupplyChainResearchError as exc:
            self.write_error(400, "invalid_research_packet", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("供应链瓶颈研究接口异常")
            self.write_error(500, "internal_error", "供应链瓶颈研究服务异常")
