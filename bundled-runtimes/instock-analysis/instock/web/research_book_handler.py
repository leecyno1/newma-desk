#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP adapter for deterministic research-book packets."""

from __future__ import annotations

import json
import logging

from instock.core.research import ResearchBookEngine, ResearchBookError
from instock.web.api_contract import AnalysisApiHandler


class ResearchBookHandler(AnalysisApiHandler):
    def get(self) -> None:
        """Prepare a draft from a same-scope dossier snapshot; never save the draft."""
        try:
            result = ResearchBookEngine().draft_from_dossier(
                self.get_query_argument("sourceSnapshotId", ""),
                symbol=self.get_query_argument("symbol", "").strip().upper(),
                market=self.get_query_argument("market", "CN").strip().upper())
            self.write_success(result)
        except ResearchBookError as exc:
            self.write_error(400, "invalid_research_book_handoff", str(exc))

    def post(self) -> None:
        if not self.request.body:
            self.write_error(400, "empty_research_book_packet", "研究组合包不能为空")
            return
        try:
            packet = json.loads(self.request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.write_error(400, "invalid_json", "研究组合包必须是有效 JSON 对象")
            return
        try:
            result = ResearchBookEngine().analyze(packet)
            self.write_analysis_success(result, module_id="research-book",
                title=f"{result['name']} · 研究组合", parameters={"asOf": result["as_of"]})
        except ResearchBookError as exc:
            self.write_error(400, "invalid_research_book_packet", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("研究组合接口异常")
            self.write_error(500, "internal_error", "研究组合服务异常")
