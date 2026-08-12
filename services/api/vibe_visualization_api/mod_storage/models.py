from typing import Any

from pydantic import Field

from vibe_visualization_api.control_plane.schemas import ApiModel


class ModStoragePut(ApiModel):
    expected_revision: int = Field(ge=0)
    value: Any


class ModStorageDocument(ApiModel):
    module_id: str
    namespace: str
    key: str
    schema_version: int
    revision: int
    value: Any
    size_bytes: int
    created_at: str
    updated_at: str


class ModStorageDocumentList(ApiModel):
    items: list[ModStorageDocument]
    next_cursor: str | None = None
