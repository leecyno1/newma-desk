from __future__ import annotations

from copy import deepcopy
from typing import Any

from vibe_visualization_api.workflow_control.errors import WorkflowValidationError


def normalize_workflow_matrix(document: dict[str, Any]) -> dict[str, Any]:
    """Return a matrix-complete workflow document without changing stable node ids."""

    normalized = deepcopy(document)
    nodes = normalized.get("nodes", [])
    lanes = list(normalized.get("lanes") or [])
    stages = list(normalized.get("stages") or [])

    if not lanes:
        lanes = [
            {
                "id": "main",
                "name": "主流程",
                "description": "由旧版线性流程自动归入的业务域。",
            }
        ]
    if not stages:
        stages = [
            {
                "id": f"stage-{index + 1}",
                "name": node.get("name") or f"阶段 {index + 1}",
                "description": "",
            }
            for index, node in enumerate(nodes)
        ] or [{"id": "stage-1", "name": "执行", "description": ""}]

    default_lane_id = lanes[0]["id"]
    for index, node in enumerate(nodes):
        if not node.get("laneId"):
            node["laneId"] = default_lane_id
        if not node.get("stageId"):
            node["stageId"] = stages[min(index, len(stages) - 1)]["id"]
        node["promotedToMenu"] = bool(node.get("promotedToMenu", False))

    normalized["lanes"] = lanes
    normalized["stages"] = stages
    return normalized


def validate_workflow_definition(definition: dict[str, Any]) -> None:
    nodes = definition["nodes"]
    node_ids = [node["id"] for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise WorkflowValidationError("workflow node ids must be unique")

    lanes = definition["lanes"]
    stages = definition["stages"]
    lane_ids = [lane["id"] for lane in lanes]
    stage_ids = [stage["id"] for stage in stages]
    if len(lane_ids) != len(set(lane_ids)):
        raise WorkflowValidationError("workflow lane ids must be unique")
    if len(stage_ids) != len(set(stage_ids)):
        raise WorkflowValidationError("workflow stage ids must be unique")

    known_lanes = set(lane_ids)
    known_stages = set(stage_ids)
    occupied: set[tuple[str, str]] = set()
    for node in nodes:
        lane_id = node["laneId"]
        stage_id = node["stageId"]
        if lane_id not in known_lanes or stage_id not in known_stages:
            raise WorkflowValidationError(
                "workflow nodes must reference known matrix lanes and stages"
            )
        coordinate = (lane_id, stage_id)
        if coordinate in occupied:
            raise WorkflowValidationError(
                "workflow matrix allows only one primary node per coordinate"
            )
        occupied.add(coordinate)

    known = set(node_ids)
    edges = definition.get("edges", [])
    edge_pairs: set[tuple[str, str]] = set()
    indegree = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source not in known or target not in known:
            raise WorkflowValidationError("workflow edges must reference known nodes")
        if source == target:
            raise WorkflowValidationError("workflow nodes cannot depend on themselves")
        pair = (source, target)
        if pair in edge_pairs:
            raise WorkflowValidationError("workflow edges must be unique")
        edge_pairs.add(pair)
        indegree[target] += 1
        outgoing[source].append(target)

    queue = [node_id for node_id, value in indegree.items() if value == 0]
    visited = 0
    while queue:
        current = queue.pop(0)
        visited += 1
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if visited != len(nodes):
        raise WorkflowValidationError("workflow graph must be acyclic")
