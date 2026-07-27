from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


GROUP_ID_PATTERN = r"^[a-z][a-z0-9-]{0,63}$"
SYMBOL_PATTERN = r"^[A-Z0-9][A-Z0-9.\-]{0,23}$"


class WatchlistModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class SecurityRef(WatchlistModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    market: Literal["CN", "HK", "US"]
    exchange: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, max_length=12)
    timezone: str | None = Field(default=None, max_length=80)
    asset_type: str | None = Field(default=None, max_length=40)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class WatchGroup(WatchlistModel):
    id: str = Field(pattern=GROUP_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    symbols: list[SecurityRef] = Field(default_factory=list, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def unique_symbols(self) -> Self:
        identities = [(item.market, item.symbol) for item in self.symbols]
        if len(identities) != len(set(identities)):
            raise ValueError("watchlist group contains duplicate securities")
        return self


class WatchlistReplace(WatchlistModel):
    revision: int = Field(ge=0)
    groups: list[WatchGroup] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_group_ids(self) -> Self:
        ids = [group.id for group in self.groups]
        if len(ids) != len(set(ids)):
            raise ValueError("watchlist contains duplicate group ids")
        return self


class WatchGroupCreate(WatchlistModel):
    id: str = Field(pattern=GROUP_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class WatchGroupUpdate(WatchlistModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class WatchlistDocument(WatchlistModel):
    user_id: str
    workspace_id: str
    revision: int = Field(ge=0)
    groups: list[WatchGroup]
    updated_at: str | None = None
