from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MODULE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"


class RefreshJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    cron: str = Field(min_length=1)
    timezone: str = "Asia/Shanghai"
    status: Literal["idle", "running", "failed"]
    next_run_at: datetime
    last_success_at: datetime | None = None
    last_error: str | None = None
