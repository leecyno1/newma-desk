from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


MODULE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
ARTIFACT_ID_PATTERN = r"^[0-9a-f]{32}$"
NODE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"


class ArtifactModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class GraphNode(ArtifactModel):
    id: str = Field(pattern=NODE_ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=600)
    kind: Literal[
        "source",
        "material",
        "component",
        "infrastructure",
        "market",
        "company",
        "risk",
        "external",
    ] = "component"
    group: str | None = Field(default=None, max_length=80)


class GraphEdge(ArtifactModel):
    source: str = Field(pattern=NODE_ID_PATTERN)
    target: str = Field(pattern=NODE_ID_PATTERN)
    label: str = Field(default="", max_length=120)
    kind: Literal["flow", "dependency", "supply", "risk"] = "flow"


class GraphArtifactCreate(ArtifactModel):
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=300)
    nodes: list[GraphNode] = Field(min_length=2, max_length=80)
    edges: list[GraphEdge] = Field(default_factory=list, max_length=160)
    source_text: str = Field(default="", max_length=80_000)
    sources: list[str] = Field(default_factory=list, max_length=30)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> "GraphArtifactCreate":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph node ids must be unique")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError("graph edges must reference declared nodes")
            if edge.source == edge.target:
                raise ValueError("graph edges cannot be self-referential")
        return self


class ArtifactSummary(ArtifactModel):
    id: str = Field(pattern=ARTIFACT_ID_PATTERN)
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    kind: Literal["graph"] = "graph"
    renderer: Literal["archify"] = "archify"
    title: str
    status: Literal["draft", "published"]
    created_at: datetime
    updated_at: datetime
    view_url: str


class ArtifactRecord(ArtifactSummary):
    spec: GraphArtifactCreate
    archify_ir: dict[str, Any]


class ReplayOrderArtifact(ArtifactModel):
    id: str = Field(min_length=1, max_length=160)
    side: Literal["buy", "sell"]
    index: int = Field(ge=0)
    timestamp: int = Field(gt=0)
    price: float = Field(gt=0)


class ReplaySecurityArtifact(ArtifactModel):
    symbol: str = Field(min_length=1, max_length=24)
    name: str = Field(min_length=1, max_length=120)
    market: Literal["CN", "HK", "US"]
    exchange: str = Field(default="", max_length=40)


class ReplayArtifactCreate(ArtifactModel):
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    title: str = Field(min_length=1, max_length=160)
    security: ReplaySecurityArtifact
    timeframe: Literal["1m", "5m", "15m", "30m", "60m", "1d", "1w", "1M"]
    cursor: int = Field(ge=0)
    total_bars: int = Field(ge=0)
    replay_timestamp: int | None = Field(default=None, gt=0)
    orders: list[ReplayOrderArtifact] = Field(default_factory=list, max_length=2_000)
    metrics: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=20_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_replay(self) -> "ReplayArtifactCreate":
        if self.cursor > self.total_bars:
            raise ValueError("replay cursor cannot exceed total bars")
        if any(order.index > self.cursor for order in self.orders):
            raise ValueError("replay orders cannot point into hidden future bars")
        return self


class ReplayArtifactRecord(ArtifactModel):
    id: str = Field(pattern=ARTIFACT_ID_PATTERN)
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    kind: Literal["replay"] = "replay"
    renderer: Literal["replay-html"] = "replay-html"
    title: str
    status: Literal["draft", "published"]
    created_at: datetime
    updated_at: datetime
    view_url: str
    spec: ReplayArtifactCreate
