import asyncio
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from pydantic import ValidationError

from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.schemas import (
    ModuleManifest,
    manifest_repository_dict,
)
from vibe_visualization_api.mod_store.schemas import (
    ExternalRuntime,
    ModStoreResponse,
    StoreCatalog,
    StoreCatalogEntry,
    StoreInstallResponse,
    StoreModDescriptor,
    StoreModResponse,
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


class ModStoreDescriptorError(ModStoreError):
    status_code = 422
    detail = "Git returned an invalid Mod descriptor"


DescriptorFetcher = Callable[
    [StoreCatalog, StoreCatalogEntry],
    Awaitable[dict[str, Any]],
]


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
    ) -> None:
        self._settings = settings
        self._store_dir = settings.mod_store_dir
        self._descriptor_fetcher = descriptor_fetcher or self._fetch_descriptor

    def _catalog(self) -> StoreCatalog:
        try:
            raw = json.loads((self._store_dir / "store.json").read_text("utf-8"))
            return StoreCatalog.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise ModStoreCatalogError() from error

    def _entry(self, catalog: StoreCatalog, mod_id: str) -> StoreCatalogEntry:
        try:
            return next(item for item in catalog.mods if item.id == mod_id)
        except StopIteration as error:
            raise ModStoreNotFoundError() from error

    def _descriptor_path(self, entry: StoreCatalogEntry) -> Path:
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

    def _source_urls(
        self,
        catalog: StoreCatalog,
        entry: StoreCatalogEntry,
    ) -> list[str]:
        encoded_path = "/".join(quote(part, safe="") for part in entry.path.split("/"))
        return [
            f"{base.rstrip('/')}/{encoded_path}"
            for base in catalog.git.raw_base_urls
        ]

    def _source_page_url(
        self,
        catalog: StoreCatalog,
        entry: StoreCatalogEntry,
    ) -> str:
        encoded_path = "/".join(quote(part, safe="") for part in entry.path.split("/"))
        encoded_prefix = "/".join(
            quote(part, safe="") for part in catalog.git.path_prefix.split("/")
        )
        return (
            f"{catalog.git.repository}/blob/{quote(catalog.git.ref, safe='')}/"
            f"{encoded_prefix}/{encoded_path}"
        )

    def _setting_for_env(self, env_name: str, fallback: str) -> str:
        field_name = env_name.removeprefix("VIBEDESK_").lower()
        value = getattr(self._settings, field_name, None)
        return value if isinstance(value, str) and value else fallback

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
            "schemaVersion": "1.0",
            "id": descriptor.id,
            "name": descriptor.name,
            "version": descriptor.version,
            **descriptor.manifest.model_dump(
                by_alias=True,
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

    def list(self, repository: ModuleRepository) -> ModStoreResponse:
        catalog = self._catalog()
        installed = {item.module_id: item for item in repository.list_published()}
        rows: list[StoreModResponse] = []
        for entry in catalog.mods:
            descriptor = self._local_descriptor(entry)
            manifest = self._manifest(descriptor)
            current = installed.get(entry.id)
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
                    upstream=descriptor.upstream,
                    category=descriptor.manifest.navigation.group_label
                    if descriptor.manifest.navigation is not None
                    else descriptor.manifest.category,
                    tags=descriptor.tags,
                    default_install=entry.default_install,
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
        entry = self._entry(catalog, mod_id)
        try:
            raw = await self._descriptor_fetcher(catalog, entry)
            descriptor = StoreModDescriptor.model_validate(raw)
        except ModStoreError:
            raise
        except (ValidationError, TypeError, ValueError) as error:
            raise ModStoreDescriptorError() from error
        if descriptor.id != mod_id:
            raise ModStoreDescriptorError()

        manifest = self._manifest(descriptor)
        current_by_id = {
            item.module_id: item for item in repository.list_published()
        }
        current = current_by_id.get(mod_id)
        source_url = self._source_page_url(catalog, entry)
        if current is not None and _manifest_equal(current.manifest, manifest):
            return StoreInstallResponse(
                action="unchanged",
                source_url=source_url,
                mod=current,
            )

        draft = repository.create_draft(manifest)
        published = repository.publish(mod_id, draft.revision)
        return StoreInstallResponse(
            action="updated" if current is not None else "installed",
            source_url=source_url,
            mod=published,
        )

    async def _fetch_descriptor(
        self,
        catalog: StoreCatalog,
        entry: StoreCatalogEntry,
    ) -> dict[str, Any]:
        git_body = await self._fetch_descriptor_from_git(catalog, entry)
        if git_body is not None:
            return git_body
        return await self._fetch_descriptor_from_http(
            self._source_urls(catalog, entry)
        )

    async def _fetch_descriptor_from_git(
        self,
        catalog: StoreCatalog,
        entry: StoreCatalogEntry,
    ) -> dict[str, Any] | None:
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
                prefix="vibedesk-mod-store-",
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
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(self._settings.mod_store_git_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for url in urls:
                try:
                    response = await client.get(
                        url,
                        headers={"Accept": "application/json"},
                    )
                except httpx.HTTPError:
                    continue
                if response.status_code != 200:
                    continue
                if len(response.content) > MAX_DESCRIPTOR_BYTES:
                    raise ModStoreDescriptorError()
                try:
                    body = response.json()
                except ValueError as error:
                    raise ModStoreDescriptorError() from error
                if not isinstance(body, dict):
                    raise ModStoreDescriptorError()
                return body
        raise ModStoreSourceError()
