import type {
  WorkflowEdge,
  WorkflowLaneDefinition,
  WorkflowNodeDefinition,
  WorkflowStageDefinition,
} from "./types";

interface WorkflowDefinitionShape {
  name?: string;
  description?: string;
  nodes: WorkflowNodeDefinition[];
  edges: WorkflowEdge[];
  lanes: WorkflowLaneDefinition[];
  stages: WorkflowStageDefinition[];
}

export function axisLetter(index: number) {
  return String.fromCharCode(65 + Math.min(index, 25));
}

export function resolveWorkflowMatrix<T extends WorkflowNodeDefinition>(
  nodes: T[],
  sourceLanes?: WorkflowLaneDefinition[],
  sourceStages?: WorkflowStageDefinition[],
) {
  const lanes = sourceLanes?.length
    ? sourceLanes
    : [{ id: "main", name: "主流程", description: "旧版流程自动归入的业务域。" }];
  const stages = sourceStages?.length
    ? sourceStages
    : nodes.map((node, index) => ({ id: `stage-${index + 1}`, name: node.name, description: "" }));
  const safeStages = stages.length ? stages : [{ id: "stage-1", name: "执行", description: "" }];
  const resolvedNodes = nodes.map((node, index) => ({
    ...node,
    laneId: node.laneId || lanes[0]!.id,
    stageId: node.stageId || safeStages[Math.min(index, safeStages.length - 1)]!.id,
    promotedToMenu: Boolean(node.promotedToMenu),
  }));
  return { lanes, stages: safeStages, nodes: resolvedNodes };
}

export function matrixCoordinate(
  laneId: string,
  stageId: string,
  lanes: WorkflowLaneDefinition[],
  stages: WorkflowStageDefinition[],
) {
  const laneIndex = Math.max(0, lanes.findIndex((lane) => lane.id === laneId));
  const stageIndex = Math.max(0, stages.findIndex((stage) => stage.id === stageId));
  return `${axisLetter(laneIndex)}${stageIndex + 1}`;
}

export function reorderAxisById<T extends { id: string }>(items: T[], sourceId: string, targetId: string) {
  if (sourceId === targetId) return items;
  const sourceIndex = items.findIndex((item) => item.id === sourceId);
  const targetIndex = items.findIndex((item) => item.id === targetId);
  if (sourceIndex < 0 || targetIndex < 0) return items;
  const next = [...items];
  const [source] = next.splice(sourceIndex, 1);
  next.splice(targetIndex, 0, source!);
  return next;
}

export function moveOrSwapNode<T extends { id: string; laneId: string; stageId: string }>(
  nodes: T[],
  nodeId: string,
  laneId: string,
  stageId: string,
) {
  const moving = nodes.find((node) => node.id === nodeId);
  if (!moving || (moving.laneId === laneId && moving.stageId === stageId)) return nodes;
  const occupied = nodes.find((node) => node.id !== nodeId && node.laneId === laneId && node.stageId === stageId);
  return nodes.map((node) => {
    if (node.id === nodeId) return { ...node, laneId, stageId };
    if (occupied && node.id === occupied.id) return { ...node, laneId: moving.laneId, stageId: moving.stageId };
    return node;
  });
}

export function summarizeTemplateVersionDiff(
  current: WorkflowDefinitionShape,
  candidate: WorkflowDefinitionShape,
) {
  const currentNodes = new Map(current.nodes.map((node) => [node.id, node]));
  const candidateNodes = new Map(candidate.nodes.map((node) => [node.id, node]));
  const addedNodes = candidate.nodes.filter((node) => !currentNodes.has(node.id)).length;
  const removedNodes = current.nodes.filter((node) => !candidateNodes.has(node.id)).length;
  const changedNodes = candidate.nodes.filter((node) => {
    const existing = currentNodes.get(node.id);
    return existing && JSON.stringify(existing) !== JSON.stringify(node);
  }).length;
  const edgeSet = (edges: WorkflowEdge[]) => new Set(edges.map((edge) => `${edge.source}->${edge.target}`));
  const currentEdges = edgeSet(current.edges);
  const candidateEdges = edgeSet(candidate.edges);
  const changedEdges = [...candidateEdges].filter((edge) => !currentEdges.has(edge)).length
    + [...currentEdges].filter((edge) => !candidateEdges.has(edge)).length;
  return {
    addedNodes,
    removedNodes,
    changedNodes,
    changedEdges,
    metadataChanged: current.name !== candidate.name || current.description !== candidate.description,
    laneOrderChanged: current.lanes.map((lane) => lane.id).join(",") !== candidate.lanes.map((lane) => lane.id).join(","),
    stageOrderChanged: current.stages.map((stage) => stage.id).join(",") !== candidate.stages.map((stage) => stage.id).join(","),
  };
}
