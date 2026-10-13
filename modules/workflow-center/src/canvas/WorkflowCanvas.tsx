import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  ViewportPortal,
  getBezierPath,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Pin } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";

import { axisLetter, matrixCoordinate } from "../matrix";
import type {
  Principal,
  WorkflowEdge,
  WorkflowLaneDefinition,
  WorkflowNodeDefinition,
  WorkflowNodeRun,
  WorkflowStageDefinition,
} from "../types";
import {
  CANVAS_LEFT,
  CANVAS_TOP,
  LANE_HEIGHT,
  NODE_HEIGHT,
  NODE_WIDTH,
  STAGE_WIDTH,
  canvasBounds,
  defaultNodePosition,
  resolveCanvasCell,
  resolveCanvasDrop,
} from "./layout";

type MatrixNode = WorkflowNodeDefinition | WorkflowNodeRun;

const EDGE_KIND_LABELS: Record<NonNullable<WorkflowEdge["kind"]>, string> = {
  handoff: "任务交接",
  data: "数据传递",
  condition: "条件路由",
  approval: "审核流转",
};

const EDGE_COLORS: Record<NonNullable<WorkflowEdge["kind"]>, string> = {
  handoff: "#66758a",
  data: "#208f9a",
  condition: "#c88423",
  approval: "#9a5fc2",
};

const EMPTY_PRINCIPALS: Principal[] = [];

const STATUS_LABELS: Record<string, string> = {
  pending: "等待前置",
  ready: "可领取",
  claimed: "已领取",
  running: "执行中",
  waiting_review: "待审核",
  completed: "已完成",
  blocked: "已阻塞",
  failed: "失败",
  cancelled: "已取消",
  skipped: "已跳过",
  stale: "需重做",
  needs_rework: "需要返工",
};

function nodeStatus(node: MatrixNode) {
  return "status" in node && typeof node.status === "string" ? node.status : "";
}

function principalName(principals: Principal[], id?: string | null) {
  return principals.find((principal) => principal.id === id)?.name || id || "未分配";
}

function edgeKey(edge: Pick<WorkflowEdge, "source" | "target">) {
  return `${edge.source}->${edge.target}`;
}

interface WorkflowCanvasNodeData extends Record<string, unknown> {
  node: MatrixNode;
  coordinate?: string;
  accountable: string;
  editable: boolean;
}

type WorkflowCanvasNode = Node<WorkflowCanvasNodeData, "workflowNode">;

interface WorkflowCanvasEdgeData extends Record<string, unknown> {
  edge: WorkflowEdge;
  selectedNodeId?: string;
  onSelect?: (edge: WorkflowEdge) => void;
}

type WorkflowCanvasEdge = Edge<WorkflowCanvasEdgeData, "workflowProcess">;

function WorkflowNodeCard({ data, selected }: NodeProps<WorkflowCanvasNode>) {
  const { node, coordinate, accountable, editable } = data;
  const status = nodeStatus(node);
  return <div className={`flow-workflow-node kind-${node.kind} ${status ? `status-${status}` : ""} ${selected ? "is-selected" : ""}`}>
    <Handle className="flow-node-handle flow-node-handle-input" type="target" position={Position.Left} isConnectable={editable} />
    <Handle className="flow-node-handle flow-node-handle-output" type="source" position={Position.Right} isConnectable={editable} />
    <header>{coordinate ? <span>{coordinate}</span> : null}{node.promotedToMenu ? <Pin /> : null}<em>{node.kind === "gate" ? "GATE" : node.kind.toUpperCase()}</em></header>
    <strong>{node.name}</strong>
    <p>{node.description || node.roleKey}</p>
    <footer><span>{accountable}</span><em>{status ? STATUS_LABELS[status] || status : `${node.outputs.length} 交付物`}</em></footer>
  </div>;
}

