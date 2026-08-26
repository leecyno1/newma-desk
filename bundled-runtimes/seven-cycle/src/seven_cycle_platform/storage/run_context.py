"""Deterministic identity and metadata for one platform run."""

from collections.abc import Iterator, Mapping
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from typing import Generic, Self, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from seven_cycle_platform.security.redaction import (
    REDACTION_MARKER,
    is_sensitive_key,
    redact_secrets,
)


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}-[0-9a-f]{12}-[0-9a-f]{12}$"
)
_RUN_ID_HASH_PREFIX_LENGTH = 12
_Key = TypeVar("_Key")
_Value = TypeVar("_Value")


class _FrozenDict(Mapping[_Key, _Value], Generic[_Key, _Value]):
    """Small deterministic mapping that rejects every mutating operation."""

    __slots__ = ("_data",)

    def __init__(self, values: Mapping[_Key, _Value]) -> None:
        self._data = dict(values)

    def __getitem__(self, key: _Key) -> _Value:
        return self._data[key]

    def __iter__(self) -> Iterator[_Key]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"_FrozenDict({self._data!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return NotImplemented
        return dict(self.items()) == dict(other.items())

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self

    def __setitem__(self, key: _Key, value: _Value) -> None:
        raise TypeError("frozen mappings are immutable")

    def __delitem__(self, key: _Key) -> None:
        raise TypeError("frozen mappings are immutable")

    def clear(self) -> None:
        raise TypeError("frozen mappings are immutable")

    def pop(self, key: _Key, default: object = None) -> None:
        raise TypeError("frozen mappings are immutable")

    def popitem(self) -> None:
        raise TypeError("frozen mappings are immutable")

    def setdefault(self, key: _Key, default: _Value | None = None) -> None:
        raise TypeError("frozen mappings are immutable")

    def update(self, *args: object, **kwargs: object) -> None:
        raise TypeError("frozen mappings are immutable")


