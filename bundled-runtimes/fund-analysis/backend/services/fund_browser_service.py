"""普通用户基金浏览器 Module。"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from services.fund_research_snapshot_service import FundResearchSnapshotService
from services.professional_scoring_service import ProfessionalScoringService


class FundBrowserService:
    """用一个窄 Interface 输出基础基金研究列表。"""

    def browse(
        self,
        keyword: Optional[str] = None,
        peer_group: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
        asset_min: Optional[float] = None,
        min_age_years: Optional[int] = None,
        min_manager_years: Optional[float] = None,
        return_6m_min: Optional[float] = None,
        return_1y_min: Optional[float] = None,
        return_3y_min: Optional[float] = None,
        max_drawdown_1y_max: Optional[float] = None,
        sharpe_1y_min: Optional[float] = None,
        style_tags: Optional[List[str]] = None,
        style_match: str = "any",
        availability: str = "evaluated",
        sort_by: str = "quality",
    ) -> Dict[str, Any]:
        from repositories import (
            get_fund_classification_repo,
            get_fund_repo,
            get_manager_repo,
            get_metric_snapshot_repo,
            get_research_profile_repo,
        )

        classification_repo = get_fund_classification_repo()
        normalized_availability = str(availability or "evaluated").strip().lower()
        if normalized_availability not in {"evaluated", "classified", "all"}:
            normalized_availability = "evaluated"
        normalized_style_tags = list(dict.fromkeys(
            str(tag or "").strip() for tag in (style_tags or []) if str(tag or "").strip()
        ))
        normalized_style_match = "all" if str(style_match or "any").strip().lower() == "all" else "any"
        if peer_group:
            filters = {
                "asset_min": asset_min,
                "min_age_years": min_age_years,
                "min_manager_years": min_manager_years,
                "return_6m_min": return_6m_min,
                "return_1y_min": return_1y_min,
                "return_3y_min": return_3y_min,
                "max_drawdown_1y_max": max_drawdown_1y_max,
                "sharpe_1y_min": sharpe_1y_min,
                "style_tags": normalized_style_tags,
                "style_match": normalized_style_match,
            }
            rows = classification_repo.list_recommendation_funds(
                peer_group,
                limit=page_size,
                keyword=keyword,
                offset=max(0, page - 1) * page_size,
                sort_by=sort_by,
                availability=normalized_availability,
                **filters,
            )
            total = classification_repo.count_recommendation_funds(
                peer_group,
                keyword=keyword,
                availability=normalized_availability,
                **filters,
            )
            source = "standardized_peer_group_universe"
            style_tag_catalog = classification_repo.get_style_tag_catalog(
                peer_group,
                availability=normalized_availability,
            )
        else:
            rows, total = get_fund_repo().browse_funds(
                keyword=keyword,
                page=page,
                page_size=page_size,
                availability=normalized_availability,
            )
            source = {
                "evaluated": "evaluated_fund_universe",
                "classified": "standardized_classified_universe",
                "all": "fund_database",
            }[normalized_availability]
            style_tag_catalog = classification_repo.empty_style_tag_catalog("")

        selection_context = self._selection_context(
            keyword=keyword,
            peer_group=peer_group,
            availability=normalized_availability,
            sort_by=sort_by,
            asset_min=asset_min,
            min_age_years=min_age_years,
            min_manager_years=min_manager_years,
            return_6m_min=return_6m_min,
            return_1y_min=return_1y_min,
            return_3y_min=return_3y_min,
            max_drawdown_1y_max=max_drawdown_1y_max,
            sharpe_1y_min=sharpe_1y_min,
            style_tags=normalized_style_tags,
            style_match=normalized_style_match,
        )
        enriched_funds = self.enrich_rows(rows)
        funds = [
            self._attach_selection_explanation(fund, row, selection_context)
            for fund, row in zip(enriched_funds, rows)
        ]

        return {
            "funds": funds,
            "total": total,
            "page": page,
            "page_size": page_size,
            "peer_group": peer_group,
            "availability": normalized_availability,
            "sort_by": sort_by,
            "source": source,
            "selection_context": selection_context,
            "style_tag_catalog": style_tag_catalog,
            "product_scope": {
                "fund_browser": "core",
                "fund_classification": "core",
                "fund_evaluation": "core",
                "investment_decision": "excluded",
            },
        }

    def enrich_rows(self, rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        from repositories import (
            get_fund_classification_repo,
            get_manager_repo,
            get_metric_snapshot_repo,
            get_research_profile_repo,
        )

        classification_repo = get_fund_classification_repo()
        codes = [str(row.get("wind_code") or "") for row in rows if row.get("wind_code")]
        profiles = get_research_profile_repo().list_profiles(codes)
        peer_groups = classification_repo.list_fund_peer_group_map(codes)
        panels = get_metric_snapshot_repo().get_latest_panels("fund", codes)
        manager_ids = [
            manager_id
            for row in rows
            for manager_id in (row.get("manager_ids") or [])
            if manager_id
        ]
        manager_map = get_manager_repo().get_managers_by_ids(manager_ids)
        scoring_service = ProfessionalScoringService()

        funds = []
        for row in rows:
            code = str(row.get("wind_code") or "")
            peer = peer_groups.get(code) or {}
            profile = {
                **(profiles.get(code) or {}),
                "peer_group": peer.get("peer_group_name") or row.get("standardized_peer_group_name") or (profiles.get(code) or {}).get("peer_group"),
                "peer_group_id": peer.get("peer_group_id") or row.get("standardized_peer_group_id"),
                "peer_group_key": peer.get("peer_group_key") or row.get("standardized_peer_group_key"),
                "classification_confidence": peer.get("confidence"),
                "classification_source": peer.get("source"),
            }
            style_tag_evidence = self._style_tag_evidence(row)
            profile["filter_style_tags"] = list(dict.fromkeys(
                item["value"] for item in style_tag_evidence if item.get("value")
            ))
            profile["style_tag_evidence"] = style_tag_evidence
            managers = [
                self._manager(manager_map[manager_id])
                for manager_id in (row.get("manager_ids") or [])
                if manager_id in manager_map
            ]
            try:
                classification_context = self._classification_context_from_row(row, peer)
                if classification_context is None:
                    classification_context = classification_repo.get_classification_context(code)
                quality = scoring_service.data_quality_service.evaluate_from_inputs(
                    row,
                    profile,
                    panels.get(code, []),
                    classification_context,
                )
                professional_scoring = scoring_service.score_from_inputs(
                    row,
                    profile,
                    panels.get(code, []),
                    quality,
                    classification_context,
                )
            except Exception:
                professional_scoring = None
            evaluation_ready = bool(
                professional_scoring
                and professional_scoring.get("status") in {"ok", "partial"}
                and professional_scoring.get("overall_score") is not None
            )
            funds.append({
                **FundResearchSnapshotService.project_fund(row),
                "managers": managers,
                "research_profile": profile,
                "rolling_metrics": FundResearchSnapshotService.project_rolling_metrics(panels.get(code, [])),
                "professional_scoring": professional_scoring,
                "classification_ready": bool(profile.get("peer_group_id") or profile.get("peer_group_key")),
                "evaluation_ready": evaluation_ready,
            })

        return funds

    @classmethod
    def _selection_context(
        cls,
        keyword: Optional[str],
        peer_group: Optional[str],
        availability: str,
        sort_by: str,
        asset_min: Optional[float],
        min_age_years: Optional[int],
        min_manager_years: Optional[float],
        return_6m_min: Optional[float],
        return_1y_min: Optional[float],
        return_3y_min: Optional[float],
        max_drawdown_1y_max: Optional[float],
        sharpe_1y_min: Optional[float],
        style_tags: Optional[List[str]],
        style_match: str,
    ) -> Dict[str, Any]:
        rules: List[Dict[str, Any]] = []

        def add_rule(key: str, label: str, operator: str, threshold: Any, unit: str, text: str) -> None:
            rules.append({
                "key": key,
                "label": label,
                "operator": operator,
                "threshold": threshold,
                "unit": unit,
                "text": text,
            })

        normalized_keyword = str(keyword or "").strip()
        normalized_group = str(peer_group or "").strip()
        if normalized_group:
            add_rule("peer_group", "专业类别", "equals", normalized_group, "text", f"专业类别为“{normalized_group}”")
        if normalized_keyword:
            add_rule("keyword", "名称或代码", "contains", normalized_keyword, "text", f"名称或代码包含“{normalized_keyword}”")
        if asset_min is not None:
            add_rule("asset_min", "基金规模", "gte", float(asset_min), "cny_100m", f"基金规模不少于 {float(asset_min):g} 亿元")
        if min_age_years is not None:
            add_rule("min_age_years", "成立年限", "gte", int(min_age_years), "years", f"成立至少 {int(min_age_years)} 年")
        if min_manager_years is not None:
            add_rule("min_manager_years", "经理管理年限", "gte", float(min_manager_years), "years", f"至少一位现任经理管理年限达到 {float(min_manager_years):g} 年")
        for key, label, value in (
            ("return_6m_min", "近 6 月收益", return_6m_min),
            ("return_1y_min", "近 1 年收益", return_1y_min),
            ("return_3y_min", "近 3 年累计收益", return_3y_min),
        ):
            if value is not None:
                add_rule(key, label, "gte", float(value), "ratio", f"{label}不低于 {float(value) * 100:g}%")
        if max_drawdown_1y_max is not None:
            add_rule(
                "max_drawdown_1y_max",
                "近 1 年最大回撤",
                "abs_lte",
                float(max_drawdown_1y_max),
                "ratio",
                f"近 1 年最大回撤不超过 {float(max_drawdown_1y_max) * 100:g}%",
            )
        if sharpe_1y_min is not None:
            add_rule("sharpe_1y_min", "近 1 年 Sharpe", "gte", float(sharpe_1y_min), "number", f"近 1 年 Sharpe 不低于 {float(sharpe_1y_min):g}")
        normalized_style_tags = list(dict.fromkeys(
            str(tag or "").strip() for tag in (style_tags or []) if str(tag or "").strip()
        ))
        if normalized_style_tags:
            normalized_style_match = "all" if str(style_match or "any").strip().lower() == "all" else "any"
            match_label = "全部匹配" if normalized_style_match == "all" else "任一匹配"
            add_rule(
                "style_tags",
                "风格标签",
                normalized_style_match,
                normalized_style_tags,
                "tags",
                f"风格标签{match_label}：{'、'.join(normalized_style_tags)}",
            )

        sort_labels = {
            "quality": "数据较完整优先",
            "multi_period": "多周期同类领先",
            "return": "近 1 年收益较高",
            "return_6m": "近 6 月收益较高",
            "return_1y": "近 1 年收益较高",
            "return_3y": "近 3 年收益较高",
            "drawdown": "回撤较小优先",
            "sharpe": "Sharpe 较高优先",
            "asset": "规模较大优先",
            "history": "成立较早优先",
        }
        availability_labels = {
            "evaluated": "可评价基金库",
            "classified": "已分类基金库",
            "all": "完整基础基金库",
        }
        sort_label = sort_labels.get(str(sort_by or "").strip().lower(), "数据较完整优先")
        scope_label = availability_labels.get(availability, "基金库")
        summary_parts = [f"从{scope_label}中筛选"]
        if normalized_group:
            summary_parts.append(f"先限定在“{normalized_group}”标准同类组")
        if len(rules) > (1 if normalized_group else 0):
            summary_parts.append(f"再核对其余 {len(rules) - (1 if normalized_group else 0)} 项条件")
        summary_parts.append(f"最后按“{sort_label}”排序")
        return {
            "status": "active" if rules else "browse",
            "peer_group": normalized_group or None,
            "availability": availability,
            "availability_label": scope_label,
            "sort_by": sort_by,
            "sort_label": sort_label,
            "rules": rules,
            "style_tags": normalized_style_tags,
            "style_match": "all" if str(style_match or "any").strip().lower() == "all" else "any",
            "summary": "，".join(summary_parts) + "。",
            "boundary": "只在同一标准类别内解释筛选和排序，不进行跨类别优劣比较，也不提供买卖建议。",
        }

    @classmethod
    def _attach_selection_explanation(
        cls,
        fund: Dict[str, Any],
        row: Dict[str, Any],
        selection_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        matched_rules = []
        missing_items = []
        for rule in selection_context.get("rules") or []:
            matched = cls._matched_rule(fund, row, rule)
            if matched:
                matched_rules.append(matched)
            else:
                missing_items.append(f"无法在列表证据中复核：{rule.get('text')}")

        profile = fund.get("research_profile") or {}
        peer_group = str(profile.get("peer_group") or selection_context.get("peer_group") or "").strip()
        confidence = cls._number(profile.get("classification_confidence"))
        classification_text = f"标准分类目录将其归入“{peer_group}”" if peer_group else "专业分类仍待确认"
        if confidence is not None:
            classification_text += f"，分类置信度 {confidence * 100:.0f}%"
        classification_text += "。"

        sort_reason = cls._sort_reason(fund, row, selection_context.get("sort_by") or "quality")
        headline = (
            f"通过 {len(matched_rules)} 项当前条件，{sort_reason}"
            if matched_rules
            else sort_reason
        )
        return {
            **fund,
            "selection_explanation": {
                "status": "matched" if not missing_items else "partial_evidence",
                "headline": headline,
                "classification_reason": classification_text,
                "classification_source": profile.get("classification_source"),
                "classification_confidence": confidence,
                "matched_rules": matched_rules,
                "sort_reason": sort_reason,
                "evidence_as_of": fund.get("nav_date") or fund.get("updated_at"),
                "missing_items": missing_items,
                "boundary": selection_context.get("boundary"),
            },
        }

    @classmethod
    def _matched_rule(
        cls,
        fund: Dict[str, Any],
        row: Dict[str, Any],
        rule: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        key = str(rule.get("key") or "")
        actual: Any = None
        actual_text = ""
        if key == "peer_group":
            actual = (fund.get("research_profile") or {}).get("peer_group")
            actual_text = f"分类为“{actual}”" if actual else ""
        elif key == "keyword":
            keyword = str(rule.get("threshold") or "").lower()
            name = str(fund.get("name") or "")
            code = str(fund.get("wind_code") or "")
            actual = code if keyword in code.lower() else name if keyword in name.lower() else None
            actual_text = f"匹配“{actual}”" if actual else ""
        elif key == "asset_min":
            actual = cls._number(fund.get("total_asset"))
            actual_text = f"实际 {actual:.1f} 亿元" if actual is not None else ""
        elif key == "min_age_years":
            established = cls._date(fund.get("establishment_date"))
            actual = round((date.today() - established).days / 365.25, 1) if established else None
            actual_text = f"已成立 {actual:.1f} 年" if actual is not None else ""
        elif key == "min_manager_years":
            years = [cls._number(item.get("management_years")) for item in fund.get("managers") or []]
            actual = max((value for value in years if value is not None), default=None)
            actual_text = f"现任经理最长 {actual:.1f} 年" if actual is not None else ""
        elif key in {"return_6m_min", "return_1y_min", "return_3y_min"}:
            window = key.split("_")[1]
            actual = cls._number(row.get(f"return_{window}_metric"))
            actual_text = f"实际 {actual * 100:.1f}%" if actual is not None else ""
        elif key == "max_drawdown_1y_max":
            actual = cls._metric(fund, "1y", "max_drawdown", "risk_metrics", "max_drawdown_1y", "max_drawdown")
            actual_text = f"实际 {abs(actual) * 100:.1f}%" if actual is not None else ""
        elif key == "sharpe_1y_min":
            actual = cls._metric(fund, "1y", "sharpe_ratio", "risk_metrics", "sharpe_ratio", "sharpe_ratio")
            actual_text = f"实际 {actual:.2f}" if actual is not None else ""
        elif key == "style_tags":
            selected = [str(item) for item in (rule.get("threshold") or []) if str(item)]
            available = [
                str(item) for item in ((fund.get("research_profile") or {}).get("filter_style_tags") or []) if str(item)
            ]
            matches = [item for item in selected if item in available]
            match_mode = str(rule.get("operator") or "any")
            passed = len(matches) == len(selected) if match_mode == "all" else bool(matches)
            actual = matches if passed else None
            actual_text = f"命中 {'、'.join(matches)}" if passed else ""
        if actual is None:
            return None
        return {**rule, "actual": actual, "actual_text": actual_text}

    @classmethod
    def _sort_reason(cls, fund: Dict[str, Any], row: Dict[str, Any], sort_by: str) -> str:
        normalized = str(sort_by or "quality").strip().lower()
        peer_metrics = fund.get("peer_return_metrics") or {}
        if normalized == "multi_period":
            positions = []
            for window, label in (("6m", "近 6 月"), ("1y", "近 1 年"), ("3y", "近 3 年")):
                metric = peer_metrics.get(window) or {}
                rank = metric.get("rank")
                count = metric.get("peer_count")
                if rank is not None and count:
                    positions.append(f"{label}同类第 {int(rank)}/{int(count)}")
            return "按多周期同类位置排序" + (f"：{'，'.join(positions)}。" if positions else "。")
        if normalized in {"return", "return_6m", "return_1y", "return_3y"}:
            window = "1y" if normalized == "return" else normalized.split("_")[1]
            label = {"6m": "近 6 月", "1y": "近 1 年", "3y": "近 3 年"}[window]
            value = cls._number(row.get(f"return_{window}_metric"))
            metric = peer_metrics.get(window) or {}
            rank = metric.get("rank")
            count = metric.get("peer_count")
            detail = f"当前收益 {value * 100:.1f}%" if value is not None else "当前收益待补"
            if rank is not None and count:
                detail += f"，同类第 {int(rank)}/{int(count)}"
            return f"按{label}收益排序：{detail}。"
        if normalized == "drawdown":
            value = cls._metric(fund, "1y", "max_drawdown", "risk_metrics", "max_drawdown_1y", "max_drawdown")
            return f"按回撤较小优先排序：近 1 年最大回撤 {abs(value) * 100:.1f}%。" if value is not None else "按回撤较小优先排序。"
        if normalized == "sharpe":
            value = cls._metric(fund, "1y", "sharpe_ratio", "risk_metrics", "sharpe_ratio", "sharpe_ratio")
            return f"按 Sharpe 较高优先排序：近 1 年 Sharpe {value:.2f}。" if value is not None else "按 Sharpe 较高优先排序。"
        if normalized == "asset":
            value = cls._number(fund.get("total_asset"))
            return f"按规模较大优先排序：当前规模 {value:.1f} 亿元。" if value is not None else "按规模较大优先排序。"
        if normalized == "history":
            established = fund.get("establishment_date")
            return f"按成立较早优先排序：成立于 {established}。" if established else "按成立较早优先排序。"
        scoring = fund.get("professional_scoring") or {}
        score = cls._number(scoring.get("overall_score"))
        return f"按数据较完整优先排序，当前可输出专业评分 {score:.1f} 分。" if score is not None else "按数据较完整优先排序。"

    @classmethod
    def _metric(
        cls,
        fund: Dict[str, Any],
        window: str,
        rolling_key: str,
        fallback_block: str,
        fallback_key: str,
        second_fallback_key: str,
    ) -> Optional[float]:
        rolling = (fund.get("rolling_metrics") or {}).get(window) or {}
        fallback = fund.get(fallback_block) or {}
        for value in (rolling.get(rolling_key), fallback.get(fallback_key), fallback.get(second_fallback_key)):
            number = cls._number(value)
            if number is not None:
                return number
        return None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed == parsed else None

    @staticmethod
    def _date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _classification_context_from_row(
        row: Dict[str, Any],
        peer: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """列表查询已经携带标准分类事实时，直接投影评分上下文，避免逐只查库。"""
        family_key = str(row.get("strategy_family_key") or "").strip()
        peer_group_id = row.get("standardized_peer_group_id") or peer.get("peer_group_id")
        peer_group_key = row.get("standardized_peer_group_key") or peer.get("peer_group_key")
        peer_group_name = row.get("standardized_peer_group_name") or peer.get("peer_group_name")
        if not family_key or not peer_group_id or not peer_group_key:
            return None

        benchmark_code = row.get("benchmark_code")
        benchmark_name = row.get("benchmark_name")
        benchmark_mapping = None
        if benchmark_code:
            benchmark_mapping = {
                "benchmark_code": benchmark_code,
                "benchmark_name": benchmark_name,
                "benchmark_type": "peer_group_benchmark",
                "mapping_method": "standardized_browser_projection",
                "confidence": row.get("classification_confidence") or peer.get("confidence") or 0.95,
                "rationale": "标准同类组的有效基准映射",
                "evidence_refs": {"source": "standardized_fund_browser_query"},
                "source": "benchmark_mappings",
            }
        missing_items = [] if benchmark_mapping else ["基金实体缺少评价时点有效的基准映射"]
        return {
            "status": "resolved",
            "fund_code": row.get("wind_code"),
            "entity_id": row.get("entity_id"),
            "canonical_code": row.get("canonical_code"),
            "canonical_name": row.get("canonical_name"),
            "strategy_family_key": family_key,
            "strategy_family_name": row.get("strategy_family_name"),
            "asset_class": row.get("asset_class"),
            "active_passive": row.get("active_passive"),
            "peer_group_id": peer_group_id,
            "peer_group_key": peer_group_key,
            "peer_group_name": peer_group_name,
            "minimum_peer_count": row.get("minimum_peer_count"),
            "benchmark_mapping": benchmark_mapping,
            "classification_confidence": row.get("classification_confidence") or peer.get("confidence") or 0.95,
            "classification_evidence": [{
                "field": "peer_group_members.peer_group_id",
                "value": peer_group_id,
                "source": "standardized_fund_browser_query",
                "reason": "基金列表已按标准实体、策略族谱和同类组联表解析",
            }],
            "missing_items": missing_items,
        }

    @staticmethod
    def _style_tag_evidence(row: Dict[str, Any]) -> List[Dict[str, Any]]:
        evidence: List[Dict[str, Any]] = []
        source_rows = (
            (
                "holding_quantitative",
                "公开持仓同类分位",
                "strong",
                row.get("holding_style_tags") or [],
                row.get("holding_style_as_of"),
                row.get("holding_style_source") or "holding_style_peer_percentile_v1",
            ),
            (
                "memo_confirmed",
                "产品纪要人工确认",
                "context",
                row.get("memo_style_tags") or [],
                row.get("memo_style_as_of"),
                "research_memo_profile_projection",
            ),
            (
                "product_positioning",
                "标准分类产品定位",
                "classification",
                row.get("classification_style_tags") or [],
                row.get("classification_sample_as_of") or row.get("nav_date"),
                "strategy_families.style_tags",
            ),
        )
        seen = set()
        for source_key, source_label, evidence_level, values, as_of, source in source_rows:
            for value in values:
                normalized = str(value or "").strip()
                key = (source_key, normalized)
                if not normalized or key in seen:
                    continue
                seen.add(key)
                evidence.append({
                    "value": normalized,
                    "source_key": source_key,
                    "source_label": source_label,
                    "evidence_level": evidence_level,
                    "as_of": as_of,
                    "source": source,
                })
        return evidence

    @staticmethod
    def _manager(row: Dict[str, Any]) -> Dict[str, Any]:
        raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        return {
            "manager_id": row.get("wind_code"),
            "wind_code": row.get("wind_code"),
            "name": row.get("name"),
            "company": row.get("company"),
            "management_years": row.get("management_years"),
            "begin_date": raw_data.get("begin_date"),
            "end_date": raw_data.get("end_date"),
            "source": "tushare.fund_manager",
        }