function WorkflowProcessEdge(props: EdgeProps<WorkflowCanvasEdge>) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
    curvature: .38,
  });
  const edge = props.data?.edge;
  if (!edge) return null;
  const kind = edge.kind || "handoff";
  const customLabel = edge.name?.trim();
  const label = customLabel || EDGE_KIND_LABELS[kind];
  const parameterCount = Object.keys(edge.parameters || {}).length;
  const related = Boolean(props.data?.selectedNodeId && (edge.source === props.data.selectedNodeId || edge.target === props.data.selectedNodeId));
  const dimmed = Boolean(props.data?.selectedNodeId && !related && !props.selected);
  return <>
    <BaseEdge
      id={props.id}
      path={path}
      markerEnd={props.markerEnd}
      interactionWidth={26}
      className={`flow-process-edge kind-${kind} ${props.selected ? "is-selected" : ""} ${related ? "is-related" : ""} ${dimmed ? "is-dimmed" : ""}`}
      style={{ ...props.style, stroke: EDGE_COLORS[kind] }}
    />
    <EdgeLabelRenderer>
      <button
        className={`flow-process-label nodrag nopan kind-${kind} ${props.selected ? "is-selected" : ""} ${related ? "is-related" : ""} ${dimmed ? "is-dimmed" : ""}`}
        style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
        onClick={(event) => { event.stopPropagation(); props.data?.onSelect?.(edge); }}
        title={edge.condition || edge.description || `${edge.source} → ${edge.target}`}
      >
        <span>{label}</span>
        {customLabel || parameterCount ? <small>{customLabel ? EDGE_KIND_LABELS[kind] : ""}{customLabel && parameterCount ? " · " : ""}{parameterCount ? `${parameterCount} 参数` : ""}</small> : null}
      </button>
    </EdgeLabelRenderer>
  </>;
}

const nodeTypes = { workflowNode: WorkflowNodeCard };
const edgeTypes = { workflowProcess: WorkflowProcessEdge };

export interface WorkflowCanvasMove {
  nodeId: string;
  laneId: string;
  stageId: string;
  canvasX: number;
  canvasY: number;
}

export interface WorkflowCanvasAdd {
  laneId: string;
  stageId: string;
  canvasX: number;
  canvasY: number;
}

export interface OrganizationWorkflowCanvasProps {
  lanes: WorkflowLaneDefinition[];
  stages: WorkflowStageDefinition[];
  nodes: MatrixNode[];
  edges: WorkflowEdge[];
  principals?: Principal[];
  editable?: boolean;
  showCoordinates?: boolean;
  showHud?: boolean;
  showAxes?: boolean;
  activeLaneId?: string;
  activeStageId?: string;
  selectedNodeId?: string;
  selectedEdgeKey?: string;
  onSelectNode(id: string): void;
  onSelectEdge?(edge: WorkflowEdge): void;
  onMoveNode?(move: WorkflowCanvasMove): void;
  onConnectNodes?(source: string, target: string): void;
  onAddNode?(input: WorkflowCanvasAdd): void;
}

