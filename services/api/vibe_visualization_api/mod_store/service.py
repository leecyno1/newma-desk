from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
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
    StoreSuiteCatalogEntry,
    RuntimeAgentWorkspace,
    WELL_KNOWN_SUITE_PATH,
    expand_mod_suite,
)


MAX_DESCRIPTOR_BYTES = 256 * 1024


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


DescriptorFetcher = Callable[
    [StoreCatalog, StoreCatalogEntry | StoreSuiteCatalogEntry],
    Awaitable[dict[str, Any]],
]
RuntimeWorkspaceResolver = Callable[[str, str], Path]


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
        runtime_workspace_resolver: RuntimeWorkspaceResolver | None = None,
    ) -> None:
        self._settings = settings
        self._store_dir = settings.mod_store_dir
        self._descriptor_fetcher = descriptor_fetcher or self._fetch_descriptor
        self._runtime_workspace_resolver = (
            runtime_workspace_resolver or resolve_runtime_workspace
        )

    def _catalog(self) -> StoreCatalog:
        try:
            raw = json.loads((self._store_dir / "store.json").read_text("utf-8"))
            return StoreCatalog.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise ModStoreCatalogError() from error

    async def _entry(
        self,
        catalog: StoreCatalog,
        mod_id: str,
    ) -> tuple[
        StoreCatalogEntry | StoreSuiteCatalogEntry,
        str | None,
        StoreModSuiteDescriptor | None,
    ]:
        standalone = next((item for item in catalog.mods if item.id == mod_id), None)
        if standalone is not None:
            return standalone, None, None
        for suite_entry in catalog.suites:
            suite = await self._suite_descriptor(catalog, suite_entry)
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
    ) -> StoreModSuiteDescriptor:
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
            (
                item
                for item, _ in expand_mod_suite(suite)
                if item.id == suite_page_id
            ),
            None,
        )
        if descriptor is None:
            raise ModStoreCatalogError()
        return descriptor

    async def list(self, repository: ModuleRepository) -> ModStoreResponse:
        catalog = self._catalog()
        installed = {item.module_id: item for item in repository.list_published()}
        rows: list[StoreModResponse] = []
        for entry, descriptor, default_install in await self._local_mods(catalog):
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
                    source_url=self._source_page_url(catalog, entry),
                )
            )
        return ModStoreResponse(
            id=catalog.id,
            name=catalog.name,
            repository=catalog.git.repository,
            ref=catalog.git.ref,
            mods=rows,
        )

    async def install(
        self,
        mod_id: str,
        repository: ModuleRepository,
    ) -> StoreInstallResponse:
        catalog = self._catalog()
        entry, suite_page_id, discovered_suite = await self._entry(catalog, mod_id)
        try:
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
        current_by_id = {item.module_id: item for item in repository.list_published()}
        current = current_by_id.get(mod_id)
        source_url = self._source_page_url(catalog, entry)
        if current is not None and _manifest_equal(current.manifest, manifest):
            return StoreInstallResponse(
                action="unchanged",
                descriptor_source=descriptor_source,
                source_url=source_url,
                mod=current,
            )

        draft = repository.create_draft(manifest)
        published = repository.publish(mod_id, draft.revision)
        return StoreInstallResponse(
            action="updated" if current is not None else "installed",
            descriptor_source=descriptor_source,
            source_url=source_url,
            mod=published,
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
