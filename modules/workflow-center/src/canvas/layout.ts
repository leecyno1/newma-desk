import type { WorkflowLaneDefinition, WorkflowNodeDefinition, WorkflowStageDefinition } from "../types";

export const CANVAS_LEFT = 144;
export const CANVAS_TOP = 86;
export const STAGE_WIDTH = 300;
export const LANE_HEIGHT = 185;
export const NODE_WIDTH = 224;
export const NODE_HEIGHT = 126;

const clamp = (value: number, minimum: number, maximum: number) => Math.min(maximum, Math.max(minimum, value));

export function defaultNodePosition(
  node: Pick<WorkflowNodeDefinition, "laneId" | "stageId" | "canvasX" | "canvasY">,
  lanes: WorkflowLaneDefinition[],
  stages: WorkflowStageDefinition[],
) {
  if (typeof node.canvasX === "number" && typeof node.canvasY === "number") {
    return { x: node.canvasX, y: node.canvasY };
  }
  const laneIndex = Math.max(0, lanes.findIndex((lane) => lane.id === node.laneId));
  const stageIndex = Math.max(0, stages.findIndex((stage) => stage.id === node.stageId));
  return {
    x: CANVAS_LEFT + stageIndex * STAGE_WIDTH + (STAGE_WIDTH - NODE_WIDTH) / 2,
    y: CANVAS_TOP + laneIndex * LANE_HEIGHT + (LANE_HEIGHT - NODE_HEIGHT) / 2,
  };
}

export function resolveCanvasDrop(
  position: { x: number; y: number },
  lanes: WorkflowLaneDefinition[],
  stages: WorkflowStageDefinition[],
) {
  const centerX = position.x + NODE_WIDTH / 2;
  const centerY = position.y + NODE_HEIGHT / 2;
  const stageIndex = clamp(Math.floor((centerX - CANVAS_LEFT) / STAGE_WIDTH), 0, stages.length - 1);
  const laneIndex = clamp(Math.floor((centerY - CANVAS_TOP) / LANE_HEIGHT), 0, lanes.length - 1);
  const stageStart = CANVAS_LEFT + stageIndex * STAGE_WIDTH;
  const laneStart = CANVAS_TOP + laneIndex * LANE_HEIGHT;
  return {
    laneId: lanes[laneIndex]!.id,
    stageId: stages[stageIndex]!.id,
    x: clamp(position.x, stageStart + 20, stageStart + STAGE_WIDTH - NODE_WIDTH - 20),
    y: clamp(position.y, laneStart + 20, laneStart + LANE_HEIGHT - NODE_HEIGHT - 20),
  };
}

export function resolveCanvasCell(
  point: { x: number; y: number },
  lanes: WorkflowLaneDefinition[],
  stages: WorkflowStageDefinition[],
) {
  const stageIndex = Math.floor((point.x - CANVAS_LEFT) / STAGE_WIDTH);
  const laneIndex = Math.floor((point.y - CANVAS_TOP) / LANE_HEIGHT);
  if (stageIndex < 0 || stageIndex >= stages.length || laneIndex < 0 || laneIndex >= lanes.length) return null;
  return {
    laneId: lanes[laneIndex]!.id,
    stageId: stages[stageIndex]!.id,
    x: clamp(point.x - NODE_WIDTH / 2, CANVAS_LEFT + stageIndex * STAGE_WIDTH + 20, CANVAS_LEFT + (stageIndex + 1) * STAGE_WIDTH - NODE_WIDTH - 20),
    y: clamp(point.y - NODE_HEIGHT / 2, CANVAS_TOP + laneIndex * LANE_HEIGHT + 20, CANVAS_TOP + (laneIndex + 1) * LANE_HEIGHT - NODE_HEIGHT - 20),
  };
}

export function canvasBounds(
  lanes: WorkflowLaneDefinition[],
  stages: WorkflowStageDefinition[],
  visibleLaneIds?: Set<string>,
  visibleStageIds?: Set<string>,
) {
  const laneIndexes = lanes.map((lane, index) => ({ lane, index })).filter(({ lane }) => !visibleLaneIds || visibleLaneIds.has(lane.id)).map(({ index }) => index);
  const stageIndexes = stages.map((stage, index) => ({ stage, index })).filter(({ stage }) => !visibleStageIds || visibleStageIds.has(stage.id)).map(({ index }) => index);
  const firstLane = laneIndexes[0] ?? 0;
  const lastLane = laneIndexes.at(-1) ?? Math.max(0, lanes.length - 1);
  const firstStage = stageIndexes[0] ?? 0;
  const lastStage = stageIndexes.at(-1) ?? Math.max(0, stages.length - 1);
  return {
    x: firstStage ? CANVAS_LEFT + firstStage * STAGE_WIDTH - 18 : 0,
    y: firstLane ? CANVAS_TOP + firstLane * LANE_HEIGHT - 18 : 0,
    width: (lastStage - firstStage + 1) * STAGE_WIDTH + (firstStage ? 36 : CANVAS_LEFT + 24),
    height: (lastLane - firstLane + 1) * LANE_HEIGHT + (firstLane ? 36 : CANVAS_TOP + 24),
  };
}
