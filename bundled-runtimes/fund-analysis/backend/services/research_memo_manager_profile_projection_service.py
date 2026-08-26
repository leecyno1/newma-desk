"""Project confirmed manager memo evidence into manager profiles."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional


class ResearchMemoManagerProfileProjectionService:
    """Aggregate manager memo evidence behind one projection interface."""

    UPDATED_BY = "research_memo_manager_profile_projection"
    PROFILE_FIELDS = {
        "product_positioning": ("产品定位",),
        "investment_objective": ("投资目标", "管理目标", "收益目标", "回报目标"),
        "investment_method": ("投资方法", "投资方法论", "组合构建方法", "研究方法", "逆向选股核心框架"),
        "core_philosophy": ("核心投资理念", "投资理念", "投资哲学", "核心理念"),
        "stock_selection_logic": ("选股逻辑", "选股方法", "投资策略"),
        "risk_philosophy": ("风险控制", "回撤控制", "风险意识", "回撤处理", "风险管理"),
        "competence_advantages": ("能力优势", "擅长", "优势", "能力圈"),
        "competence_boundaries": ("能力边界", "不擅长行业", "不擅长", "局限", "风险点", "短板"),
        "concentration": ("持仓集中度", "组合集中度", "集中度"),
        "turnover": ("换手率", "换手"),
        "excess_return_source": ("超额收益来源", "超额收益", "收益来源"),
        "holding_style": ("持股风格", "市值风格", "风格定位"),
    }
    INDUSTRIES = (
        "农业", "轻工", "非银", "汽车", "军工", "电子", "通信", "半导体", "人工智能",
        "AI", "算力", "新能源", "光伏", "风电", "储能", "电池", "医药", "创新药",
        "医疗", "消费", "食品饮料", "白酒", "家电", "银行", "券商", "保险", "地产",
        "建筑", "建材", "化工", "新材料", "钢铁", "煤炭", "有色", "铜", "铝", "黄金",
        "公用事业", "交运", "互联网", "软件", "云计算", "港股", "海外", "信用债",
        "利率债", "转债",
    )
    INDUSTRY_INVESTMENT_CUES = (
        "持仓", "仓位", "配置", "加仓", "减仓", "买入", "卖出", "重仓", "底仓",
        "超配", "低配", "看好", "关注", "聚焦", "重点方向", "投资机会",
        "配置价值", "投资价值", "擅长", "能力圈", "深入研究", "研究覆盖", "轮动",
        "波段", "最优解", "偏好", "高胜率", "高赔率",
    )
    INDUSTRY_NOISE_CUES = (
        "风险揭示", "免责声明", "不构成投资建议", "仅供", "公开宣传", "销售有限公司",
        "销售牌照", "会员单位", "基金业协会", "保交所", "理财子公司", "保险资管",
        "信托登记", "基金托管人", "注册登记机构", "业绩比较基准", "本基金的投资范围",
        "投资组合比例为", "法律法规", "中国证监会允许", "曾任职", "任职于", "从业经历",
        "个人履历", "基金经理简介", "主讲人", "前十大股票持仓分析", "占净值比",
        "任职业绩", "数据来源：Wind", "基金定期报告",
    )

    def __init__(self, report_repo: Any, manager_repo: Optional[Any] = None):
        self.report_repo = report_repo
        self._manager_repo = manager_repo

    def project_report(self, report: Dict[str, Any], affected_manager_ids: List[str]) -> Dict[str, Any]:
        manager_ids = list(dict.fromkeys(
            str(item or "").strip() for item in affected_manager_ids if str(item or "").strip()
        ))
        results = [self._project_manager(manager_id, report) for manager_id in manager_ids]
        return self._summary(results)

    def rebuild_managers(self, manager_ids: List[str]) -> Dict[str, Any]:
        """Rebuild confirmed manager memo profiles after extraction rules change."""
        normalized = list(dict.fromkeys(
            str(item or "").strip() for item in manager_ids if str(item or "").strip()
        ))
        result = self._summary([self._project_manager(manager_id, {}) for manager_id in normalized])
        manager_repo = self._get_manager_repo()
        result["orphaned_deleted_count"] = (
            manager_repo.delete_orphaned_projected_profiles(self.UPDATED_BY)
            if hasattr(manager_repo, "delete_orphaned_projected_profiles")
            else 0
        )
        return result

    def _summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "updated_by": self.UPDATED_BY,
            "managers": results,
            "projected_count": sum(item["status"] == "projected" for item in results),
            "deleted_count": sum(item["status"] == "deleted" for item in results),
            "skipped_count": sum(item["status"] == "skipped" for item in results),
        }

    def _project_manager(self, manager_id: str, current_report: Dict[str, Any]) -> Dict[str, Any]:
        manager_repo = self._get_manager_repo()
        existing = manager_repo.get_profile(manager_id)
        if existing and existing.get("updated_by") != self.UPDATED_BY:
            return {"manager_id": manager_id, "status": "skipped", "reason": "manual_profile_preserved"}

        reports = self._reports_for_manager(manager_id, current_report)
        if not reports:
            deleted = manager_repo.delete_projected_profile(manager_id, self.UPDATED_BY)
            return {
                "manager_id": manager_id,
                "status": "deleted" if deleted else "skipped",
                "reason": "no_confirmed_manager_memos",
            }

        field_evidence: Dict[str, List[Dict[str, Any]]] = {field: [] for field in self.PROFILE_FIELDS}
        industry_evidence: List[Dict[str, Any]] = []
        style_evidence: List[Dict[str, Any]] = []
        insight_evidence: List[Dict[str, Any]] = []

        for report in reports:
            content = str(report.get("content") or "")
            for field, headings in self.PROFILE_FIELDS.items():
                candidates = [
                    self._section_evidence(field, content, headings, report),
                    self._direct_field_evidence(field, content, report),
                ]
                evidence = max(
                    (item for item in candidates if item),
                    key=lambda item: (float(item.get("confidence") or 0), len(str(item.get("value") or ""))),
                    default=None,
                )
                if evidence:
                    field_evidence[field].append(evidence)
            industry_evidence.extend(self._industry_evidence(content, report))
            style_evidence.extend(self._style_evidence(report))
            insight_evidence.extend(self._insight_evidence(report))

        style_counts = Counter(item["value"] for item in style_evidence)
        style_label = style_counts.most_common(1)[0][0] if style_counts else None
        focus_industries = self._rank_values(industry_evidence, limit=8)
        profile = {
            "product_positioning": self._best_value(field_evidence["product_positioning"]),
            "investment_objective": self._best_value(field_evidence["investment_objective"]),
            "investment_method": self._best_value(field_evidence["investment_method"]),
            "core_philosophy": self._best_value(field_evidence["core_philosophy"]),
            "stock_selection_logic": self._best_value(field_evidence["stock_selection_logic"]),
            "risk_philosophy": self._best_value(field_evidence["risk_philosophy"]),
            "focus_industries": focus_industries,
            "competence_advantages": self._best_value(field_evidence["competence_advantages"]),
            "competence_boundaries": self._best_value(field_evidence["competence_boundaries"]),
            "style_label": style_label,
            "concentration": self._best_value(field_evidence["concentration"]),
            "turnover": self._best_value(field_evidence["turnover"]),
            "excess_return_source": self._best_value(field_evidence["excess_return_source"]),
            "holding_style": self._best_value(field_evidence["holding_style"]),
            "key_insights": [item["value"] for item in insight_evidence[:8]],
            "red_flags": [],
            "interviews_analyzed": len(reports),
            "last_interview_date": max(
                (str(report.get("report_date") or "") for report in reports),
                default="",
            ) or None,
            "evidence": {
                "source": self.UPDATED_BY,
                "manager_id": manager_id,
                "report_count": len(reports),
                "reports": [self._report_ref(report) for report in reports],
                "fields": {field: items for field, items in field_evidence.items() if items},
                "focus_industries": industry_evidence,
                "style_labels": style_evidence,
                "key_insights": insight_evidence,
            },
            "updated_by": self.UPDATED_BY,
        }
        profile["evidence"]["framework"] = {
            "product_positioning": field_evidence["product_positioning"],
            "investment_objective": field_evidence["investment_objective"],
            "investment_method": field_evidence["investment_method"],
            "excess_return_source": field_evidence["excess_return_source"],
            "holding_style": field_evidence["holding_style"],
        }
        if not any([
            profile["product_positioning"], profile["investment_objective"], profile["investment_method"],
            profile["core_philosophy"], profile["stock_selection_logic"], profile["risk_philosophy"],
            profile["focus_industries"], profile["competence_advantages"],
            profile["competence_boundaries"], profile["style_label"], profile["key_insights"],
            profile["excess_return_source"], profile["holding_style"],
        ]):
            deleted = manager_repo.delete_projected_profile(manager_id, self.UPDATED_BY)
            return {
                "manager_id": manager_id,
                "status": "deleted" if deleted else "skipped",
                "reason": "no_profile_evidence",
            }

        if not manager_repo.upsert_profile(manager_id, profile):
            return {"manager_id": manager_id, "status": "skipped", "reason": "persistence_failed"}
        return {"manager_id": manager_id, "status": "projected", "profile": profile}

    def _reports_for_manager(self, manager_id: str, current_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        if hasattr(self.report_repo, "list_reports_for_manager_exact"):
            rows = self.report_repo.list_reports_for_manager_exact(manager_id, limit=200)
        else:
            rows = self.report_repo.list_reports(
                manager_id=manager_id,
                page=1,
                page_size=50,
                sort_by="report_date",
                sort_order="desc",
            ).get("reports", [])
        if manager_id in self._report_manager_ids(current_report):
            rows.append(current_report)
        deduplicated: Dict[str, Dict[str, Any]] = {}
        for report in rows:
            if manager_id not in self._report_manager_ids(report):
                continue
            key = str(report.get("source_hash") or report.get("id") or report.get("title") or "")
            deduplicated[key] = report
        return sorted(
            deduplicated.values(),
            key=lambda item: str(item.get("report_date") or item.get("updated_at") or ""),
            reverse=True,
        )

    @staticmethod
    def _report_manager_ids(report: Dict[str, Any]) -> List[str]:
        manager_ids = [
            str(item.get("manager_id") or "").strip()
            for item in report.get("manager_links") or []
            if str(item.get("manager_id") or "").strip()
        ]
        legacy_manager_id = str(report.get("manager_id") or "").strip()
        if legacy_manager_id:
            manager_ids.append(legacy_manager_id)
        return list(dict.fromkeys(manager_ids))

    def _section_evidence(
        self,
        field: str,
        content: str,
        headings: tuple[str, ...],
        report: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        lines = [re.sub(r"\s+", " ", line).strip() for line in content.splitlines()]
        for index, line in enumerate(lines):
            match = self._section_heading(line, headings)
            if not match:
                continue
            heading, inline_value = match
            section = [inline_value] if inline_value else []
            for next_line in ([] if inline_value else lines[index + 1:index + 7]):
                if not next_line:
                    continue
                if self._starts_profile_section(next_line):
                    break
                if section and self._looks_like_document_heading(next_line):
                    break
                if re.fullmatch(r"\d{1,3}", next_line):
                    continue
                if len(next_line) <= 18 and re.search(r"(?:理念|逻辑|策略|框架|风险|优势|边界|集中度|换手)$", next_line):
                    break
                section.append(next_line)
            value = " ".join(section).strip()[:360]
            if len(value) < 8 or not self._usable_field_value(field, value):
                continue
            confidence = 0.9 if not inline_value else 0.86
            return self._evidence(value, f"{heading}：{value}", report, confidence, "section_heading")
        return None

    @classmethod
    def _starts_profile_section(cls, line: str) -> bool:
        return any(cls._section_heading(line, headings) for headings in cls.PROFILE_FIELDS.values())

    @staticmethod
    def _looks_like_document_heading(line: str) -> bool:
        text = re.sub(r"\s+", " ", str(line or "")).strip()
        if re.match(r"^(?:[一二三四五六七八九十]+[、.．]|\d+[、.．])", text):
            return True
        return len(text) <= 24 and text.endswith(("行业对比", "交流环节", "问答环节", "情况更新"))

    @classmethod
    def _section_heading(
        cls,
        line: str,
        headings: tuple[str, ...],
    ) -> Optional[tuple[str, str]]:
        original = str(line or "").strip()
        normalized = re.sub(
            r"^(?:[一二三四五六七八九十]+[、.．]\s*|\d+[.、)]\s*|[（(]?\d+[）)]\s*)",
            "",
            original,
        ).strip()
        for heading in sorted(headings, key=len, reverse=True):
            if normalized == heading:
                return heading, ""
            if re.fullmatch(rf"{re.escape(heading)}\s*[:：]", normalized):
                return heading, ""
            inline = re.match(rf"^{re.escape(heading)}\s*[:：]\s*(.+)$", normalized)
            if inline:
                return heading, inline.group(1).strip()
            if normalized != original and len(normalized) <= 24 and normalized.endswith(heading):
                return heading, ""
        return None

    def _direct_field_evidence(
        self,
        field: str,
        content: str,
        report: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        candidates: List[tuple[int, str, float, str]] = []
        for raw_line in str(content or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line or len(line) > 600 or "风险揭示" in line or self._is_interview_question(line):
                continue
            if field == "excess_return_source" and "超额" in line:
                score = sum(cue in line for cue in (
                    "行业配置效应", "个股选择效应", "贡献度最大的", "超额贡献", "行业分布",
                ))
                if score >= 1:
                    candidates.append((score, line, 0.9 if score >= 3 else 0.82, "explicit_attribution_statement"))
            elif field == "product_positioning":
                positioning_cues = (
                    "聚焦", "全市场", "赛道", "主题基金", "投资范围", "策略边界",
                    "差异化", "风格", "区分", "主动权益", "固收", "指数", "周期资源",
                )
                explicit_positioning = (
                    "产品定位" in line
                    or bool(re.search(r"定位(?:为|是|及标签|\s*[:：])", line))
                    or ("产品" in line and "定位" in line)
                )
                score = sum(cue in line for cue in positioning_cues)
                if explicit_positioning and score:
                    score += 5 if "定位为" in line else 3
                    confidence = min(0.96, 0.9 + score * 0.005)
                    candidates.append((score, line, confidence, "explicit_product_positioning_statement"))
            elif field == "investment_objective":
                objective_cues = (
                    "绝对收益", "收益率", "长期复合", "长期稳健", "回报", "为客户持续赚钱",
                    "控制回撤", "最大回撤", "波动率", "持有体验",
                )
                objective_marker = any(cue in line for cue in (
                    "投资目标", "收益目标", "回报目标", "绝对收益目标",
                    "偏绝对收益", "为客户持续赚钱", "力争", "争取",
                ))
                score = sum(cue in line for cue in objective_cues)
                if objective_marker and score:
                    objective = re.sub(r"^(?:产品定位|投资目标|收益目标|回报目标)\s*[:：]\s*", "", line).strip()
                    confidence = min(0.96, 0.9 + score * 0.006)
                    candidates.append((score, objective, confidence, "explicit_investment_objective_statement"))
            elif field == "investment_method":
                method_cues = (
                    "自上而下", "自下而上", "组合构建", "宏观", "供需", "行业轮动",
                    "筛选", "选股", "估值", "止盈", "止损", "研究", "分散", "集中", "标的",
                )
                score = sum(cue in line for cue in method_cues)
                explicit_method = (
                    ("自上而下" in line and "自下而上" in line)
                    or "组合构建方法" in line
                    or "投资方法" in line
                    or "研究方法" in line
                )
                if explicit_method and score >= 2:
                    confidence = min(0.96, 0.9 + score * 0.008)
                    candidates.append((score, line, confidence, "explicit_investment_method_statement"))
            elif field == "holding_style" and "风格" in line:
                style_cues = ("价值", "成长", "均衡", "红利", "低估值", "高股息", "大盘", "中盘", "小盘", "周期")
                context_cues = ("持仓", "组合", "产品", "管理", "配置", "不做风格漂移")
                score = sum(cue in line for cue in style_cues) + 2 * sum(cue in line for cue in context_cues)
                if score >= 3:
                    candidates.append((score, line, 0.86, "explicit_holding_style_statement"))
            elif field == "risk_philosophy" and ("回撤控制" in line or "风险控制" in line):
                mechanism_score = sum(cue in line for cue in (
                    "仓位", "集中度", "分散", "估值", "止损", "止盈", "减仓", "回避",
                    "流动性", "信用", "久期", "对冲", "安全边际", "风险预算", "控制在",
                    "不超过", "绝对收益", "防御",
                ))
                if mechanism_score:
                    score = 2 + mechanism_score
                    candidates.append((score, line, 0.9 if score >= 4 else 0.84, "explicit_risk_framework_statement"))
            elif field == "concentration" and "集中度" in line:
                score = 2 + sum(cue in line for cue in ("控制", "前十大", "单一行业", "分散"))
                candidates.append((score, line, 0.82, "explicit_portfolio_statement"))
            elif field == "turnover" and "换手" in line:
                score = 2 + sum(cue in line for cue in ("高换手", "低换手", "中低换手", "换手率"))
                candidates.append((score, line, 0.82, "explicit_portfolio_statement"))
        if not candidates:
            return None
        candidates = [item for item in candidates if self._usable_field_value(field, item[1])]
        if not candidates:
            return None
        _, value, confidence, source = max(candidates, key=lambda item: (item[0], len(item[1])))
        return self._evidence(value[:360], value, report, confidence, source)

    @classmethod
    def _usable_field_value(cls, field: str, value: str) -> bool:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text or cls._is_interview_question(text):
            return False
        if re.fullmatch(
            r"(?:组合构建(?:方法)?|投资约束|投资目标(?:及理念)?|收益目标|回报目标|投资理念|投资策略|风险控制|回撤控制|选股逻辑|能力圈|产品定位|投资方法(?:论)?|研究方法|方法|框架|优势|边界|\s)+",
            text,
        ):
            return False
        if field == "product_positioning":
            return any(cue in text for cue in (
                "聚焦", "全市场", "赛道", "主题基金", "投资范围", "策略边界",
                "差异化", "风格", "区分", "主动权益", "固收", "指数", "周期资源",
            ))
        if field == "investment_objective":
            return any(cue in text for cue in (
                "绝对收益", "收益率", "长期复合", "长期稳健", "回报", "为客户持续赚钱",
                "控制回撤", "最大回撤", "波动率", "持有体验",
            ))
        if field == "investment_method":
            return any(cue in text for cue in (
                "自上而下", "自下而上", "组合构建", "宏观", "供需", "行业轮动",
                "筛选", "选股", "估值", "止盈", "止损", "研究", "分散", "集中", "标的",
            ))
        if field == "risk_philosophy":
            mechanisms = (
                "仓位", "集中度", "分散", "估值", "止损", "止盈", "减仓", "回避",
                "流动性", "信用", "久期", "对冲", "安全边际", "风险预算", "控制在",
                "不超过", "绝对收益", "防御", "危机管理", "投资逻辑",
            )
            return any(cue in text for cue in mechanisms)
        return True

    @staticmethod
    def _is_interview_question(value: str) -> bool:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return False
        if re.match(r"^(?:Q\d*|问题\d*|提问|问)\s*[：:]", text, re.IGNORECASE):
            return True
        question_cues = ("请问", "您如何", "您怎么看", "您在", "能否", "可否", "是否", "分享一下", "是什么", "为什么", "怎么")
        return ("?" in text or "？" in text) and any(cue in text for cue in question_cues)

    def _industry_evidence(self, content: str, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        segments = self._industry_segments(content)
        hits = []
        for industry in self.INDUSTRIES:
            candidates = []
            for index, segment in enumerate(segments):
                if not self._contains_industry(segment, industry):
                    continue
                previous = segments[index - 1] if index > 0 else ""
                for excerpt in self._industry_local_contexts(segment, industry):
                    score = self._industry_investment_score(industry, excerpt, previous)
                    if score > 0:
                        candidates.append((score, excerpt))
            if not candidates:
                continue
            score, excerpt = max(candidates, key=lambda item: (item[0], len(item[1])))
            confidence = min(0.9, 0.72 + score * 0.03)
            hits.append(self._evidence(
                industry,
                excerpt,
                report,
                confidence,
                "investment_context_industry",
            ))
        return hits

    @classmethod
    def _industry_segments(cls, content: str) -> List[str]:
        lines = [
            re.sub(r"[\t\r ]+", " ", line).strip()
            for line in str(content or "").splitlines()
            if line.strip()
        ]
        if not lines:
            return []
        compact_lengths = [len(re.sub(r"\s+", "", line)) for line in lines]
        fragmented = len(lines) >= 50 and sum(length <= 2 for length in compact_lengths) / len(lines) >= 0.65
        source = "".join(lines) if fragmented else "\n".join(lines)
        source = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", source)
        segments = re.split(
            r"\n+|(?<=[。！？!?；;])|(?=(?:Q|A|问|答)\s*[:：])",
            source,
            flags=re.IGNORECASE,
        )
        normalized = []
        for segment in segments:
            text = re.sub(r"\s+", " ", segment).strip()
            if not text:
                continue
            if len(text) <= 700:
                normalized.append(text)
                continue
            for start in range(0, len(text), 360):
                normalized.append(text[start:start + 520])
        return normalized

    @classmethod
    def _industry_investment_score(cls, industry: str, segment: str, previous: str = "") -> int:
        text = re.sub(r"\s+", " ", str(segment or "")).strip()
        if not text or cls._is_interview_question(text):
            return 0
        if any(cue in text for cue in cls.INDUSTRY_NOISE_CUES):
            return 0
        if re.search(r"(?:合计|股票仓位)\d+(?:\.\d+)?", text) and len(re.findall(r"\d+(?:\.\d+)?%", text)) >= 3:
            return 0
        if re.search(r"(?:他们|机构|理财|保险资金)[^。；]{0,20}(?:通过|进行|持仓|配置|买入|投资)", text):
            return 0
        escaped = re.escape(industry)
        if re.search(
            rf"(?:不擅长|涉及不多|很少(?:研究|涉及)|没有(?:覆盖|研究)|不参与|回避|不配置|不会(?:买|配)|不看好|低配|减持)"
            rf"[^。；!?！？]{{0,24}}{escaped}",
            text,
        ) or re.search(
            rf"{escaped}[^。；!?！？]{{0,24}}(?:不擅长|涉及不多|不会(?:配置|加仓)|不配置|不参与|回避|低配|减持|不会配置很多)",
            text,
        ):
            return 0
        if industry in {"银行", "保险", "非银"} and re.search(
            rf"{escaped}(?:自营|理财|资管|机构|客户|从业|资金部|金融市场部|监管|有刚性配置需求|都会偏好)",
            text,
        ):
            return 0
        if industry in {"银行", "保险", "非银"} and re.search(
            rf"{escaped}(?:公司|资金|等机构|介入|支付|资本新规|大厦|协会|会员)",
            text,
        ) and not re.search(
            rf"(?:看好|配置|持仓|重仓|买入|加仓)[^。；!?！？]{{0,18}}{escaped}(?:公司|股|板块|行业)?",
            text,
        ):
            return 0
        if industry == "银行" and not re.search(
            r"(?:配置|加仓|减仓|买入|卖出|重仓|底仓|超配|低配|看好|聚焦|配置价值|投资价值)"
            r"[^。；!?！？]{0,42}银行|银行[^。；!?！？]{0,42}"
            r"(?:配置|加仓|减仓|买入|卖出|重仓|底仓|超配|低配|看好|聚焦|配置价值|投资价值)",
            text,
        ):
            return 0

        action = (
            r"(?:持仓|仓位|配置|加仓|减仓|买入|卖出|重仓|底仓|超配|低配|看好|关注|聚焦|"
            r"重点方向|投资机会|配置价值|投资价值|擅长|深入研究|研究覆盖|轮动|波段|布局|"
            r"切换到|加入(?:到)?(?:我们的)?组合|高胜率|高赔率)"
        )
        score = 0
        if re.search(rf"{action}[^。；!?！？]{{0,42}}{escaped}", text):
            score += 2
        if re.search(rf"{escaped}[^。；!?！？]{{0,42}}{action}", text):
            score += 2
        if re.search(rf"{escaped}[^。；!?！？]{{0,12}}\d+(?:\.\d+)?\s*(?:%|个点)", text) and any(
            cue in text for cue in ("持仓", "仓位", "配置", "组合", "占比", "比例", "其中")
        ):
            score += 3
        if re.search(rf"(?:能力圈|研究覆盖|主要覆盖|系统性覆盖|擅长)[^。；!?！？]{{0,60}}{escaped}", text):
            score += 3
        previous_text = re.sub(r"\s+", " ", str(previous or "")).strip()
        if score == 0 and any(cue in previous_text[-80:] for cue in (
            "投资机会", "关注方向", "重点方向", "行业观点", "组合配置", "持仓情况",
        )):
            if len(text) <= 100:
                score = 1
        return score

    @classmethod
    def _industry_local_contexts(cls, segment: str, industry: str) -> List[str]:
        contexts = []
        pattern = re.compile(
            r"(?<![A-Za-z])AI(?![A-Za-z])" if industry == "AI" else re.escape(industry),
            re.IGNORECASE if industry == "AI" else 0,
        )
        for match in pattern.finditer(segment):
            start = max(0, match.start() - 90)
            end = min(len(segment), match.end() + 130)
            contexts.append(re.sub(r"\s+", " ", segment[start:end]).strip())
        return contexts

    @staticmethod
    def _contains_industry(text: str, industry: str) -> bool:
        if industry == "AI":
            return bool(re.search(r"(?<![A-Za-z])AI(?![A-Za-z])", text, re.IGNORECASE))
        return industry in text

    def _style_evidence(self, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        confirmed_labels = set(report.get("style_labels") or [])
        evidence = []
        for proposal in report.get("review_proposals") or []:
            label = str(proposal.get("value") or "").strip()
            if (
                proposal.get("kind") != "style_label"
                or proposal.get("review_status") != "confirmed"
                or proposal.get("scope") != "manager"
                or label not in confirmed_labels
            ):
                continue
            source_ref = proposal.get("source_ref") or {}
            evidence.append(self._evidence(
                label,
                str(source_ref.get("excerpt") or label),
                report,
                float(proposal.get("confidence") or 0.9),
                str(proposal.get("extraction_source") or "confirmed_manager_style_label"),
            ))
        return evidence

    def _insight_evidence(self, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        points = [str(item).strip() for item in report.get("key_points") or [] if str(item or "").strip()]
        if not points:
            summary = str(report.get("summary") or "").strip()
            points = [summary[:240]] if summary else []
        return [self._evidence(point, point, report, 0.68, "memo_key_point") for point in points[:3]]

    @staticmethod
    def _best_value(items: List[Dict[str, Any]]) -> Optional[str]:
        if not items:
            return None
        best = max(
            items,
            key=lambda item: (
                float(item.get("confidence") or 0),
                min(len(str(item.get("value") or "")), 360),
                str(item.get("report_date") or ""),
            ),
        )
        return str(best.get("value") or "").strip() or None

    @staticmethod
    def _rank_values(items: List[Dict[str, Any]], limit: int) -> List[str]:
        counts = Counter(item["value"] for item in items)
        recency = {
            value: max(str(item.get("report_date") or "") for item in items if item["value"] == value)
            for value in counts
        }
        values = sorted(counts, key=lambda value: (-counts[value], -int(recency[value].replace("-", "") or 0), value))
        return values[:limit]

    def _evidence(
        self,
        value: str,
        excerpt: str,
        report: Dict[str, Any],
        confidence: float,
        extraction_source: str,
    ) -> Dict[str, Any]:
        return {
            "value": str(value).strip(),
            "report_id": str(report.get("id") or ""),
            "report_title": report.get("title"),
            "report_date": report.get("report_date"),
            "relative_path": report.get("local_relative_path"),
            "source_path": report.get("local_source_path"),
            "excerpt": re.sub(r"\s+", " ", str(excerpt or "")).strip()[:360],
            "confidence": confidence,
            "extraction_source": extraction_source,
        }

    @staticmethod
    def _report_ref(report: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "report_id": str(report.get("id") or ""),
            "title": report.get("title"),
            "report_date": report.get("report_date"),
            "relative_path": report.get("local_relative_path"),
            "source_path": report.get("local_source_path"),
        }

    @staticmethod
    def _excerpt(content: str, start: int, radius: int) -> str:
        return re.sub(r"\s+", " ", content[max(0, start - radius):start + radius]).strip()

    @staticmethod
    def _proposal_excerpt(report: Dict[str, Any], kind: str, value: str) -> str:
        for proposal in report.get("review_proposals") or []:
            if proposal.get("kind") == kind and proposal.get("value") == value and proposal.get("review_status") == "confirmed":
                return str((proposal.get("source_ref") or {}).get("excerpt") or value)
        return value

    def _get_manager_repo(self):
        if self._manager_repo is None:
            from repositories.manager_repo import ManagerRepo

            self._manager_repo = ManagerRepo()
        return self._manager_repo
