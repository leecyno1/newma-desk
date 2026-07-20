import re
from typing import Annotated, Literal
from urllib.parse import unquote_to_bytes, urljoin, urlsplit

from pydantic import (
    AfterValidator,
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from pydantic.alias_generators import to_camel


LOCAL_URL_ORIGIN = "https://module.local"
MODULE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
MODULE_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
MODULE_CATEGORY_PATTERN = r"^[a-z][a-z0-9-]{1,31}$"
MODULE_EVENT_PATTERN = r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$"
INVALID_PERCENT_ENCODING = re.compile(r"%(?![0-9a-fA-F]{2})")
URL_ADAPTER = TypeAdapter(AnyUrl)


def _decode_uri_component(value: str) -> str:
    if INVALID_PERCENT_ENCODING.search(value):
        raise ValueError("malformed percent encoding")
    try:
        return unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("malformed URL encoding") from error


def _fully_decode(value: str) -> str | None:
    decoded = value
    for _ in range(10):
        try:
            next_value = _decode_uri_component(decoded)
        except ValueError:
            return None
        if next_value == decoded:
            return decoded
        decoded = next_value
    return None


def _validate_local_url(value: str) -> str:
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or ".." in value
    ):
        raise ValueError("unsafe local module URL")

    path_end_candidates = [
        position for marker in "?#" if (position := value.find(marker)) >= 0
    ]
    path_end = min(path_end_candidates, default=len(value))
    decoded_path = _fully_decode(value[:path_end])
    if (
        decoded_path is None
        or not decoded_path.startswith("/")
        or decoded_path.startswith("//")
        or "\\" in decoded_path
        or ".." in decoded_path
        or "." in decoded_path.split("/")
    ):
        raise ValueError("unsafe local module URL")

    try:
        resolved = urlsplit(urljoin(LOCAL_URL_ORIGIN, value))
        origin = f"{resolved.scheme}://{resolved.netloc}"
    except ValueError as error:
        raise ValueError("invalid local module URL") from error
    if origin != LOCAL_URL_ORIGIN:
        raise ValueError("local module URL must stay on the module origin")
    return value


def _validate_external_url(value: str) -> str:
    try:
        parsed = URL_ADAPTER.validate_python(value)
    except ValidationError as error:
        raise ValueError("invalid external module URL") from error
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("external module URL must use HTTP or HTTPS")
    return value


LocalUrl = Annotated[str, AfterValidator(_validate_local_url)]
ExternalUrl = Annotated[str, AfterValidator(_validate_external_url)]
ModuleEventName = Annotated[str, Field(pattern=MODULE_EVENT_PATTERN)]


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=False,
    )


class StructuredEntry(ApiModel):
    type: Literal["structured"]
    url: LocalUrl


class StaticEntry(ApiModel):
    type: Literal["static"]
    url: LocalUrl


class ExternalEntry(ApiModel):
    type: Literal["external"]
    url: ExternalUrl


ModuleEntry = Annotated[
    StructuredEntry | StaticEntry | ExternalEntry,
    Field(discriminator="type"),
]


class ManualRefresh(ApiModel):
    mode: Literal["manual"]


class ScheduledRefresh(ApiModel):
    mode: Literal["schedule"]
    cron: str = Field(min_length=1)


ModuleRefresh = Annotated[
    ManualRefresh | ScheduledRefresh,
    Field(discriminator="mode"),
]


class ModuleEvents(ApiModel):
    emits: list[ModuleEventName] = Field(default_factory=list)
    accepts: list[ModuleEventName] = Field(default_factory=list)


class ModuleNavigation(ApiModel):
    group_label: str = Field(min_length=1, max_length=40)
    group_order: int = Field(default=100, ge=0)
    item_order: int = Field(default=100, ge=0)
    icon: Literal["research", "market", "quant", "module"] = "module"


class ModuleManifest(ApiModel):
    schema_version: Literal["1.0"]
    id: str = Field(pattern=MODULE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(pattern=MODULE_VERSION_PATTERN)
    category: str = Field(pattern=MODULE_CATEGORY_PATTERN)
    navigation: ModuleNavigation | None = None
    entry: ModuleEntry
    icon: str | None = None
    permissions: list[str] = Field(default_factory=list)
    data_services: list[str] = Field(default_factory=list)
    agent_capabilities: list[str] = Field(default_factory=list)
    events: ModuleEvents = Field(default_factory=ModuleEvents)
    refresh: ModuleRefresh | None = None

    @field_validator("icon", "navigation", "refresh", mode="before")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("optional manifest fields cannot be null")
        return value


class StoredModuleResponse(ApiModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        from_attributes=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )

    module_id: str
    revision: int
    status: Literal["draft", "published", "disabled"]
    manifest: ModuleManifest
    created_at: str


def manifest_repository_dict(manifest: ModuleManifest) -> dict[str, object]:
    return manifest.model_dump(by_alias=True, exclude_none=True, mode="json")
