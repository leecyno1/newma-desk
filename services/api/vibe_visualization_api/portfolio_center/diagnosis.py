"""Imported portfolio snapshots and bounded, first-order portfolio diagnostics.

Snapshots do not create executions. Risk sensitivities are supplied evidence, not
inferred from asset names or research ratings.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic.alias_generators import to_camel

from .issuer import compile_issuer_exposure
from .liquidity import compile_liquidity_plan
from .conclusion import compile_conclusion
from .thresholds import compile_nav_thresholds


class DiagnosisModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False)


class SnapshotHolding(DiagnosisModel):
    asset_type: Literal["stock", "fund", "bond", "equity_future", "bond_future", "cash", "liability", "other"]
    market: str = Field(default="", max_length=40)
    symbol: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    account: str = Field(min_length=1, max_length=80)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    book_value: float | None = None
    fx_to_base: float | None = Field(default=None, gt=0)
    available_cash: float | None = Field(default=None, ge=0)
    proceeds_amount: float | None = Field(default=None, ge=0)
    proceeds_date: date | None = None
    proceeds_account: str = Field(default='', max_length=80)
    proceeds_source: str = Field(default='', max_length=240)
    equity_beta: float | None = None
    equity_benchmark: str = Field(default="", max_length=60)
    rate_pnl_per_bp: float | None = None
    modified_duration: float | None = Field(default=None, ge=0)
    contracts: int | None = Field(default=None, gt=0)
    contract_dv01: float | None = Field(default=None, gt=0)
    rate_as_of: date | None = None
    expiry_date: date | None = None
    direction: Literal["long", "short"] | None = None
    notional: float | None = Field(default=None, gt=0)
    issuer: str = Field(default="", max_length=120)
    source: str = Field(default="用户导入，未独立核验", max_length=240)

    @model_validator(mode="after")
    def check_conventions(self):
        if self.asset_type == "liability" and self.book_value is not None and self.book_value > 0:
            raise ValueError("负债的账面净值贡献须为负数")
        if self.asset_type in {"stock", "fund", "bond", "cash"} and self.book_value is not None and self.book_value < 0:
            raise ValueError("该类持仓本轮只接受非负市值；空头请勿伪装为现货")
        if self.asset_type.endswith("future") and self.direction is None:
            raise ValueError("期货必须填写多空方向，不能根据名称推断对冲")
        if self.available_cash is not None and (self.asset_type != "cash" or self.book_value is None or self.available_cash > self.book_value):
            raise ValueError("可用现金仅能填在现金行，且不得超过该行账面金额")
        if self.modified_duration is not None and self.asset_type != 'bond':
            raise ValueError('修正久期换算仅用于普通固定利率债券，基金回归久期不能填在这里')
        if (self.contracts is not None or self.contract_dv01 is not None) and self.asset_type != 'bond_future':
            raise ValueError('本轮手数与每手 DV01 换算仅用于国债期货')
        if self.expiry_date is not None and not self.asset_type.endswith('future'):
            raise ValueError('合约到期日仅用于期货')
        if (self.proceeds_amount is not None or self.proceeds_date is not None or self.proceeds_account or self.proceeds_source) and self.asset_type not in {'stock', 'fund', 'bond'}:
            raise ValueError('预计变现款只填在股票、基金或债券行，已到账现金及期货不得重复填入')
        return self


class AdditionalScenario(DiagnosisModel):
    label: str = Field(min_length=1, max_length=60)
    equity_shock_pct: float = Field(ge=-100, le=100)
    rate_shock_bp: float = Field(ge=-1000, le=1000)

    @model_validator(mode='after')
    def check_label(self):
        self.label = self.label.strip()
        if not self.label:
            raise ValueError('请填写情景名称')
        return self


class OutflowAllocation(DiagnosisModel):
    account: str = Field(min_length=1, max_length=80)
    amount: float = Field(ge=0)


class PortfolioSnapshotInput(DiagnosisModel):
    nav_warning_floor: float | None = Field(default=None, ge=0)
    # One snapshot contains one product only. Empty keeps legacy imports unassigned.
    product_id: str = Field(default='', max_length=80)
    name: str = Field(min_length=1, max_length=100)
    as_of: date
    base_currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")
    nav_floor: float | None = Field(default=None, ge=0)
    near_term_outflow: float = Field(default=0, ge=0)
    cash_need_date: date | None = None
    additional_scenarios: list[AdditionalScenario] = Field(default_factory=list, max_length=6)
    outflow_allocations: list[OutflowAllocation] = Field(default_factory=list, max_length=2000)
    holdings: list[SnapshotHolding] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def check_snapshot(self):
        if self.nav_warning_floor is not None and self.nav_floor is not None and self.nav_warning_floor < self.nav_floor:
            raise ValueError('净值预警线不能低于净值底线；两者均填写基准币净资产金额，不是单位净值或百分比')
        if self.product_id != self.product_id.strip():
            raise ValueError('产品编号不能带首尾空格；同一产品请沿用固定编号')
        allocation_accounts = [a.account for a in self.outflow_allocations]
        if len(set(allocation_accounts)) != len(allocation_accounts):
            raise ValueError('同一账户的近期预留请合并填写')
        if not set(allocation_accounts).issubset({p.account for p in self.holdings}):
            raise ValueError('预留账户须与持仓中的账户名称一致')
        if sum(a.amount for a in self.outflow_allocations) > self.near_term_outflow + 1e-8:
            raise ValueError('账户预留合计不能超过近期需留资金总额')
        if len({s.label for s in self.additional_scenarios}) != len(self.additional_scenarios):
            raise ValueError('自定义情景名称不能重复')
        keys = [(p.account, p.asset_type, p.market, p.symbol, p.direction) for p in self.holdings]
        seen = {}
        for index, key in enumerate(keys):
            if key in seen:
                raise ValueError(f"重复持仓：第 {seen[key]+1} 行与第 {index+1} 行（{self.holdings[index].account} · {self.holdings[index].symbol}）；同账户同资产同方向请先合并，避免重复计量")
            seen[key] = index
        rates: dict[str, float] = {}
        for p in self.holdings:
            if p.currency == self.base_currency and p.fx_to_base not in (None, 1):
                raise ValueError("基准币种的折算汇率必须为 1")
            if p.fx_to_base is not None:
                if p.currency in rates and abs(rates[p.currency] - p.fx_to_base) > 1e-9:
                    raise ValueError("同一币种的快照汇率必须一致")
                rates[p.currency] = p.fx_to_base
        if self.as_of > date.today():
            raise ValueError("持仓截止日不能在未来")
        if self.cash_need_date is not None and self.cash_need_date < self.as_of:
            raise ValueError('资金观察日不能早于持仓截止日')
        return self


class PortfolioImportInput(DiagnosisModel):
    nav_warning_floor: float | None = Field(default=None, ge=0)
    product_id: str = Field(default='', max_length=80)
    name: str = Field(min_length=1, max_length=100)
    as_of: date
    base_currency: str = "CNY"
    nav_floor: float | None = Field(default=None, ge=0)
    near_term_outflow: float = Field(default=0, ge=0)
    cash_need_date: date | None = None
    additional_scenarios: list[AdditionalScenario] = Field(default_factory=list, max_length=6)
    outflow_allocations: list[OutflowAllocation] = Field(default_factory=list, max_length=2000)
    text: str = Field(min_length=1, max_length=1_000_000)


HEADERS = {"资产类型": "assetType", "市场": "market", "代码": "symbol", "名称": "name", "账户": "account", "币种": "currency", "账面金额": "bookValue", "折算汇率": "fxToBase", "可用现金": "availableCash", "权益Beta": "equityBeta", "对冲基准": "equityBenchmark", "利率每基点损益": "ratePnlPerBp", "方向": "direction", "名义金额": "notional", "发行人": "issuer", "依据": "source"}
HEADERS.update({'修正久期': 'modifiedDuration', '持仓手数': 'contracts', '每手DV01': 'contractDv01', '利率参数日期': 'rateAsOf', '合约到期日': 'expiryDate'})
HEADERS.update({'预计到账金额': 'proceedsAmount', '预计到账日': 'proceedsDate', '收款账户': 'proceedsAccount', '到账依据': 'proceedsSource'})
ASSETS = {"股票": "stock", "基金": "fund", "债券": "bond", "股指期货": "equity_future", "国债期货": "bond_future", "现金": "cash", "负债": "liability", "其他": "other"}


class ImportValidationError(ValueError):
    def __init__(self, error: ValidationError, line: int | None = None):
        self.issues = []
        for issue in error.errors(include_input=False, include_url=False):
            self.issues.append({**issue, 'loc': (['csvRow', line] if line is not None else []) + list(issue['loc']),
                                'ctx': {k: v for k, v in issue.get('ctx', {}).items() if isinstance(v, (str, int, float))}})
        super().__init__((f'文件第 {line} 行：' if line is not None else '') + '；'.join(item['msg'] for item in self.issues))


def parse_import(data: PortfolioImportInput) -> PortfolioSnapshotInput:
    text = data.text.lstrip("\ufeff").strip()
    reader = csv.DictReader(io.StringIO(text), delimiter="\t" if "\t" in text.splitlines()[0] else ",", strict=True)
    raw_headers = reader.fieldnames or []
    headers = [HEADERS.get(h.strip(), h.strip()) for h in raw_headers]
    if len(set(headers)) != len(headers):
        raise ValueError("表头存在重复字段")
    if not {"assetType", "symbol", "name", "account", "currency"}.issubset(headers):
        raise ValueError("必须包含资产类型、代码、名称、账户、币种列；请下载模板或从 Excel 粘贴带表头内容")
    holdings = []
    try:
        csv_rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f"CSV 格式错误：{exc}") from exc
    for line, raw in enumerate(csv_rows, 2):
        if None in raw:
            raise ValueError(f"第 {line} 行列数与表头不一致")
        row = {HEADERS.get(k.strip(), k.strip()): v.strip() for k, v in raw.items() if v is not None and v.strip()}
        if not row:
            continue
        row["assetType"] = ASSETS.get(row.get("assetType", ""), row.get("assetType", ""))
        if "direction" in row:
            row["direction"] = {"多": "long", "空": "short", "多头": "long", "空头": "short"}.get(row["direction"], row["direction"])
        try:
            holdings.append(SnapshotHolding.model_validate(row))
        except ValidationError as exc:
            raise ImportValidationError(exc, line) from exc
    try:
        return PortfolioSnapshotInput(**data.model_dump(exclude={"text"}), holdings=holdings)
    except ValidationError as exc:
        raise ImportValidationError(exc) from exc


def resolve_rate_input(p: SnapshotHolding, as_of: date) -> tuple[float | None, str, list[str]]:
    """Return signed whole-position P&L per upward bp, in holding currency."""
    derived = p.modified_duration is not None or p.contracts is not None or p.contract_dv01 is not None
    if p.rate_as_of is not None and p.rate_as_of != as_of:
        return None, '参数日期与持仓日不一致，未用于计算', ['与持仓日一致的利率参数日期']
    if p.rate_pnl_per_bp is not None:
        note = '直接导入整笔利率损益；未独立核验'
        if derived:
            note += '；已填写整笔值，未用久期或每手 DV01 覆盖'
        if p.rate_as_of is None:
            note += '；参数日期未提供，尚未核验时点'
        return p.rate_pnl_per_bp, note, []
    if not derived:
        return None, '未提供利率参数', []
    if p.rate_as_of is None or not p.source.strip() or p.source == '用户导入，未独立核验':
        return None, '换算须提供同日参数及具体来源', ['换算参数日期及具体依据']
    if p.asset_type == 'bond' and p.modified_duration is not None and p.book_value is not None:
        return -p.book_value * p.modified_duration / 10000, '换算：−含息市值 × 修正久期 ÷ 10000；仅普通固定利率债的一阶估计', []
    if p.asset_type == 'bond_future' and p.contracts is not None and p.contract_dv01 is not None:
        return p.contracts * p.contract_dv01 * (1 if p.direction == 'short' else -1), '换算：手数 × 每手 DV01 × 方向符号（空正、多负）；未重估 CTD/基差', []
    return None, '换算字段未齐备', ['债券含息市值与修正久期，或国债期货手数与每手 DV01']


def diagnose(snapshot: PortfolioSnapshotInput, archive: dict | None = None) -> dict:
    gaps: list[str] = []
    rows = []
    exposures: dict[str, dict] = {}
    entries = (archive or {}).get("entries", [])
    lifecycle_alerts = []
    for p in snapshot.holdings:
        fx = 1 if p.currency == snapshot.base_currency else p.fx_to_base
        value = p.book_value * fx if p.book_value is not None and fx is not None else None
        missing = []
        if value is None:
            missing.append("账面金额或折算汇率")
        equity = rate = 0.0
        if p.asset_type in {"stock", "fund"}:
            equity = value * p.equity_beta if value is not None and p.equity_beta is not None and (p.equity_beta == 0 or p.equity_benchmark) else None
        elif p.asset_type == "equity_future":
            equity = p.notional * fx * (1 if p.direction == "long" else -1) if p.notional is not None and fx is not None and p.equity_benchmark else None
        rate_input, rate_basis = None, ''
        if p.asset_type in {"bond", "fund", "bond_future"}:
            rate_input, rate_basis, rate_gaps = resolve_rate_input(p, snapshot.as_of)
            missing.extend(rate_gaps)
            rate = rate_input * fx if rate_input is not None and fx is not None else None
        if p.asset_type.endswith('future'):
            if p.expiry_date is None:
                missing.append('合约到期日（无法判断展期风险）')
            elif p.expiry_date <= snapshot.as_of:
                equity = rate = None
                rate_basis += '；合约已到期，本次不采用该对冲参数'
                lifecycle_alerts.append(f'{p.name}：已到合约到期日，不再计作有效对冲；请核对结算或展期后的持仓')
            elif (p.expiry_date - snapshot.as_of).days <= 10:
                lifecycle_alerts.append(f'{p.name}：距合约到期 {(p.expiry_date - snapshot.as_of).days} 天，关注展期、交割与对冲中断')
        if p.asset_type == "other":
            equity = rate = None
        if equity is None:
            missing.append("权益敏感度及对应基准")
        if rate is None:
            missing.append("整笔持仓的利率每基点损益")
        if p.asset_type == "bond_future" and rate is not None and rate != 0 and ((p.direction == "short" and rate < 0) or (p.direction == "long" and rate > 0)):
            rate = None
            missing.append("国债期货敏感度符号与多空方向冲突")
        if p.asset_type == "cash" and p.available_cash is None:
            missing.append("现金可用额度")
        refs = [e for e in entries if p.asset_type == "stock" and e.get("security", {}).get("market") == p.market and e.get("security", {}).get("symbol") == p.symbol]
        for reason in missing:
            gaps.append(f"{p.name}：缺少或待核对{reason}")
        if equity is not None and equity != 0:
            bucket = exposures.setdefault(p.equity_benchmark, {"benchmark": p.equity_benchmark, "assets": 0.0, "futures": 0.0})
            bucket["futures" if p.asset_type == "equity_future" else "assets"] += equity
        rows.append({**p.model_dump(mode="json", by_alias=True), "baseValue": value, "equityExposure": equity, "ratePnlPerBpBase": rate, "resolvedRatePnlPerBp": rate_input, "rateInputBasis": rate_basis, "gaps": missing, "references": refs[:10]})
    values_complete = all(r["baseValue"] is not None for r in rows)
    known_value = sum(r["baseValue"] or 0 for r in rows)
    nav = known_value if values_complete else None
    accounts = sorted({p.account for p in snapshot.holdings})
    allocations = {a.account: a.amount for a in snapshot.outflow_allocations}
    unallocated_outflow = max(0, snapshot.near_term_outflow - sum(allocations.values()))
    cash_by_account = {}
    for account in accounts:
        cash = [r for r in rows if r["account"] == account and r["assetType"] == "cash"]
        cash_by_account[account] = sum(r["availableCash"] * (1 if r["currency"] == snapshot.base_currency else r["fxToBase"]) for r in cash) if cash and all(r["availableCash"] is not None and r["baseValue"] is not None for r in cash) else None
    scenarios = []
    assumptions = [("权益下跌，利率上行", -10, 50), ("权益上涨，利率下行", 10, -50), ("权益下跌，利率下行", -10, -50)]
    assumptions += [(f'自定义 · {s.label}', s.equity_shock_pct, s.rate_shock_bp) for s in snapshot.additional_scenarios]
    for label, stock_shock, rate_bp in assumptions:
        known_assets = known_futures = 0.0
        futures_losses: dict[str, float] = defaultdict(float)
        incomplete_accounts = set()
        complete = True
        contributions = []
        for row_index, row in enumerate(rows):
            eq, rate = row["equityExposure"], row["ratePnlPerBpBase"]
            future = row["assetType"].endswith("future")
            pnl = eq * stock_shock / 100 + rate * rate_bp if eq is not None and rate is not None else None
            contributions.append({'rowIndex': row_index, 'pnl': pnl,
                                  'futuresLossDemand': max(0, -pnl) if future and pnl is not None else None})
            if eq is None or rate is None:
                complete = False
                if future:
                    incomplete_accounts.add(row["account"])
                continue
            if future:
                known_futures += pnl
                # Do not assume offsets or instant cash transfers across contracts/accounts.
                futures_losses[row["account"]] += max(0, -pnl)
            else:
                known_assets += pnl
        total = known_assets + known_futures if complete else None
        stress_nav = nav + total if nav is not None and total is not None else None
        cash_rows = [{"account": a, "available": c, "futuresLossDemand": None if a in incomplete_accounts else futures_losses[a], "reservedOutflow": allocations.get(a, 0), "remaining": c - futures_losses[a] - allocations.get(a, 0) if c is not None and a not in incomplete_accounts else None} for a, c in cash_by_account.items()]
        cash_after_needs = sum(c['remaining'] for c in cash_rows) - unallocated_outflow if all(c['remaining'] is not None for c in cash_rows) else None
        scenarios.append({"contributions": contributions, "label": label, "equityShockPct": stock_shock, "rateShockBp": rate_bp, "knownAssetPnl": known_assets, "knownFuturesPnl": known_futures, "totalPnl": total, "stressNav": stress_nav, "floorHeadroom": stress_nav - snapshot.nav_floor if stress_nav is not None and snapshot.nav_floor is not None else None, "cashByAccount": cash_rows, "cashAfterKnownNeeds": cash_after_needs})
    liquidity_plan = compile_liquidity_plan(rows, snapshot.as_of, snapshot.cash_need_date, snapshot.base_currency, scenarios)
    unverified_plans = sum(item['status'] in {'incomplete', 'reconcile', 'no_deadline', 'account_unverified'} for item in liquidity_plan['items'])
    if unverified_plans:
        gaps.append(f'{unverified_plans} 项预计到账计划待核对，未改变当前现金测算；详见资金到账计划')
    aged = (date.today() - snapshot.as_of).days > 4
    if aged:
        gaps.append("持仓快照已超过 4 个自然日；仅供历史参考，不作为当前安全判断")
    missing_cash = [a for a, c in cash_by_account.items() if c is None]
    if missing_cash:
        gaps.append("账户可用现金未完整提供：" + "、".join(missing_cash))
    undated_rates = sum(p.asset_type in {'bond', 'fund', 'bond_future'} and p.rate_pnl_per_bp is not None and p.rate_as_of is None for p in snapshot.holdings)
    if undated_rates:
        gaps.append(f'{undated_rates} 项直接导入的利率参数未注明日期；当前按输入值测算，尚未核验时点，详见换算依据')
    thresholds = compile_nav_thresholds(nav, scenarios, snapshot.nav_warning_floor, snapshot.nav_floor)
    alerts = lifecycle_alerts
    for item in thresholds['rows']:
        if item['status'] == 'warning':
            floor_note = '尚未设定底线' if snapshot.nav_floor is None else '尚未触及底线'
            alerts.append(f"{item['label']}：触及或低于设定预警线，{floor_note}；须复核，不自动交易")
        elif item['status'] == 'floor_reached':
            alerts.append(f"{item['label']}：恰好触及设定底线，余量为零；须优先复核，不自动交易")
    if nav is not None and snapshot.nav_floor is not None and nav < snapshot.nav_floor:
        alerts.append('持仓快照净值已低于设定底线，尚未施加情景冲击')
    for s in scenarios:
        if s['cashAfterKnownNeeds'] is not None and s['cashAfterKnownNeeds'] < 0 and snapshot.near_term_outflow > 0:
            alerts.append(f"{s['label']}：现金汇总不足以覆盖估算期货亏损及近期需留资金")
        if s["floorHeadroom"] is not None and s["floorHeadroom"] < 0:
            alerts.append(f"{s['label']}：简化情景净值跌破设定底线")
        for c in s["cashByAccount"]:
            if c["remaining"] is not None and c["remaining"] < 0:
                alerts.append(f"{s['label']}：{c['account']} 可用现金不足以覆盖估算期货亏损及账户预留")
    for r in rows:
        for ref in r["references"]:
            if ref.get("status") in {"stale", "invalidated"}:
                alerts.append(f"{r['name']}：上游研究{ref.get('title', '')}已过期或论点失效，需回原模块复核")
    issuer_exposure = compile_issuer_exposure(rows, nav)
    if issuer_exposure['unmatched']:
        gaps.append(f"{len(issuer_exposure['unmatched'])} 行股票/债券未能明确归属发行人；发行人集中度尚不完整")
    for item in issuer_exposure['items']:
        if item['crossAsset']:
            alerts.append(f"{item['issuer']}：同时持有其股票与债券，需关注同一主体风险；指数及国债期货不能视为其信用风险对冲")
    # Concentration is by asset identity, not by import row or account.
    groups = {}
    for r in rows:
        if r["assetType"] in {"cash", "liability", "equity_future", "bond_future"}:
            continue
        key = (r["assetType"], r["market"], r["symbol"], r["currency"])
        g = groups.setdefault(key, {"name": r["name"], "symbol": r["symbol"], "value": 0.0, "known": True})
        g["value"] += r["baseValue"] or 0
        g["known"] = g["known"] and r["baseValue"] is not None
    gross = sum(g["value"] for g in groups.values()) if all(g["known"] for g in groups.values()) else None
    concentrations = [{"name": g["name"], "symbol": g["symbol"], "baseValue": g["value"] if g["known"] else None, "weightPct": g["value"] / gross * 100 if gross else None} for g in groups.values()]
    rate_assets = sum(r['ratePnlPerBpBase'] or 0 for r in rows if not r['assetType'].endswith('future'))
    rate_futures = sum(r['ratePnlPerBpBase'] or 0 for r in rows if r['assetType'].endswith('future'))
    rate_buckets = []
    rate_rows = [r for r in rows if r['assetType'] in {'fund', 'bond', 'bond_future'}]
    for currency in sorted({r['currency'] for r in rate_rows}):
        members = [r for r in rate_rows if r['currency'] == currency]
        assets = sum(r['ratePnlPerBpBase'] or 0 for r in members if r['assetType'] != 'bond_future')
        futures = sum(r['ratePnlPerBpBase'] or 0 for r in members if r['assetType'] == 'bond_future')
        rate_buckets.append({'currency': currency, 'assets': assets, 'futures': futures, 'net': assets + futures if all(r['ratePnlPerBpBase'] is not None for r in members) else None})
    report = {"method": "snapshot-linear-diagnosis-v9", "asOf": str(snapshot.as_of), "baseCurrency": snapshot.base_currency, "nav": nav, "knownBookValue": known_value, "navFloor": snapshot.nav_floor, "navHeadroom": nav - snapshot.nav_floor if nav is not None and snapshot.nav_floor is not None else None, "nearTermOutflow": snapshot.near_term_outflow, "unallocatedOutflow": unallocated_outflow, "coverage": {"total": len(rows), "valued": sum(r["baseValue"] is not None for r in rows), "sensitivity": sum(r["equityExposure"] is not None and r["ratePnlPerBpBase"] is not None for r in rows)}, "status": "历史参考" if aged else "需要关注" if alerts else "待补证据" if gaps else "简化测算完成", "alerts": alerts, "gaps": gaps, "rows": rows, "equityHedges": [{**b, "net": b["assets"] + b["futures"]} for b in exposures.values()], "rateBuckets": rate_buckets, "rateHedge": {"knownAssets": rate_assets, "knownFutures": rate_futures, "net": rate_assets + rate_futures if all(r['ratePnlPerBpBase'] is not None for r in rows) else None}, "issuerExposure": issuer_exposure, "liquidityPlan": liquidity_plan, "concentrations": sorted(concentrations, key=lambda r: -(r["baseValue"] or 0)), "scenarios": scenarios, "limitations": ["账面金额来自导入资料，未连接券商对账；期货名义金额不计入净资产，保证金不可重复记入现金。", "仅作权益与平行利率冲击的一阶测算，不含信用利差、违约、汇率冲击、基差、非线性和保证金比例上调。", "期货亏损按账户内各合约亏损加总，未假设盈利抵销或跨账户即时调拨；不是券商追保通知。账户已分配的近期预留单独扣除；剩余未分配金额在组合层面另扣，不假设跨账户调拨。", "基金尚未自动穿透；导入敏感度需来自有日期的研究或可靠估算，缺少值不能填零。上游档案存在不代表风险研究完整。"]}
    report['navWarningFloor'] = snapshot.nav_warning_floor
    report['navThresholds'] = thresholds
    report['conclusion'] = compile_conclusion(report)
    return report
