#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP adapter for Desk-supplied market event and flow packets."""

from __future__ import annotations

import json
import logging

from instock.core.market_data_provider import MarketDataError
from instock.core.research import EventFlowEngine, EventFlowError
from instock.web.api_contract import AnalysisApiHandler


class EventFlowHandler(AnalysisApiHandler):
    def post(self) -> None:
        if not self.request.body:
            self.write_error(400, "empty_event_flow_packet", "事件资金包不能为空")
            return
        try:
            packet = json.loads(self.request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.write_error(400, "invalid_json", "事件资金请求必须是有效 JSON 对象")
            return
        try:
            result = EventFlowEngine().analyze_request(packet)
            symbol = (result.get("query") or {}).get("symbol")
            self.write_analysis_success(
                result,
                module_id="event-flow",
                title=f"{symbol} · 公司事件" if symbol else "公司事件",
                parameters={
                    "symbol": symbol,
                    "asOf": result.get("as_of"),
                    "inputMode": result.get("input_mode"),
                },
            )
        except EventFlowError as exc:
            self.write_error(400, "invalid_event_flow_packet", str(exc))
        except MarketDataError as exc:
            self.write_error(502, "desk_data_unavailable", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("公司事件接口异常")
            self.write_error(500, "internal_error", "公司事件服务异常")
