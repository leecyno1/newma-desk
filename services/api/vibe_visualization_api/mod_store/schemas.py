import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from vibe_visualization_api.control_plane.schemas import (
    ApiModel,
    ModuleAction,
    ModuleCompatibility,
    ModuleEntry,
    ModuleEvents,
    ModuleNavigation,
    ModuleRefresh,
    StoredModuleResponse,
)


MODULE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
MODULE_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
MODULE_CATEGORY_PATTERN = r"^[a-z][a-z0-9-]{1,31}$"
STORE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
SUITE_ID_PATTERN = r"^[a-z][a-z0-9-]{1,47}$"
WELL_KNOWN_SUITE_PATH = "/.well-known/newma-dock-suite.json"
LEGACY_WELL_KNOWN_SUITE_PATH = "/.well-known/vibedesk-suite.json"
SUITE_ENV_PATTERN = r"^(?:NEWMA_DOCK|VIBEDESK)_[A-Z0-9_]+$"


def _https_url(value: str, label: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{label} must be an HTTPS URL")
    return value.rstrip("/")


def _http_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("defaultBaseUrl must be an HTTP(S) origin")
    return f"{parsed.scheme}://{parsed.netloc}"


def _external_route(value: str) -> str:
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or ".." in value
    ):
        raise ValueError("external route must be a safe absolute path")
    return value


