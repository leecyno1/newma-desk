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
    ModuleNavigationDirectory,
    ModuleNavigationProject,
    ModuleRefresh,
    ModuleStorage,
    ModuleWikiProfile,
    StoredModuleResponse,
)

MODULE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
MODULE_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
MODULE_CATEGORY_PATTERN = r"^[a-z][a-z0-9-]{1,31}$"
STORE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
SUITE_ID_PATTERN = r"^[a-z][a-z0-9-]{1,47}$"
WELL_KNOWN_SUITE_PATH = "/.well-known/newma-desk-suite.json"
LEGACY_NEWMA_DOCK_SUITE_PATH = "/.well-known/newma-dock-suite.json"
LEGACY_VIBEDESK_SUITE_PATH = "/.well-known/vibedesk-suite.json"
SUITE_ENV_PATTERN = r"^(?:NEWMA_DESK|NEWMA_DOCK|VIBEDESK)_[A-Z0-9_]+$"
RUNTIME_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
RUNTIME_WORKSPACE_PATTERN = r"^[a-z][a-z0-9-]{1,31}$"
INVESTMENT_DOMAIN_IDS = {
    "market-surface",
    "fundamentals",
    "global-intelligence",
    "capital-flow",
    "event-intelligence",
    "policy-intelligence",
    "cycle-research",
    "asset-allocation",
    "tactical-timing",
    "equity-research",
    "fund-research",
    "bond-research",
    "quant-research",
    "investment-committee",
    "trading-risk-portfolio",
}


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
            or any(
                character
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/-"
                for character in value
            )
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
            value.startswith(("/", "\\"))
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
            value.startswith(("/", "\\"))
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
        if value not in {
            WELL_KNOWN_SUITE_PATH,
            LEGACY_NEWMA_DOCK_SUITE_PATH,
            LEGACY_VIBEDESK_SUITE_PATH,
        }:
            raise ValueError(
                "HTTP Suite Discovery path must be "
                f"{WELL_KNOWN_SUITE_PATH}, {LEGACY_NEWMA_DOCK_SUITE_PATH} "
                f"or {LEGACY_VIBEDESK_SUITE_PATH}"
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
            value.startswith(("/", "\\"))
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
            or any(
                re.fullmatch(MODULE_ID_PATTERN, item) is None
                for item in self.retired_mods
            )
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


class DeskAgentWorkspace(ApiModel):
    """Allow the Agent to operate in the trusted Newma-Desk source tree."""

    type: Literal["desk"]


class RuntimeAgentWorkspace(ApiModel):
    """Resolve an Agent workspace through the restricted Runtime Descriptor."""

    type: Literal["runtime"]
    runtime_id: str = Field(pattern=RUNTIME_ID_PATTERN)
    workspace_name: str = Field(pattern=RUNTIME_WORKSPACE_PATTERN)


AgentWorkspace = Annotated[
    DeskAgentWorkspace | RuntimeAgentWorkspace,
    Field(discriminator="type"),
]


class StoreManifestTemplate(ApiModel):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    category: str = Field(pattern=MODULE_CATEGORY_PATTERN)
    navigation: ModuleNavigation | None = None
    icon: str | None = None
    permissions: list[str] = Field(default_factory=list)
    data_services: list[str] = Field(default_factory=list)
    storage: ModuleStorage | None = None
    wiki: ModuleWikiProfile | None = None
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
            if (
                self.compatibility is not None
                or self.storage is not None
                or self.wiki is not None
                or self.actions is not None
            ):
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
    agent_workspace: AgentWorkspace | None = None
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
    group_label: str | None = Field(default=None, min_length=1, max_length=40)
    group_order: int | None = Field(default=None, ge=0)
    item_order: int | None = Field(default=None, ge=0)
    label: str | None = Field(default=None, min_length=1, max_length=40)
    directory: ModuleNavigationDirectory | None = None
    project: ModuleNavigationProject | None = None
    icon: (
        Literal[
            "today",
            "research",
            "market",
            "quant",
            "trading",
            "settings",
            "module",
        ]
        | None
    ) = None
    role: Literal["page", "settings"] | None = None


class StoreSuitePageManifest(ApiModel):
    schema_version: Literal["1.0", "1.1"] | None = None
    category: str | None = Field(default=None, pattern=MODULE_CATEGORY_PATTERN)
    icon: str | None = None
    permissions: list[str] | None = None
    data_services: list[str] | None = None
    storage: ModuleStorage | None = None
    wiki: ModuleWikiProfile | None = None
    compatibility: ModuleCompatibility | None = None
    agent_capabilities: list[str] | None = None
    actions: dict[str, ModuleAction] | None = None
    events: ModuleEvents | None = None
    refresh: ModuleRefresh | None = None


class StoreSuitePage(ApiModel):
    id: str = Field(pattern=MODULE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    version: str | None = Field(default=None, pattern=MODULE_VERSION_PATTERN)
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
    agent_workspace: AgentWorkspace | None = None
    manifest: StoreManifestTemplate
    pages: list[StoreSuitePage] = Field(min_length=1)

    @field_validator("upstream")
    @classmethod
    def validate_upstream(cls, value: str | None) -> str | None:
        return _https_url(value, "upstream") if value is not None else None

    @model_validator(mode="after")
    def validate_navigation_and_pages(self):
        navigation = self.manifest.navigation
        if navigation is None:
            raise ValueError("Mod Suite navigation is required")
        if navigation.directory is None or navigation.directory.id != self.id:
            raise ValueError(
                f"Mod Suite must use navigation.directory.id={self.id} "
                "to remain one complete project"
            )
        domain_id = navigation.project.id if navigation.project is not None else self.id
        if domain_id not in INVESTMENT_DOMAIN_IDS and domain_id != self.id:
            raise ValueError(
                "Mod Suite must use an investment domain or its own suite id as project id"
            )
        page_ids = [page.id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("Mod Suite contains duplicate page ids")
        for page in self.pages:
            page_navigation = page.navigation
            if (
                page_navigation.project is not None
                and page_navigation.project.id != domain_id
            ):
                raise ValueError(
                    "Mod Suite cannot split pages across investment domains"
                )
            if (
                page_navigation.directory is not None
                and page_navigation.directory.id != navigation.directory.id
            ):
                raise ValueError(
                    "Mod Suite cannot split pages into another project group"
                )
            if (
                page_navigation.group_label is not None
                and page_navigation.group_label != navigation.group_label
            ) or (
                page_navigation.group_order is not None
                and page_navigation.group_order != navigation.group_order
            ):
                raise ValueError(
                    "Mod Suite cannot split pages across navigation groups"
                )
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
        navigation.setdefault("project", {
            "id": suite.id,
            "name": suite.name,
            "order": shared_navigation.group_order,
            "description": suite.description,
        })
        if page.navigation.item_order is not None:
            navigation["itemOrder"] = page.navigation.item_order
        navigation["label"] = page.navigation.label or page.name
        if page.navigation.icon is not None:
            navigation["icon"] = page.navigation.icon
        if page.navigation.role is not None:
            navigation["role"] = page.navigation.role

        merged_manifest = {
            **shared_manifest,
            **page_manifest,
            "navigation": navigation,
        }
        merged_schema_version = merged_manifest.get("schemaVersion", "1.0")
        if merged_schema_version == "1.1":
            merged_manifest.pop("agentCapabilities", None)
        else:
            merged_manifest.pop("compatibility", None)
            merged_manifest.pop("actions", None)

        descriptor = StoreModDescriptor.model_validate(
            {
                "schemaVersion": "1.0",
                "id": page.id,
                "name": page.name,
                "description": page.description,
                "version": page.version or suite.version,
                "publisher": suite.publisher,
                "upstream": suite.upstream,
                "tags": page.tags if page.tags is not None else suite.tags,
                "runtime": {
                    "type": "external",
                    "baseUrlEnv": suite.runtime.base_url_env,
                    "defaultBaseUrl": suite.runtime.default_base_url,
                    "route": page.route,
                },
                **(
                    {
                        "agentWorkspace": suite.agent_workspace.model_dump(
                            by_alias=True,
                            mode="json",
                        )
                    }
                    if suite.agent_workspace is not None
                    else {}
                ),
                "manifest": merged_manifest,
            }
        )
        expanded.append((descriptor, page.default_install))
    return expanded


def validate_complete_project_groups(
    descriptors: list[StoreModDescriptor],
) -> None:
    groups: dict[str, list[ModuleNavigation]] = {}
    for descriptor in descriptors:
        navigation = descriptor.manifest.navigation
        if navigation is None or navigation.directory is None:
            continue
        groups.setdefault(navigation.directory.id, []).append(navigation)

    for directory_id, members in groups.items():
        project_ids = {
            navigation.project.id if navigation.project is not None else None
            for navigation in members
        }
        group_labels = {navigation.group_label for navigation in members}
        group_orders = {navigation.group_order for navigation in members}
        directory_labels = {
            navigation.directory.label
            for navigation in members
            if navigation.directory is not None
        }
        if (
            len(project_ids) != 1
            or None in project_ids
            or len(group_labels) != 1
            or len(group_orders) != 1
            or len(directory_labels) != 1
        ):
            raise ValueError(
                f"{directory_id} is one complete project and cannot be split "
                "across Desk columns"
            )


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
    suite_id: str
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
    installed_version: str | None = None
    installed_status: Literal["published", "disabled"] | None = None
    navigation: ModuleNavigation | None = None
    source_url: str


class ModStoreResponse(StoreResponseModel):
    id: str
    name: str
    repository: str
    ref: str
    catalog_source: Literal["bundled", "github"] = "bundled"
    commit: str | None = None
    synced_at: str | None = None
    mods: list[StoreModResponse]


class StoreInstallResponse(StoreResponseModel):
    action: Literal["installed", "updated", "unchanged"]
    descriptor_source: Literal["remote", "bundled"]
    source_url: str
    source_commit: str | None = None
    mod: StoredModuleResponse


class StoreProjectInstallResponse(StoreResponseModel):
    action: Literal["installed", "updated", "unchanged"]
    project_id: str
    source_commit: str | None = None
    mods: list[StoredModuleResponse]
