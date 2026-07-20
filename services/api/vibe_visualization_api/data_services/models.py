import re
from typing import Literal, Self
from urllib.parse import unquote, urlsplit

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel


SERVICE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")
SCHEMA_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
PERMISSION_PATTERN = r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$"
SECRET_NAME_PATTERN = r"^[A-Z][A-Z0-9_]{1,127}$"
INVALID_PERCENT_ENCODING = re.compile(r"%(?![0-9a-fA-F]{2})")


class DataServiceModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


def _fully_decode(value: str) -> str:
    decoded = value
    for _ in range(10):
        if INVALID_PERCENT_ENCODING.search(decoded):
            raise ValueError("path contains malformed percent encoding")
        next_value = unquote(decoded, errors="strict")
        if next_value == decoded:
            return decoded
        decoded = next_value
    raise ValueError("path encoding is too deeply nested")


def validate_service_path(value: str) -> str:
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "?" in value
        or "#" in value
    ):
        raise ValueError("service path must be a safe absolute path")
    decoded = _fully_decode(value)
    if (
        not decoded.startswith("/")
        or decoded.startswith("//")
        or "\\" in decoded
        or any(ord(character) < 32 for character in decoded)
        or any(part in {".", ".."} for part in decoded.split("/"))
    ):
        raise ValueError("service path must be a safe absolute path")
    return value


class ServiceCapability(DataServiceModel):
    method: Literal["GET", "POST"]
    path: str
    input_schema: str = Field(pattern=SCHEMA_NAME_PATTERN)
    output_schema: str = Field(pattern=SCHEMA_NAME_PATTERN)
    permission: str = Field(pattern=PERMISSION_PATTERN)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_service_path(value)


class DataServiceDescriptor(DataServiceModel):
    id: str = Field(pattern=SERVICE_ID_PATTERN)
    base_url: AnyHttpUrl
    health_path: str = "/health"
    transport: Literal["rest", "mcp", "sse", "websocket"]
    capabilities: dict[str, ServiceCapability]
    timeout_seconds: float = Field(default=15, gt=0, le=300)
    auth_secret: str | None = Field(default=None, pattern=SECRET_NAME_PATTERN)
    allowed_hosts: list[str] = Field(default_factory=list)

    @field_validator("health_path")
    @classmethod
    def validate_health_path(cls, value: str) -> str:
        return validate_service_path(value)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        parsed = urlsplit(str(value))
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "data service base URL cannot contain credentials or query"
            )
        validate_service_path(parsed.path or "/")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_allowed_hosts(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for host in value:
            clean = host.strip().casefold().rstrip(".")
            if not clean or "/" in clean or "://" in clean:
                raise ValueError("allowed hosts must contain hostnames or IP addresses")
            if clean not in normalized:
                normalized.append(clean)
        return normalized

    @model_validator(mode="after")
    def validate_capability_ids(self) -> Self:
        if not self.capabilities:
            raise ValueError("data service must declare at least one capability")
        for capability_id in self.capabilities:
            if CAPABILITY_ID_PATTERN.fullmatch(capability_id) is None:
                raise ValueError("invalid data service capability id")
        return self
