import secrets
from datetime import datetime, timedelta, timezone

from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.schemas import ModuleWikiProfile
from vibe_visualization_api.data_services.client import (
    DataServiceClient,
    DataServiceClientError,
)
from vibe_visualization_api.data_services.registry import (
    DataServiceRegistry,
    DataServiceRegistryError,
)
from vibe_visualization_api.wiki.models import (
    WikiHandoff,
    WikiHandoffCreate,
    WikiLink,
    WikiLinkMatch,
    WikiLinkResolutionRequest,
    WikiLinkResolutionResponse,
    WikiModProfileResponse,
    WikiPageContext,
    WikiSubjectMatch,
    WikiSubjectRef,
)
from vibe_visualization_api.wiki.store import WikiHandoffStore, WikiSubjectStore


INTENT_COMPLEMENTS: dict[str, set[str]] = {
    "market.overview": {
        "event.timeline",
        "market.sentiment",
        "news.monitor",
        "technical.structure",
        "equity.research",
        "industry.chain",
        "fund.research",
    },
    "market.sentiment": {
        "market.overview",
        "technical.structure",
        "capital.flow",
        "news.monitor",
    },
    "event.timeline": {
        "market.overview",
        "news.monitor",
        "technical.structure",
        "fund.research",
    },
    "news.monitor": {
        "market.overview",
        "event.timeline",
        "equity.research",
        "fund.research",
    },
    "technical.structure": {
        "market.overview",
        "market.sentiment",
        "event.timeline",
        "fund.research",
    },
    "equity.research": {
        "market.overview",
        "news.monitor",
        "industry.chain",
    },
    "industry.chain": {"market.overview", "equity.research", "news.monitor"},
    "fund.research": {
        "market.overview",
        "event.timeline",
        "news.monitor",
        "technical.structure",
    },
    "policy.monitor": {
        "market.overview",
        "event.timeline",
        "news.monitor",
        "capital.flow",
        "equity.research",
        "industry.chain",
    },
}


class WikiModuleNotFoundError(KeyError):
    pass


class WikiEntrypointUnavailableError(ValueError):
    pass


def _data_capabilities(manifest: dict[str, object]) -> list[str]:
    actions = manifest.get("actions")
    if not isinstance(actions, dict):
        return []
    capabilities: set[str] = set()
    for action_id, raw_action in actions.items():
        if not isinstance(action_id, str) or not isinstance(raw_action, dict):
            continue
        binding = raw_action.get("binding")
        if not isinstance(binding, dict) or binding.get("type") != "data":
            continue
        capability = binding.get("capability")
        capabilities.add(capability if isinstance(capability, str) else action_id)
    return sorted(capabilities)


def _concept_slug(canonical_id: str) -> str:
    return canonical_id.rsplit(":", 1)[-1].casefold()


