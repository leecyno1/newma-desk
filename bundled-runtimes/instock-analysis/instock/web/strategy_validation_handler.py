#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP adapter for point-in-time strategy validation packets."""

from __future__ import annotations

import asyncio
import json
import logging

from instock.core.market_data_provider import MarketDataError, get_market_data_provider
from instock.core.validation import StrategyValidationEngine, StrategyValidationError
from instock.web.api_contract import AnalysisApiHandler


class StrategyValidationHandler(AnalysisApiHandler):
    async def post(self) -> None:
        if not self.request.body:
            self.write_error(400, "empty_validation_packet", "策略验证包不能为空")
            return
        try:
            packet = json.loads(self.request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.write_error(400, "invalid_json", "策略验证包必须是有效 JSON 对象")
            return
        try:
            result = await asyncio.to_thread(
                StrategyValidationEngine(get_market_data_provider()).validate,
                packet,
            )
            strategy = result.get("strategy") or {}
            self.write_analysis_success(
                result,
                module_id="strategy-validation",
                title=f"{strategy.get('name') or strategy.get('id') or '策略'} · 验证",
                parameters={
                    "strategyId": strategy.get("id"),
                    "benchmark": result.get("benchmark"),
                    "asOf": result.get("as_of"),
                },
            )
        except StrategyValidationError as exc:
            self.write_error(400, "invalid_validation_packet", str(exc))
        except MarketDataError as exc:
            self.write_error(502, "market_data_unavailable", str(exc))
        except Exception:  # noqa: BLE001
            logging.exception("策略验证接口异常")
            self.write_error(500, "internal_error", "策略验证服务异常")
