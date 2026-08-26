#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP adapter for deterministic research-book packets."""

from __future__ import annotations

import json
import logging

from instock.core.research import ResearchBookEngine, ResearchBookError
from instock.web.api_contract import AnalysisApiHandler


class ResearchBookHandler(AnalysisApiHandler):
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
            self.write_analysis_success(
                result,
                module_id="research-book",
                title=f"{result.get('name') or '研究组合'} · 组合检查",
                parameters={
                    "name": result.get("name"),
                    "asOf": result.get("as_of"),
                    "items": (result.get("summary") or {}).get("items"),
                },
            )
        except ResearchBookError as exc:
            self.write_error(400, "invalid_research_book_packet", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("研究组合接口异常")
            self.write_error(500, "internal_error", "研究组合服务异常")