class WikiService:
    def __init__(
        self,
        repository: ModuleRepository,
        data_registry: DataServiceRegistry,
        data_client: DataServiceClient,
        handoff_store: WikiHandoffStore,
        subject_store: WikiSubjectStore,
    ):
        self._repository = repository
        self._data_registry = data_registry
        self._data_client = data_client
        self._handoff_store = handoff_store
        self._subject_store = subject_store

    def _index_context(self, context: WikiPageContext) -> None:
        for subject in [context.primary_subject, *context.related_subjects]:
            self._subject_store.upsert(
                subject,
                concept_ids=(
                    context.concept_ids
                    if subject.canonical_id == context.primary_subject.canonical_id
                    else []
                ),
                source="mod-context",
            )

    async def search_subjects(
        self,
        query: str,
        *,
        subject_type: str | None = None,
        market: str | None = None,
        limit: int = 12,
    ) -> list[WikiSubjectMatch]:
        local = self._subject_store.search(
            query,
            subject_type=subject_type,
            market=market,
            limit=limit,
        )
        if local and local[0].matched_by != "upstream":
            return local
        if subject_type not in {None, "security", "etf", "fund"}:
            return local
        try:
            provider = self._data_registry.resolve("market.symbol-search")
            result = await self._data_client.invoke(
                provider,
                "market.symbol-search",
                {"query": query, "market": market or "ALL", "limit": limit},
            )
        except (DataServiceClientError, DataServiceRegistryError, KeyError, ValueError):
            return local
        payload = result.get("data") if isinstance(result, dict) else None
        rows = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return local

        normalized_subjects: list[WikiSubjectRef] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            asset_type = str(row.get("assetType") or "stock").casefold()
            wiki_type = {
                "stock": "security",
                "etf": "etf",
                "fund": "fund",
            }.get(asset_type)
            row_market = str(row.get("market") or "").upper()
            symbol = str(row.get("symbol") or "").strip().upper()
            name = str(row.get("name") or symbol).strip()
            if (
                wiki_type is None
                or row_market not in {"CN", "HK", "US"}
                or not symbol
                or not name
                or (subject_type and wiki_type != subject_type)
                or (market and row_market != market)
            ):
                continue
            subject = WikiSubjectRef(
                type=wiki_type,
                canonicalId=f"{wiki_type}:{row_market}:{symbol}",
                displayName=name,
                market=row_market,
                symbol=symbol,
                assetType=asset_type,
            )
            normalized_subjects.append(subject)

        alias_subject_id: str | None = None
        if len(normalized_subjects) == 1:
            alias_subject_id = normalized_subjects[0].canonical_id
        elif query.isascii() and not query.isdigit():
            cn_stocks = [
                subject
                for subject in normalized_subjects
                if subject.type == "security" and subject.market == "CN"
            ]
            if cn_stocks and normalized_subjects[0].canonical_id == cn_stocks[0].canonical_id:
                alias_subject_id = cn_stocks[0].canonical_id
        for subject in normalized_subjects:
            self._subject_store.upsert(
                subject,
                aliases=[query] if subject.canonical_id == alias_subject_id else [],
                source="market.symbol-search",
                confidence=0.95,
            )
        return self._subject_store.search(
            query,
            subject_type=subject_type,
            market=market,
            limit=limit,
        )

    def list_mod_profiles(self) -> list[WikiModProfileResponse]:
        profiles: list[WikiModProfileResponse] = []
        registered_capabilities = set(self._data_registry.capabilities())
        for module in self._repository.list_published():
            raw_wiki = module.manifest.get("wiki")
            if not isinstance(raw_wiki, dict):
                continue
            wiki = ModuleWikiProfile.model_validate(raw_wiki)
            data_capabilities = [
                item
                for item in _data_capabilities(module.manifest)
                if item in registered_capabilities
            ]
            profiles.append(
                WikiModProfileResponse(
                    moduleId=module.module_id,
                    revision=module.revision,
                    name=str(module.manifest.get("name") or module.module_id),
                    wiki=wiki,
                    dataCapabilities=data_capabilities,
                )
            )
        return profiles

    def resolve_links(
        self,
        request: WikiLinkResolutionRequest,
    ) -> WikiLinkResolutionResponse:
        self._index_context(request.context)
        modules = {
            module.module_id: module for module in self._repository.list_published()
        }
        source = modules.get(request.source_mod_id)
        if source is None:
            raise WikiModuleNotFoundError(request.source_mod_id)

        source_capabilities = set(_data_capabilities(source.manifest))
        context_concepts = {
            _concept_slug(concept_id) for concept_id in request.context.concept_ids
        }
        links: list[WikiLink] = []
        for profile in self.list_mod_profiles():
            if profile.module_id == request.source_mod_id:
                continue
            if request.context.primary_subject.type not in profile.wiki.subject_types:
                continue

            common_concepts = sorted(
                context_concepts.intersection(profile.wiki.concepts)
            )
            common_data = sorted(
                source_capabilities.intersection(profile.data_capabilities)
            )
            for entrypoint in profile.wiki.entrypoints:
                if entrypoint.intent in INTENT_COMPLEMENTS.get(request.context.intent, set()):
                    intent_score = 25
                elif entrypoint.intent == request.context.intent:
                    intent_score = 5
                else:
                    intent_score = 10
                score = min(
                    100,
                    35
                    + intent_score
                    + (10 if common_concepts else 0)
                    + (5 if common_data else 0)
                    + 15,
                )
                reasons = [
                    f"支持同一{request.context.primary_subject.type}对象",
                    f"可进入{entrypoint.label}",
                ]
                if common_concepts:
                    reasons.append(f"关联概念：{'、'.join(common_concepts[:3])}")
                if common_data:
                    reasons.append(f"共享数据：{'、'.join(common_data[:2])}")
                links.append(
                    WikiLink(
                        id=f"{profile.module_id}:{entrypoint.id}",
                        targetModId=profile.module_id,
                        targetRevision=profile.revision,
                        entrypointId=entrypoint.id,
                        intent=entrypoint.intent,
                        label=entrypoint.label,
                        reason="；".join(reasons),
                        score=score,
                        match=WikiLinkMatch(
                            subjectType=request.context.primary_subject.type,
                            intentScore=intent_score,
                            concepts=common_concepts,
                            dataCapabilities=common_data,
                        ),
                    )
                )

        links.sort(key=lambda link: (-link.score, link.target_mod_id, link.entrypoint_id))
        return WikiLinkResolutionResponse(
            sourceModId=request.source_mod_id,
            subject=request.context.primary_subject,
            links=links[: request.limit],
            generatedAt=datetime.now(timezone.utc),
        )

    def create_handoff(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: WikiHandoffCreate,
    ) -> WikiHandoff:
        self._index_context(request.context)
        modules = {
            module.module_id: module for module in self._repository.list_published()
        }
        if request.source_mod_id not in modules:
            raise WikiModuleNotFoundError(request.source_mod_id)
        target = modules.get(request.target_mod_id)
        if target is None:
            raise WikiModuleNotFoundError(request.target_mod_id)
        raw_wiki = target.manifest.get("wiki")
        if not isinstance(raw_wiki, dict):
            raise WikiEntrypointUnavailableError("target Mod has no Wiki profile")
        wiki = ModuleWikiProfile.model_validate(raw_wiki)
        if request.context.primary_subject.type not in wiki.subject_types:
            raise WikiEntrypointUnavailableError(
                "target Mod does not support this Wiki subject type"
            )
        entrypoint = next(
            (item for item in wiki.entrypoints if item.id == request.entrypoint_id),
            None,
        )
        if entrypoint is None:
            raise WikiEntrypointUnavailableError("target Wiki entrypoint is unavailable")

        created_at = datetime.now(timezone.utc)
        handoff = WikiHandoff(
            version=1,
            id=f"hf_{secrets.token_urlsafe(18)}",
            sourceModId=request.source_mod_id,
            sourceSnapshotId=request.context.snapshot_id,
            targetModId=request.target_mod_id,
            entrypointId=request.entrypoint_id,
            subject=request.context.primary_subject,
            relatedSubjects=request.context.related_subjects,
            conceptIds=request.context.concept_ids,
            intent=entrypoint.intent,
            timeframe=request.context.timeframe,
            parameters={**entrypoint.defaults, **request.parameters},
            createdAt=created_at,
            expiresAt=created_at + timedelta(minutes=5),
        )
        return self._handoff_store.put(
            user_id=user_id,
            workspace_id=workspace_id,
            handoff=handoff,
        )
