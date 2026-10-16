import asyncio
import json

from instock.core.workbench.market_journal import get_market_journal_store
from instock.web.api_contract import AnalysisApiHandler, cors_origins


class MarketJournalHandler(AnalysisApiHandler):
    async def get(self, review_id=None):
        store = get_market_journal_store()
        if review_id:
            result = await asyncio.to_thread(store.get, review_id)
            if result is None:
                self.write_error(404, "review_not_found", "复盘记录不存在")
                return
        else:
            try:
                offset = int(self.get_argument("offset", "0"))
                if offset < 0: raise ValueError()
            except ValueError:
                self.write_error(400, "invalid_offset", "分页参数不正确")
                return
            try:
                result = await asyncio.to_thread(store.list, offset, self.get_argument("status", "all"))
            except ValueError as exc:
                self.write_error(400, "invalid_review_filter", str(exc))
                return
        self.write_success(result)

    async def post(self, review_id=None):
        origin = self.request.headers.get("Origin")
        if origin and origin not in (f"{self.request.protocol}://{self.request.host}", *cors_origins()):
            self.write_error(403, "origin_not_allowed", "不允许该页面写入本地复盘")
            return
        if len(self.request.body) > 1_000_000:
            self.write_error(413, "review_too_large", "复盘证据超过1MB")
            return
        try:
            body = json.loads(self.request.body)
            if not isinstance(body, dict): raise ValueError("复盘内容须为对象")
            store = get_market_journal_store()
            result = await asyncio.to_thread(store.add_check, review_id, body) if review_id else await asyncio.to_thread(store.create, body)
        except (ValueError, TypeError, KeyError) as exc:
            self.write_error(400, "invalid_review", str(exc))
            return
        except LookupError:
            self.write_error(404, "review_not_found", "复盘记录不存在")
            return
        self.write_success(result)
