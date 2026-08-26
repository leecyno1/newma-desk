"""Project reviewed research memo evidence into fund research profiles."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional


class ResearchMemoProfileProjectionService:
    """Build one fund profile from confirmed memo labels and standardized classification."""

    UPDATED_BY = "research_memo_profile_projection"
    MERGEABLE_UPDATERS = {UPDATED_BY, "manager-tenure-sync"}
    PROFILE_KINDS = {"style_label", "classification", "tag"}

    def __init__(
        self,
        report_repo: Any,
        profile_repo: Optional[Any] = None,
        classification_adapter: Optional[Any] = None,
    ):
        self.report_repo = report_repo
        self._profile_repo = profile_repo
        self._classification_adapter = classification_adapter

    def project_report(
        self,
        report: Dict[str, Any],
        affected_fund_ids: List[str],
    ) -> Dict[str, Any]:
        fund_ids = list(dict.fromkeys(
            str(fund_id or "").strip().upper()
            for fund_id in affected_fund_ids
            if str(fund_id or "").strip()
        ))
        results = []
        projected_entities = set()
        for fund_id in fund_ids:
            context = self._get_classification_adapter().get_classification_context(fund_id) or {}
            entity_key = str(context.get("canonical_code") or fund_id).strip().upper()
            if entity_key in projected_entities:
                continue
            projected_entities.add(entity_key)
            results.append(self._project_fund(fund_id, report, context))
        return {
            "updated_by": self.UPDATED_BY,
            "funds": results,
            "projected_count": sum(item["status"] == "projected" for item in results),
            "deleted_count": sum(item["status"] == "deleted" for item in results),
            "cleared_count": sum(item["status"] == "cleared" for item in results),
            "skipped_count": sum(item["status"] == "skipped" for item in results),
        }

    def _project_fund(
        self,
        wind_code: str,
        current_report: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        classification_adapter = self._get_classification_adapter()
        profile_wind_code = str(context.get("canonical_code") or wind_code).strip().upper()
        profile_repo = self._get_profile_repo()
        existing = profile_repo.get_profile(profile_wind_code)
        if existing and existing.get("updated_by") not in self.MERGEABLE_UPDATERS:
            return {
                "wind_code": profile_wind_code,
                "source_wind_code": wind_code,
                "status": "skipped",
                "reason": "manual_profile_preserved",
            }

        entity_fund_ids = classification_adapter.list_entity_share_codes(wind_code)
        entity_fund_ids = list(dict.fromkeys([
            *entity_fund_ids,
            wind_code,
            profile_wind_code,
        ]))
        alias_cleanup_count = self._clear_alias_profiles(
            profile_repo,
            entity_fund_ids,
            profile_wind_code,
        )
        reports = self._reports_for_fund(entity_fund_ids, current_report)
        confirmed = self._confirmed_profile_items(reports, entity_fund_ids)
        style_labels = [item["value"] for item in confirmed if item["kind"] == "style_label"]
        if not style_labels:
            if (
                existing
                and existing.get("manager_tenure_start")
                and profile_repo.clear_projected_style(profile_wind_code, self.UPDATED_BY)
            ):
                return {"wind_code": profile_wind_code, "status": "cleared", "reason": "no_confirmed_style_label", "alias_cleanup_count": alias_cleanup_count}
            if existing and profile_repo.delete_projected_profile(profile_wind_code, self.UPDATED_BY):
                return {"wind_code": profile_wind_code, "status": "deleted", "reason": "no_confirmed_style_label", "alias_cleanup_count": alias_cleanup_count}
            return {"wind_code": profile_wind_code, "status": "skipped", "reason": "no_confirmed_style_label", "alias_cleanup_count": alias_cleanup_count}

        style_counts = Counter(style_labels)
        style_recency = {
            label: max(
                str(item.get("report_date") or item.get("updated_at") or "")
                for item in confirmed
                if item["kind"] == "style_label" and item["value"] == label
            )
            for label in style_counts
        }
        ranked_styles = sorted(style_counts)
        ranked_styles.sort(key=lambda label: style_recency[label], reverse=True)
        ranked_styles.sort(key=lambda label: style_counts[label], reverse=True)
        primary_style = ranked_styles[0]

        benchmark = context.get("benchmark_mapping") or {}
        peer_group = context.get("peer_group_name") or context.get("peer_group_key")
        primary_benchmark = benchmark.get("benchmark_name") or benchmark.get("benchmark_code")
        if context.get("status") != "resolved" or not peer_group or not primary_benchmark:
            return {
                "wind_code": profile_wind_code,
                "source_wind_code": wind_code,
                "status": "skipped",
                "reason": "standardized_classification_unavailable",
                "missing_items": context.get("missing_items") or [],
                "alias_cleanup_count": alias_cleanup_count,
            }

        classifications = self._unique_values(confirmed, "classification")
        tags = self._unique_values(confirmed, "tag")
        strategy_tags = list(dict.fromkeys([*ranked_styles, *classifications, *tags]))
        evidence = {
            **((existing or {}).get("evidence") or {}),
            "source": self.UPDATED_BY,
            "fund_entity": {
                "canonical_code": profile_wind_code,
                "linked_share_codes": entity_fund_ids,
            },
            "primary_style": {
                "value": primary_style,
                "confirmed_report_count": style_counts[primary_style],
            },
            "research_memos": confirmed,
            "classification": {
                "status": context.get("status"),
                "peer_group_key": context.get("peer_group_key"),
                "peer_group_name": context.get("peer_group_name"),
                "benchmark_code": benchmark.get("benchmark_code"),
                "benchmark_name": benchmark.get("benchmark_name"),
                "evidence": context.get("classification_evidence") or [],
            },
        }
        profile = profile_repo.upsert_profile(
            wind_code=profile_wind_code,
            primary_benchmark=primary_benchmark,
            peer_group=peer_group,
            style_label=primary_style,
            strategy_tags=strategy_tags,
            manager_tenure_start=existing.get("manager_tenure_start") if existing else None,
            capacity_notes=existing.get("capacity_notes") if existing else None,
            data_quality_notes="风格标签来自人工确认且明确指向该产品的调研纪要；同类组和基准来自基金分类目录",
            evidence=evidence,
            updated_by=self.UPDATED_BY,
        )
        return {
            "wind_code": profile_wind_code,
            "source_wind_code": wind_code,
            "status": "projected",
            "profile": profile,
            "alias_cleanup_count": alias_cleanup_count,
        }

    def _clear_alias_profiles(
        self,
        profile_repo: Any,
        entity_fund_ids: List[str],
        canonical_code: str,
    ) -> int:
        cleared = 0
        for alias in entity_fund_ids:
            normalized = str(alias or "").strip().upper()
            if not normalized or normalized == canonical_code:
                continue
            profile = profile_repo.get_profile(normalized)
            if not profile or profile.get("updated_by") != self.UPDATED_BY:
                continue
            if profile.get("manager_tenure_start") and profile_repo.clear_projected_style(normalized, self.UPDATED_BY):
                cleared += 1
            elif profile_repo.delete_projected_profile(normalized, self.UPDATED_BY):
                cleared += 1
        return cleared

    def _reports_for_fund(
        self,
        wind_codes: List[str],
        current_report: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        reports: Dict[str, Dict[str, Any]] = {}
        for wind_code in wind_codes:
            reports.update({
                str(item.get("id")): item
                for item in self.report_repo.list_reports_for_fund(wind_code)
                if item.get("id")
            })
        current_fund_ids = {
            str(fund_id or "").strip().upper()
            for fund_id in current_report.get("fund_ids", [])
        }
        if current_fund_ids.intersection(wind_codes):
            reports[str(current_report.get("id"))] = current_report
        return list(reports.values())

    def _confirmed_profile_items(
        self,
        reports: List[Dict[str, Any]],
        entity_fund_ids: List[str],
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        target_codes = {
            str(fund_id or "").strip().upper()
            for fund_id in entity_fund_ids
            if str(fund_id or "").strip()
        }
        field_by_kind = {
            "style_label": "style_labels",
            "classification": "classifications",
            "tag": "tags",
        }
        for report in reports:
            confirmed_fields = {
                kind: set(report.get(field_name) or [])
                for kind, field_name in field_by_kind.items()
            }
            for proposal in report.get("review_proposals", []):
                kind = proposal.get("kind")
                value = str(proposal.get("value") or "").strip()
                if (
                    proposal.get("review_status") != "confirmed"
                    or kind not in self.PROFILE_KINDS
                    or value not in confirmed_fields[kind]
                    or not target_codes.intersection(
                        str(code or "").strip().upper()
                        for code in (proposal.get("target_fund_ids") or [])
                    )
                ):
                    continue
                source_ref = proposal.get("source_ref") or {}
                items.append({
                    "report_id": report.get("id"),
                    "report_title": report.get("title"),
                    "report_date": report.get("report_date"),
                    "updated_at": report.get("updated_at"),
                    "kind": kind,
                    "value": value,
                    "confidence": proposal.get("confidence"),
                    "review_status": "confirmed",
                    "reviewed_at": proposal.get("reviewed_at"),
                    "relative_path": source_ref.get("relative_path") or report.get("local_relative_path"),
                    "source_path": source_ref.get("source_path") or report.get("local_source_path"),
                    "excerpt": source_ref.get("excerpt"),
                    "scope": "fund",
                    "target_fund_ids": proposal.get("target_fund_ids") or [],
                })
        return items

    @staticmethod
    def _unique_values(items: List[Dict[str, Any]], kind: str) -> List[str]:
        return list(dict.fromkeys(item["value"] for item in items if item["kind"] == kind))

    def _get_profile_repo(self):
        if self._profile_repo is None:
            from repositories import get_research_profile_repo

            self._profile_repo = get_research_profile_repo()
        return self._profile_repo

    def _get_classification_adapter(self):
        if self._classification_adapter is None:
            from repositories import get_fund_classification_repo

            self._classification_adapter = get_fund_classification_repo()
        return self._classification_adapter
