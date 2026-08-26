"""Pydantic response and request models for the local API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Pagination(BaseModel):
    """Metadata for a bounded list response."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)


class ResponseEnvelope(BaseModel):
    """Common, auditable response shape for every endpoint."""

    model_config = ConfigDict(extra="forbid")

    data: Any
    provenance: dict[str, Any]
    freshness: str
    usage_status: str
    caveats: list[str]
    pagination: Pagination | None = None


CHECKSUM_RESPONSE_HEADERS = {
    "ETag": {
        "description": "Stable representation validator for conditional GET.",
        "schema": {"type": "string"},
    },
    "Cache-Control": {
        "description": "Local catalog cache policy.",
        "schema": {"type": "string"},
    },
    "X-Catalog-Checksum": {
        "description": "Checksum of the verified DuckDB catalog.",
        "schema": {"type": "string"},
    },
    "X-Manifest-Checksum": {
        "description": "Checksum of the verified published-run manifest.",
        "schema": {"type": "string"},
    },
    "X-Config-Hash": {
        "description": "Configuration hash of the verified run.",
        "schema": {"type": "string"},
    },
}

APPROVED_ROUTE_RESPONSES = {
    200: {
        "description": "Verified immutable catalog response.",
        "headers": CHECKSUM_RESPONSE_HEADERS,
    },
    304: {
        "description": "Representation has not changed.",
        "headers": CHECKSUM_RESPONSE_HEADERS,
    },
    404: {"description": "Endpoint was not found.", "model": ResponseEnvelope},
    422: {"description": "Request was invalid.", "model": ResponseEnvelope},
    503: {"description": "Published data was unavailable.", "model": ResponseEnvelope},
}


@dataclass(frozen=True, slots=True)
class QueryFilters:
    """Normalized allow-listed query inputs."""

    as_of: date | None
    vintage: str | None
    model_version: str | None
    horizon: int | None
    scenario: str | None
    benchmark: str | None
    asset_tier: str | None
    cycle_ids: tuple[str, ...]
    limit: int
    offset: int

    def etag_parameters(self) -> dict[str, object]:
        return {
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "asset_tier": self.asset_tier,
            "benchmark": self.benchmark,
            "cycle_ids": list(self.cycle_ids),
            "horizon": self.horizon,
            "limit": self.limit,
            "model_version": self.model_version,
            "offset": self.offset,
            "scenario": self.scenario,
            "vintage": self.vintage,
        }
