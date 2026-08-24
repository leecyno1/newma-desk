from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx
from pydantic import ValidationError

from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.schemas import (
    ModuleManifest,
    manifest_repository_dict,
)
from vibe_visualization_api.external_mod_runtimes import (
    load_runtime_descriptor,
    resolve_runtime_workspace,
)
from vibe_visualization_api.mod_store.schemas import (
    AgentWorkspace,
    ExternalRuntime,
    LEGACY_NEWMA_DOCK_SUITE_PATH,
    LEGACY_VIBEDESK_SUITE_PATH,
    ModStoreResponse,
    StoreCatalog,
    StoreCatalogEntry,
    StoreInstallResponse,
    StoreModDescriptor,
    StoreModSuiteDescriptor,
    StoreModResponse,
    StoreProjectInstallResponse,
    StoreSuiteCatalogEntry,
    RuntimeAgentWorkspace,
    WELL_KNOWN_SUITE_PATH,
    expand_mod_suite,
    validate_complete_project_groups,
)


MAX_DESCRIPTOR_BYTES = 256 * 1024
MAX_CATALOG_BYTES = 512 * 1024
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ENGLISH_TITLE_TOKENS = {
    "ai": "AI",
    "cn": "CN",
    "czsc": "CZSC",
    "etf": "ETF",
    "h": "H",
    "hk": "HK",
    "hkex": "HKEX",
    "llm": "LLM",
    "newma": "Newma",
    "rss": "RSS",
    "us": "US",
}


def _english_mod_name(mod_id: str) -> str:
    return " ".join(
        ENGLISH_TITLE_TOKENS.get(token, token.capitalize())
        for token in mod_id.split("-")
    )


class ModStoreError(Exception):
    status_code = 500
    detail = "Mod store unavailable"


class ModStoreNotFoundError(ModStoreError):
    status_code = 404
    detail = "Mod is not available in this store"


class ModStoreCatalogError(ModStoreError):
    status_code = 500
    detail = "Mod store catalog is invalid"


class ModStoreSourceError(ModStoreError):
    status_code = 502
    detail = "Unable to download Mod from Git"


class ModStoreDiscoveryError(ModStoreError):
    status_code = 502
    detail = "Unable to discover Mod Suite"


class ModStoreDescriptorError(ModStoreError):
    status_code = 422
    detail = "Git returned an invalid Mod descriptor"


class ModStoreSyncError(ModStoreError):
    status_code = 502
    detail = "Unable to sync Mod catalog from GitHub"


DescriptorFetcher = Callable[
    [StoreCatalog, StoreCatalogEntry | StoreSuiteCatalogEntry],
    Awaitable[dict[str, Any]],
]
RuntimeWorkspaceResolver = Callable[[str, str], Path]
CatalogSnapshotFetcher = Callable[
    [StoreCatalog],
    Awaitable[tuple[str, dict[str, Any], dict[str, dict[str, Any]]]],
]


@dataclass(frozen=True)
class RemoteCatalogSnapshot:
    catalog: StoreCatalog
    commit: str
    synced_at: str
    descriptors: dict[str, dict[str, Any]]


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _manifest_equal(left: dict[str, Any], right: dict[str, object]) -> bool:
    return _stable_json(left) == _stable_json(right)


