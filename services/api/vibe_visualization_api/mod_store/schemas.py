from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from vibe_visualization_api.control_plane.schemas import (
    ApiModel,
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


class StoreCatalog(ApiModel):
    schema_version: Literal["1.0"]
    id: str = Field(pattern=STORE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    git: StoreGitSource
    mods: list[StoreCatalogEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_mods(self):
        ids = [item.id for item in self.mods]
        paths = [item.path for item in self.mods]
        if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
            raise ValueError("store catalog contains duplicate Mods")
        return self


class ExternalRuntime(ApiModel):
    type: Literal["external"]
    base_url_env: str = Field(pattern=r"^VIBEDESK_[A-Z0-9_]+$")
    default_base_url: str
    route: str = Field(min_length=1, max_length=240)

    @field_validator("default_base_url")
    @classmethod
    def validate_default_base_url(cls, value: str) -> str:
        return _http_origin(value)

    @field_validator("route")
    @classmethod
    def validate_route(cls, value: str) -> str:
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "\\" in value
            or ".." in value
        ):
            raise ValueError("external route must be a safe absolute path")
        return value


class DirectRuntime(ApiModel):
    type: Literal["direct"]
    entry: ModuleEntry


StoreRuntime = Annotated[
    ExternalRuntime | DirectRuntime,
    Field(discriminator="type"),
]


class StoreManifestTemplate(ApiModel):
    category: str = Field(pattern=MODULE_CATEGORY_PATTERN)
    navigation: ModuleNavigation | None = None
    icon: str | None = None
    permissions: list[str] = Field(default_factory=list)
    data_services: list[str] = Field(default_factory=list)
    agent_capabilities: list[str] = Field(default_factory=list)
    events: ModuleEvents = Field(default_factory=ModuleEvents)
    refresh: ModuleRefresh | None = None


class StoreModDescriptor(ApiModel):
    schema_version: Literal["1.0"]
    id: str = Field(pattern=MODULE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    version: str = Field(pattern=MODULE_VERSION_PATTERN)
    publisher: str = Field(min_length=1, max_length=80)
    upstream: str
    tags: list[str] = Field(default_factory=list, max_length=8)
    runtime: StoreRuntime
    manifest: StoreManifestTemplate

    @field_validator("upstream")
    @classmethod
    def validate_upstream(cls, value: str) -> str:
        return _https_url(value, "upstream")


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
