"""同步并汇总 FOF 公开披露的底层基金持仓。"""

import json
import math
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class FundFofHoldingService:
    SOURCE = "eastmoney.fundmobapi.fof_holdings"
    ENDPOINT = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition"
    SCOPE = "仅展示公开接口返回的底层基金持仓，不代表 FOF 全部组合。"
    MIN_DISCLOSED_FUNDS = 5
    MIN_DISCLOSED_NAV_RATIO = 20.0
    MIN_CLASSIFIED_NAV_COVERAGE = 0.6
    CONCENTRATION_STYLE_LABELS = {
        "高集中": "底层高集中",
        "中等集中": "底层中等集中",
        "较分散": "底层较分散",
    }
    CLASSIFICATION_STYLE_LABELS = {
        "权益类": "底层权益基金主导",
        "固收类": "底层固收基金主导",
        "混合类": "底层混合基金主导",
        "货币类": "底层货币基金主导",
        "FOF类": "底层 FOF 主导",
        "跨市场/QDII": "底层跨市场基金主导",
        "REITs": "底层 REITs 主导",
        "商品类": "底层商品基金主导",
        "指数类": "底层指数基金主导",
    }

    def __init__(
        self,
        repo: Optional[Any] = None,
        opener=urlopen,
        classification_repo: Optional[Any] = None,
    ):
        if repo is None:
            from repositories import get_fund_classification_repo, get_fund_underlying_holding_repo

            repo = get_fund_underlying_holding_repo()
            classification_repo = classification_repo or get_fund_classification_repo()
        self.repo = repo
        self.opener = opener
        self.classification_repo = classification_repo

    def get(self, wind_code: str, limit: int = 8, refresh: bool = False) -> Dict[str, Any]:
        sync_result = self.sync(wind_code) if refresh else None
        rows = self.repo.list_latest_periods(wind_code, limit=limit)
        if not rows:
            return {
                "wind_code": wind_code,
                "status": "unavailable",
                "latest": None,
                "history": [],
                "professional_profile": self._professional_profile([]),
                "evidence_gate": self._evidence_gate([]),
                "source": self.SOURCE,
                "source_url": self._source_url(wind_code),
                "scope": self.SCOPE,
                "missing_items": (sync_result or {}).get("missing_items")
                or ["本地尚无 FOF 底层基金持仓，请先执行同步"],
            }

        history = self._summarize(rows)
        latest = history[0]
        latest["holdings"] = self._enrich_classifications(
            latest.get("holdings") or [],
            self._classification_map(latest.get("holdings") or []),
        )
        for period in history[1:]:
            period["holdings"] = []
        evidence_gate = self._evidence_gate(latest.get("holdings") or [])
        return {
            "wind_code": wind_code,
            "status": "available",
            "latest": latest,
            "history": history,
            "professional_profile": self._professional_profile(latest.get("holdings") or []),
            "evidence_gate": evidence_gate,
            "source": latest.get("source") or self.SOURCE,
            "source_url": latest.get("source_url") or self._source_url(wind_code),
            "scope": self.SCOPE,
            "missing_items": evidence_gate.get("missing_items") or [],
        }

    def sync(self, wind_code: str) -> Dict[str, Any]:
        try:
            rows = self.fetch(wind_code)
            written = self.repo.replace_period(wind_code, rows)
            return {
                "status": "synced",
                "wind_code": wind_code,
                "records": written,
                "latest_report_date": rows[0]["report_date"],
                "source": self.SOURCE,
                "source_url": self._source_url(wind_code),
                "missing_items": [],
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "wind_code": wind_code,
                "records": 0,
                "source": self.SOURCE,
                "source_url": self._source_url(wind_code),
                "missing_items": [str(exc) or "FOF 底层基金持仓同步失败"],
            }

    @classmethod
    def professional_profiles_from_rows(
        cls,
        rows_map: Dict[str, List[Dict[str, Any]]],
        classification_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        classification_map = classification_map or {}
        return {
            wind_code: cls.profile_from_snapshot({
                "status": "available",
                "latest": {
                    **cls._summarize(rows)[0],
                    "holdings": cls._enrich_classifications(
                        cls._summarize(rows)[0].get("holdings") or [],
                        classification_map,
                    ),
                } if rows else None,
                "source": (rows[0] or {}).get("source") if rows else cls.SOURCE,
            })
            for wind_code, rows in rows_map.items()
            if rows
        }

    @classmethod
    def profile_from_snapshot(cls, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        latest = snapshot.get("latest") or {}
        holdings = latest.get("holdings") or []
        professional = cls._professional_profile(holdings)
        gate = cls._evidence_gate(holdings)
        return {
            **professional,
            "status": "available" if holdings else "unavailable",
            "report_date": latest.get("report_date"),
            "evidence_gate": gate,
            "source": snapshot.get("source") or latest.get("source") or cls.SOURCE,
            "scope": snapshot.get("scope") or cls.SCOPE,
        }

    @classmethod
    def style_evidence(cls, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        gate = profile.get("evidence_gate") or {}
        if profile.get("status") != "available" or gate.get("status") != "sufficient":
            return []
        evidence: List[Dict[str, Any]] = []
        concentration_label = cls.CONCENTRATION_STYLE_LABELS.get(
            str(profile.get("concentration_label") or "")
        )
        if concentration_label:
            evidence.append({
            "value": concentration_label,
            "status": "quantitative",
            "source": "public_fof_underlying_holdings",
            "basis": (
                f"{profile.get('report_date') or '最新披露'} · "
                f"公开底层基金 {int(profile.get('disclosed_fund_count') or 0)} 只 · "
                f"占净值 {float(profile.get('disclosed_nav_ratio') or 0):.2f}% · "
                f"前 5 大占净值 {float(profile.get('top5_nav_ratio') or 0):.2f}%"
            ),
            "report_date": profile.get("report_date"),
            "disclosed_fund_count": int(profile.get("disclosed_fund_count") or 0),
            "disclosed_nav_ratio": float(profile.get("disclosed_nav_ratio") or 0),
            "top5_nav_ratio": float(profile.get("top5_nav_ratio") or 0),
            "data_source": profile.get("source") or cls.SOURCE,
            "caveat": cls.SCOPE,
            })
        classification_label = str(profile.get("classification_style_label") or "")
        if classification_label:
            evidence.append({
                "value": classification_label,
                "status": "quantitative",
                "source": "public_fof_underlying_classification",
                "basis": (
                    f"{profile.get('report_date') or '最新披露'} · "
                    f"底层基金分类权重覆盖 "
                    f"{float(profile.get('classification_coverage') or 0) * 100:.1f}% · "
                    f"主导类别 {profile.get('dominant_classification') or '待确认'}"
                ),
                "report_date": profile.get("report_date"),
                "classification_coverage": float(profile.get("classification_coverage") or 0),
                "classification_distribution": profile.get("classification_distribution") or [],
                "data_source": "standardized_fund_classification+registered_fund_type+eastmoney.fof_holdings",
                "caveat": "标准同类组优先；缺失时只按数据库登记类型做宽分类，未分类部分保留为未知。",
            })
        return evidence

    def fetch(self, wind_code: str) -> List[Dict[str, Any]]:
        source_url = self._source_url(wind_code)
        request = Request(
            source_url,
            headers={
                "User-Agent": "Mozilla/5.0 FundResearch/1.0",
                "Referer": f"https://fund.eastmoney.com/{self._fund_code(wind_code)}.html",
            },
        )
        timeout = max(3, min(int(os.environ.get("FUND_PUBLIC_DATA_TIMEOUT_SECONDS", "12")), 30))
        with self.opener(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
        return self.parse_payload(payload, source_url=source_url)

    def _classification_map(self, holdings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if self.classification_repo is None:
            return {}
        codes = list(dict.fromkeys(
            str(item.get("underlying_fund_code") or "").strip()
            for item in holdings
            if str(item.get("underlying_fund_code") or "").strip()
        ))
        return self.build_classification_map(self.classification_repo, codes)

    @classmethod
    def build_classification_map(
        cls,
        classification_repo: Any,
        codes: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        normalized_codes = list(dict.fromkeys(
            str(code or "").strip().upper()
            for code in codes
            if str(code or "").strip()
        ))
        if not normalized_codes or classification_repo is None:
            return {}

        peer_loader = getattr(classification_repo, "list_fund_peer_group_map", None)
        identity_loader = getattr(classification_repo, "list_fund_identity_map", None)
        peer_map = peer_loader(normalized_codes) if callable(peer_loader) else {}
        identity_map = identity_loader(normalized_codes) if callable(identity_loader) else {}
        result: Dict[str, Dict[str, Any]] = {}
        for code in normalized_codes:
            peer = peer_map.get(code) or {}
            identity = identity_map.get(code) or {}
            if peer:
                result[code] = {
                    **identity,
                    **peer,
                    "classification_level": "standardized_peer_group",
                    "classification_label": peer.get("peer_group_name"),
                    "classification_basis_field": "peer_group_members.peer_group_id",
                    "classification_basis_value": peer.get("peer_group_id"),
                }
                continue
            if not identity:
                continue
            fallback = cls._registered_type_fallback(identity)
            result[code] = {
                **identity,
                **fallback,
                "classification_level": (
                    "registered_type" if fallback.get("asset_class") else "identity_only"
                ),
                "classification_label": (
                    f"登记类型宽分类：{cls._classification_bucket(fallback)}"
                    if fallback.get("asset_class") else None
                ),
            }
        return result

    @classmethod
    def _enrich_classifications(
        cls,
        holdings: List[Dict[str, Any]],
        classification_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        enriched = []
        for holding in holdings:
            code = str(holding.get("underlying_fund_code") or "").strip()
            classification = classification_map.get(code) or {}
            classification_level = str(classification.get("classification_level") or "")
            if classification.get("peer_group_id"):
                classification_status = "standardized"
            elif classification.get("asset_class"):
                classification_status = "registered_type"
            elif classification.get("wind_code"):
                classification_status = "identity_only"
            else:
                classification_status = "unmatched"
            enriched.append({
                **holding,
                "classification_status": classification_status,
                "classification_level": classification_level or None,
                "matched_fund_code": classification.get("wind_code"),
                "asset_class": classification.get("asset_class"),
                "strategy_family_key": classification.get("strategy_family_key"),
                "strategy_family_name": classification.get("strategy_family_name"),
                "peer_group_id": classification.get("peer_group_id"),
                "peer_group_name": classification.get("peer_group_name"),
                "classification_label": classification.get("classification_label"),
                "classification_source": classification.get("source"),
                "registered_fund_type": classification.get("registered_fund_type"),
                "contract_type": classification.get("contract_type"),
                "invest_type": classification.get("invest_type"),
                "classification_basis_field": classification.get("classification_basis_field"),
                "classification_basis_value": classification.get("classification_basis_value"),
            })
        return enriched

    @classmethod
    def parse_payload(cls, payload: Any, source_url: str = "") -> List[Dict[str, Any]]:
        data = json.loads(payload) if isinstance(payload, str) else payload
        if not isinstance(data, dict) or data.get("ErrCode") not in {0, "0", None}:
            raise ValueError(str((data or {}).get("ErrMsg") or "FOF 公开接口返回失败"))
        report_date = str(data.get("Expansion") or "").strip()
        holdings = ((data.get("Datas") or {}).get("fundfofs") or [])
        if not report_date or not holdings:
            raise ValueError("公开披露中未找到 FOF 底层基金持仓")

        rows = []
        for sequence, item in enumerate(holdings, start=1):
            raw_code = str(item.get("TZJJDM") or "").strip().upper()
            name = str(item.get("TZJJMC") or "").strip()
            if not raw_code or not name:
                continue
            code = raw_code if "." in raw_code else f"{raw_code}.OF"
            rows.append({
                "report_date": report_date,
                "sequence": sequence,
                "underlying_fund_code": code,
                "underlying_fund_name": name,
                "nav_ratio": cls._number(item.get("ZJZBL")),
                "daily_return": cls._number(item.get("RZDF")),
                "source": cls.SOURCE,
                "source_url": source_url,
            })
        if not rows:
            raise ValueError("公开披露中未找到有效的 FOF 底层基金持仓")
        return rows

    @classmethod
    def _summarize(cls, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("report_date") or "")[:10]].append(dict(row))
        periods = []
        for report_date in sorted(grouped, reverse=True):
            holdings = sorted(grouped[report_date], key=lambda item: (item.get("sequence") or 9999))
            periods.append({
                "report_date": report_date,
                "holding_count": len(holdings),
                "disclosed_nav_ratio": round(sum(float(item.get("nav_ratio") or 0) for item in holdings), 4),
                "holdings": holdings,
                "source": holdings[0].get("source"),
                "source_url": holdings[0].get("source_url"),
                "fetched_at": holdings[0].get("fetched_at"),
            })
        return periods

    @classmethod
    def _professional_profile(cls, holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        weights = sorted((float(item.get("nav_ratio") or 0) for item in holdings), reverse=True)
        total = sum(weights)
        top5 = sum(weights[:5])
        if top5 >= 35:
            concentration = "高集中"
        elif top5 >= 20:
            concentration = "中等集中"
        else:
            concentration = "较分散"
        classification_profile = cls._classification_profile(holdings)
        return {
            "disclosed_fund_count": len(holdings),
            "disclosed_nav_ratio": round(total, 4),
            "top5_nav_ratio": round(top5, 4),
            "largest_nav_ratio": round(weights[0], 4) if weights else None,
            "concentration_label": concentration if weights else None,
            **classification_profile,
            "double_fee_status": "incomplete_public_evidence",
            "boundary": "公开底层基金只用于穿透和集中度解释；未取得全部底层费率前，不宣称完整双层费用。",
        }

    @classmethod
    def _classification_profile(cls, holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        disclosed_total = sum(float(item.get("nav_ratio") or 0) for item in holdings)
        bucket_weights: Dict[str, float] = defaultdict(float)
        classified_weight = 0.0
        classified_count = 0
        standardized_count = 0
        registered_type_count = 0
        for holding in holdings:
            bucket = cls._classification_bucket(holding)
            if not bucket:
                continue
            weight = float(holding.get("nav_ratio") or 0)
            bucket_weights[bucket] += weight
            classified_weight += weight
            classified_count += 1
            if holding.get("peer_group_id"):
                standardized_count += 1
            elif holding.get("classification_status") == "registered_type":
                registered_type_count += 1
        unknown_weight = max(0.0, disclosed_total - classified_weight)
        distribution = [
            {
                "category": category,
                "nav_ratio": round(weight, 4),
                "share_of_disclosed": round(weight / disclosed_total, 6) if disclosed_total else 0.0,
            }
            for category, weight in sorted(bucket_weights.items(), key=lambda item: (-item[1], item[0]))
        ]
        if unknown_weight > 0:
            distribution.append({
                "category": "未分类",
                "nav_ratio": round(unknown_weight, 4),
                "share_of_disclosed": round(unknown_weight / disclosed_total, 6) if disclosed_total else 0.0,
            })
        coverage = classified_weight / disclosed_total if disclosed_total else 0.0
        dominant = max(bucket_weights.items(), key=lambda item: item[1], default=(None, 0.0))
        dominant_share = dominant[1] / classified_weight if classified_weight else 0.0
        style_label = (
            cls.CLASSIFICATION_STYLE_LABELS.get(str(dominant[0] or ""))
            if coverage >= cls.MIN_CLASSIFIED_NAV_COVERAGE and dominant_share >= 0.5
            else None
        )
        return {
            "style_distribution_status": (
                "available" if coverage >= cls.MIN_CLASSIFIED_NAV_COVERAGE
                else "insufficient_classification_coverage"
            ),
            "classified_fund_count": classified_count,
            "standardized_classified_fund_count": standardized_count,
            "registered_type_classified_fund_count": registered_type_count,
            "classified_nav_ratio": round(classified_weight, 4),
            "classification_coverage": round(coverage, 6),
            "classification_distribution": distribution,
            "dominant_classification": dominant[0],
            "dominant_classification_share": round(dominant_share, 6),
            "classification_style_label": style_label,
            "classification_boundary": "标准同类组优先，缺失时仅按数据库登记类型做宽分类；这不等同于完整资产配置穿透。",
        }

    @staticmethod
    def _classification_bucket(holding: Dict[str, Any]) -> Optional[str]:
        asset_class = str(holding.get("asset_class") or "").strip()
        strategy_family = str(holding.get("strategy_family_key") or "").strip()
        if asset_class == "global" or strategy_family in {
            "qdii_global_theme", "active_equity_cross_market",
        }:
            return "跨市场/QDII"
        return {
            "equity": "权益类",
            "index": "权益类",
            "fixed_income": "固收类",
            "multi_asset": "混合类",
            "money_market": "货币类",
            "fof": "FOF类",
            "cross_market": "跨市场/QDII",
            "reit": "REITs",
            "commodities": "商品类",
            "index_generic": "指数类",
        }.get(asset_class)

    @classmethod
    def _registered_type_fallback(cls, identity: Dict[str, Any]) -> Dict[str, Any]:
        fields = [
            ("funds.type", str(identity.get("registered_fund_type") or "").strip()),
            ("funds.raw_data.universe.contract_type", str(identity.get("contract_type") or "").strip()),
            ("funds.raw_data.universe.invest_type", str(identity.get("invest_type") or "").strip()),
            ("funds.raw_data.universe.fund_type_raw", str(identity.get("raw_fund_type") or "").strip()),
        ]

        def matched(terms: tuple[str, ...]) -> Optional[tuple[str, str]]:
            for field, value in fields:
                upper_value = value.upper()
                if value and any(term.upper() in upper_value for term in terms):
                    return field, value
            return None

        special_rules = (
            (("FOF", "基金中基金", "养老目标"), "fof"),
            (("QDII", "海外基金"), "cross_market"),
            (("REIT", "基础设施基金"), "reit"),
            (("商品", "期货", "黄金", "白银", "原油", "豆粕", "农产品"), "commodities"),
        )
        for terms, asset_class in special_rules:
            basis = matched(terms)
            if basis:
                return {
                    "asset_class": asset_class,
                    "source": basis[0],
                    "classification_basis_field": basis[0],
                    "classification_basis_value": basis[1],
                }

        fund_type = fields[0][1]
        ordered_fields = fields[1:] + fields[:1] if "指数" in fund_type else fields
        broad_rules = (
            (("货币", "现金管理"), "money_market"),
            (("债券", "固收", "纯债"), "fixed_income"),
            (("股票", "权益"), "equity"),
            (("混合", "多资产"), "multi_asset"),
        )
        for field, value in ordered_fields:
            upper_value = value.upper()
            for terms, asset_class in broad_rules:
                if value and any(term.upper() in upper_value for term in terms):
                    return {
                        "asset_class": asset_class,
                        "source": field,
                        "classification_basis_field": field,
                        "classification_basis_value": value,
                    }

        index_basis = matched(("指数", "ETF", "LOF"))
        if index_basis:
            return {
                "asset_class": "index_generic",
                "source": index_basis[0],
                "classification_basis_field": index_basis[0],
                "classification_basis_value": index_basis[1],
            }
        return {
            "asset_class": None,
            "source": identity.get("identity_source") or "funds",
            "classification_basis_field": None,
            "classification_basis_value": None,
        }

    @classmethod
    def _evidence_gate(cls, holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        count = len(holdings)
        coverage = sum(float(item.get("nav_ratio") or 0) for item in holdings)
        missing = []
        if count < cls.MIN_DISCLOSED_FUNDS:
            missing.append(f"公开底层基金仅 {count} 只，至少需要 {cls.MIN_DISCLOSED_FUNDS} 只")
        if coverage < cls.MIN_DISCLOSED_NAV_RATIO:
            missing.append(
                f"公开底层基金占净值 {coverage:.2f}%，至少需要 {cls.MIN_DISCLOSED_NAV_RATIO:.0f}%"
            )
        return {
            "status": "sufficient" if not missing else "insufficient_evidence",
            "minimum_disclosed_funds": cls.MIN_DISCLOSED_FUNDS,
            "minimum_disclosed_nav_ratio": cls.MIN_DISCLOSED_NAV_RATIO,
            "disclosed_fund_count": count,
            "disclosed_nav_ratio": round(coverage, 4),
            "missing_items": missing,
            "included_in_score": False,
            "role": "FOF 综合评价的前置证据门槛",
        }

    @classmethod
    def _source_url(cls, wind_code: str) -> str:
        return f"{cls.ENDPOINT}?{urlencode({'FCODE': cls._fund_code(wind_code), 'deviceid': '123', 'plat': 'Android', 'product': 'EFund', 'version': '6.3.8'})}"

    @staticmethod
    def _fund_code(wind_code: str) -> str:
        return str(wind_code or "").strip().upper().split(".", 1)[0]

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None
