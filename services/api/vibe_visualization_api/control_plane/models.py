from dataclasses import dataclass
from typing import Any, Literal


ModuleStatus = Literal["draft", "published", "disabled"]


@dataclass(frozen=True)
class StoredModule:
    module_id: str
    revision: int
    status: ModuleStatus
    manifest: dict[str, Any]
    created_at: str
