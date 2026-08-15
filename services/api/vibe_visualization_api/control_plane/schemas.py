import re
from typing import Any, Annotated, Literal
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
    model_validator,
)
from pydantic.alias_generators import to_camel

from vibe_visualization_api.schema_validation import validate_schema_document


LOCAL_URL_ORIGIN = "https://module.local"
MODULE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
MODULE_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
MODULE_CATEGORY_PATTERN = r"^[a-z][a-z0-9-]{1,31}$"
MODULE_EVENT_PATTERN = r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$"
MODULE_CAPABILITY_PATTERN = r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$"
MODULE_SERVICE_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
WIKI_CONCEPT_PATTERN = r"^[a-z][a-z0-9-]{1,63}$"
WIKI_ENTRYPOINT_PATTERN = r"^[a-z][a-z0-9-]{1,63}$"
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


class ModuleNavigationDirectory(ApiModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,47}$")
    label: str = Field(min_length=1, max_length=40)
    order: int = Field(default=100, ge=0)


class ProjectIconLogo(ApiModel):
    type: Literal["icon"]
    name: Literal[
        "today",
        "research",
        "market",
        "quant",
        "trading",
        "settings",
        "module",
    ]


class ProjectLetterLogo(ApiModel):
    type: Literal["letter"]
    text: str = Field(min_length=1, max_length=2)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if value.strip() != value or not 1 <= len(value) <= 2:
            raise ValueError("project letter logo must contain 1-2 visible characters")
        return value


class ProjectImageLogo(ApiModel):
    type: Literal["image"]
    src: LocalUrl | ExternalUrl
    alt: str | None = Field(default=None, min_length=1, max_length=80)


ProjectLogo = Annotated[
    ProjectIconLogo | ProjectLetterLogo | ProjectImageLogo,
    Field(discriminator="type"),
]


class ModuleNavigationProject(ApiModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,47}$")
    name: str = Field(min_length=1, max_length=80)
    order: int = Field(default=100, ge=0)
    description: str | None = Field(default=None, min_length=1, max_length=240)
    logo: ProjectLogo | None = None


class ModuleNavigation(ApiModel):
    group_label: str = Field(min_length=1, max_length=40)
    group_order: int = Field(default=100, ge=0)
    item_order: int = Field(default=100, ge=0)
    label: str | None = Field(default=None, min_length=1, max_length=40)
    directory: ModuleNavigationDirectory | None = None
    icon: Literal[
        "today",
        "research",
        "market",
        "quant",
        "trading",
        "settings",
        "module",
    ] = "module"
    role: Literal["page", "settings"] | None = None
    project: ModuleNavigationProject | None = None


class ModuleCompatibility(ApiModel):
    level: Literal[1, 2, 3]
    bridge_protocol: Literal["1.0"]
    sdk_version: str | None = Field(default=None, min_length=1, max_length=80)
    view_spec_version: Literal["1.0"] | None = None


class ModuleStorageNamespace(ApiModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,47}$")
    scope: Literal["user-workspace"] = "user-workspace"
    schema_version: int = Field(ge=1, le=10_000)
    quota_mb: int = Field(ge=1, le=100)
    max_item_kb: int = Field(default=256, ge=1, le=1024)


class StatelessModuleStorage(ApiModel):
    mode: Literal["stateless"]


class DeskManagedModuleStorage(ApiModel):
    mode: Literal["desk-managed"]
    namespaces: list[ModuleStorageNamespace] = Field(min_length=1, max_length=32)

    @field_validator("namespaces")
    @classmethod
    def validate_unique_namespaces(
        cls,
        value: list[ModuleStorageNamespace],
    ) -> list[ModuleStorageNamespace]:
        ids = [namespace.id for namespace in value]
        if len(ids) != len(set(ids)):
            raise ValueError("storage namespace IDs must be unique")
        return value


class DedicatedModuleStorage(ApiModel):
    mode: Literal["dedicated"]
    adapter: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")


class ArtifactModuleStorage(ApiModel):
    mode: Literal["artifact"]