def _canonicalize_json(value: object, *, path: str = "$") -> JsonValue:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite float")
        return value
    if isinstance(value, (list, tuple)):
        return [
            _canonicalize_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError(f"{path} mapping keys must be strings")
        return {
            key: _canonicalize_json(value[key], path=f"{path}.{key}")
            for key in sorted(value)
        }
    raise TypeError(f"{path} contains a non-JSON value")


def _freeze_canonical_json(value: JsonValue) -> object:
    if isinstance(value, dict):
        return _FrozenDict(
            {
                key: _freeze_canonical_json(nested_value)
                for key, nested_value in value.items()
            }
        )
    if isinstance(value, list):
        return tuple(_freeze_canonical_json(item) for item in value)
    return value


def _freeze_json(value: object) -> object:
    return _freeze_canonical_json(_canonicalize_json(value))


def _redact_quality_metadata(
    value: object,
    *,
    secret_field: bool = False,
) -> object:
    if isinstance(value, str):
        if secret_field and value:
            return REDACTION_MARKER
        return redact_secrets(value)
    if isinstance(value, (list, tuple)):
        return [
            _redact_quality_metadata(item, secret_field=secret_field)
            for item in value
        ]
    if isinstance(value, Mapping):
        return {
            key: _redact_quality_metadata(
                nested_value,
                secret_field=(
                    secret_field
                    or (isinstance(key, str) and is_sensitive_key(key))
                ),
            )
            for key, nested_value in value.items()
        }
    return value


def _thaw_json(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_json(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("immutable metadata contains a non-JSON value")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize JSON-compatible data with stable key ordering."""

    canonical_value = _canonicalize_json(value)
    return json.dumps(
        canonical_value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def compute_config_hash(config: Mapping[str, object]) -> str:
    """Return the SHA-256 digest of a canonically serialized config."""

    if not isinstance(config, Mapping):
        raise TypeError("config must be a mapping")
    return hashlib.sha256(canonical_json_bytes(config)).hexdigest()


def _run_identity_hash(
    *,
    as_of: date,
    data_vintage: date,
    model_version: str,
    config_hash: str,
    input_checksums: Mapping[str, str],
) -> str:
    identity = {
        "as_of": as_of.isoformat(),
        "config_hash": config_hash,
        "data_vintage": data_vintage.isoformat(),
        "input_checksums": input_checksums,
        "model_version": model_version,
    }
    return hashlib.sha256(canonical_json_bytes(identity)).hexdigest()


def make_run_id(
    *,
    as_of: date,
    data_vintage: date,
    model_version: str,
    config_hash: str,
    input_checksums: Mapping[str, str],
) -> str:
    """Build a stable run identifier from the complete run identity."""

    identity_hash = _run_identity_hash(
        as_of=as_of,
        data_vintage=data_vintage,
        model_version=model_version,
        config_hash=config_hash,
        input_checksums=input_checksums,
    )
    return (
        f"{as_of.isoformat()}-"
        f"{config_hash[:_RUN_ID_HASH_PREFIX_LENGTH]}-"
        f"{identity_hash[:_RUN_ID_HASH_PREFIX_LENGTH]}"
    )


class RunContext(BaseModel):
    """Strict immutable metadata shared by every published product."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    run_id: str = Field(pattern=RUN_ID_PATTERN.pattern)
    as_of: date
    data_vintage: date
    model_version: str = Field(min_length=1)
    config_hash: str
    created_at: datetime
    input_checksums: _FrozenDict[str, str]
    quality_summary: _FrozenDict[str, object]
    product_checksums: _FrozenDict[str, str]

    @classmethod
    def create(
        cls,
        *,
        as_of: date,
        data_vintage: date,
        model_version: str,
        config: Mapping[str, object],
        input_checksums: Mapping[str, str],
        quality_summary: Mapping[str, object],
        created_at: datetime,
        product_checksums: Mapping[str, str] | None = None,
    ) -> Self:
        """Create a validated context from unhashed configuration data."""

        normalized_model_version = model_version.strip()
        config_hash = compute_config_hash(config)
        run_id = make_run_id(
            as_of=as_of,
            data_vintage=data_vintage,
            model_version=normalized_model_version,
            config_hash=config_hash,
            input_checksums=input_checksums,
        )
        return cls(
            run_id=run_id,
            as_of=as_of,
            data_vintage=data_vintage,
            model_version=normalized_model_version,
            config_hash=config_hash,
            created_at=created_at,
            input_checksums=dict(input_checksums),
            quality_summary=dict(quality_summary),
            product_checksums=dict(product_checksums or {}),
        )

    @field_validator("model_version")
    @classmethod
    def validate_model_version(cls, model_version: str) -> str:
        normalized = model_version.strip()
        if not normalized:
            raise ValueError("model_version must not be blank")
        return normalized

    @field_validator("config_hash")
    @classmethod
    def validate_config_hash(cls, config_hash: str) -> str:
        if not _SHA256_PATTERN.fullmatch(config_hash):
            raise ValueError("config_hash must be a lowercase SHA-256 digest")
        return config_hash

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, created_at: datetime) -> datetime:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return created_at.astimezone(timezone.utc)

    @field_validator("input_checksums", "product_checksums", mode="before")
    @classmethod
    def validate_checksum_map(
        cls,
        checksums: object,
        info: ValidationInfo,
    ) -> _FrozenDict[str, str]:
        if not isinstance(checksums, Mapping):
            raise ValueError(f"{info.field_name} must be a mapping")
        names = list(checksums)
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError(f"{info.field_name} keys must be non-empty strings")
        normalized: dict[str, str] = {}
        for name in sorted(names):
            checksum = checksums[name]
            if not isinstance(checksum, str) or not _SHA256_PATTERN.fullmatch(
                checksum
            ):
                raise ValueError(
                    f"{info.field_name} values must be lowercase SHA-256 digests"
                )
            normalized[name] = checksum
        if info.field_name == "input_checksums" and not normalized:
            raise ValueError("input_checksums must not be empty")
        return _FrozenDict(normalized)

    @field_validator("quality_summary", mode="before")
    @classmethod
    def validate_quality_summary(
        cls,
        summary: object,
    ) -> _FrozenDict[str, object]:
        try:
            frozen_summary = _freeze_json(_redact_quality_metadata(summary))
        except TypeError as error:
            raise ValueError(str(error)) from error
        if not isinstance(frozen_summary, _FrozenDict):
            raise ValueError("quality_summary must be a mapping")
        return frozen_summary

    @field_serializer("input_checksums", "product_checksums")
    def serialize_checksum_map(
        self,
        checksums: _FrozenDict[str, str],
    ) -> dict[str, str]:
        return dict(checksums.items())

    @field_serializer("quality_summary")
    def serialize_quality_summary(
        self,
        summary: _FrozenDict[str, object],
    ) -> dict[str, JsonValue]:
        serialized = _thaw_json(summary)
        if not isinstance(serialized, dict):
            raise TypeError("quality_summary must serialize as a mapping")
        return serialized

    @model_validator(mode="after")
    def validate_run_id(self) -> Self:
        expected_run_id = make_run_id(
            as_of=self.as_of,
            data_vintage=self.data_vintage,
            model_version=self.model_version,
            config_hash=self.config_hash,
            input_checksums=self.input_checksums,
        )
        if self.run_id != expected_run_id:
            raise ValueError("run_id does not match the run identity")
        return self

    def with_product_checksums(
        self,
        product_checksums: Mapping[str, str],
    ) -> Self:
        """Return a validated copy containing finalized product checksums."""

        payload = self.model_dump(mode="python")
        payload["product_checksums"] = dict(product_checksums)
        return type(self).model_validate(payload)

    def to_json_bytes(self) -> bytes:
        """Return deterministic UTF-8 JSON suitable for durable storage."""

        return canonical_json_bytes(self.model_dump(mode="json")) + b"\n"
