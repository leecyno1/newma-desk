"""Match a research memo to fund managers without guessing from generic folders."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


class ResearchMemoManagerMatcher:
    """Resolve manager names from explicit memo evidence and a local manager catalog."""

    GENERIC_NAMES = {
        "基金", "基金经理", "经理", "路演", "纪要", "交流", "访谈", "观点", "投资",
        "市场", "内部", "参考", "研究", "产品", "介绍", "推介", "材料", "更新",
        "策略", "会议", "报告", "调研", "分享", "行业", "公司", "团队", "过审版",
        "权益", "固收", "医药", "消费", "科技", "制造", "宏观", "债券", "指数",
        "海外", "价值", "成长", "均衡", "主题", "量化", "年度", "季度", "月度",
        "周期", "资源", "景气", "内参", "权益成长", "权益绩优", "权益经理",
        "景气驱动", "全球欣越", "市场观点", "行业观点", "观点更新", "大安全",
        "黄金", "安和", "通利",
    }
    TITLE_CUES = (
        "基金经理", "总路演", "路演", "交流", "访谈", "投资理念", "投资风格",
        "调研", "纪要", "报告", "观点", "线上", "近期", "产品介绍", "基金推介",
        "先生", "女士",
    )
    COMPANY_SUFFIXES = (
        "基金管理股份有限公司", "基金管理有限公司", "资产管理有限公司",
        "投资管理有限公司", "股份有限公司", "有限公司", "基金",
    )
    SURNAME_PREFIXES = tuple("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊甄曲封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶黎乔苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公")
    COMPOUND_SURNAMES = (
        "欧阳", "司马", "上官", "诸葛", "夏侯", "东方", "皇甫", "尉迟", "公孙",
        "慕容", "宇文", "长孙", "司徒", "司空", "令狐", "轩辕", "南宫", "独孤",
    )

    def __init__(
        self,
        managers: Iterable[Dict[str, Any]],
        company_names: Iterable[str] = (),
    ):
        self.managers = [
            {
                "manager_id": str(item.get("wind_code") or item.get("manager_id") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "company": str(item.get("company") or "").strip(),
            }
            for item in managers
            if str(item.get("name") or "").strip()
        ]
        self.by_name: Dict[str, List[Dict[str, str]]] = {}
        for manager in self.managers:
            self.by_name.setdefault(manager["name"], []).append(manager)
        self.company_aliases = {
            alias
            for manager in self.managers
            if (alias := self._company_alias(manager.get("company")))
        }
        self.company_aliases.update(
            alias
            for company in company_names
            if (alias := self._company_alias(company))
        )

    def match(self, content: str, filename: str, relative_path: str = "") -> List[Dict[str, Any]]:
        stem = re.sub(r"\.(?:pdf|docx|pptx|md|txt)$", "", str(filename or ""), flags=re.IGNORECASE)
        context = " ".join([stem, str(relative_path or ""), str(content or "")[:2_000]])
        matches: Dict[str, Dict[str, Any]] = {}

        for candidate, excerpt in self._explicit_content_candidates(content):
            self._add(matches, candidate, context, excerpt, 0.98, "explicit_field")

        for manager in sorted(self.managers, key=lambda item: len(item["name"]), reverse=True):
            name = manager["name"]
            if not self._catalog_name_in_title(name, stem, manager.get("company")):
                continue
            resolved = self._resolve(name, context)
            if not resolved:
                continue
            self._store(
                matches,
                name,
                candidate_id=resolved["manager_id"],
                company=resolved.get("company"),
                excerpt=f"文件名：{filename}",
                confidence=0.96,
                extraction_source="manager_catalog_title",
            )

        for candidate in self._filename_candidates(stem):
            self._add(matches, candidate, context, f"文件名：{filename}", 0.84, "filename_pattern")

        return sorted(
            matches.values(),
            key=lambda item: (bool(item.get("candidate_id")), float(item.get("confidence") or 0), len(item["value"])),
            reverse=True,
        )

    def normalize_candidate(self, raw_candidate: str) -> str:
        """Return one valid manager name, or an empty string for generic noise."""
        candidate = self._clean_candidate(raw_candidate)
        return candidate if self._valid_candidate(candidate) else ""

    def resolve_candidate(self, raw_candidate: str, context: str = "") -> Optional[Dict[str, str]]:
        """Resolve only the same normalized name against the manager catalog."""
        candidate = self.normalize_candidate(raw_candidate)
        if not candidate:
            return None
        resolved = self._resolve(candidate, str(context or ""))
        if not resolved:
            return None
        return {
            "value": candidate,
            "candidate_id": resolved["manager_id"],
            "manager_id": resolved["manager_id"],
            "manager_name": candidate,
            "company": resolved.get("company") or "",
        }

    def has_exact_name_evidence(self, raw_candidate: str, evidence: str) -> bool:
        """Reject a short manager name when the excerpt only contains a longer Chinese name."""
        candidate = self.normalize_candidate(raw_candidate)
        text = str(evidence or "")
        if not candidate or not text:
            return False
        prefix = r"(?:^|[^\u4e00-\u9fff·]|基金经理|经理|主讲人|主讲嘉宾|分享嘉宾|嘉宾)"
        suffix = r"(?:先生|女士|老师|总)?(?![\u4e00-\u9fff·])"
        return bool(re.search(rf"{prefix}{re.escape(candidate)}{suffix}", text))

    def _add(
        self,
        matches: Dict[str, Dict[str, Any]],
        raw_candidate: str,
        context: str,
        excerpt: str,
        confidence: float,
        extraction_source: str,
    ) -> None:
        candidate = self.normalize_candidate(raw_candidate)
        if not candidate:
            return
        resolved = self.resolve_candidate(candidate, context)
        self._store(
            matches,
            candidate,
            candidate_id=(resolved or {}).get("manager_id"),
            company=(resolved or {}).get("company"),
            excerpt=excerpt,
            confidence=max(confidence, 0.96 if resolved and extraction_source == "filename_pattern" else 0),
            extraction_source=extraction_source,
        )

    @staticmethod
    def _store(
        matches: Dict[str, Dict[str, Any]],
        value: str,
        candidate_id: Optional[str],
        company: Optional[str],
        excerpt: str,
        confidence: float,
        extraction_source: str,
    ) -> None:
        candidate = {
            "value": value,
            "candidate_id": candidate_id,
            "company": company,
            "excerpt": re.sub(r"\s+", " ", excerpt).strip()[:240],
            "confidence": min(1.0, max(0.0, confidence)),
            "extraction_source": extraction_source,
        }
        current = matches.get(value)
        if not current or (
            bool(candidate_id), candidate["confidence"]
        ) > (bool(current.get("candidate_id")), float(current.get("confidence") or 0)):
            matches[value] = candidate

    def _resolve(self, name: str, context: str) -> Optional[Dict[str, str]]:
        candidates = self.by_name.get(name, [])
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            return None
        matched = [
            item for item in candidates
            if (alias := self._company_alias(item.get("company"))) and alias in context
        ]
        return matched[0] if len(matched) == 1 else None

    def _catalog_name_in_title(self, name: str, stem: str, company: str) -> bool:
        start = stem.find(name)
        while start >= 0:
            end = start + len(name)
            before = stem[:start]
            after = stem[end:]
            after_ok = not after or not self._is_chinese(after[0]) or any(after.startswith(cue) for cue in self.TITLE_CUES)
            if start == 0 or not self._is_chinese(stem[start - 1]):
                before_ok = True
            else:
                alias = self._company_alias(company)
                before_ok = self._company_prefix_matches(before, alias) or self._title_prefix_is_company(before)
            if before_ok and after_ok:
                return True
            start = stem.find(name, start + 1)
        return False

    @staticmethod
    def _explicit_content_candidates(content: str) -> List[tuple[str, str]]:
        results: List[tuple[str, str]] = []
        patterns = (
            r"基金经理\s*[：:]\s*([\u4e00-\u9fff·]{2,6})(?:先生|女士)?",
            r"(?:主讲人|主讲嘉宾|分享嘉宾)\s*[：:]\s*(?:[^\n：:]{0,20}?基金经理\s*)?([\u4e00-\u9fff·]{2,6})(?:先生|女士)?",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, str(content or "")):
                line_start = str(content).rfind("\n", 0, match.start()) + 1
                line_end = str(content).find("\n", match.end())
                if line_end < 0:
                    line_end = min(len(str(content)), match.end() + 160)
                line = str(content)[line_start:line_end]
                prefix = str(content)[max(line_start, match.start() - 12):match.start()]
                if re.search(r"(?:历任|前任|原任|上一任|曾任)\s*$", prefix):
                    continue
                results.append((match.group(1), line))
        return results

    def _filename_candidates(self, stem: str) -> List[str]:
        candidates: List[str] = []
        for bracketed in re.findall(r"[【\[]([^】\]]{2,20})[】\]]", stem):
            candidates.extend(re.findall(r"[\u4e00-\u9fff·]{2,4}", re.split(r"[-—_（(]", bracketed)[0]))

        title_company_aliases = set(self.company_aliases)
        for title_alias in re.findall(r"([\u4e00-\u9fff]{2,8})基金", stem):
            if any(
                company_alias.startswith(title_alias) or title_alias.startswith(company_alias)
                for company_alias in self.company_aliases
            ):
                title_company_aliases.add(title_alias)
        for token in re.split(r"[-—_\s：:、，,【\]()（）]+", stem):
            if 2 <= len(token) <= 8 and any(
                company_alias.startswith(token)
                for company_alias in self.company_aliases
            ):
                title_company_aliases.add(token)

        stripped_title = stem
        for alias in sorted(title_company_aliases, key=len, reverse=True):
            if len(alias) < 2:
                continue
            stripped_title = re.sub(re.escape(f"{alias}基金"), "-", stripped_title)
            stripped_title = re.sub(re.escape(alias), "-", stripped_title)
        title_variants = [stripped_title]

        normalized_variants = []
        for value in title_variants:
            normalized = re.sub(r"[【\[](?:内部参考|周期|过审版|权益)[】\]]", "-", value)
            normalized = re.sub(r"^(?:19|20)?\d{4,8}[-_\s]*", "", normalized)
            normalized = re.sub(r"基金经理|基金", "-", normalized)
            normalized = re.sub(r"(?:一季报|二季报|三季报|四季报|半年报|年报)(?=(?:路演|交流|访谈|纪要))", "", normalized)
            normalized_variants.append(normalized)

        for variant in normalized_variants:
            for token in re.split(r"[-—_\s：:，,]+", variant):
                if not token:
                    continue
                token_candidates = []
                for part in re.split(r"[、&＆]+", token):
                    cleaned = re.sub(
                        r"(?:19|20)?\d{4,8}|Q[1-4]|过审版|内部参考|单页$|最新观点$|近期观点$",
                        "",
                        part,
                        flags=re.IGNORECASE,
                    )
                    cleaned = re.sub(
                        r"(?:总(?:[^-—_\s]{0,12})?(?:路演|交流|访谈|会议|纪要|介绍|观点)|"
                        r"路演|交流|调研|访谈|会议|纪要|报告|投资理念|投资风格|观点|近期|最新).*$",
                        "",
                        cleaned,
                    )
                    cleaned = re.sub(r"[（(].*$", "", cleaned)
                    normalized = self.normalize_candidate(cleaned)
                    if normalized and not any(
                        company_alias.startswith(normalized)
                        for company_alias in self.company_aliases
                    ):
                        token_candidates.append(normalized)
                if token_candidates:
                    candidates.extend(token_candidates)
                    break

            for match in re.finditer(
                r"([\u4e00-\u9fff·]{2,3})(?=[-_]?(?:19|20)?\d{4,8}(?:$|[^\d]))",
                variant,
            ):
                candidate = self.normalize_candidate(match.group(1))
                if candidate:
                    candidates.append(candidate)

        cue_pattern = "|".join(map(re.escape, self.TITLE_CUES))
        for variant in normalized_variants:
            for match in re.finditer(rf"([\u4e00-\u9fff·]{{2,4}})(?=(?:{cue_pattern}))", variant):
                candidates.append(match.group(1))
            for match in re.finditer(
                r"([\u4e00-\u9fff·]{2,3})(?=总[^-—_\s]{0,12}(?:路演|交流|访谈|会议|纪要|介绍|观点))",
                variant,
            ):
                candidates.append(match.group(1))
        return list(dict.fromkeys(candidates))

    def _valid_candidate(self, value: str) -> bool:
        if not value or value in self.GENERIC_NAMES or re.fullmatch(r"(?:19|20)\d{2}", value):
            return False
        if not re.fullmatch(r"[\u4e00-\u9fff·]{2,4}", value):
            return False
        if value in self.company_aliases:
            return False
        compound_surname = next((surname for surname in self.COMPOUND_SURNAMES if value.startswith(surname)), "")
        if compound_surname:
            if len(value) not in {3, 4}:
                return False
        elif len(value) not in {2, 3} or value[0] not in self.SURNAME_PREFIXES:
            return False
        if any(value.endswith(suffix) for suffix in ("基金", "公司", "团队", "策略", "纪要")):
            return False
        return True

    def _title_prefix_is_company(self, value: str) -> bool:
        prefix = re.split(r"[-—_\s【\[]", str(value or ""))[-1]
        return any(self._company_prefix_matches(prefix, alias) for alias in self.company_aliases)

    @staticmethod
    def _company_prefix_matches(value: str, alias: str) -> bool:
        return bool(alias and (value.endswith(alias) or value.endswith(f"{alias}基金")))

    @staticmethod
    def _clean_candidate(value: str) -> str:
        return re.sub(r"(?:先生|女士|老师|总)$", "", str(value or "").strip())

    @classmethod
    def _company_alias(cls, value: Any) -> str:
        company = str(value or "").strip()
        for suffix in (*cls.COMPANY_SUFFIXES, "有限责任公司", "资产管理"):
            if company.endswith(suffix):
                return company[:-len(suffix)]
        return company

    @staticmethod
    def _is_chinese(value: str) -> bool:
        return bool(re.fullmatch(r"[\u4e00-\u9fff]", value))
