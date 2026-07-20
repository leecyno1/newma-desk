from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


MODULE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
SNAPSHOT_ID_PATTERN = r"^[0-9a-f]{32}$"


class SnapshotModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class Snapshot(SnapshotModel):
    id: str = Field(pattern=SNAPSHOT_ID_PATTERN)
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    created_at: datetime
    data: dict[str, Any]


class SnapshotSummary(SnapshotModel):
    id: str = Field(pattern=SNAPSHOT_ID_PATTERN)
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    created_at: datetime
    url: str