class StoreGitSource(ApiModel):
    repository: str
    ref: str = Field(min_length=1, max_length=120)
    path_prefix: str = Field(min_length=1, max_length=120)
    mirrors: list[str] = Field(default_factory=list, max_length=4)
    raw_base_urls: list[str] = Field(min_length=1, max_length=4)

    @field_validator("repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        return _https_url(value, "repository")

    @field_validator("mirrors")
    @classmethod
    def validate_mirrors(cls, values: list[str]) -> list[str]:
        return [_https_url(value, "mirrors") for value in values]

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        if (
            not value[0].isalnum()
            or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/-" for character in value)
            or ".." in value
            or "//" in value
        ):
            raise ValueError("ref must be a safe Git reference")
        return value

    @field_validator("raw_base_urls")
    @classmethod
    def validate_raw_base_urls(cls, values: list[str]) -> list[str]:
        return [_https_url(value, "rawBaseUrls") for value in values]

    @field_validator("path_prefix")
    @classmethod
    def validate_path_prefix(cls, value: str) -> str:
        if (
            value.startswith(('/', '\\'))
            or "\\" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("pathPrefix must be a safe repository path")
        return value


class StoreCatalogEntry(ApiModel):
    id: str = Field(pattern=MODULE_ID_PATTERN)
    path: str = Field(min_length=1, max_length=240)
    default_install: bool = False

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if (
            value.startswith(('/', '\\'))
            or "\\" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or not value.endswith("/mod.json")
        ):
            raise ValueError("store Mod path must be a safe */mod.json path")
        return value


class StoreHttpSuiteDiscovery(ApiModel):
    type: Literal["http"]
    base_url_env: str = Field(pattern=SUITE_ENV_PATTERN)
    default_base_url: str
    path: str = WELL_KNOWN_SUITE_PATH

    @field_validator("default_base_url")
    @classmethod
    def validate_default_base_url(cls, value: str) -> str:
        return _http_origin(value)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if value not in {WELL_KNOWN_SUITE_PATH, LEGACY_WELL_KNOWN_SUITE_PATH}:
            raise ValueError(
                "HTTP Suite Discovery path must be "
                f"{WELL_KNOWN_SUITE_PATH} or {LEGACY_WELL_KNOWN_SUITE_PATH}"
            )
        return value


class StoreSuiteCatalogEntry(ApiModel):
    id: str = Field(pattern=SUITE_ID_PATTERN)
    path: str | None = Field(default=None, min_length=1, max_length=240)
    discovery: StoreHttpSuiteDiscovery | None = None
    default_install: bool = False

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            value.startswith(('/', '\\'))
            or "\\" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or not value.endswith("/suite.json")
        ):
            raise ValueError("store Mod Suite path must be a safe */suite.json path")
        return value

    @model_validator(mode="after")
    def validate_source(self):
        if (self.path is None) == (self.discovery is None):
            raise ValueError(
                "store Mod Suite must declare exactly one Suite Discovery source"
            )
        return self


class StoreCatalog(ApiModel):
    schema_version: Literal["1.0"]
    id: str = Field(pattern=STORE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    git: StoreGitSource
    mods: list[StoreCatalogEntry] = Field(default_factory=list)
    suites: list[StoreSuiteCatalogEntry] = Field(default_factory=list)
    retired_mods: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_mods(self):
        if not self.mods and not self.suites:
            raise ValueError("store catalog must contain a Mod or Mod Suite")
        ids = [item.id for item in self.mods]
        suite_ids = [item.id for item in self.suites]
        paths = [item.path for item in self.mods] + [
            item.path for item in self.suites if item.path is not None
        ]
        suite_sources = [
            f"file:{item.path}"
            if item.path is not None
            else (
                f"http:{item.discovery.base_url_env}:"
                f"{item.discovery.default_base_url}:{item.discovery.path}"
            )
            for item in self.suites
            if item.path is not None or item.discovery is not None
        ]
        if (
            len(ids) != len(set(ids))
            or len(suite_ids) != len(set(suite_ids))
            or set(ids).intersection(suite_ids)
            or len(paths) != len(set(paths))
            or len(suite_sources) != len(set(suite_sources))
            or len(self.retired_mods) != len(set(self.retired_mods))
            or any(re.fullmatch(MODULE_ID_PATTERN, item) is None for item in self.retired_mods)
            or set(ids).intersection(self.retired_mods)
        ):
            raise ValueError("store catalog contains duplicate Mods or Mod Suites")
        return self


class ExternalRuntime(ApiModel):
    type: Literal["external"]
    base_url_env: str = Field(pattern=SUITE_ENV_PATTERN)
    default_base_url: str
    route: str = Field(min_length=1, max_length=240)

    @field_validator("default_base_url")
    @classmethod
    def validate_default_base_url(cls, value: str) -> str:
        return _http_origin(value)

    @field_validator("route")
    @classmethod
    def validate_route(cls, value: str) -> str:
        return _external_route(value)


class DirectRuntime(ApiModel):
    type: Literal["direct"]
    entry: ModuleEntry


StoreRuntime = Annotated[
    ExternalRuntime | DirectRuntime,
    Field(discriminator="type"),
]


class StoreManifestTemplate(ApiModel):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    category: str = Field(pattern=MODULE_CATEGORY_PATTERN)
    navigation: ModuleNavigation | None = None
    icon: str | None = None
    permissions: list[str] = Field(default_factory=list)
    data_services: list[str] = Field(default_factory=list)
    compatibility: ModuleCompatibility | None = None
    agent_capabilities: list[str] | None = None
    actions: dict[str, ModuleAction] | None = None
    events: ModuleEvents = Field(default_factory=ModuleEvents)
    refresh: ModuleRefresh | None = None

    @model_validator(mode="before")
    @classmethod
    def apply_versioned_defaults(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        schema_version = normalized.get("schemaVersion", "1.0")
        if schema_version == "1.0":
            normalized.setdefault("agentCapabilities", [])
        elif schema_version == "1.1":
            normalized.setdefault("actions", {})
        return normalized

    @model_validator(mode="after")
    def validate_versioned_template(self):
        if self.schema_version == "1.0":
            if self.compatibility is not None or self.actions is not None:
                raise ValueError("Manifest template 1.0 cannot declare 1.1 fields")
            return self
        if self.compatibility is None or self.actions is None:
            raise ValueError("Manifest template 1.1 requires compatibility and actions")
        if self.agent_capabilities is not None:
            raise ValueError("Manifest template 1.1 must use explicit action bindings")
        return self


class StoreModDescriptor(ApiModel):
    schema_version: Literal["1.0"]
    id: str = Field(pattern=MODULE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    version: str = Field(pattern=MODULE_VERSION_PATTERN)
    publisher: str = Field(min_length=1, max_length=80)
    upstream: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=8)
    runtime: StoreRuntime
    manifest: StoreManifestTemplate

    @field_validator("upstream")
    @classmethod
    def validate_upstream(cls, value: str | None) -> str | None:
        return _https_url(value, "upstream") if value is not None else None


class SuiteExternalRuntime(ApiModel):
    type: Literal["external"]
    base_url_env: str = Field(pattern=SUITE_ENV_PATTERN)
    default_base_url: str

    @field_validator("default_base_url")
    @classmethod
    def validate_default_base_url(cls, value: str) -> str:
        return _http_origin(value)


class StoreSuitePageNavigation(ApiModel):
    item_order: int | None = Field(default=None, ge=0)
    label: str | None = Field(default=None, min_length=1, max_length=40)
    icon: Literal[
        "today",
        "research",
        "market",
        "quant",
        "trading",
        "settings",
        "module",
    ] | None = None
    role: Literal["page", "settings"] | None = None


class StoreSuitePageManifest(ApiModel):
    icon: str | None = None
    permissions: list[str] | None = None
    data_services: list[str] | None = None
    compatibility: ModuleCompatibility | None = None
    agent_capabilities: list[str] | None = None
    actions: dict[str, ModuleAction] | None = None
    events: ModuleEvents | None = None
    refresh: ModuleRefresh | None = None


class StoreSuitePage(ApiModel):
    id: str = Field(pattern=MODULE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    tags: list[str] | None = Field(default=None, max_length=8)
    route: str = Field(min_length=1, max_length=240)
    navigation: StoreSuitePageNavigation = Field(
        default_factory=StoreSuitePageNavigation
    )
    manifest: StoreSuitePageManifest = Field(default_factory=StoreSuitePageManifest)
    default_install: bool | None = None

    @field_validator("route")
    @classmethod
    def validate_route(cls, value: str) -> str:
        return _external_route(value)


class StoreModSuiteDescriptor(ApiModel):
    schema_version: Literal["1.0"]
    id: str = Field(pattern=SUITE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    version: str = Field(pattern=MODULE_VERSION_PATTERN)
    publisher: str = Field(min_length=1, max_length=80)
    upstream: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=8)
    runtime: SuiteExternalRuntime
    manifest: StoreManifestTemplate
    pages: list[StoreSuitePage] = Field(min_length=1)

    @field_validator("upstream")
    @classmethod
    def validate_upstream(cls, value: str | None) -> str | None:
        return _https_url(value, "upstream") if value is not None else None

    @model_validator(mode="after")
    def validate_navigation_and_pages(self):
        navigation = self.manifest.navigation
        if (
            navigation is None
            or navigation.directory is None
            or navigation.directory.id != self.id
        ):
            raise ValueError(
                "Mod Suite navigation directory id must equal the Suite id"
            )
        page_ids = [page.id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("Mod Suite contains duplicate page ids")
        return self


def expand_mod_suite(
    suite: StoreModSuiteDescriptor,
) -> list[tuple[StoreModDescriptor, bool | None]]:
    shared_manifest = suite.manifest.model_dump(
        by_alias=True,
        exclude_none=True,
        mode="json",
    )
    shared_navigation = suite.manifest.navigation
    if shared_navigation is None:  # guarded by StoreModSuiteDescriptor
        raise ValueError("Mod Suite navigation is required")

    expanded: list[tuple[StoreModDescriptor, bool | None]] = []
    for page in suite.pages:
        page_manifest = page.manifest.model_dump(
            by_alias=True,
            exclude_none=True,
            mode="json",
        )
        navigation = shared_navigation.model_dump(
            by_alias=True,
            exclude_none=True,
            mode="json",
        )
        if page.navigation.item_order is not None:
            navigation["itemOrder"] = page.navigation.item_order
        navigation["label"] = page.navigation.label or page.name
        if page.navigation.icon is not None:
            navigation["icon"] = page.navigation.icon
        if page.navigation.role is not None:
            navigation["role"] = page.navigation.role

        descriptor = StoreModDescriptor.model_validate(
            {
                "schemaVersion": "1.0",
                "id": page.id,
                "name": page.name,
                "description": page.description,
                "version": suite.version,
                "publisher": suite.publisher,
                "upstream": suite.upstream,
                "tags": page.tags if page.tags is not None else suite.tags,
                "runtime": {
                    "type": "external",
                    "baseUrlEnv": suite.runtime.base_url_env,
                    "defaultBaseUrl": suite.runtime.default_base_url,
                    "route": page.route,
                },
                "manifest": {
                    **shared_manifest,
                    **page_manifest,
                    "navigation": navigation,
                },
            }
        )
        expanded.append((descriptor, page.default_install))
    return expanded


class StoreResponseModel(ApiModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        from_attributes=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class StoreModResponse(StoreResponseModel):
    id: str
    name: str
    description: str
    version: str
    publisher: str
    upstream: str
    category: str
    tags: list[str]
    default_install: bool
    install_state: Literal["available", "installed", "update-available"]
    installed_revision: int | None = None
    source_url: str


class ModStoreResponse(StoreResponseModel):
    id: str
    name: str
    repository: str
    ref: str
    mods: list[StoreModResponse]


class StoreInstallResponse(StoreResponseModel):
    action: Literal["installed", "updated", "unchanged"]
    source_url: str
    mod: StoredModuleResponse
