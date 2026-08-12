from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from vibe_visualization_api.watchlists.models import SecurityRef


class MarketAlertModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class MarketAlertCreate(MarketAlertModel):
    security: SecurityRef
    direction: Literal["above", "below"]
    price: float = Field(gt=0)
    label: str = Field(default="", max_length=80)
    enabled: bool = True

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        return value.strip()


class MarketAlertUpdate(MarketAlertModel):
    direction: Literal["above", "below"] | None = None
    price: float | None = Field(default=None, gt=0)
    label: str | None = Field(default=None, max_length=80)
    enabled: bool | None = None

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("market alert update must include at least one field")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("market alert update fields cannot be null")
        return self


class MarketAlert(MarketAlertModel):
    id: str
    user_id: str
    workspace_id: str
    security: SecurityRef
    direction: Literal["above", "below"]
    price: float
    label: str
    enabled: bool
    created_at: str
    updated_at: str


class MarketAlertList(MarketAlertModel):
    user_id: str
    workspace_id: str
    items: list[MarketAlert]


class MarketAlertDeleteResult(MarketAlertModel):
    id: str
    deleted: bool = True