ModuleStorage = Annotated[
    StatelessModuleStorage
    | DeskManagedModuleStorage
    | DedicatedModuleStorage
    | ArtifactModuleStorage,
    Field(discriminator="mode"),
]


class AgentActionBinding(ApiModel):
    type: Literal["agent"]
    capability: str | None = Field(default=None, pattern=MODULE_CAPABILITY_PATTERN)
    memory_scope: Literal[
        "user-agent-mod",
        "task",
    ]


class ModelActionBinding(ApiModel):
    type: Literal["model"]
    capability: str | None = Field(default=None, pattern=MODULE_CAPABILITY_PATTERN)


class DataActionBinding(ApiModel):
    type: Literal["data"]
    service: str | None = Field(default=None, pattern=MODULE_SERVICE_PATTERN)
    capability: str | None = Field(default=None, pattern=MODULE_CAPABILITY_PATTERN)


class LocalActionBinding(ApiModel):
    type: Literal["local"]
    capability: str | None = Field(default=None, pattern=MODULE_CAPABILITY_PATTERN)


ModuleActionBinding = Annotated[
    AgentActionBinding
    | ModelActionBinding
    | DataActionBinding
    | LocalActionBinding,
    Field(discriminator="type"),
]


class ModuleAction(ApiModel):
    binding: ModuleActionBinding
    execution: Literal["request", "task", "stream"]
    permission: str = Field(pattern=MODULE_CAPABILITY_PATTERN)
    input_schema: dict[str, Any] | str | None = None
    output_schema: dict[str, Any] | str | None = None
    confirmation: Literal["none", "user", "strong"] = "none"
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)

    @field_validator("input_schema", "output_schema")
    @classmethod
    def validate_schema_contract(
        cls, value: dict[str, Any] | str | None
    ) -> dict[str, Any] | str | None:
        if isinstance(value, str):
            if not 1 <= len(value) <= 512:
                raise ValueError("schema reference must be between 1 and 512 chars")
            return value
        if isinstance(value, dict):
            validate_schema_document(value)
        return value


WikiSubjectType = Literal[
    "security",
    "etf",
    "fund",
    "company",
    "industry",
    "concept",
    "event",
    "topic",
]


class ModuleWikiEntrypoint(ApiModel):
    id: str = Field(pattern=WIKI_ENTRYPOINT_PATTERN)
    intent: str = Field(pattern=MODULE_CAPABILITY_PATTERN)
    label: str = Field(min_length=1, max_length=80)
    context_contract: Literal["newma.wiki.subject.v1"]
    defaults: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        max_length=32,
    )

    @field_validator("defaults")
    @classmethod
    def validate_defaults(
        cls,
        value: dict[str, str | int | float | bool],
    ) -> dict[str, str | int | float | bool]:
        if any(isinstance(item, str) and len(item) > 500 for item in value.values()):
            raise ValueError("Wiki default strings cannot exceed 500 characters")
        return value