function OrganizationWorkflowCanvasInner(props: OrganizationWorkflowCanvasProps) {
  const { lanes, stages, editable = false } = props;
  const showCoordinates = props.showCoordinates ?? editable;
  const showHud = props.showHud ?? editable;
  const showAxes = props.showAxes ?? editable;
  const principals = props.principals || EMPTY_PRINCIPALS;
  const visibleLaneIds = useMemo(() => new Set(props.activeLaneId ? [props.activeLaneId] : lanes.map((lane) => lane.id)), [lanes, props.activeLaneId]);
  const visibleStageIds = useMemo(() => new Set(props.activeStageId ? [props.activeStageId] : stages.map((stage) => stage.id)), [props.activeStageId, stages]);
  const visibleNodes = useMemo(() => props.nodes.filter((node) => visibleLaneIds.has(node.laneId) && visibleStageIds.has(node.stageId)), [props.nodes, visibleLaneIds, visibleStageIds]);
  const builtNodes = useMemo<WorkflowCanvasNode[]>(() => visibleNodes.map((node) => ({
    id: node.id,
    type: "workflowNode",
    position: defaultNodePosition(node, lanes, stages),
    data: {
      node,
      coordinate: showCoordinates ? matrixCoordinate(node.laneId, node.stageId, lanes, stages) : undefined,
      accountable: "accountablePrincipalId" in node ? principalName(principals, node.accountablePrincipalId) : node.roleKey,
      editable,
    },
    selected: props.selectedNodeId === node.id,
    draggable: editable,
    connectable: editable,
    selectable: true,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    zIndex: 5,
  })), [editable, lanes, principals, props.selectedNodeId, showCoordinates, stages, visibleNodes]);
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<WorkflowCanvasNode>(builtNodes);
  const { fitBounds, screenToFlowPosition, setCenter } = useReactFlow<WorkflowCanvasNode, WorkflowCanvasEdge>();
  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const flowEdges = useMemo<WorkflowCanvasEdge[]>(() => props.edges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)).map((edge) => {
    const kind = edge.kind || "handoff";
    return {
      id: edgeKey(edge),
      type: "workflowProcess",
      source: edge.source,
      target: edge.target,
      data: { edge, selectedNodeId: props.selectedNodeId, onSelect: props.onSelectEdge },
      selected: props.selectedEdgeKey === edgeKey(edge),
      selectable: true,
      deletable: false,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: EDGE_COLORS[kind] },
      zIndex: 2,
    };
  }), [props.edges, props.onSelectEdge, props.selectedEdgeKey, props.selectedNodeId, visibleNodeIds]);
  const bounds = useMemo(() => canvasBounds(lanes, stages, visibleLaneIds, visibleStageIds), [lanes, stages, visibleLaneIds, visibleStageIds]);
  const fitTarget = useMemo(() => {
    if (editable || showAxes || !visibleNodes.length) return bounds;
    const positions = visibleNodes.map((node) => defaultNodePosition(node, lanes, stages));
    const x = Math.min(...positions.map((position) => position.x));
    const y = Math.min(...positions.map((position) => position.y));
    const right = Math.max(...positions.map((position) => position.x + NODE_WIDTH));
    const bottom = Math.max(...positions.map((position) => position.y + NODE_HEIGHT));
    return { x, y, width: right - x, height: bottom - y };
  }, [bounds, editable, lanes, showAxes, stages, visibleNodes]);

  useEffect(() => setFlowNodes(builtNodes), [builtNodes, setFlowNodes]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => void fitBounds(fitTarget, { padding: editable ? .035 : .06, duration: 240 }));
    return () => cancelAnimationFrame(frame);
  }, [editable, fitBounds, fitTarget]);

  const moveNode = useCallback((_event: MouseEvent | TouchEvent, node: WorkflowCanvasNode) => {
    if (!editable || !props.onMoveNode) return;
    const drop = resolveCanvasDrop(node.position, lanes, stages);
    setFlowNodes((current) => current.map((item) => item.id === node.id ? { ...item, position: { x: drop.x, y: drop.y } } : item));
    props.onMoveNode({ nodeId: node.id, laneId: drop.laneId, stageId: drop.stageId, canvasX: drop.x, canvasY: drop.y });
  }, [editable, lanes, props, setFlowNodes, stages]);

  const connectNodes = useCallback((connection: Connection) => {
    if (!editable || !connection.source || !connection.target || connection.source === connection.target) return;
    if (props.edges.some((edge) => edge.source === connection.source && edge.target === connection.target)) return;
    props.onConnectNodes?.(connection.source, connection.target);
  }, [editable, props]);

  const addNode = useCallback((event: React.MouseEvent) => {
    if (!editable || !props.onAddNode || event.detail !== 2) return;
    const point = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const cell = resolveCanvasCell(point, lanes, stages);
    if (cell && visibleLaneIds.has(cell.laneId) && visibleStageIds.has(cell.stageId)) {
      props.onAddNode({ laneId: cell.laneId, stageId: cell.stageId, canvasX: cell.x, canvasY: cell.y });
    }
  }, [editable, lanes, props, screenToFlowPosition, stages, visibleLaneIds, visibleStageIds]);

  const focusNode = (id: string) => {
    const node = flowNodes.find((item) => item.id === id);
    if (!node) return;
    void setCenter(node.position.x + NODE_WIDTH / 2, node.position.y + NODE_HEIGHT / 2, { zoom: 1.12, duration: 260 });
    props.onSelectNode(id);
  };

  return <ReactFlow<WorkflowCanvasNode, WorkflowCanvasEdge>
    nodes={flowNodes}
    edges={flowEdges}
    nodeTypes={nodeTypes}
    edgeTypes={edgeTypes}
    onNodesChange={onNodesChange}
    onNodeClick={(_event, node) => props.onSelectNode(node.id)}
    onEdgeClick={(_event, edge) => edge.data?.edge && props.onSelectEdge?.(edge.data.edge)}
    onNodeDragStop={moveNode}
    onConnect={connectNodes}
    onPaneClick={addNode}
    nodesDraggable={editable}
    nodesConnectable={editable}
    elementsSelectable
    panOnDrag
    zoomOnDoubleClick={false}
    minZoom={.28}
    maxZoom={editable ? 1.8 : 1.25}
    snapToGrid={editable}
    snapGrid={[10, 10]}
    deleteKeyCode={null}
    onlyRenderVisibleElements={flowNodes.length > 35}
    proOptions={{ hideAttribution: true }}
  >
    <Background variant={BackgroundVariant.Lines} gap={24} size={1} color="color-mix(in srgb, var(--mod-border, #dce1e9) 48%, transparent)" />
    {showAxes ? <ViewportPortal>
      <div
        className="flow-matrix-axis-layer"
        style={{
          width: CANVAS_LEFT + stages.length * STAGE_WIDTH,
          height: CANVAS_TOP + lanes.length * LANE_HEIGHT,
        }}
      >
        <div className="flow-axis-corner"><span>坐标</span><strong>业务域 × 阶段</strong></div>
        <div
          className="flow-matrix-grid"
          style={{
            left: CANVAS_LEFT,
            top: CANVAS_TOP,
            width: stages.length * STAGE_WIDTH,
            height: lanes.length * LANE_HEIGHT,
            backgroundSize: `${STAGE_WIDTH}px 100%, 100% ${LANE_HEIGHT}px`,
          }}
        />
        {stages.map((stage, index) => visibleStageIds.has(stage.id) ? <div
          className="flow-axis-header flow-stage-header"
          key={stage.id}
          style={{ left: CANVAS_LEFT + index * STAGE_WIDTH + 8, top: 14, width: STAGE_WIDTH - 16 }}
        ><span>{index + 1}</span><div><strong>{stage.name}</strong><small>{stage.description || "流程阶段"}</small></div></div> : null)}
        {lanes.map((lane, index) => visibleLaneIds.has(lane.id) ? <div
          className="flow-axis-header flow-lane-header"
          key={lane.id}
          style={{ left: 6, top: CANVAS_TOP + index * LANE_HEIGHT + (LANE_HEIGHT - 74) / 2, width: CANVAS_LEFT - 12 }}
        ><span>{axisLetter(index)}</span><div><strong>{lane.name}</strong><small>{lane.description || "业务域"}</small></div></div> : null)}
      </div>
    </ViewportPortal> : null}
    {showHud ? <Panel position="bottom-center" className="workflow-flow-hud">
      <span>{editable ? "拖动节点 · 拖出连线 · 双击空白新增" : "拖动画布 · 滚轮缩放"}</span>
      {visibleNodes.length > 1 ? <select aria-label="定位节点" value={props.selectedNodeId || ""} onChange={(event) => focusNode(event.target.value)}><option value="">定位节点</option>{visibleNodes.map((node) => <option value={node.id} key={node.id}>{showCoordinates ? `${matrixCoordinate(node.laneId, node.stageId, lanes, stages)} · ` : ""}{node.name}</option>)}</select> : null}
    </Panel> : null}
    <MiniMap pannable zoomable position="bottom-left" nodeColor={(node) => {
      const kind = (node.data as WorkflowCanvasNodeData).node.kind;
      return kind === "automation" ? "#1c9f8a" : kind === "gate" ? "#9a5fc2" : kind === "review" ? "#c88423" : "#4777d9";
    }} maskColor="rgba(24, 34, 50, .12)" />
    <Controls position="bottom-right" orientation="horizontal" showInteractive={false} />
  </ReactFlow>;
}

export function OrganizationWorkflowCanvas(props: OrganizationWorkflowCanvasProps) {
  return <div className={`organization-flow-canvas ${props.editable ? "is-editable" : "is-readonly"}`}><ReactFlowProvider><OrganizationWorkflowCanvasInner {...props} /></ReactFlowProvider></div>;
}
