"""Offline identity backfill for manager memo candidates."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Optional


class ResearchMemoManagerIdentitySyncService:
    """Resolve only exact, unique Tushare identities and persist their audit trail."""

    ACCEPTED_SOURCES = {
        "explicit_field",
        "manager_catalog_title",
        "filename_pattern",
        "llm",
    }
    COMPANY_ALIAS_CANONICAL = {
        "兴全": "兴证全球",
        "信澳": "信达澳亚",
        "上投摩根": "摩根",
        "泰达宏利": "宏利",
        "景顺": "景顺长城",
        "工银": "工银瑞信",
        "中邮": "中邮创业",
    }

    def __init__(
        self,
        data_service: Any,
        report_repo: Any,
        manager_repo: Any,
        fund_repo: Optional[Any] = None,
        company_names: Iterable[str] = (),
    ):
        self.data_service = data_service
        self.report_repo = report_repo
        self.manager_repo = manager_repo
        self._fund_repo = fund_repo
        self.company_aliases = {
            alias
            for company in company_names
            if len(alias := self._company_alias(company)) >= 2
        }

    def sync_pending(
        self,
        folder_id: Optional[str] = None,
        limit: int = 200,
        apply: bool = False,
    ) -> Dict[str, Any]:
        pending = [
            item
            for item in self.report_repo.list_pending_reviews(folder_id)
            if item.get("kind") == "manager"
            and item.get("extraction_source") in self.ACCEPTED_SOURCES
            and str(item.get("value") or "").strip()
            and str(item.get("report_date_source") or "") in {"filename", "content"}
        ]
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for item in pending:
            by_name.setdefault(str(item.get("value") or "").strip(), []).append(item)
        names = sorted(
            by_name,
            key=lambda name: max(float(item.get("confidence") or 0) for item in by_name[name]),
            reverse=True,
        )[:max(1, int(limit))]

        results = []
        persisted = 0
        persisted_tenure_count = 0
        updated_proposals = 0
        updated_fund_assignments = 0
        missing_local_fund_count = 0
        for name in names:
            identities = self.data_service.get_manager_identity_candidates(name)
            if not identities:
                results.append({"name": name, "status": "not_found"})
                continue
            identity_context = {
                str(identity.get("manager_id") or ""): {
                    "identity": identity,
                    "company": self._resolve_company(identity)[0],
                }
                for identity in identities
                if str(identity.get("manager_id") or "")
            }
            proposals_by_identity: Dict[str, List[Dict[str, Any]]] = {}
            ambiguous_proposals = 0
            company_mismatch_proposals = 0
            identity_conflict_proposals = 0
            for proposal in by_name[name]:
                matched_ids = []
                for manager_id, context in identity_context.items():
                    if self._proposal_identity_conflict(
                        proposal,
                        context["identity"],
                        context["company"],
                    ):
                        identity_conflict_proposals += 1
                        continue
                    if self._proposal_matches_company(
                        proposal,
                        context["identity"],
                        context["company"],
                    ):
                        matched_ids.append(manager_id)
                if len(matched_ids) == 1:
                    proposals_by_identity.setdefault(matched_ids[0], []).append(proposal)
                elif len(matched_ids) > 1:
                    ambiguous_proposals += 1
                else:
                    company_mismatch_proposals += 1

            if not proposals_by_identity:
                results.append({
                    "name": name,
                    "status": (
                        "identity_conflict" if identity_conflict_proposals
                        else "ambiguous" if ambiguous_proposals
                        else "company_mismatch"
                    ),
                    "identity_count": len(identities),
                    "proposal_count": len(by_name[name]),
                    "ambiguous_proposal_count": ambiguous_proposals,
                    "company_mismatch_proposal_count": company_mismatch_proposals,
                    "identity_conflict_proposal_count": identity_conflict_proposals,
                })
                continue

            identity_results = []
            persistence_failed = False
            for manager_id, eligible_proposals in proposals_by_identity.items():
                context = identity_context[manager_id]
                identity = context["identity"]
                company = context["company"]
                saved = True
                fund_sync = {"updated": 0, "missing": 0}
                tenure_count = 0
                if apply:
                    saved = self.manager_repo.upsert_manager(manager_id, {
                        "name": name,
                        "company": company,
                        "education": identity.get("education") or "",
                        "experience_years": self._experience_years(identity.get("tenures") or []),
                        "management_years": self._experience_years(identity.get("tenures") or []),
                        "current_funds": identity.get("current_funds") or [],
                        "historical_performance": {
                            "tenure_count": len(identity.get("tenures") or []),
                            "source": "tushare.fund_manager",
                        },
                        "raw_data": {
                            "source": "tushare.fund_manager",
                            "identity_backfill": True,
                            "gender": identity.get("gender"),
                            "birth_year": identity.get("birth_year"),
                            "synced_at": self._now(),
                        },
                    })
                    if saved:
                        tenures = self._local_tenures(identity)
                        if self.manager_repo.replace_fund_tenures(manager_id, tenures):
                            tenure_count = len(tenures)
                            persisted_tenure_count += tenure_count
                        updated_proposals += self._bind_proposals(eligible_proposals, identity, company)
                        fund_sync = self._sync_current_funds(identity)
                        updated_fund_assignments += fund_sync["updated"]
                        missing_local_fund_count += fund_sync["missing"]
                        persisted += 1
                    else:
                        persistence_failed = True

                identity_results.append({
                    "manager_id": manager_id,
                    "company": company,
                    "current_fund_count": len(identity.get("current_funds") or []),
                    "fund_assignment_count": fund_sync["updated"],
                    "tenure_count": tenure_count,
                    "proposal_count": len(eligible_proposals),
                })

            resolved_proposals = sum(item["proposal_count"] for item in identity_results)
            fully_resolved = resolved_proposals == len(by_name[name])
            results.append({
                "name": name,
                "status": (
                    "persistence_failed" if persistence_failed
                    else "resolved" if fully_resolved
                    else "partially_resolved"
                ),
                "identity_count": len(identity_results),
                "identities": identity_results,
                "proposal_count": resolved_proposals,
                "ambiguous_proposal_count": ambiguous_proposals,
                "company_mismatch_proposal_count": company_mismatch_proposals,
                "identity_conflict_proposal_count": identity_conflict_proposals,
            })

        return {
            "mode": "apply" if apply else "preview",
            "pending_proposal_count": len(pending),
            "requested_name_count": len(names),
            "resolved_name_count": sum(item["status"] in {"resolved", "partially_resolved"} for item in results),
            "partially_resolved_name_count": sum(item["status"] == "partially_resolved" for item in results),
            "ambiguous_name_count": sum(item["status"] == "ambiguous" for item in results),
            "identity_conflict_name_count": sum(item["status"] == "identity_conflict" for item in results),
            "not_found_name_count": sum(item["status"] == "not_found" for item in results),
            "company_mismatch_name_count": sum(item["status"] == "company_mismatch" for item in results),
            "persisted_manager_count": persisted,
            "persisted_tenure_count": persisted_tenure_count,
            "updated_proposal_count": updated_proposals,
            "updated_fund_assignment_count": updated_fund_assignments,
            "missing_local_fund_count": missing_local_fund_count,
            "results": results,
        }

    def audit_confirmed(
        self,
        folder_id: Optional[str] = None,
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Backfill evidence grades for confirmed manager links and reopen only real conflicts."""
        reports = self.report_repo.list_manager_review_reports(folder_id)
        identities_by_name: Dict[str, List[Dict[str, Any]]] = {}
        verified = 0
        incomplete = 0
        reopened = 0
        updated = 0
        affected_manager_ids: set[str] = set()
        attention_items: List[Dict[str, Any]] = []

        for source_report in reports:
            report = deepcopy(source_report)
            proposals = list(report.get("review_proposals") or [])
            changed = False
            reopened_manager_names: set[str] = set()
            reopened_manager_ids: set[str] = set()
            for proposal in proposals:
                if proposal.get("kind") != "manager" or proposal.get("review_status") != "confirmed":
                    continue
                manager_name = str(proposal.get("value") or "").strip()
                identities = identities_by_name.setdefault(
                    manager_name,
                    self._local_identity_candidates(manager_name)
                    or self.data_service.get_manager_identity_candidates(manager_name),
                )
                verification = self._audit_verification(report, proposal, identities)
                status = verification["status"]
                if status == "unique_exact_name":
                    verified += 1
                elif status == "identity_conflict":
                    reopened += 1
                    reopened_manager_names.add(manager_name)
                    reopened_manager_ids.add(str(proposal.get("candidate_id") or "").strip())
                    attention_items.append(self._attention_item(report, proposal, verification))
                else:
                    incomplete += 1
                    attention_items.append(self._attention_item(report, proposal, verification))

                if proposal.get("identity_verification") != verification:
                    proposal["identity_verification"] = verification
                    changed = True
                if status == "identity_conflict":
                    proposal["review_status"] = "pending"
                    proposal["reopened_at"] = verification["verified_at"]
                    changed = True

            if not apply or not changed:
                continue

            for manager_id in reopened_manager_ids:
                if manager_id:
                    self.report_repo.remove_report_manager_link(str(report.get("id") or ""), manager_id)
                    affected_manager_ids.add(manager_id)

            fund_ids = list(report.get("fund_ids") or [])
            if reopened_manager_names:
                for proposal in proposals:
                    source_ref = proposal.get("source_ref") or {}
                    if (
                        proposal.get("kind") == "fund"
                        and proposal.get("extraction_source") == "tushare.fund_manager"
                        and str(source_ref.get("manager_name") or "").strip() in reopened_manager_names
                    ):
                        proposal["review_status"] = "pending"
                        proposal["reopened_at"] = self._now()
                        value = str(proposal.get("value") or "").strip()
                        if value and not any(
                            other is not proposal
                            and other.get("kind") == "fund"
                            and other.get("review_status") == "confirmed"
                            and str(other.get("value") or "").strip() == value
                            for other in proposals
                        ):
                            fund_ids = [item for item in fund_ids if item != value]

            links = self.report_repo.list_report_manager_links(str(report.get("id") or ""))
            self.report_repo.update_report(str(report.get("id") or ""), {
                "manager_id": links[0]["manager_id"] if len(links) == 1 else "",
                "manager_name": links[0]["manager_name"] if len(links) == 1 else "",
                "fund_ids": fund_ids,
                "review_proposals": proposals,
                "review_status": "pending" if any(
                    item.get("review_status") == "pending" for item in proposals
                ) else "reviewed",
                "updated_at": self._now(),
            })
            updated += 1

        return {
            "mode": "apply" if apply else "preview",
            "confirmed_proposal_count": verified + incomplete + reopened,
            "verified_count": verified,
            "evidence_incomplete_count": incomplete,
            "reopened_conflict_count": reopened,
            "updated_report_count": updated,
            "affected_manager_ids": sorted(item for item in affected_manager_ids if item),
            "attention_items": attention_items,
        }

    def _audit_verification(
        self,
        report: Dict[str, Any],
        proposal: Dict[str, Any],
        identities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        verified_at = self._now()
        manager_name = str(proposal.get("value") or "").strip()
        candidate_id = str(proposal.get("candidate_id") or "").strip()
        source_ref = proposal.get("source_ref") or {}
        evidence = " ".join(filter(None, [
            str(report.get("title") or ""),
            str(report.get("local_relative_path") or ""),
            str(source_ref.get("relative_path") or ""),
            str(source_ref.get("excerpt") or ""),
        ]))
        evidence_companies = self._evidence_company_aliases(evidence)
        report_date_source = str(report.get("report_date_source") or "unknown")
        report_date = self._date(report.get("report_date")) if report_date_source in {"filename", "content"} else None
        candidate_matches = [
            identity for identity in identities
            if str(identity.get("manager_id") or "").strip() == candidate_id
        ]
        base = {
            "source": "tushare.fund_manager",
            "verified_at": verified_at,
            "manager_name": manager_name,
            "candidate_id": candidate_id or None,
            "report_date_source": report_date_source,
            "report_date_precision": str(report.get("report_date_precision") or "unknown"),
            "evidence_companies": sorted(evidence_companies),
        }
        if not candidate_id:
            return {**base, "status": "identity_conflict", "reason": "missing_candidate_id"}
        if not identities:
            return {
                **base,
                "status": "exact_name_evidence_incomplete",
                "missing_evidence": ["identity_catalog"],
            }
        if len(candidate_matches) != 1:
            return {
                **base,
                "status": "identity_conflict",
                "reason": "candidate_not_unique",
                "candidate_count": len(identities),
            }

        candidate = candidate_matches[0]
        primary_company = self._resolve_company(candidate)[0]
        all_candidate_companies = self._identity_company_aliases(candidate, primary_company)
        active_companies = (
            self._identity_company_aliases(candidate, primary_company, report_date=report_date)
            if report_date else set()
        )
        base.update({
            "candidate_companies": sorted(all_candidate_companies),
            "active_companies": sorted(active_companies),
        })
        if report_date and len(active_companies) > 1:
            return {
                **base,
                "status": "identity_conflict",
                "reason": "same_name_multiple_active_companies",
            }

        comparison_companies = active_companies or all_candidate_companies
        if evidence_companies and comparison_companies and not evidence_companies.intersection(comparison_companies):
            return {
                **base,
                "status": "identity_conflict",
                "reason": "company_mismatch",
            }

        if len(identities) > 1:
            matched_ids = {
                str(identity.get("manager_id") or "").strip()
                for identity in identities
                if self._proposal_matches_company(proposal, identity, self._resolve_company(identity)[0])
            }
            if matched_ids != {candidate_id}:
                return {
                    **base,
                    "status": "identity_conflict",
                    "reason": "same_name_ambiguous",
                    "matched_candidate_count": len(matched_ids),
                }

        missing_evidence = []
        if not report_date:
            missing_evidence.append("report_date")
        if not evidence_companies:
            missing_evidence.append("company")
        if evidence_companies and not comparison_companies:
            missing_evidence.append("company_tenure")
        if missing_evidence:
            return {
                **base,
                "status": "exact_name_evidence_incomplete",
                "missing_evidence": missing_evidence,
            }
        return {
            **base,
            "status": "unique_exact_name",
            "company": next(iter(sorted(evidence_companies.intersection(comparison_companies))), None),
        }

    def _local_identity_candidates(self, manager_name: str) -> List[Dict[str, Any]]:
        try:
            catalog = self.manager_repo.list_identity_catalog()
        except (AttributeError, TypeError):
            return []
        identities = []
        for item in catalog:
            if str(item.get("name") or "").strip() != manager_name:
                continue
            manager_id = str(item.get("wind_code") or item.get("manager_id") or "").strip()
            if not manager_id:
                continue
            try:
                tenures = self.manager_repo.list_fund_tenures(manager_id)
            except (AttributeError, TypeError):
                tenures = []
            identities.append({
                "manager_id": manager_id,
                "name": manager_name,
                "company": item.get("company") or "",
                "current_funds": [
                    str(tenure.get("fund_code") or "").strip()
                    for tenure in tenures
                    if tenure.get("is_current") and str(tenure.get("fund_code") or "").strip()
                ],
                "tenures": tenures,
                "source": "local_manager_fund_tenures",
            })
        return identities

    @staticmethod
    def _attention_item(
        report: Dict[str, Any],
        proposal: Dict[str, Any],
        verification: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "report_id": str(report.get("id") or ""),
            "relative_path": report.get("local_relative_path"),
            "manager_name": proposal.get("value"),
            "candidate_id": proposal.get("candidate_id"),
            "status": verification.get("status"),
            "reason": verification.get("reason"),
            "missing_evidence": verification.get("missing_evidence") or [],
        }

    def _sync_current_funds(self, identity: Dict[str, Any]) -> Dict[str, int]:
        manager_id = str(identity.get("manager_id") or "").strip()
        if not manager_id:
            return {"updated": 0, "missing": 0}
        updated = 0
        missing = 0
        for fund_code in list(dict.fromkeys(identity.get("current_funds") or [])):
            code = str(fund_code or "").strip().upper()
            fund = self.fund_repo.get_fund(code)
            if not fund:
                missing += 1
                continue
            manager_ids = list(dict.fromkeys([*(fund.get("manager_ids") or []), manager_id]))
            if manager_ids == list(fund.get("manager_ids") or []):
                continue
            saved = self.fund_repo.update_manager_assignments(code, manager_ids, {
                "source": "tushare.fund_manager",
                "identity_backfill": True,
                "manager_ids": manager_ids,
                "synced_at": self._now(),
            })
            updated += int(bool(saved))
        return {"updated": updated, "missing": missing}

    def _local_tenures(self, identity: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for tenure in identity.get("tenures") or []:
            code = str(tenure.get("fund_code") or "").strip().upper()
            start_date = str(tenure.get("start_date") or "")[:10]
            if not code or not start_date:
                continue
            fund = self.fund_repo.get_fund(code)
            if not fund:
                continue
            rows.append({
                "fund_code": code,
                "fund_name": fund.get("name") or tenure.get("fund_name") or code,
                "start_date": start_date,
                "end_date": str(tenure.get("end_date") or "")[:10] or None,
                "is_current": bool(tenure.get("is_current")),
                "performance_snapshot": {
                    "status": "pending_nav_metrics",
                    "source": "tushare.fund_manager",
                },
                "source": "tushare.fund_manager",
                "raw_data": tenure,
            })
        return rows

    def _bind_proposals(
        self,
        proposals: List[Dict[str, Any]],
        identity: Dict[str, Any],
        company: str,
    ) -> int:
        reports: Dict[str, Dict[str, Any]] = {}
        proposal_ids_by_report: Dict[str, set[str]] = {}
        for item in proposals:
            report_id = str(item.get("report_id") or "").strip()
            proposal_id = str(item.get("id") or "").strip()
            if report_id and proposal_id:
                proposal_ids_by_report.setdefault(report_id, set()).add(proposal_id)

        updated = 0
        verified_at = self._now()
        for report_id, proposal_ids in proposal_ids_by_report.items():
            report = reports.setdefault(report_id, self.report_repo.get_report(report_id))
            if not report:
                continue
            changed = 0
            review_proposals = list(report.get("review_proposals") or [])
            for proposal in review_proposals:
                if str(proposal.get("id") or "") not in proposal_ids:
                    continue
                proposal["candidate_id"] = identity.get("manager_id")
                proposal["identity_verification"] = {
                    "status": "unique_exact_name",
                    "source": "tushare.fund_manager",
                    "verified_at": verified_at,
                    "company": company or None,
                }
                changed += 1
            if changed:
                self.report_repo.update_report(report_id, {
                    "review_proposals": review_proposals,
                    "updated_at": verified_at,
                })
                updated += changed
        return updated

    def _resolve_company(self, identity: Dict[str, Any]) -> tuple[str, str]:
        tenures = identity.get("tenures") or []
        current_companies = {
            company
            for tenure in tenures
            if tenure.get("is_current")
            if (company := self._fund_company(str(tenure.get("fund_code") or "")))
        }
        if len(current_companies) > 1:
            return "", "ambiguous_current_company"
        if len(current_companies) == 1:
            return next(iter(current_companies)), "current_fund"
        for tenure in sorted(tenures, key=lambda item: str(item.get("start_date") or ""), reverse=True):
            company = self._fund_company(str(tenure.get("fund_code") or ""))
            if company:
                return company, "latest_fund"
        return "", "unavailable"

    def _identity_company_aliases(
        self,
        identity: Dict[str, Any],
        primary_company: str,
        report_date: Optional[datetime] = None,
    ) -> set[str]:
        tenures = identity.get("tenures") or []
        if report_date is not None:
            active_tenures = [
                tenure
                for tenure in tenures
                if self._tenure_active_on(tenure, report_date)
            ]
            companies = [
                self._fund_company(str(tenure.get("fund_code") or ""))
                for tenure in active_tenures
            ]
        else:
            companies = [primary_company]
            companies.extend(
                self._fund_company(str(tenure.get("fund_code") or ""))
                for tenure in tenures
            )
        return {
            self._canonical_company_alias(alias)
            for company in companies
            if len(alias := self._company_alias(company)) >= 2
        }

    def _proposal_matches_company(
        self,
        proposal: Dict[str, Any],
        identity: Dict[str, Any],
        primary_company: str,
    ) -> bool:
        source_ref = proposal.get("source_ref") or {}
        evidence = " ".join(filter(None, [
            str(proposal.get("report_title") or ""),
            str(source_ref.get("relative_path") or ""),
            str(source_ref.get("excerpt") or ""),
        ]))
        evidence_aliases = self._evidence_company_aliases(evidence)
        if not evidence_aliases:
            return True
        report_date = self._date(proposal.get("report_date"))
        identity_company_aliases = self._identity_company_aliases(
            identity,
            primary_company,
            report_date=report_date,
        )
        return bool(evidence_aliases.intersection(identity_company_aliases))

    def _proposal_identity_conflict(
        self,
        proposal: Dict[str, Any],
        identity: Dict[str, Any],
        primary_company: str,
    ) -> bool:
        report_date = self._date(proposal.get("report_date"))
        if report_date is None:
            return False
        active_companies = self._identity_company_aliases(
            identity,
            primary_company,
            report_date=report_date,
        )
        return len(active_companies) > 1

    def _evidence_company_aliases(self, evidence: str) -> set[str]:
        matched = {alias for alias in self.company_aliases if alias in str(evidence or "")}
        for alias in self.COMPANY_ALIAS_CANONICAL:
            if alias in str(evidence or ""):
                matched.add(alias)
        return {
            self._canonical_company_alias(alias)
            for alias in matched
            if not any(alias != other and alias in other for other in matched)
        }

    @classmethod
    def _canonical_company_alias(cls, alias: str) -> str:
        return cls.COMPANY_ALIAS_CANONICAL.get(str(alias or "").strip(), str(alias or "").strip())

    @classmethod
    def _tenure_active_on(cls, tenure: Dict[str, Any], report_date: datetime) -> bool:
        start = cls._date(tenure.get("start_date"))
        end = cls._date(tenure.get("end_date"))
        return bool(start and start <= report_date and (end is None or report_date <= end))

    @staticmethod
    def _date(value: Any) -> Optional[datetime]:
        text = str(value or "").strip()[:10]
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _fund_company(self, fund_code: str) -> str:
        if not fund_code:
            return ""
        fund = self.fund_repo.get_fund(fund_code) or {}
        raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
        for value in (
            fund.get("company"),
            raw_data.get("company"),
            (raw_data.get("universe") or {}).get("company") if isinstance(raw_data.get("universe"), dict) else None,
            (raw_data.get("universe") or {}).get("manager") if isinstance(raw_data.get("universe"), dict) else None,
            (raw_data.get("info") or {}).get("company") if isinstance(raw_data.get("info"), dict) else None,
        ):
            company = str(value or "").strip()
            if company:
                return company
        return ""

    @staticmethod
    def _company_alias(value: Any) -> str:
        company = str(value or "").strip()
        for suffix in (
            "基金管理有限责任公司", "基金管理股份有限公司", "基金管理有限公司",
            "基金管理", "资产管理有限公司",
            "投资管理有限公司", "股份有限公司", "有限责任公司", "有限公司",
            "资产管理", "基金",
        ):
            if company.endswith(suffix):
                return company[:-len(suffix)]
        return company

    @staticmethod
    def _experience_years(tenures: List[Dict[str, Any]]) -> float:
        starts = sorted(str(item.get("start_date") or "")[:10] for item in tenures if item.get("start_date"))
        if not starts:
            return 0.0
        try:
            start = datetime.fromisoformat(starts[0]).date()
        except ValueError:
            return 0.0
        return round(max(0, (datetime.now(UTC).date() - start).days) / 365.25, 2)

    @property
    def fund_repo(self):
        if self._fund_repo is None:
            from repositories import get_fund_repo

            self._fund_repo = get_fund_repo()
        return self._fund_repo

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