class ModuleWikiProfile(ApiModel):
    contract_version: Literal["1.0"]
    subject_types: list[WikiSubjectType] = Field(min_length=1, max_length=16)
    concepts: list[str] = Field(
        default_factory=list,
        max_length=50,
    )
    entrypoints: list[ModuleWikiEntrypoint] = Field(min_length=1, max_length=20)

    @field_validator("subject_types")
    @classmethod
    def validate_subject_types(
        cls,
        value: list[WikiSubjectType],
    ) -> list[WikiSubjectType]:
        if len(value) != len(set(value)):
            raise ValueError("Wiki subject types must be unique")
        return value

    @field_validator("concepts")
    @classmethod
    def validate_concepts(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(
            re.fullmatch(WIKI_CONCEPT_PATTERN, item) is None for item in value
        ):
            raise ValueError("Wiki concepts must be unique valid slugs")
        return value

    @field_validator("entrypoints")
    @classmethod
    def validate_entrypoints(
        cls,
        value: list[ModuleWikiEntrypoint],
    ) -> list[ModuleWikiEntrypoint]:
        ids = [entrypoint.id for entrypoint in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Wiki entrypoint IDs must be unique")
        return value


class ModSessionCreate(ApiModel):
    instance_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)


class ModSessionGrants(ApiModel):
    permissions: list[str]
    actions: list[str]


class ModSessionResponse(ApiModel):
    session_id: str
    instance_id: str
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: str
    user_id: str
    workspace_id: str
    module_id: str
    revision: int
    grants: ModSessionGrants


class ModContextUpdate(ApiModel):
    context: dict[str, Any]


class ModContextResponse(ApiModel):
    module_id: str
    revision: int
    user_id: str
    workspace_id: str
    context: dict[str, Any]
    updated_at: str


class ModuleManifest(ApiModel):
    schema_version: Literal["1.0", "1.1"]
    id: str = Field(pattern=MODULE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(pattern=MODULE_VERSION_PATTERN)
    category: str = Field(pattern=MODULE_CATEGORY_PATTERN)
    navigation: ModuleNavigation | None = None
    entry: ModuleEntry
    icon: str | None = None
    compatibility: ModuleCompatibility | None = None
    permissions: list[str] = Field(default_factory=list)
    data_services: list[str] = Field(default_factory=list)
    storage: ModuleStorage | None = None
    wiki: ModuleWikiProfile | None = None
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
        schema_version = normalized.get("schemaVersion")
        if schema_version == "1.0":
            normalized.setdefault("agentCapabilities", [])
        elif schema_version == "1.1":
            normalized.setdefault("actions", {})
        return normalized

    @field_validator(
        "icon",
        "navigation",
        "compatibility",
        "storage",
        "wiki",
        "agent_capabilities",
        "actions",
        "refresh",
        mode="before",
    )
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("optional manifest fields cannot be null")
        return value

    @model_validator(mode="after")
    def validate_versioned_contract(self) -> "ModuleManifest":
        if self.schema_version == "1.0":
            if (
                self.compatibility is not None
                or self.storage is not None
                or self.wiki is not None
                or self.actions is not None
            ):
                raise ValueError("Manifest 1.0 cannot declare 1.1 fields")
            return self

        if self.compatibility is None or self.actions is None:
            raise ValueError("Manifest 1.1 requires compatibility and actions")
        if self.agent_capabilities is not None:
            raise ValueError("Manifest 1.1 must use explicit action bindings")
        if (
            self.compatibility.level == 3
            and self.compatibility.view_spec_version is None
        ):
            raise ValueError("Level 3 Mods must declare a ViewSpec version")
        if self.compatibility.level == 1 and self.actions:
            raise ValueError("Level 1 Mods cannot declare connected actions")

        permissions = set(self.permissions)
        services = set(self.data_services)
        if isinstance(self.storage, DeskManagedModuleStorage):
            if "storage.read" not in permissions:
                raise ValueError(
                    "Desk-managed storage requires storage.read permission"
                )
            if "storage.write" not in permissions:
                raise ValueError(
                    "Desk-managed storage requires storage.write permission"
                )
        for action_id, action in self.actions.items():
            if re.fullmatch(MODULE_CAPABILITY_PATTERN, action_id) is None:
                raise ValueError("invalid Mod action id")
            if action.permission not in permissions:
                raise ValueError("Action permission must be declared by the Mod")
            if (
                isinstance(action.binding, DataActionBinding)
                and action.binding.service is not None
                and action.binding.service not in services
            ):
                raise ValueError("Data action service must be declared by the Mod")
            if (
                isinstance(action.binding, AgentActionBinding)
                and action.execution != "task"
            ):
                raise ValueError("Agent actions must use task execution")
            if (
                isinstance(action.binding, ModelActionBinding)
                and action.execution != "request"
            ):
                raise ValueError("Model actions must use request execution")
            if action_id == "trade.execute" and action.confirmation != "strong":
                raise ValueError("Trading actions require strong confirmation")
        return self


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
    copilot_prompts: dict[str, list[dict[str, Any]]] | None = None


def manifest_repository_dict(manifest: ModuleManifest) -> dict[str, object]:
    return manifest.model_dump(by_alias=True, exclude_none=True, mode="json")
