import heapq
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from vibe_visualization_api.artifacts.models import GraphArtifactCreate, GraphNode


class ArtifactRenderError(Exception):
    """Raised when Archify cannot render a validated graph artifact."""


COMPONENT_TYPES = {
    "source": "external",
    "material": "database",
    "component": "backend",
    "infrastructure": "cloud",
    "market": "frontend",
    "company": "external",
    "risk": "security",
    "external": "external",
}

EDGE_VARIANTS = {
    "flow": "emphasis",
    "dependency": "default",
    "supply": "dashed",
    "risk": "security",
}


def _fallback_component_position(index: int, count: int) -> tuple[int, int]:
    if count <= 5:
        return 60 + index * 330, 150
    columns = 4
    row, column = divmod(index, columns)
    if row % 2 == 1:
        column = columns - 1 - column
    return 60 + column * 290, 110 + row * 190


def _component_positions(spec: GraphArtifactCreate) -> dict[str, tuple[int, int]]:
    """Lay out a DAG by dependency depth while preserving declared node order."""
    node_ids = [node.id for node in spec.nodes]
    order = {node_id: index for index, node_id in enumerate(node_ids)}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in spec.edges:
        outgoing[edge.source].append(edge.target)
        indegree[edge.target] += 1

    ready = [order[node_id] for node_id in node_ids if indegree[node_id] == 0]
    heapq.heapify(ready)
    layer = {node_id: 0 for node_id in node_ids}
    visited: list[str] = []
    while ready:
        node_id = node_ids[heapq.heappop(ready)]
        visited.append(node_id)
        for target in outgoing[node_id]:
            layer[target] = max(layer[target], layer[node_id] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, order[target])

    if len(visited) != len(node_ids):
        return {
            node_id: _fallback_component_position(index, len(node_ids))
            for index, node_id in enumerate(node_ids)
        }

    columns: dict[int, list[str]] = {}
    for node_id in node_ids:
        columns.setdefault(layer[node_id], []).append(node_id)
    max_rows = max(len(items) for items in columns.values())
    positions: dict[str, tuple[int, int]] = {}
    for depth, items in columns.items():
        top = 80 + ((max_rows - len(items)) * 132) // 2
        for row, node_id in enumerate(items):
            positions[node_id] = (60 + depth * 310, top + row * 132)
    return positions


def _component(node: GraphNode, position: tuple[int, int]) -> dict[str, Any]:
    x, y = position
    subtitle = node.subtitle.strip()
    if len(subtitle) > 150:
        subtitle = f"{subtitle[:147]}…"
    return {
        "id": node.id,
        "type": COMPONENT_TYPES[node.kind],
        "label": node.label,
        "sublabel": subtitle,
        "tag": node.group or node.kind,
        "pos": [x, y],
        "size": [190, 86],
    }


def to_archify_ir(spec: GraphArtifactCreate) -> dict[str, Any]:
    node_ids = [node.id for node in spec.nodes]
    positions = _component_positions(spec)
    sources = [item.strip() for item in spec.sources if item.strip()]
    cards: list[dict[str, Any]] = []
    if sources:
        cards.append({"dot": "cyan", "title": "信息来源", "items": sources[:8]})
    cards.append(
        {
            "dot": "emerald",
            "title": "图谱说明",
            "items": [
                f"{len(spec.nodes)} 个节点 · {len(spec.edges)} 条关系",
                "由 Newma-Desk Artifact Adapter 转换并使用 Archify 渲染",
            ],
        }
    )
    return {
        "schema_version": 1,
        "diagram_type": "architecture",
        "meta": {
            "title": spec.title,
            "subtitle": spec.subtitle,
            "animation": "trace",
            "visual_preset": "signal-flow",
            "quality_profile": "standard",
            "views": [
                {
                    "id": "industry-path",
                    "label": "产业链主路径",
                    "focus": node_ids[: min(len(node_ids), 16)],
                    "note": "沿 Agent 识别并由用户固化的产业链关系逐站查看。",
                }
            ],
        },
        "components": [
            _component(node, positions[node.id])
            for node in spec.nodes
        ],
        "connections": [
            {
                "id": f"edge-{index + 1}",
                "from": edge.source,
                "to": edge.target,
                "label": edge.label,
                "variant": EDGE_VARIANTS[edge.kind],
                "route": "auto",
            }
            for index, edge in enumerate(spec.edges)
        ],
        "cards": cards,
    }


class ArchifyRenderer:
    def __init__(self, archify_root: Path, node_binary: str = "node"):
        self._root = archify_root.resolve()
        self._renderer = (
            self._root / "renderers" / "architecture" / "render-architecture.mjs"
        )
        self._node_binary = node_binary

    def render(self, ir: dict[str, Any]) -> str:
        if not self._renderer.is_file():
            raise ArtifactRenderError("Archify renderer is not installed")
        with tempfile.TemporaryDirectory(prefix="newma-desk-archify-") as directory:
            root = Path(directory)
            source_path = root / "artifact.architecture.json"
            output_path = root / "artifact.html"
            source_path.write_text(
                json.dumps(ir, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                result = subprocess.run(
                    [
                        self._node_binary,
                        str(self._renderer),
                        str(source_path),
                        str(output_path),
                    ],
                    cwd=self._root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ArtifactRenderError("Archify renderer could not start") from error
            if result.returncode != 0:
                diagnostic = (result.stderr or result.stdout).strip()
                raise ArtifactRenderError(
                    f"Archify rejected the graph: {diagnostic[:1200]}"
                )
            try:
                html = output_path.read_text(encoding="utf-8")
            except OSError as error:
                raise ArtifactRenderError("Archify did not produce an HTML view") from error
            if "<!doctype html" not in html.lower() or len(html) > 5_000_000:
                raise ArtifactRenderError("Archify produced an invalid HTML view")
            return html
