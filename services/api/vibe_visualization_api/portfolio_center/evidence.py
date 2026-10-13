"""复用上游只读证据；定性提示与组合敏感度计算严格分离。"""
import asyncio
import math
from datetime import date

from vibe_visualization_api.data_services.client import DataServiceClientError
from vibe_visualization_api.data_services.registry import DataServiceRegistryError
from vibe_visualization_api.schema_validation import JsonContractError
from .diagnosis import PortfolioSnapshotInput


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def project_fund_evidence(symbol: str, payload: dict, as_of: date) -> dict:
    result = {"status": "unavailable", "asOf": None, "estimatedDuration": None,
              "rSquared": None, "method": None, "source": "fund-analysis-data",
              "note": "基金模块暂无可复用久期证据；不代表没有利率风险。"}
    if payload.get('status') == 'ambiguous':
        result.update(status='ambiguous', note='基金代码存在多个匹配，请在持仓中补全交易所或 .OF 后缀。')
        return result
    resolved = str(payload.get('symbol', '')).upper()
    exact = resolved == symbol or (len(symbol) == 6 and symbol.isdigit() and resolved in {f'{symbol}.OF', f'{symbol}.SH', f'{symbol}.SZ'})
    if payload.get('status') != 'available' or not exact:
        return result
    d = payload.get('duration') or {}
    result.update(resolvedSymbol=resolved, method=d.get('methodology_version'), source=d.get('source') or result['source'])
    if d.get('status') == 'not_applicable':
        result.update(status='not_applicable', note='上游久期模型不适用于该基金，不能因此将利率敏感度填为 0。')
        return result
    try:
        observed = date.fromisoformat(str(d.get('as_of_date'))[:10])
    except ValueError:
        return result
    result['asOf'] = observed.isoformat()
    if observed > as_of:
        result.update(status='after_snapshot', note='证据日期晚于持仓快照，不用于本次历史评估。')
        return result
    if d.get('status') not in {'ok', 'low_fit'} or not _finite(d.get('estimated_duration')) or not _finite(d.get('r_squared')):
        return result
    result.update(estimatedDuration=d['estimated_duration'], rSquared=d['r_squared'])
    # 31 天为本地提示阈值，不是监管有效期；所有回归值均不进入 DV01。
    state = 'stale' if (as_of-observed).days > 31 else 'low_fit' if d['r_squared'] < .45 or d['status'] == 'low_fit' else 'reference_only'
    note = {'stale': '距快照日超过 31 天，仅作历史参考。', 'low_fit': '回归拟合较低，不作强结论。', 'reference_only': '可作为基金利率风险线索。'}[state]
    result.update(status=state, note=note+'这是净值回归估算，不是披露修正久期，未换算或覆盖持仓利率损益。')
    return result


async def read_fund_evidence(snapshot: PortfolioSnapshotInput, client, registry) -> list[dict]:
    funds = {(p.market, p.symbol.upper()): p.name for p in snapshot.holdings if p.asset_type == 'fund'}
    semaphore = asyncio.Semaphore(3)

    async def read(key, name):
        market, symbol = key
        item = {"market": market, "symbol": symbol, "name": name}
        if market != 'CN':
            return dict(item, status='unsupported', note='当前基金证据通道仅支持明确标注 CN 的基金；未关联不等于无风险。')
        try:
            async with semaphore:
                payload = await asyncio.wait_for(client.invoke(registry.get('fund-analysis-data'), 'fund.risk.evidence', {'symbol': symbol}), timeout=8)
            return dict(item, **project_fund_evidence(symbol, payload, snapshot.as_of))
        except (DataServiceClientError, DataServiceRegistryError, JsonContractError, TimeoutError):
            return dict(item, status='unavailable', note='基金证据服务暂不可用；保留持仓原值及已有测算，请稍后重试。')

    # 大组合不允许数百个串行超时阻塞；本批最多 12 个，其余明确标记未读取。
    entries = list(funds.items())
    results = await asyncio.gather(*(read(key, name) for key, name in entries[:12]))
    results.extend(dict(market=key[0], symbol=key[1], name=name, status='not_loaded', note='本次仅读取前 12 只不同基金，此项尚未读取。') for key, name in entries[12:])
    return results