class ModStoreService:
    def __init__(
        self,
        settings: Settings,
        *,
        descriptor_fetcher: DescriptorFetcher | None = None,
        catalog_snapshot_fetcher: CatalogSnapshotFetcher | None = None,
        runtime_workspace_resolver: RuntimeWorkspaceResolver | None = None,
    ) -> None:
        self._settings = settings
        self._store_dir = settings.mod_store_dir
        self._descriptor_fetcher = descriptor_fetcher or self._fetch_descriptor
        self._catalog_snapshot_fetcher = (
            catalog_snapshot_fetcher or self._fetch_github_snapshot
        )
        self._runtime_workspace_resolver = (
            runtime_workspace_resolver or resolve_runtime_workspace
        )
        self._sync_lock = asyncio.Lock()
        self._snapshot_cache_signature: tuple[int, int, int, int] | None = None
        self._snapshot_cache_value: RemoteCatalogSnapshot | None = None
        self._snapshot_cache_loaded = False
        self._expanded_snapshot: RemoteCatalogSnapshot | None = None
        self._expanded_snapshot_mods: list[
            tuple[
                StoreCatalogEntry | StoreSuiteCatalogEntry,
                StoreModDescriptor,
                bool,
            ]
        ] | None = None
        self._expanded_snapshot_manifests: dict[str, dict[str, object]] | None = None

    def _catalog(self) -> StoreCatalog:
        try:
            raw = json.loads((self._store_dir / "store.json").read_text("utf-8"))
            return StoreCatalog.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise ModStoreCatalogError() from error

    def _snapshot_path(self) -> Path:
        return self._settings.runtime_dir / "mod-store-catalog.json"

    @staticmethod
    def _github_repository_parts(repository: str) -> tuple[str, str]:
        parsed = urlsplit(repository)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.hostname != "github.com" or len(parts) != 2:
            raise ModStoreSyncError()
        owner, name = parts
        return owner, name.removesuffix(".git")

    def _catalog_at_commit(
        self,
        catalog: StoreCatalog,
        commit: str,
    ) -> StoreCatalog:
        owner, name = self._github_repository_parts(catalog.git.repository)
        git = catalog.git.model_copy(
            update={
                "ref": commit,
                "mirrors": [],
                "raw_base_urls": [
                    "https://raw.githubusercontent.com/"
                    f"{owner}/{name}/{commit}/{catalog.git.path_prefix}"
                ],
            }
        )
        return catalog.model_copy(update={"git": git})

    @staticmethod
    def _validate_catalog_authority(
        bundled: StoreCatalog,
        remote: StoreCatalog,
    ) -> None:
        if (
            remote.id != bundled.id
            or remote.git.repository != bundled.git.repository
            or remote.git.ref != bundled.git.ref
            or remote.git.path_prefix != bundled.git.path_prefix
        ):
            raise ModStoreSyncError()

    @staticmethod
    def _validate_catalog_coverage(
        bundled: StoreCatalog,
        remote: StoreCatalog,
    ) -> None:
        remote_mods = {entry.id: entry.path for entry in remote.mods}
        remote_suites = {
            entry.id: (
                entry.path,
                entry.discovery.model_dump(mode="json")
                if entry.discovery is not None
                else None,
            )
            for entry in remote.suites
        }
        if any(remote_mods.get(entry.id) != entry.path for entry in bundled.mods):
            raise ModStoreSyncError()
        if any(
            remote_suites.get(entry.id)
            != (
                entry.path,
                entry.discovery.model_dump(mode="json")
                if entry.discovery is not None
                else None,
            )
            for entry in bundled.suites
        ):
            raise ModStoreSyncError()

    @staticmethod
    def _validate_git_descriptors(
        catalog: StoreCatalog,
        descriptors: dict[str, dict[str, Any]],
    ) -> None:
        expected_ids = {
            entry.id for entry in [*catalog.mods, *catalog.suites] if entry.path
        }
        if set(descriptors) != expected_ids:
            raise ModStoreSyncError()

        expanded: list[StoreModDescriptor] = []
        try:
            for entry in catalog.mods:
                descriptor = StoreModDescriptor.model_validate(descriptors[entry.id])
                if descriptor.id != entry.id:
                    raise ModStoreSyncError()
                expanded.append(descriptor)
            for entry in catalog.suites:
                if entry.path is None:
                    continue
                suite = StoreModSuiteDescriptor.model_validate(descriptors[entry.id])
                if suite.id != entry.id:
                    raise ModStoreSyncError()
                expanded.extend(item for item, _ in expand_mod_suite(suite))
            validate_complete_project_groups(expanded)
        except (ValidationError, TypeError, ValueError) as error:
            raise ModStoreSyncError() from error

    def _snapshot(self) -> RemoteCatalogSnapshot | None:
        path = self._snapshot_path()
        try:
            stat = path.stat()
            catalog_stat = (self._store_dir / "store.json").stat()
        except OSError:
            self._snapshot_cache_signature = None
            self._snapshot_cache_value = None
            self._snapshot_cache_loaded = True
            self._expanded_snapshot = None
            self._expanded_snapshot_mods = None
            self._expanded_snapshot_manifests = None
            return None

        signature = (
            stat.st_mtime_ns,
            stat.st_size,
            catalog_stat.st_mtime_ns,
            catalog_stat.st_size,
        )
        if (
            self._snapshot_cache_loaded
            and self._snapshot_cache_signature == signature
        ):
            return self._snapshot_cache_value

        snapshot: RemoteCatalogSnapshot | None = None
        try:
            raw = json.loads(path.read_text("utf-8"))
            if not isinstance(raw, dict) or raw.get("schemaVersion") != "1.0":
                raise ValueError("Unsupported Mod catalog snapshot schema")
            commit = raw.get("commit")
            synced_at = raw.get("syncedAt")
            descriptor_rows = raw.get("descriptors")
            if (
                not isinstance(commit, str)
                or GIT_COMMIT_PATTERN.fullmatch(commit) is None
                or not isinstance(synced_at, str)
                or not isinstance(descriptor_rows, dict)
            ):
                raise ValueError("Invalid Mod catalog snapshot metadata")
            datetime.fromisoformat(synced_at)
            catalog = StoreCatalog.model_validate(raw.get("catalog"))
            bundled = self._catalog()
            self._validate_catalog_authority(bundled, catalog)
            self._validate_catalog_coverage(bundled, catalog)
            descriptors = {
                key: value
                for key, value in descriptor_rows.items()
                if isinstance(key, str) and isinstance(value, dict)
            }
            if len(descriptors) != len(descriptor_rows):
                raise ValueError("Invalid Mod catalog snapshot descriptors")
            self._validate_git_descriptors(catalog, descriptors)
            snapshot = RemoteCatalogSnapshot(
                catalog=self._catalog_at_commit(catalog, commit),
                commit=commit,
                synced_at=synced_at,
                descriptors=descriptors,
            )
        except (
            OSError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
            ModStoreError,
        ):
            snapshot = None
        self._snapshot_cache_signature = signature
        self._snapshot_cache_value = snapshot
        self._snapshot_cache_loaded = True
        if snapshot is None:
            self._expanded_snapshot = None
            self._expanded_snapshot_mods = None
            self._expanded_snapshot_manifests = None
        return snapshot

    def _write_snapshot(
        self,
        catalog: StoreCatalog,
        commit: str,
        synced_at: str,
        descriptors: dict[str, dict[str, Any]],
    ) -> None:
        path = self._snapshot_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temp.write_text(
            json.dumps(
                {
                    "schemaVersion": "1.0",
                    "repository": catalog.git.repository,
                    "ref": catalog.git.ref,
                    "commit": commit,
                    "syncedAt": synced_at,
                    "catalog": catalog.model_dump(by_alias=True, mode="json"),
                    "descriptors": descriptors,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.chmod(temp, 0o600)
        os.replace(temp, path)
        self._snapshot_cache_signature = None
        self._snapshot_cache_value = None
        self._snapshot_cache_loaded = False
        self._expanded_snapshot = None
        self._expanded_snapshot_mods = None
        self._expanded_snapshot_manifests = None

    async def _entry(
        self,
        catalog: StoreCatalog,
        mod_id: str,
        descriptors: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[
        StoreCatalogEntry | StoreSuiteCatalogEntry,
        str | None,
        StoreModSuiteDescriptor | None,
    ]:
        standalone = next((item for item in catalog.mods if item.id == mod_id), None)
        if standalone is not None:
            return standalone, None, None
        for suite_entry in catalog.suites:
            suite = await self._suite_descriptor(
                catalog,
                suite_entry,
                descriptors=descriptors,
            )
            if any(page.id == mod_id for page in suite.pages):
                return (
                    suite_entry,
                    mod_id,
                    suite if suite_entry.discovery is not None else None,
                )
        raise ModStoreNotFoundError()

    def _descriptor_path(
        self,
        entry: StoreCatalogEntry | StoreSuiteCatalogEntry,
    ) -> Path:
        if entry.path is None:
            raise ModStoreCatalogError()
        store_root = self._store_dir.resolve()
        path = (store_root / entry.path).resolve()
        if not path.is_relative_to(store_root):
            raise ModStoreCatalogError()
        return path

    def _local_descriptor(self, entry: StoreCatalogEntry) -> StoreModDescriptor:
        try:
            raw = json.loads(self._descriptor_path(entry).read_text("utf-8"))
            descriptor = StoreModDescriptor.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise ModStoreCatalogError() from error
        if descriptor.id != entry.id:
            raise ModStoreCatalogError()
        return descriptor

    def _local_suite_descriptor(
        self,
        entry: StoreSuiteCatalogEntry,
    ) -> StoreModSuiteDescriptor:
        try:
            raw = json.loads(self._descriptor_path(entry).read_text("utf-8"))
            descriptor = StoreModSuiteDescriptor.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise ModStoreCatalogError() from error
        if descriptor.id != entry.id:
            raise ModStoreCatalogError()
        return descriptor

    async def _suite_descriptor(
        self,
        catalog: StoreCatalog,
        entry: StoreSuiteCatalogEntry,
        *,
        descriptors: dict[str, dict[str, Any]] | None = None,
    ) -> StoreModSuiteDescriptor:
        if descriptors is not None and entry.path is not None:
            raw = descriptors.get(entry.id)
            if raw is None:
                raise ModStoreCatalogError()
            try:
                descriptor = StoreModSuiteDescriptor.model_validate(raw)
            except ValidationError as error:
                raise ModStoreCatalogError() from error
            if descriptor.id != entry.id:
                raise ModStoreCatalogError()
            return descriptor
        if entry.path is not None:
            return self._local_suite_descriptor(entry)
        try:
            raw = await self._descriptor_fetcher(catalog, entry)
            descriptor = StoreModSuiteDescriptor.model_validate(raw)
        except ModStoreError:
            raise
        except (ValidationError, TypeError, ValueError) as error:
            raise ModStoreDescriptorError() from error
        if descriptor.id != entry.id:
            raise ModStoreDescriptorError()
        return descriptor

    async def _local_mods(
        self,
        catalog: StoreCatalog,
    ) -> list[
        tuple[
            StoreCatalogEntry | StoreSuiteCatalogEntry,
            StoreModDescriptor,
            bool,
        ]
    ]:
        rows: list[
            tuple[
                StoreCatalogEntry | StoreSuiteCatalogEntry,
                StoreModDescriptor,
                bool,
            ]
        ] = [
            (entry, self._local_descriptor(entry), entry.default_install)
            for entry in catalog.mods
        ]
        for entry in catalog.suites:
            suite = await self._suite_descriptor(catalog, entry)
            for descriptor, page_default in expand_mod_suite(suite):
                rows.append(
                    (
                        entry,
                        descriptor,
                        entry.default_install if page_default is None else page_default,
                    )
                )
        ids = [descriptor.id for _, descriptor, _ in rows]
        if len(ids) != len(set(ids)) or set(ids).intersection(catalog.retired_mods):
            raise ModStoreCatalogError()
        try:
            validate_complete_project_groups([descriptor for _, descriptor, _ in rows])
        except ValueError as error:
            raise ModStoreCatalogError() from error
        return rows

    async def _snapshot_mods(
        self,
        catalog: StoreCatalog,
        descriptors: dict[str, dict[str, Any]],
    ) -> list[
        tuple[
            StoreCatalogEntry | StoreSuiteCatalogEntry,
            StoreModDescriptor,
            bool,
        ]
    ]:
        rows: list[
            tuple[
                StoreCatalogEntry | StoreSuiteCatalogEntry,
                StoreModDescriptor,
                bool,
            ]
        ] = []
        try:
            for entry in catalog.mods:
                descriptor = StoreModDescriptor.model_validate(descriptors[entry.id])
                if descriptor.id != entry.id:
                    raise ModStoreCatalogError()
                rows.append((entry, descriptor, entry.default_install))
            for entry in catalog.suites:
                suite = await self._suite_descriptor(
                    catalog,
                    entry,
                    descriptors=descriptors,
                )
                for descriptor, page_default in expand_mod_suite(suite):
                    rows.append(
                        (
                            entry,
                            descriptor,
                            entry.default_install
                            if page_default is None
                            else page_default,
                        )
                    )
        except (KeyError, ValidationError, TypeError, ValueError) as error:
            raise ModStoreCatalogError() from error

        ids = [descriptor.id for _, descriptor, _ in rows]
        if len(ids) != len(set(ids)) or set(ids).intersection(catalog.retired_mods):
            raise ModStoreCatalogError()
        try:
            validate_complete_project_groups([descriptor for _, descriptor, _ in rows])
        except ValueError as error:
            raise ModStoreCatalogError() from error
        return rows

    async def resolve_agent_workspace(self, mod_id: str) -> Path | None:
        """Resolve a Mod's editable source tree from trusted Store metadata.

        Descriptors may select the Desk source tree or a named workspace from
        the Runtime Descriptor. They cannot provide arbitrary filesystem paths.
        """

        catalog = self._catalog()
        standalone = next((item for item in catalog.mods if item.id == mod_id), None)
        agent_workspace: AgentWorkspace | None = None
        if standalone is not None:
            agent_workspace = self._local_descriptor(standalone).agent_workspace
        else:
            for suite_entry in catalog.suites:
                suite = await self._suite_descriptor(catalog, suite_entry)
                if any(page.id == mod_id for page in suite.pages):
                    # HTTP discovery is an untrusted content source. Its pages
                    # remain readable/installable, but it cannot grant a local
                    # Agent permission to edit the Desk or Runtime workspaces.
                    agent_workspace = (
                        suite.agent_workspace if suite_entry.path is not None else None
                    )
                    break
            else:
                raise ModStoreNotFoundError()
        if agent_workspace is None:
            return None
        if agent_workspace.type == "desk":
            return self._settings.workspace_root.expanduser().resolve()
        return self._resolve_runtime_agent_workspace(agent_workspace)

    def _resolve_runtime_agent_workspace(
        self,
        agent_workspace: RuntimeAgentWorkspace,
    ) -> Path:
        try:
            descriptor = load_runtime_descriptor()
            runtime = next(
                item
                for item in descriptor["runtimes"]
                if isinstance(item, dict)
                and item.get("id") == agent_workspace.runtime_id
            )
            workspaces = runtime.get("workspaces")
            if not isinstance(workspaces, dict):
                raise KeyError(agent_workspace.workspace_name)
            workspace = workspaces[agent_workspace.workspace_name]
            if not isinstance(workspace, dict) or not isinstance(
                workspace.get("env"), str
            ):
                raise KeyError(agent_workspace.workspace_name)
            configured = self._setting_for_env(str(workspace["env"]), "")
        except (KeyError, StopIteration, TypeError, ValueError) as error:
            raise ModStoreCatalogError() from error
        if configured:
            path = Path(configured).expanduser()
            if path.is_absolute():
                return path.resolve()
            try:
                return (
                    resolve_runtime_workspace(
                        agent_workspace.runtime_id,
                        agent_workspace.workspace_name,
                        env={str(workspace["env"]): configured},
                    )
                    .expanduser()
                    .resolve()
                )
            except (KeyError, OSError, TypeError, ValueError) as error:
                raise ModStoreCatalogError() from error
        try:
            return (
                self._runtime_workspace_resolver(
                    agent_workspace.runtime_id,
                    agent_workspace.workspace_name,
                )
                .expanduser()
                .resolve()
            )
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise ModStoreCatalogError() from error

    def _source_urls(
        self,
        catalog: StoreCatalog,
        entry: StoreCatalogEntry | StoreSuiteCatalogEntry,
    ) -> list[str]:
        if entry.path is None:
            raise ModStoreCatalogError()
        encoded_path = "/".join(quote(part, safe="") for part in entry.path.split("/"))
        return [
            f"{base.rstrip('/')}/{encoded_path}" for base in catalog.git.raw_base_urls
        ]

    def _source_page_url(
        self,
        catalog: StoreCatalog,
        entry: StoreCatalogEntry | StoreSuiteCatalogEntry,
    ) -> str:
        if isinstance(entry, StoreSuiteCatalogEntry) and entry.discovery is not None:
            return self._discovery_url(entry)
        if entry.path is None:
            raise ModStoreCatalogError()
        encoded_path = "/".join(quote(part, safe="") for part in entry.path.split("/"))
        encoded_prefix = "/".join(
            quote(part, safe="") for part in catalog.git.path_prefix.split("/")
        )
        return (
            f"{catalog.git.repository}/blob/{quote(catalog.git.ref, safe='')}/"
            f"{encoded_prefix}/{encoded_path}"
        )

    def _setting_for_env(self, env_name: str, fallback: str) -> str:
        if env_name.startswith("NEWMA_DESK_"):
            suffix = env_name.removeprefix("NEWMA_DESK_")
        elif env_name.startswith("NEWMA_DOCK_"):
            suffix = env_name.removeprefix("NEWMA_DOCK_")
        elif env_name.startswith("VIBEDESK_"):
            suffix = env_name.removeprefix("VIBEDESK_")
        else:
            raise ModStoreCatalogError()
        field_name = suffix.lower()
        value = getattr(self._settings, field_name, None)
        if isinstance(value, (str, Path)) and str(value):
            return str(value)
        for candidate in (
            f"NEWMA_DESK_{suffix}",
            f"NEWMA_DOCK_{suffix}",
            f"VIBEDESK_{suffix}",
        ):
            environment_value = os.environ.get(candidate)
            if environment_value:
                return environment_value
        return fallback

    def _discovery_urls(self, entry: StoreSuiteCatalogEntry) -> list[str]:
        preferred = self._discovery_url(entry)
        discovery = entry.discovery
        if discovery is None or discovery.path != WELL_KNOWN_SUITE_PATH:
            return [preferred]
        parsed = urlsplit(preferred)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return [
            preferred,
            f"{origin}{LEGACY_NEWMA_DOCK_SUITE_PATH}",
            f"{origin}{LEGACY_VIBEDESK_SUITE_PATH}",
        ]

    def _discovery_url(self, entry: StoreSuiteCatalogEntry) -> str:
        discovery = entry.discovery
        if discovery is None:
            raise ModStoreCatalogError()
        base_url = self._setting_for_env(
            discovery.base_url_env,
            discovery.default_base_url,
        )
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ModStoreCatalogError()
        return f"{parsed.scheme}://{parsed.netloc}{discovery.path}"

    def _manifest(self, descriptor: StoreModDescriptor) -> dict[str, object]:
        runtime = descriptor.runtime
        if isinstance(runtime, ExternalRuntime):
            base_url = self._setting_for_env(
                runtime.base_url_env,
                runtime.default_base_url,
            ).rstrip("/")
            entry: dict[str, str] = {
                "type": "external",
                "url": urljoin(f"{base_url}/", runtime.route.lstrip("/")),
            }
        else:
            entry = runtime.entry.model_dump(by_alias=True, mode="json")

        manifest_data = {
            "schemaVersion": descriptor.manifest.schema_version,
            "id": descriptor.id,
            "name": descriptor.name,
            "version": descriptor.version,
            "presentation": {
                "englishName": _english_mod_name(descriptor.id),
                "description": descriptor.description,
                "titleOwner": "host",
            },
            **descriptor.manifest.model_dump(
                by_alias=True,
                exclude={"schema_version"},
                exclude_none=True,
                mode="json",
            ),
            "entry": entry,
        }
        try:
            manifest = ModuleManifest.model_validate(manifest_data)
        except ValidationError as error:
            raise ModStoreDescriptorError() from error
        return manifest_repository_dict(manifest)

    def _local_install_descriptor(
        self,
        entry: StoreCatalogEntry | StoreSuiteCatalogEntry,
        suite_page_id: str | None,
    ) -> StoreModDescriptor:
        """Resolve the bundled descriptor used when the Git source is unavailable."""

        if suite_page_id is None:
            if not isinstance(entry, StoreCatalogEntry):
                raise ModStoreCatalogError()
            return self._local_descriptor(entry)

        if not isinstance(entry, StoreSuiteCatalogEntry):
            raise ModStoreCatalogError()
        suite = self._local_suite_descriptor(entry)
        descriptor = next(
            (item for item, _ in expand_mod_suite(suite) if item.id == suite_page_id),
            None,
        )
        if descriptor is None:
            raise ModStoreCatalogError()
        return descriptor

    async def _active_mods(
        self,
    ) -> tuple[
        StoreCatalog,
        list[
            tuple[
                StoreCatalogEntry | StoreSuiteCatalogEntry,
                StoreModDescriptor,
                bool,
            ]
        ],
        RemoteCatalogSnapshot | None,
    ]:
        snapshot = self._snapshot()
        if snapshot is not None:
            if (
                self._expanded_snapshot is snapshot
                and self._expanded_snapshot_mods is not None
            ):
                return snapshot.catalog, self._expanded_snapshot_mods, snapshot
            mods = await self._snapshot_mods(snapshot.catalog, snapshot.descriptors)
            self._expanded_snapshot = snapshot
            self._expanded_snapshot_mods = mods
            self._expanded_snapshot_manifests = {
                descriptor.id: self._manifest(descriptor)
                for _, descriptor, _ in mods
            }
            return (
                snapshot.catalog,
                mods,
                snapshot,
            )
        catalog = self._catalog()
        return catalog, await self._local_mods(catalog), None

    async def sync(self, repository: ModuleRepository) -> ModStoreResponse:
        async with self._sync_lock:
            bundled = self._catalog()
            try:
                commit, raw_catalog, descriptors = await self._catalog_snapshot_fetcher(
                    bundled
                )
                if GIT_COMMIT_PATTERN.fullmatch(commit) is None:
                    raise ModStoreSyncError()
                remote = StoreCatalog.model_validate(raw_catalog)
                self._validate_catalog_authority(bundled, remote)
                self._validate_catalog_coverage(bundled, remote)
                self._validate_git_descriptors(remote, descriptors)
                synced_at = datetime.now(timezone.utc).isoformat()
                self._write_snapshot(remote, commit, synced_at, descriptors)
            except ModStoreError:
                raise
            except (OSError, ValidationError, TypeError, ValueError) as error:
                raise ModStoreSyncError() from error
        return await self.list(repository)

    async def _fetch_github_snapshot(
        self,
        catalog: StoreCatalog,
    ) -> tuple[str, dict[str, Any], dict[str, dict[str, Any]]]:
        # GitHub is the sole release authority. Mirrors may distribute already
        # commit-pinned content, but they must never choose the catalog commit.
        self._github_repository_parts(catalog.git.repository)
        git_snapshot = await self._fetch_github_snapshot_from_git(catalog)
        if git_snapshot is not None:
            return git_snapshot

        owner, name = self._github_repository_parts(catalog.git.repository)
        timeout = httpx.Timeout(self._settings.mod_store_git_timeout_seconds)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Newma-Desk-Mod-Store",
        }
        token = self._settings.mod_store_github_token.get_secret_value().strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            headers=headers,
        ) as client:
            commit_body = await self._fetch_json_document(
                client,
                "https://api.github.com/repos/"
                f"{quote(owner, safe='')}/{quote(name, safe='')}/commits/"
                f"{quote(catalog.git.ref, safe='')}",
                max_bytes=MAX_DESCRIPTOR_BYTES,
            )
            commit = commit_body.get("sha")
            if (
                not isinstance(commit, str)
                or GIT_COMMIT_PATTERN.fullmatch(commit) is None
            ):
                raise ModStoreSyncError()

            raw_root = (
                "https://raw.githubusercontent.com/"
                f"{quote(owner, safe='')}/{quote(name, safe='')}/{commit}/"
                f"{quote(catalog.git.path_prefix, safe='/')}"
            )
            raw_catalog = await self._fetch_json_document(
                client,
                f"{raw_root}/store.json",
                max_bytes=MAX_CATALOG_BYTES,
            )
            try:
                remote = StoreCatalog.model_validate(raw_catalog)
            except ValidationError as error:
                raise ModStoreSyncError() from error

            semaphore = asyncio.Semaphore(6)

            async def fetch_entry(
                entry: StoreCatalogEntry | StoreSuiteCatalogEntry,
            ) -> tuple[str, dict[str, Any]]:
                if entry.path is None:
                    raise ModStoreSyncError()
                encoded_path = "/".join(
                    quote(part, safe="") for part in entry.path.split("/")
                )
                async with semaphore:
                    body = await self._fetch_json_document(
                        client,
                        f"{raw_root}/{encoded_path}",
                        max_bytes=MAX_DESCRIPTOR_BYTES,
                    )
                return entry.id, body

            entries = [entry for entry in [*remote.mods, *remote.suites] if entry.path]
            descriptors = dict(await asyncio.gather(*(fetch_entry(e) for e in entries)))
            return commit, raw_catalog, descriptors

    async def _fetch_github_snapshot_from_git(
        self,
        catalog: StoreCatalog,
    ) -> tuple[str, dict[str, Any], dict[str, dict[str, Any]]] | None:
        timeout = self._settings.mod_store_git_timeout_seconds
        environment = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
        }
        try:
            self._settings.runtime_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="newma-desk-catalog-",
                dir=self._settings.runtime_dir,
            ) as directory:
                initialized = await self._run_git(
                    ["init", "--bare", directory],
                    timeout=timeout,
                    environment=environment,
                )
                if initialized is None:
                    return None
                fetched = await self._run_git(
                    [
                        "--git-dir",
                        directory,
                        "fetch",
                        "--depth=1",
                        "--no-tags",
                        catalog.git.repository,
                        catalog.git.ref,
                    ],
                    timeout=timeout,
                    environment=environment,
                )
                if fetched is None:
                    return None
                commit_body = await self._run_git(
                    ["--git-dir", directory, "rev-parse", "FETCH_HEAD"],
                    timeout=timeout,
                    environment=environment,
                )
                if commit_body is None:
                    return None
                commit = commit_body.decode("ascii", errors="ignore").strip()
                if GIT_COMMIT_PATTERN.fullmatch(commit) is None:
                    raise ModStoreSyncError()
                catalog_body = await self._run_git(
                    [
                        "--git-dir",
                        directory,
                        "show",
                        f"{commit}:{catalog.git.path_prefix}/store.json",
                    ],
                    timeout=timeout,
                    environment=environment,
                )
                if catalog_body is None or len(catalog_body) > MAX_CATALOG_BYTES:
                    raise ModStoreSyncError()
                try:
                    raw_catalog = json.loads(catalog_body)
                    remote = StoreCatalog.model_validate(raw_catalog)
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    ValidationError,
                ) as error:
                    raise ModStoreSyncError() from error

                descriptors: dict[str, dict[str, Any]] = {}
                for entry in [*remote.mods, *remote.suites]:
                    if entry.path is None:
                        continue
                    body = await self._run_git(
                        [
                            "--git-dir",
                            directory,
                            "show",
                            f"{commit}:{remote.git.path_prefix}/{entry.path}",
                        ],
                        timeout=timeout,
                        environment=environment,
                    )
                    if body is None or len(body) > MAX_DESCRIPTOR_BYTES:
                        raise ModStoreSyncError()
                    try:
                        value = json.loads(body)
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise ModStoreSyncError() from error
                    if not isinstance(value, dict):
                        raise ModStoreSyncError()
                    descriptors[entry.id] = value
                return commit, raw_catalog, descriptors
        except OSError:
            return None
        return None

    async def _fetch_json_document(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        max_bytes: int,
    ) -> dict[str, Any]:
        try:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise ModStoreSyncError()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ModStoreSyncError()
                    chunks.append(chunk)
        except httpx.HTTPError as error:
            raise ModStoreSyncError() from error
        try:
            body = json.loads(b"".join(chunks))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModStoreSyncError() from error
        if not isinstance(body, dict):
            raise ModStoreSyncError()
        return body

    async def list(self, repository: ModuleRepository) -> ModStoreResponse:
        catalog, catalog_mods, snapshot = await self._active_mods()
        installed = {item.module_id: item for item in repository.list_installed()}
        rows: list[StoreModResponse] = []
        for entry, descriptor, default_install in catalog_mods:
            manifest = (
                self._expanded_snapshot_manifests.get(descriptor.id)
                if snapshot is self._expanded_snapshot
                and self._expanded_snapshot_manifests is not None
                else None
            )
            if manifest is None:
                manifest = self._manifest(descriptor)
            current = installed.get(descriptor.id)
            if current is None:
                install_state = "available"
            elif _manifest_equal(current.manifest, manifest):
                install_state = "installed"
            else:
                install_state = "update-available"
            rows.append(
                StoreModResponse(
                    id=descriptor.id,
                    suite_id=entry.id,
                    name=descriptor.name,
                    description=descriptor.description,
                    version=descriptor.version,
                    publisher=descriptor.publisher,
                    upstream=descriptor.upstream or catalog.git.repository,
                    category=descriptor.manifest.navigation.group_label
                    if descriptor.manifest.navigation is not None
                    else descriptor.manifest.category,
                    tags=descriptor.tags,
                    default_install=default_install,
                    install_state=install_state,
                    installed_revision=current.revision if current else None,
                    installed_version=(
                        str(current.manifest.get("version")) if current else None
                    ),
                    installed_status=current.status if current else None,
                    navigation=descriptor.manifest.navigation,
                    source_url=self._source_page_url(catalog, entry),
                )
            )
        return ModStoreResponse(
            id=catalog.id,
            name=catalog.name,
            repository=catalog.git.repository,
            ref=self._catalog().git.ref if snapshot else catalog.git.ref,
            catalog_source="github" if snapshot else "bundled",
            commit=snapshot.commit if snapshot else None,
            synced_at=snapshot.synced_at if snapshot else None,
            mods=rows,
        )

    async def install(
        self,
        mod_id: str,
        repository: ModuleRepository,
    ) -> StoreInstallResponse:
        snapshot = self._snapshot()
        catalog = snapshot.catalog if snapshot is not None else self._catalog()
        entry, suite_page_id, discovered_suite = await self._entry(
            catalog,
            mod_id,
            descriptors=snapshot.descriptors if snapshot else None,
        )
        try:
            if snapshot is not None and entry.path is not None:
                raw = snapshot.descriptors[entry.id]
            else:
                raw = (
                    discovered_suite.model_dump(by_alias=True, mode="json")
                    if discovered_suite is not None
                    else await self._descriptor_fetcher(catalog, entry)
                )
        except ModStoreSourceError as source_error:
            try:
                descriptor = self._local_install_descriptor(entry, suite_page_id)
            except ModStoreError:
                raise source_error
            descriptor_source = "bundled"
        else:
            descriptor_source = "remote"
            try:
                if suite_page_id is None:
                    descriptor = StoreModDescriptor.model_validate(raw)
                else:
                    suite = StoreModSuiteDescriptor.model_validate(raw)
                    if suite.id != entry.id:
                        raise ModStoreDescriptorError()
                    descriptor = next(
                        (
                            item
                            for item, _ in expand_mod_suite(suite)
                            if item.id == suite_page_id
                        ),
                        None,
                    )
                    if descriptor is None:
                        raise ModStoreDescriptorError()
            except ModStoreError:
                raise
            except (ValidationError, TypeError, ValueError) as error:
                raise ModStoreDescriptorError() from error
        if descriptor.id != mod_id:
            raise ModStoreDescriptorError()

        manifest = self._manifest(descriptor)
        current_by_id = {item.module_id: item for item in repository.list_installed()}
        current = current_by_id.get(mod_id)
        source_url = self._source_page_url(catalog, entry)
        if (
            current is not None
            and current.status == "published"
            and _manifest_equal(current.manifest, manifest)
        ):
            return StoreInstallResponse(
                action="unchanged",
                descriptor_source=descriptor_source,
                source_url=source_url,
                source_commit=snapshot.commit if snapshot else None,
                mod=current,
            )

        published = repository.install_batch([manifest])[0]
        return StoreInstallResponse(
            action="updated" if current is not None else "installed",
            descriptor_source=descriptor_source,
            source_url=source_url,
            source_commit=snapshot.commit if snapshot else None,
            mod=published,
        )

    async def install_project(
        self,
        project_id: str,
        repository: ModuleRepository,
    ) -> StoreProjectInstallResponse:
        if not re.fullmatch(r"^[a-z][a-z0-9-]{1,47}$", project_id):
            raise ModStoreNotFoundError()

        _, rows, snapshot = await self._active_mods()
        selected = [
            descriptor
            for _, descriptor, _ in rows
            if descriptor.manifest.navigation is not None
            and descriptor.manifest.navigation.project is not None
            and descriptor.manifest.navigation.project.id == project_id
        ]
        if not selected:
            selected = [
                descriptor
                for _, descriptor, _ in rows
                if (
                    descriptor.manifest.navigation.directory.id
                    if descriptor.manifest.navigation is not None
                    and descriptor.manifest.navigation.directory is not None
                    else descriptor.id
                )
                == project_id
            ]
        if not selected:
            raise ModStoreNotFoundError()

        installed = {item.module_id: item for item in repository.list_installed()}
        manifests = [self._manifest(descriptor) for descriptor in selected]
        changed = [
            manifest
            for manifest in manifests
            if (
                (current := installed.get(str(manifest["id"]))) is None
                or current.status != "published"
                or not _manifest_equal(current.manifest, manifest)
            )
        ]
        if not changed:
            modules = [installed[str(manifest["id"])] for manifest in manifests]
            action = "unchanged"
        else:
            modules = repository.install_batch(manifests)
            action = (
                "updated"
                if any(installed.get(item.module_id) for item in modules)
                else "installed"
            )
        return StoreProjectInstallResponse(
            action=action,
            project_id=project_id,
            source_commit=snapshot.commit if snapshot else None,
            mods=modules,
        )

    async def _fetch_descriptor(
        self,
        catalog: StoreCatalog,
        entry: StoreCatalogEntry | StoreSuiteCatalogEntry,
    ) -> dict[str, Any]:
        if isinstance(entry, StoreSuiteCatalogEntry) and entry.discovery is not None:
            return await self._fetch_descriptor_from_http(
                self._discovery_urls(entry),
                source_error=ModStoreDiscoveryError,
                fallback_statuses={404},
            )
        git_body = await self._fetch_descriptor_from_git(catalog, entry)
        if git_body is not None:
            return git_body
        return await self._fetch_descriptor_from_http(self._source_urls(catalog, entry))

    async def _fetch_descriptor_from_git(
        self,
        catalog: StoreCatalog,
        entry: StoreCatalogEntry | StoreSuiteCatalogEntry,
    ) -> dict[str, Any] | None:
        if entry.path is None:
            raise ModStoreCatalogError()
        repositories = [catalog.git.repository, *catalog.git.mirrors]
        descriptor_path = f"{catalog.git.path_prefix}/{entry.path}"
        timeout = self._settings.mod_store_git_timeout_seconds
        environment = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
        }
        try:
            with tempfile.TemporaryDirectory(
                prefix="newma-desk-mod-store-",
                dir=self._settings.runtime_dir,
            ) as directory:
                initialized = await self._run_git(
                    ["init", "--bare", directory],
                    timeout=timeout,
                    environment=environment,
                )
                if initialized is None:
                    return None
                for repository in repositories:
                    fetched = await self._run_git(
                        [
                            "--git-dir",
                            directory,
                            "fetch",
                            "--depth=1",
                            "--no-tags",
                            repository,
                            catalog.git.ref,
                        ],
                        timeout=timeout,
                        environment=environment,
                    )
                    if fetched is None:
                        continue
                    content = await self._run_git(
                        [
                            "--git-dir",
                            directory,
                            "show",
                            f"FETCH_HEAD:{descriptor_path}",
                        ],
                        timeout=timeout,
                        environment=environment,
                    )
                    if content is None:
                        continue
                    if len(content) > MAX_DESCRIPTOR_BYTES:
                        raise ModStoreDescriptorError()
                    try:
                        body = json.loads(content)
                    except json.JSONDecodeError as error:
                        raise ModStoreDescriptorError() from error
                    if not isinstance(body, dict):
                        raise ModStoreDescriptorError()
                    return body
        except OSError:
            return None
        return None

    async def _run_git(
        self,
        arguments: list[str],
        *,
        timeout: float,
        environment: dict[str, str],
    ) -> bytes | None:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=environment,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except FileNotFoundError:
            return None
        except TimeoutError:
            if process is not None and process.returncode is None:
                process.kill()
                await process.communicate()
            return None
        if process.returncode != 0:
            return None
        return stdout

    async def _fetch_descriptor_from_http(
        self,
        urls: list[str],
        *,
        source_error: type[ModStoreError] = ModStoreSourceError,
        fallback_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(self._settings.mod_store_git_timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            for url in urls:
                try:
                    async with client.stream(
                        "GET",
                        url,
                        headers={"Accept": "application/json"},
                    ) as response:
                        if response.status_code != 200:
                            if (
                                fallback_statuses is not None
                                and response.status_code not in fallback_statuses
                            ):
                                raise source_error()
                            continue
                        content_length = response.headers.get("content-length")
                        if content_length is not None:
                            try:
                                declared_size = int(content_length)
                            except ValueError as error:
                                raise ModStoreDescriptorError() from error
                            if declared_size > MAX_DESCRIPTOR_BYTES:
                                raise ModStoreDescriptorError()
                        chunks: list[bytes] = []
                        total_size = 0
                        async for chunk in response.aiter_bytes():
                            total_size += len(chunk)
                            if total_size > MAX_DESCRIPTOR_BYTES:
                                raise ModStoreDescriptorError()
                            chunks.append(chunk)
                except httpx.HTTPError:
                    continue
                content = b"".join(chunks)
                try:
                    body = json.loads(content)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ModStoreDescriptorError() from error
                if not isinstance(body, dict):
                    raise ModStoreDescriptorError()
                return body
        raise source_error()
