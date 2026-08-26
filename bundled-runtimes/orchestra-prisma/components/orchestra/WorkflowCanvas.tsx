import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Bot,
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  Clock3,
  Columns3,
  Cpu,
  Database,
  FileCheck2,
  Focus,
  GripVertical,
  LayoutGrid,
  LocateFixed,
  Maximize2,
  Network,
  Orbit,
  Pause,
  Pin,
  PinOff,
  Play,
  Radio,
  Rewind,
  RotateCcw,
  Search,
  ServerCog,
  SkipBack,
  SkipForward,
  UsersRound,
  Vote,
  Wrench,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import type { AgentProfile, AgentRuntime, DecisionEvent } from '@/types/orchestra';
import {
  buildReplayFrames,
  confidenceLabels,
  extractReportSignal,
  stanceHistoryFor,
  stanceLabels,
  type InvestmentStance,
} from '@/utils/orchestraReplay';

type Point = { x: number; y: number };
type FlowPath = {
  id: string;
  from: Point;
  to: Point;
  stage: number;
  agentId?: string;
  group?: string;
  relation?: 'briefing' | 'vote';
};
type Artifact = { label: string; text: string; kind: 'method' | 'evidence' | 'result' };
type Zone = { group: GroupName; className: string; x: number; y: number; width: number; height: number };
type GroupName = (typeof GROUPS)[number];
type GroupSummary = { group: GroupName; point: Point; agents: AgentProfile[] };
type LayoutMode = 'committee' | 'grouped' | 'debate';
type ManualPositions = Record<LayoutMode, Record<string, Point>>;
type AgentDragState = { agentId: string; startX: number; startY: number; origin: Point };

const CANVAS_WIDTH = 1900;
const MIN_CANVAS_HEIGHT = 1480;
const ROW_GAP = 132;
const MINI_WIDTH = 210;
const MINI_HEIGHT = 126;
const GROUPS = ['宏观组', '配置组', '股票组', '基金经理组'] as const;
const LAYOUT_STORAGE_KEY = 'orchestra:workflow-layout:v2';
const emptyManualPositions = (): ManualPositions => ({ committee: {}, grouped: {}, debate: {} });

const laneX: Record<GroupName, number> = {
  宏观组: 455,
  配置组: 680,
  股票组: 905,
  基金经理组: 1395,
};

const phaseOrder: Record<string, number> = {
  queued: 0,
  planning: 1,
  research: 2,
  deliberation: 3,
  convergence: 4,
  decision: 5,
  completed: 6,
  failed: 6,
  cancelled: 6,
};

const groupClass: Record<string, string> = {
  宏观组: 'macro',
  配置组: 'allocation',
  股票组: 'equity',
  基金经理组: 'pm',
};

const statusLabel: Record<AgentRuntime['status'], string> = {
  idle: '待命',
  queued: '排队',
  working: '执行',
  completed: '完成',
  failed: '异常',
};

const curve = (from: Point, to: Point) => {
  const bend = Math.max(58, Math.abs(to.x - from.x) * 0.44);
  return `M ${from.x} ${from.y} C ${from.x + bend} ${from.y}, ${to.x - bend} ${to.y}, ${to.x} ${to.y}`;
};

const compactText = (text: string, max = 48) => {
  const normalized = text.replace(/【[^】]+】/g, '').replace(/\s+/g, ' ').trim();
  if (!normalized) return '等待阶段成果';
  return normalized.length > max ? `${normalized.slice(0, max)}…` : normalized;
};

const artifactsFor = (profile: AgentProfile, runtime?: AgentRuntime): Artifact[] => {
  if (!runtime || ['idle', 'queued'].includes(runtime.status)) return [];
  const artifacts: Artifact[] = [{
    label: '研究路径',
    text: runtime.thoughts[1] || runtime.thoughts[0] || `聚焦 ${profile.focus}`,
    kind: 'method',
  }];
  if (runtime.tools.length > 0 || runtime.output) {
    artifacts.push({
      label: runtime.tools.length > 0 ? '数据证据' : '证据审计',
      text: runtime.tools.length > 0 ? runtime.tools.join(' · ') : compactText(runtime.output, 42),
      kind: 'evidence',
    });
  }
  if (runtime.status === 'completed' && runtime.output) {
    const signal = extractReportSignal(runtime.output);
    const signalLabel = signal.stance === 'unknown' ? '' : ` · ${stanceLabels[signal.stance]}`;
    artifacts.push({ label: `阶段成果${signalLabel}`, text: compactText(runtime.output, 54), kind: 'result' });
  }
  return artifacts.slice(-3);
};

const distributeRows = (count: number, height: number): number[] => {
  if (count <= 0) return [];
  if (count === 1) return [height / 2];
  const top = 140;
  const bottom = height - 130;
  const gap = (bottom - top) / (count - 1);
  return Array.from({ length: count }, (_, index) => top + gap * index);
};

const columnCountFor = (count: number, group: GroupName, mode: LayoutMode) => {
  if (count <= 1) return 1;
  if (mode === 'grouped') return count > 10 ? 3 : count > 4 ? 2 : 1;
  if (mode === 'debate') return 1;
  if (group === '基金经理组') return count > 14 ? 3 : count > 5 ? 2 : 1;
  return count > 18 ? 3 : count > 7 ? 2 : 1;
};

const gridPoints = (
  count: number,
  centerX: number,
  centerY: number,
  columns: number,
  xGap: number,
  yGap: number,
): Point[] => {
  if (count <= 0) return [];
  const rows = Math.ceil(count / columns);
  const points: Point[] = [];
  for (let index = 0; index < count; index += 1) {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const itemsInRow = row === rows - 1 && count % columns ? count % columns : columns;
    const rowOffset = (columns - itemsInRow) * xGap / 2;
    points.push({
      x: centerX + (column - (columns - 1) / 2) * xGap + rowOffset,
      y: centerY + (row - (rows - 1) / 2) * yGap,
    });
  }
  return points;
};

const laneGridPoints = (
  count: number,
  centerX: number,
  canvasHeight: number,
  columns: number,
  xGap: number,
): Point[] => {
  if (count <= 0) return [];
  const rows = Math.ceil(count / columns);
  const rowPositions = distributeRows(rows, canvasHeight);
  return Array.from({ length: count }, (_, index) => {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const itemsInRow = row === rows - 1 && count % columns ? count % columns : columns;
    const rowOffset = (columns - itemsInRow) * xGap / 2;
    return {
      x: centerX + (column - (columns - 1) / 2) * xGap + rowOffset,
      y: rowPositions[row],
    };
  });
};

const arcPoints = (
  count: number,
  center: Point,
  radiusX: number,
  radiusY: number,
  side: 'left' | 'right',
): Point[] => {
  if (count <= 0) return [];
  if (count === 1) return [{ x: center.x + (side === 'left' ? -radiusX : radiusX), y: center.y }];
  const start = -1.12;
  const end = 1.12;
  return Array.from({ length: count }, (_, index) => {
    const angle = start + ((end - start) * index) / (count - 1);
    const horizontal = Math.cos(angle) * radiusX;
    return {
      x: center.x + (side === 'left' ? -horizontal : horizontal),
      y: center.y + Math.sin(angle) * radiusY,
    };
  });
};

const loadSavedLayout = (): { mode: LayoutMode; positions: ManualPositions } => {
  try {
    const value = JSON.parse(window.localStorage.getItem(LAYOUT_STORAGE_KEY) || '{}') as {
      mode?: LayoutMode;
      positions?: Partial<ManualPositions>;
    };
    return {
      mode: ['committee', 'grouped', 'debate'].includes(value.mode || '') ? value.mode! : 'committee',
      positions: {
        committee: value.positions?.committee || {},
        grouped: value.positions?.grouped || {},
        debate: value.positions?.debate || {},
      },
    };
  } catch {
    return { mode: 'committee', positions: emptyManualPositions() };
  }
};

const zoneFor = (group: GroupName, points: Point[]): Zone | null => {
  if (points.length === 0) return null;
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  return {
    group,
    className: groupClass[group] || '',
    x: minX - 96,
    y: minY - 62,
    width: maxX - minX + 192,
    height: maxY - minY + 124,
  };
};

const activityLevel = (runtime?: AgentRuntime) => {
  if (!runtime) return 0.16;
  return Math.min(1, 0.2
    + runtime.tools.length * 0.1
    + runtime.evidence.length * 0.07
    + Math.min(runtime.output.length / 5000, 0.36));
};

const aggregateStatus = (profiles: AgentProfile[], runtimes: Record<string, AgentRuntime>): AgentRuntime['status'] => {
  const statuses = profiles.map((profile) => runtimes[profile.id]?.status || 'idle');
  if (statuses.includes('working')) return 'working';
  if (statuses.includes('failed')) return 'failed';
  if (statuses.length > 0 && statuses.every((status) => status === 'completed')) return 'completed';
  if (statuses.includes('queued')) return 'queued';
  return 'idle';
};

const elapsedLabel = (runtime: AgentRuntime | undefined, now: number) => {
  if (!runtime?.started_at) return '—';
  const start = new Date(runtime.started_at).getTime();
  const end = runtime.completed_at ? new Date(runtime.completed_at).getTime() : now;
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return seconds < 3600 ? `${minutes}m${seconds % 60}s` : `${Math.floor(minutes / 60)}h${minutes % 60}m`;
};

const WorkflowCanvas = ({
  agents,
  runtimes,
  events = [],
  maxConcurrency,
  phase,
  topic,
  plan,
  consensus,
  decision,
  orchestraThinking,
  showThinking,
  showArtifacts,
  replayEventIndex = null,
  onReplayEventIndexChange = () => undefined,
  onSelect,
  onOpenReport,
}: {
  agents: AgentProfile[];
  runtimes: Record<string, AgentRuntime>;
  events?: DecisionEvent[];
  maxConcurrency?: number;
  phase: string;
  topic: string;
  plan: string;
  consensus: string;
  decision: string;
  orchestraThinking: string;
  showThinking: boolean;
  showArtifacts: boolean;
  replayEventIndex?: number | null;
  onReplayEventIndexChange?: (eventIndex: number | null) => void;
  onSelect: (agent: AgentProfile) => void;
  onOpenReport?: (agent: AgentProfile) => void;
}) => {
  const initialFitZoom = () => {
    const railWidth = window.innerWidth <= 820 ? 24 : window.innerWidth <= 1040 ? 394 : 458;
    const widthFit = (window.innerWidth - railWidth) / CANVAS_WIDTH;
    const heightFit = (window.innerHeight - 140) / MIN_CANVAS_HEIGHT;
    return Math.max(0.32, Math.min(0.72, widthFit, heightFit));
  };
  const scrollRef = useRef<HTMLDivElement>(null);
  const panRef = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const agentDragRef = useRef<AgentDragState | null>(null);
  const viewportFrameRef = useRef<number | null>(null);
  const initialLayoutRef = useRef<ReturnType<typeof loadSavedLayout> | null>(null);
  if (initialLayoutRef.current === null) initialLayoutRef.current = loadSavedLayout();
  const [zoom, setZoom] = useState(initialFitZoom);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(initialLayoutRef.current.mode);
  const [manualPositions, setManualPositions] = useState<ManualPositions>(initialLayoutRef.current.positions);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<GroupName>>(new Set());
  const [focusedAgentId, setFocusedAgentId] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isPanning, setIsPanning] = useState(false);
  const [draggingAgentId, setDraggingAgentId] = useState<string | null>(null);
  const [showStances, setShowStances] = useState(true);
  const [isReplayPlaying, setIsReplayPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [now, setNow] = useState(() => Date.now());
  const [viewport, setViewport] = useState({ left: 0, top: 0, width: 1, height: 1 });
  const phaseIndex = phaseOrder[phase] ?? 0;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({ mode: layoutMode, positions: manualPositions }));
  }, [layoutMode, manualPositions]);

  const layout = useMemo(() => {
    const grouped = Object.fromEntries(GROUPS.map((group) => [group, agents.filter((agent) => agent.group === group)])) as Record<GroupName, AgentProfile[]>;
    const expanded = Object.fromEntries(GROUPS.map((group) => [group, collapsedGroups.has(group) ? [] : grouped[group]])) as Record<GroupName, AgentProfile[]>;
    const columns = Object.fromEntries(GROUPS.map((group) => [
      group,
      columnCountFor(expanded[group].length, group, layoutMode),
    ])) as Record<GroupName, number>;
    const rowCounts = GROUPS.map((group) => Math.ceil(expanded[group].length / columns[group]));
    const maxRows = Math.max(...rowCounts, 1);
    const maxGroupCount = Math.max(...GROUPS.map((group) => expanded[group].length), 1);
    const canvasHeight = layoutMode === 'grouped'
      ? Math.max(MIN_CANVAS_HEIGHT, maxRows * ROW_GAP * 2 + 360)
      : layoutMode === 'debate'
        ? Math.max(MIN_CANVAS_HEIGHT, maxGroupCount * 78 + 300)
        : Math.max(MIN_CANVAS_HEIGHT, maxRows * ROW_GAP + 220);
    const centerY = canvasHeight / 2;
    const brainX = layoutMode === 'committee' ? 1160 : layoutMode === 'grouped' ? 1120 : 1100;
    const points: Record<string, Point> = {
      topic: { x: 82, y: centerY },
      orchestra: { x: 245, y: centerY },
      collectiveBrain: { x: brainX, y: centerY },
      decision: { x: 1810, y: centerY },
    };
    const summaries: GroupSummary[] = [];
    const groupAnchors: Record<GroupName, Point> = layoutMode === 'grouped'
      ? {
        宏观组: { x: 470, y: canvasHeight * 0.3 },
        配置组: { x: 810, y: canvasHeight * 0.3 },
        股票组: { x: 650, y: canvasHeight * 0.73 },
        基金经理组: { x: 1460, y: canvasHeight * 0.52 },
      }
      : layoutMode === 'debate'
        ? {
          宏观组: { x: 500, y: centerY - 320 },
          配置组: { x: 650, y: centerY },
          股票组: { x: 810, y: centerY + 320 },
          基金经理组: { x: 1450, y: centerY },
        }
        : {
          宏观组: { x: laneX['宏观组'], y: centerY },
          配置组: { x: laneX['配置组'], y: centerY },
          股票组: { x: laneX['股票组'], y: centerY },
          基金经理组: { x: 1492, y: centerY },
        };

    GROUPS.forEach((group) => {
      if (collapsedGroups.has(group)) {
        const point = groupAnchors[group];
        points[`group:${group}`] = point;
        summaries.push({ group, point, agents: grouped[group] });
        return;
      }
      let generated: Point[];
      if (layoutMode === 'committee') {
        generated = laneGridPoints(
          expanded[group].length,
          groupAnchors[group].x,
          canvasHeight,
          columns[group],
          group === '基金经理组' ? 195 : 96,
        );
      } else if (layoutMode === 'grouped') {
        generated = gridPoints(
          expanded[group].length,
          groupAnchors[group].x,
          groupAnchors[group].y,
          columns[group],
          group === '基金经理组' ? 165 : 104,
          118,
        );
      } else {
        const baseRadiusY = Math.max(430, (canvasHeight - 320) / 2);
        const radiusX: Record<GroupName, number> = {
          宏观组: 650,
          配置组: 480,
          股票组: 310,
          基金经理组: 350,
        };
        const radiusY: Record<GroupName, number> = {
          宏观组: baseRadiusY,
          配置组: baseRadiusY * 0.78,
          股票组: baseRadiusY * 0.56,
          基金经理组: baseRadiusY,
        };
        generated = arcPoints(
          expanded[group].length,
          points.collectiveBrain,
          radiusX[group],
          radiusY[group],
          group === '基金经理组' ? 'right' : 'left',
        );
      }
      expanded[group].forEach((agent, index) => {
        points[agent.id] = generated[index];
      });
    });

    const activeManualPositions = manualPositions[layoutMode];
    agents.forEach((agent) => {
      const manual = activeManualPositions[agent.id];
      if (!manual || collapsedGroups.has(agent.group as GroupName) || !points[agent.id]) return;
      points[agent.id] = {
        x: Math.max(330, Math.min(1710, manual.x)),
        y: Math.max(90, Math.min(canvasHeight - 90, manual.y)),
      };
    });

    const paths: FlowPath[] = [{ id: 'topic-orchestra', from: points.topic, to: points.orchestra, stage: 1 }];
    (['宏观组', '配置组', '股票组'] as const).forEach((group) => {
      if (collapsedGroups.has(group)) {
        const point = points[`group:${group}`];
        paths.push(
          { id: `orchestra-group-${group}`, from: points.orchestra, to: point, stage: 2, group },
          { id: `group-${group}-brain`, from: point, to: points.collectiveBrain, stage: 2, group },
        );
      } else {
        grouped[group].forEach((agent) => paths.push(
          { id: `orchestra-${agent.id}`, from: points.orchestra, to: points[agent.id], stage: 2, agentId: agent.id },
          { id: `${agent.id}-brain`, from: points[agent.id], to: points.collectiveBrain, stage: 2, agentId: agent.id },
        ));
      }
    });
    if (collapsedGroups.has('基金经理组')) {
      const point = points['group:基金经理组'];
      paths.push(
        { id: 'brain-group-pm', from: points.collectiveBrain, to: point, stage: 3, group: '基金经理组' },
        { id: 'group-pm-decision', from: point, to: points.decision, stage: 4, group: '基金经理组', relation: 'vote' },
      );
    } else {
      grouped['基金经理组'].forEach((agent) => paths.push(
        { id: `brain-${agent.id}`, from: points.collectiveBrain, to: points[agent.id], stage: 3, agentId: agent.id, relation: 'briefing' },
        { id: `${agent.id}-decision`, from: points[agent.id], to: points.decision, stage: 4, agentId: agent.id, relation: 'vote' },
      ));
    }

    const zones = GROUPS.map((group) => {
      const zonePoints = collapsedGroups.has(group)
        ? [points[`group:${group}`]]
        : grouped[group].map((agent) => points[agent.id]);
      return zoneFor(group, zonePoints.filter(Boolean));
    }).filter((zone): zone is Zone => Boolean(zone));
    return {
      grouped,
      points,
      paths,
      zones,
      summaries,
      canvasHeight,
      columns,
      visibleAgents: agents.filter((agent) => !collapsedGroups.has(agent.group as GroupName)),
      researchAgents: agents.filter((agent) => agent.group !== '基金经理组'),
      pmAgents: grouped['基金经理组'],
    };
  }, [agents, collapsedGroups, layoutMode, manualPositions]);

  const visibleEvents = useMemo(
    () => replayEventIndex === null ? events : events.slice(0, replayEventIndex + 1),
    [events, replayEventIndex],
  );
  const replayFrames = useMemo(() => buildReplayFrames(events), [events]);
  const selectedReplayFramePosition = useMemo(() => {
    if (replayEventIndex === null || replayFrames.length === 0) return -1;
    const exact = replayFrames.findIndex((frame) => frame.eventIndex === replayEventIndex);
    if (exact >= 0) return exact;
    let position = 0;
    replayFrames.forEach((frame, index) => {
      if (frame.eventIndex <= replayEventIndex) position = index;
    });
    return position;
  }, [replayEventIndex, replayFrames]);
  const selectedReplayFrame = selectedReplayFramePosition >= 0
    ? replayFrames[selectedReplayFramePosition]
    : null;

  useEffect(() => {
    if (!isReplayPlaying || replayEventIndex === null || replayFrames.length === 0) return;
    if (selectedReplayFramePosition >= replayFrames.length - 1) {
      setIsReplayPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => {
      onReplayEventIndexChange(replayFrames[selectedReplayFramePosition + 1].eventIndex);
    }, 220 / playbackRate);
    return () => window.clearTimeout(timer);
  }, [
    isReplayPlaying,
    onReplayEventIndexChange,
    playbackRate,
    replayEventIndex,
    replayFrames,
    selectedReplayFramePosition,
  ]);

  useEffect(() => {
    if (replayEventIndex === null) setIsReplayPlaying(false);
  }, [replayEventIndex]);

  const telemetry = useMemo(() => {
    const result: Record<string, { eventCount: number; latestTool: string; lastEvent: string }> = {};
    visibleEvents.forEach((event) => {
      if (!event.agent_id) return;
      const current = result[event.agent_id] || { eventCount: 0, latestTool: '', lastEvent: '' };
      current.eventCount += 1;
      current.lastEvent = event.type;
      if (event.type === 'agent.tool.started') current.latestTool = String(event.payload.tool || '');
      result[event.agent_id] = current;
    });
    return result;
  }, [visibleEvents]);

  const searchResults = useMemo(() => {
    const needle = searchQuery.trim().toLowerCase();
    if (!needle) return agents.slice(0, 8);
    return agents.filter((agent) => `${agent.id} ${agent.name} ${agent.group} ${agent.focus}`.toLowerCase().includes(needle)).slice(0, 8);
  }, [agents, searchQuery]);

  const statusCounts = useMemo(() => {
    const values = agents.map((agent) => runtimes[agent.id]?.status || 'idle');
    return {
      working: values.filter((status) => status === 'working').length,
      queued: values.filter((status) => status === 'queued').length,
      completed: values.filter((status) => status === 'completed').length,
      failed: values.filter((status) => status === 'failed').length,
      external: agents.filter((agent) => agent.connection?.kind && agent.connection.kind !== 'orchestra').length,
    };
  }, [agents, runtimes]);

  const pmSignals = useMemo(() => layout.pmAgents.map((agent) => {
    const reportSignal = extractReportSignal(runtimes[agent.id]?.output || '');
    const history = stanceHistoryFor(visibleEvents, agent.id);
    const stance = reportSignal.stance === 'unknown'
      ? history.at(-1)?.stance || 'unknown'
      : reportSignal.stance;
    return {
      agent,
      stance,
      confidence: reportSignal.confidence,
      changed: history.length > 1,
    };
  }), [layout.pmAgents, runtimes, visibleEvents]);
  const stanceByAgent = useMemo(
    () => new Map(pmSignals.map((item) => [item.agent.id, item])),
    [pmSignals],
  );
  const stanceCounts = useMemo(() => pmSignals.reduce<Record<InvestmentStance, number>>((counts, item) => {
    counts[item.stance] += 1;
    return counts;
  }, { bullish: 0, cautious: 0, bearish: 0, abstain: 0, unknown: 0 }), [pmSignals]);
  const expressedStanceCount = pmSignals.length - stanceCounts.unknown;
  const dominantStance: InvestmentStance = stanceCounts.bearish > stanceCounts.bullish
    ? 'bearish'
    : stanceCounts.bullish > 0
      ? 'bullish'
      : stanceCounts.cautious > 0
        ? 'cautious'
        : stanceCounts.abstain > 0
          ? 'abstain'
          : 'unknown';

  const updateViewport = useCallback(() => {
    if (viewportFrameRef.current !== null) return;
    const publish = () => {
      viewportFrameRef.current = null;
      const scroll = scrollRef.current;
      if (!scroll) return;
      const next = { left: scroll.scrollLeft, top: scroll.scrollTop, width: scroll.clientWidth, height: scroll.clientHeight };
      setViewport((current) => (
        current.left === next.left
        && current.top === next.top
        && current.width === next.width
        && current.height === next.height
          ? current
          : next
      ));
    };
    viewportFrameRef.current = typeof window.requestAnimationFrame === 'function'
      ? window.requestAnimationFrame(publish)
      : window.setTimeout(publish, 16);
  }, []);

  useEffect(() => {
    updateViewport();
    const scroll = scrollRef.current;
    if (!scroll || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(updateViewport);
    observer.observe(scroll);
    return () => observer.disconnect();
  }, [zoom, layout.canvasHeight, updateViewport]);

  useEffect(() => () => {
    if (viewportFrameRef.current !== null) {
      window.cancelAnimationFrame?.(viewportFrameRef.current);
    }
  }, []);

  const scrollToWorld = useCallback((point: Point, behavior: ScrollBehavior = 'smooth') => {
    const scroll = scrollRef.current;
    if (!scroll) return;
    const left = Math.max(0, point.x * zoom - scroll.clientWidth / 2);
    const top = Math.max(0, point.y * zoom - scroll.clientHeight / 2);
    if (typeof scroll.scrollTo === 'function') scroll.scrollTo({ left, top, behavior });
    else {
      scroll.scrollLeft = left;
      scroll.scrollTop = top;
    }
  }, [zoom]);

  useEffect(() => {
    if (!focusedAgentId) return;
    const point = layout.points[focusedAgentId];
    if (point) window.requestAnimationFrame(() => scrollToWorld(point));
  }, [focusedAgentId, layout.points, scrollToWorld]);

  const setZoomAround = (nextZoom: number, clientX?: number, clientY?: number) => {
    const scroll = scrollRef.current;
    const clamped = Math.max(0.22, Math.min(1.15, nextZoom));
    if (!scroll) {
      setZoom(clamped);
      return;
    }
    const rect = scroll.getBoundingClientRect();
    const anchorX = (clientX ?? rect.left + scroll.clientWidth / 2) - rect.left;
    const anchorY = (clientY ?? rect.top + scroll.clientHeight / 2) - rect.top;
    const worldX = (scroll.scrollLeft + anchorX) / zoom;
    const worldY = (scroll.scrollTop + anchorY) / zoom;
    setZoom(clamped);
    window.requestAnimationFrame(() => {
      scroll.scrollLeft = worldX * clamped - anchorX;
      scroll.scrollTop = worldY * clamped - anchorY;
      updateViewport();
    });
  };

  const fitCanvas = () => {
    const scroll = scrollRef.current;
    if (!scroll) return;
    const next = Math.max(0.22, Math.min(0.78, (scroll.clientWidth - 24) / CANVAS_WIDTH, (scroll.clientHeight - 24) / layout.canvasHeight));
    setZoom(next);
    window.requestAnimationFrame(() => {
      scroll.scrollLeft = 0;
      scroll.scrollTop = 0;
      updateViewport();
    });
  };

  const focusAgent = (agent: AgentProfile) => {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      next.delete(agent.group as GroupName);
      return next;
    });
    setFocusedAgentId(agent.id);
    setSearchOpen(false);
    setSearchQuery('');
  };

  const locateActiveAgent = () => {
    const active = agents.find((agent) => runtimes[agent.id]?.status === 'working')
      || agents.find((agent) => runtimes[agent.id]?.status === 'queued')
      || agents.find((agent) => runtimes[agent.id]?.status === 'failed');
    if (active) focusAgent(active);
  };

  const toggleGroup = (group: GroupName) => {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
    if (focusedAgentId && agents.find((agent) => agent.id === focusedAgentId)?.group === group) setFocusedAgentId(null);
  };

  const togglePinnedAgent = (agent: AgentProfile) => {
    setManualPositions((current) => {
      const nextMode = { ...current[layoutMode] };
      if (nextMode[agent.id]) delete nextMode[agent.id];
      else if (layout.points[agent.id]) nextMode[agent.id] = layout.points[agent.id];
      return { ...current, [layoutMode]: nextMode };
    });
  };

  const beginAgentDrag = (event: React.PointerEvent<HTMLButtonElement>, agent: AgentProfile) => {
    const point = layout.points[agent.id];
    if (!point) return;
    event.preventDefault();
    event.stopPropagation();
    agentDragRef.current = {
      agentId: agent.id,
      startX: event.clientX,
      startY: event.clientY,
      origin: point,
    };
    setDraggingAgentId(agent.id);
  };

  const resetCurrentLayout = () => {
    setManualPositions((current) => ({ ...current, [layoutMode]: {} }));
    setFocusedAgentId(null);
  };

  useEffect(() => {
    if (!draggingAgentId) return;
    const move = (event: PointerEvent) => {
      const drag = agentDragRef.current;
      if (!drag) return;
      const point = {
        x: Math.max(330, Math.min(1710, drag.origin.x + (event.clientX - drag.startX) / zoom)),
        y: Math.max(90, Math.min(layout.canvasHeight - 90, drag.origin.y + (event.clientY - drag.startY) / zoom)),
      };
      setManualPositions((current) => ({
        ...current,
        [layoutMode]: { ...current[layoutMode], [drag.agentId]: point },
      }));
    };
    const finish = () => {
      agentDragRef.current = null;
      setDraggingAgentId(null);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', finish, { once: true });
    window.addEventListener('pointercancel', finish, { once: true });
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
    };
  }, [draggingAgentId, layout.canvasHeight, layoutMode, zoom]);

  const startReplay = () => {
    if (replayFrames.length === 0) return;
    onReplayEventIndexChange(replayFrames[0].eventIndex);
    setIsReplayPlaying(true);
  };

  const jumpReplayKey = (direction: -1 | 1) => {
    if (replayFrames.length === 0) return;
    const current = selectedReplayFramePosition < 0 ? replayFrames.length : selectedReplayFramePosition;
    const target = direction < 0
      ? [...replayFrames].map((frame, index) => ({ frame, index })).reverse().find((item) => item.index < current && item.frame.isKey)
      : replayFrames.map((frame, index) => ({ frame, index })).find((item) => item.index > current && item.frame.isKey);
    if (target) onReplayEventIndexChange(target.frame.eventIndex);
  };

  const pathState = (path: FlowPath) => {
    if (phaseIndex > path.stage) return 'is-complete';
    if (phaseIndex !== path.stage) return '';
    if (path.agentId) {
      const status = runtimes[path.agentId]?.status;
      return status === 'working' || status === 'completed' ? 'is-active' : '';
    }
    if (path.group) {
      const status = aggregateStatus(layout.grouped[path.group as GroupName], runtimes);
      return status === 'working' || status === 'completed' ? 'is-active' : '';
    }
    return 'is-active';
  };

  const focusedProfile = focusedAgentId ? agents.find((agent) => agent.id === focusedAgentId) || null : null;
  const replayActor = selectedReplayFrame?.agentId
    ? agents.find((agent) => agent.id === selectedReplayFrame.agentId)?.name || selectedReplayFrame.agentId
    : 'Orchestra';
  const researchComplete = layout.researchAgents.filter((agent) => runtimes[agent.id]?.status === 'completed').length;
  const pmComplete = layout.pmAgents.filter((agent) => runtimes[agent.id]?.status === 'completed').length;
  const brainMemories = [
    plan ? { label: '研究计划', value: '已拆解' } : null,
    researchComplete > 0 ? { label: '研究成果', value: `${researchComplete}/${layout.researchAgents.length}` } : null,
    pmComplete > 0 ? { label: '经理审议', value: `${pmComplete}/${layout.pmAgents.length}` } : null,
    consensus ? { label: '共识纪要', value: '已收敛' } : null,
    decision ? { label: '正式决议', value: '已生成' } : null,
  ].filter((item): item is { label: string; value: string } => Boolean(item));
  const orchestraActive = ['planning', 'convergence', 'decision'].includes(phase);
  const brainActive = ['research', 'deliberation', 'convergence', 'decision'].includes(phase);
  const decisionActive = ['convergence', 'decision', 'completed'].includes(phase);
  const minimapScaleX = MINI_WIDTH / CANVAS_WIDTH;
  const minimapScaleY = MINI_HEIGHT / layout.canvasHeight;
  const highDensity = agents.length > 35;
  const worldViewport = {
    left: viewport.left / zoom - 260,
    right: (viewport.left + viewport.width) / zoom + 260,
    top: viewport.top / zoom - 180,
    bottom: (viewport.top + viewport.height) / zoom + 180,
  };
  const renderedAgents = !highDensity || viewport.width <= 1
    ? layout.visibleAgents
    : layout.visibleAgents.filter((agent) => {
      const point = layout.points[agent.id];
      const status = runtimes[agent.id]?.status;
      return focusedAgentId === agent.id
        || status === 'working'
        || status === 'queued'
        || status === 'failed'
        || (point
          && point.x >= worldViewport.left
          && point.x <= worldViewport.right
          && point.y >= worldViewport.top
          && point.y <= worldViewport.bottom);
    });
  const renderedAgentIds = new Set(renderedAgents.map((agent) => agent.id));
  const renderedPaths = !highDensity
    ? layout.paths
    : layout.paths.filter((path) => !path.agentId || renderedAgentIds.has(path.agentId));
  const pinnedCount = Object.keys(manualPositions[layoutMode]).length;

  return (
    <div className={`workflow-viewport ${focusedAgentId ? 'has-focus' : ''}`}>
      <div className="workflow-meta">
        <div>
          <span>EVOLVING DECISION GRAPH</span>
          <strong>动态研究席位拓扑 · {agents.length} 席</strong>
        </div>
        <div className="workflow-meta-right">
          <div className="workflow-scheduler-hud" aria-label="Agent 调度状态">
            <span className="is-working"><Activity size={11} />{statusCounts.working}/{maxConcurrency || '∞'}</span>
            <span>排队 {statusCounts.queued}</span>
            <span>完成 {statusCounts.completed}</span>
            {statusCounts.failed > 0 && <span className="is-failed">异常 {statusCounts.failed}</span>}
            {statusCounts.external > 0 && <span className="is-external"><ServerCog size={11} />{statusCounts.external}</span>}
            {highDensity && <span title="当前视口渲染 Agent 数">渲染 {renderedAgents.length}/{layout.visibleAgents.length}</span>}
          </div>
          <div className="workflow-legend" aria-label="状态图例">
            <span><i className="queued" />待命</span>
            <span><i className="working" />思考中</span>
            <span><i className="complete" />成果已沉淀</span>
          </div>
        </div>
      </div>

      <div className="workflow-canvas-tools">
        <div className="workflow-layout-modes" role="group" aria-label="Agent 布局模式">
          <button type="button" className={layoutMode === 'committee' ? 'is-active' : ''} onClick={() => { setLayoutMode('committee'); setFocusedAgentId(null); }} aria-label="投委会布局" title="投委会布局"><Columns3 size={14} /></button>
          <button type="button" className={layoutMode === 'grouped' ? 'is-active' : ''} onClick={() => { setLayoutMode('grouped'); setFocusedAgentId(null); }} aria-label="分组布局" title="分组布局"><LayoutGrid size={14} /></button>
          <button type="button" className={layoutMode === 'debate' ? 'is-active' : ''} onClick={() => { setLayoutMode('debate'); setFocusedAgentId(null); }} aria-label="辩论布局" title="辩论布局"><Orbit size={14} /></button>
        </div>
        <button type="button" className={searchOpen ? 'is-active' : ''} onClick={() => setSearchOpen((value) => !value)} aria-label="搜索 Agent" title="搜索 Agent"><Search size={15} /></button>
        <button type="button" onClick={locateActiveAgent} disabled={statusCounts.working + statusCounts.queued + statusCounts.failed === 0} aria-label="定位当前执行 Agent" title="定位当前执行 Agent"><LocateFixed size={15} /></button>
        <button type="button" className={showStances ? 'is-active' : ''} onClick={() => setShowStances((value) => !value)} aria-label="切换经理投票层" title="经理投票层"><Vote size={15} /></button>
        {pinnedCount > 0 && <button type="button" onClick={resetCurrentLayout} aria-label="重置当前布局" title={`重置当前布局 · ${pinnedCount} 个固定席位`}><RotateCcw size={14} /></button>}
        {focusedAgentId && <button type="button" className="is-active" onClick={() => setFocusedAgentId(null)} aria-label="退出焦点模式" title="退出焦点模式"><Focus size={15} /></button>}
        {searchOpen && (
          <div className="workflow-agent-search">
            <label><Search size={14} /><input autoFocus value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && searchResults[0]) focusAgent(searchResults[0]); }} placeholder="定位 Agent" aria-label="搜索画布 Agent" /></label>
            <div>
              {searchResults.map((agent) => (
                <button type="button" key={agent.id} onClick={() => focusAgent(agent)}><span>{agent.id}</span><strong>{agent.name}</strong><small>{agent.group}</small></button>
              ))}
              {searchResults.length === 0 && <p>无匹配席位</p>}
            </div>
          </div>
        )}
      </div>

      {focusedProfile && (
        <div className="workflow-focus-banner" role="status">
          <Focus size={14} />
          <span><strong>{focusedProfile.name}</strong><small>{focusedProfile.group} · {focusedProfile.connection?.kind === 'external_http' ? '外部 Agent' : focusedProfile.connection?.kind === 'openai_compatible' ? '独立模型' : 'Orchestra'}</small></span>
          <button type="button" onClick={() => setFocusedAgentId(null)} aria-label="退出焦点模式"><X size={14} /></button>
        </div>
      )}

      {showStances && expressedStanceCount > 0 && (
        <div className="workflow-vote-hud" aria-label="基金经理投票分布">
          <header><Vote size={13} /><span>经理分歧</span><b>{expressedStanceCount}/{pmSignals.length}</b></header>
          <div>
            <span className="is-bullish"><i />看多 {stanceCounts.bullish}</span>
            <span className="is-cautious"><i />谨慎 {stanceCounts.cautious}</span>
            <span className="is-bearish"><i />看空 {stanceCounts.bearish}</span>
            {stanceCounts.abstain > 0 && <span className="is-abstain"><i />弃权 {stanceCounts.abstain}</span>}
          </div>
          {pmSignals.some((item) => item.changed) && <small>有 {pmSignals.filter((item) => item.changed).length} 席观点发生变化</small>}
        </div>
      )}

      <div
        ref={scrollRef}
        className={`workflow-scroll ${isPanning ? 'is-panning' : ''}`}
        style={{ '--workflow-grid-size': `${28 * zoom}px` } as React.CSSProperties}
        onScroll={updateViewport}
        onWheel={(event) => {
          if (!event.ctrlKey && !event.metaKey) return;
          event.preventDefault();
          setZoomAround(zoom * Math.exp(-event.deltaY * 0.002), event.clientX, event.clientY);
        }}
        onPointerDown={(event) => {
          if ((event.target as HTMLElement).closest('button, input, textarea, select, a')) return;
          const scroll = scrollRef.current;
          if (!scroll) return;
          panRef.current = { x: event.clientX, y: event.clientY, left: scroll.scrollLeft, top: scroll.scrollTop };
          setIsPanning(true);
          scroll.setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={(event) => {
          const scroll = scrollRef.current;
          const pan = panRef.current;
          if (!scroll || !pan) return;
          scroll.scrollLeft = pan.left - (event.clientX - pan.x);
          scroll.scrollTop = pan.top - (event.clientY - pan.y);
        }}
        onPointerUp={(event) => {
          panRef.current = null;
          setIsPanning(false);
          scrollRef.current?.releasePointerCapture?.(event.pointerId);
        }}
        onPointerCancel={() => {
          panRef.current = null;
          setIsPanning(false);
        }}
      >
        <div className="workflow-stage-shell" style={{ width: CANVAS_WIDTH * zoom, height: layout.canvasHeight * zoom }}>
          <div className={`workflow-stage phase-${phase}`} style={{ width: CANVAS_WIDTH, height: layout.canvasHeight, transform: `scale(${zoom})` }}>
            {phaseIndex > 0 && phaseIndex < 6 && <div className="workflow-stage-scan" aria-hidden="true" />}

            {layout.zones.map((zone) => (
              <div key={zone.group} className={`workflow-zone zone-${zone.className} ${collapsedGroups.has(zone.group) ? 'is-collapsed' : ''}`} style={{ left: zone.x, top: zone.y, width: zone.width, height: zone.height }}>
                <button type="button" className="workflow-zone-toggle" onClick={() => toggleGroup(zone.group)} aria-label={`${collapsedGroups.has(zone.group) ? '展开' : '折叠'}${zone.group}`} title={`${collapsedGroups.has(zone.group) ? '展开' : '折叠'}${zone.group}`}>
                  {collapsedGroups.has(zone.group) ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                  <span>{zone.group}</span><b>{layout.grouped[zone.group].length}</b>
                </button>
              </div>
            ))}

            <svg className="workflow-links" viewBox={`0 0 ${CANVAS_WIDTH} ${layout.canvasHeight}`} aria-hidden="true">
              {renderedPaths.map((path) => {
                const state = pathState(path);
                const focused = focusedAgentId && path.agentId === focusedAgentId;
                const dimmed = focusedAgentId && path.agentId && path.agentId !== focusedAgentId;
                const profile = path.agentId ? agents.find((agent) => agent.id === path.agentId) : null;
                const sourceClass = profile?.connection?.kind === 'external_http' ? 'is-external' : profile?.connection?.kind === 'openai_compatible' ? 'is-model' : '';
                const voteStance = path.relation === 'vote'
                  ? path.agentId
                    ? stanceByAgent.get(path.agentId)?.stance || 'unknown'
                    : dominantStance
                  : 'unknown';
                const voteClass = showStances && path.relation === 'vote' && voteStance !== 'unknown' ? `is-vote is-${voteStance}` : '';
                const d = curve(path.from, path.to);
                return (
                  <g key={path.id} className={`${state} ${focused ? 'is-focused' : ''} ${dimmed ? 'is-dimmed' : ''} ${sourceClass} ${voteClass}`}>
                    <path d={d} className="workflow-link-glow" />
                    <path d={d} className="workflow-link-core" />
                    {state === 'is-active' && !dimmed && [0, 1, 2].map((packet) => (
                      <circle r={packet === 0 ? 3.4 : 2.4} className="flow-packet" key={packet} opacity={1 - packet * 0.2}>
                        <animateMotion dur={`${2.15 + packet * 0.28}s`} begin={`${packet * 0.54}s`} repeatCount="indefinite" path={d} />
                      </circle>
                    ))}
                  </g>
                );
              })}
            </svg>

            <div className="workflow-source" style={{ left: layout.points.topic.x, top: layout.points.topic.y }}><span>投决议题</span><strong>{topic || '等待新议题'}</strong></div>

            <div className={`workflow-orchestra ${orchestraActive ? 'is-active' : ''} ${phaseIndex > 1 ? 'is-complete' : ''}`} style={{ left: layout.points.orchestra.x, top: layout.points.orchestra.y }}>
              <Network size={19} /><div><strong>Orchestra</strong><span>主席编排</span></div>
            </div>

            {layout.summaries.map((summary) => {
              const status = aggregateStatus(summary.agents, runtimes);
              const completed = summary.agents.filter((agent) => runtimes[agent.id]?.status === 'completed').length;
              return (
                <div key={summary.group} className={`workflow-group-summary ${groupClass[summary.group]} is-${status}`} style={{ left: summary.point.x, top: summary.point.y }}>
                  <button type="button" onClick={() => toggleGroup(summary.group)} aria-label={`展开${summary.group}`}>
                    <UsersRound size={19} /><span><strong>{summary.group}</strong><small>{completed}/{summary.agents.length} 完成 · {statusLabel[status]}</small></span><ChevronRight size={14} />
                  </button>
                </div>
              );
            })}

            {renderedAgents.map((agent, agentIndex) => {
              const point = layout.points[agent.id];
              if (!point) return null;
              const runtime = runtimes[agent.id];
              const artifacts = artifactsFor(agent, runtime);
              const status = runtime?.status || 'idle';
              const intensity = activityLevel(runtime);
              const side = point.x < layout.points.collectiveBrain.x ? 'stack-right' : point.x < 1500 ? 'stack-left' : 'stack-right';
              const isFocused = focusedAgentId === agent.id;
              const isDimmed = Boolean(focusedAgentId && !isFocused);
              const isPinned = Boolean(manualPositions[layoutMode][agent.id]);
              const ConnectionIcon = agent.connection?.kind === 'external_http' ? ServerCog : agent.connection?.kind === 'openai_compatible' ? Bot : Cpu;
              const latestTool = telemetry[agent.id]?.latestTool || runtime?.tools.at(-1) || '';
              const stanceSignal = stanceByAgent.get(agent.id);
              return (
                <div
                  key={agent.id}
                  className={`workflow-agent-cluster ${groupClass[agent.group] || ''} ${side} is-${status} ${isFocused ? 'is-focused' : ''} ${isDimmed ? 'is-dimmed' : ''} ${isPinned ? 'is-pinned' : ''} ${draggingAgentId === agent.id ? 'is-dragging' : ''}`}
                  style={{ left: point.x, top: point.y, '--agent-index': agentIndex, '--activity': intensity } as React.CSSProperties}
                >
                  {status === 'working' && !isDimmed && <><span className="workflow-node-ripple ripple-one" aria-hidden="true" /><span className="workflow-node-ripple ripple-two" aria-hidden="true" /><div className="workflow-synapses" aria-hidden="true">{[0, 1, 2, 3, 4].map((particle) => <span key={particle} style={{ '--particle-angle': `${particle * 72}deg`, animationDelay: `${particle * -0.58}s` } as React.CSSProperties} />)}</div></>}

                  {showArtifacts && artifacts.length > 0 && !isDimmed && (
                    <button type="button" className="workflow-artifact-stack" aria-label={`打开 ${agent.name} 阶段成果`} onClick={() => onOpenReport?.(agent)} disabled={!onOpenReport || !runtime?.output}>
                      {artifacts.map((artifact, index) => <div key={`${artifact.kind}-${artifact.text}`} className={`workflow-artifact is-${artifact.kind}`} style={{ '--artifact-index': index, animationDelay: `${index * 90}ms` } as React.CSSProperties}><span>{artifact.label}</span><strong>{artifact.text}</strong></div>)}
                    </button>
                  )}

                  <button type="button" className="workflow-agent" onClick={() => onSelect(agent)} aria-label={`${agent.name} 详情`}>
                    <span className="workflow-agent-topline">
                      <span className="workflow-agent-id">{agent.id}</span>
                      <span className="workflow-agent-source">
                        {showStances && stanceSignal && stanceSignal.stance !== 'unknown' && (
                          <span className={`workflow-agent-vote is-${stanceSignal.stance}`} title={`${stanceLabels[stanceSignal.stance]} · ${confidenceLabels[stanceSignal.confidence]}${stanceSignal.changed ? ' · 观点发生变化' : ''}`}>
                            {stanceLabels[stanceSignal.stance]}{stanceSignal.changed ? '↻' : ''}
                          </span>
                        )}
                        <em className={`is-${agent.connection?.kind || 'orchestra'}`} title={agent.connection?.kind === 'external_http' ? '外部 Agent' : agent.connection?.kind === 'openai_compatible' ? `独立模型 · ${agent.connection.model || ''}` : 'Orchestra'}><ConnectionIcon size={10} /></em>
                      </span>
                    </span>
                    <strong>{agent.name}</strong>
                    <span className="workflow-agent-focus">{latestTool || agent.focus}</span>
                    <span className="workflow-agent-metrics">
                      <span className={`is-${status}`}><i />{statusLabel[status]}</span>
                      <span title="执行时长"><Clock3 size={9} />{elapsedLabel(runtime, now)}</span>
                      <span title="工具调用"><Wrench size={9} />{runtime?.tools.length || 0}</span>
                      <span title="证据数量"><Database size={9} />{runtime?.evidence.length || 0}</span>
                    </span>
                    {showArtifacts && artifacts.length > 0 && <b>{artifacts.length}</b>}
                  </button>
                  <button type="button" className={`workflow-agent-focus-action ${isFocused ? 'is-active' : ''}`} onClick={() => isFocused ? setFocusedAgentId(null) : focusAgent(agent)} aria-label={`${isFocused ? '退出聚焦' : '聚焦'} ${agent.name}`} title={`${isFocused ? '退出聚焦' : '聚焦'} ${agent.name}`}><Focus size={12} /></button>
                  <button type="button" className="workflow-agent-drag-action" onPointerDown={(event) => beginAgentDrag(event, agent)} aria-label={`拖动 ${agent.name}`} title="拖动并固定席位"><GripVertical size={12} /></button>
                  <button type="button" className={`workflow-agent-pin-action ${isPinned ? 'is-active' : ''}`} onClick={() => togglePinnedAgent(agent)} aria-label={`${isPinned ? '取消固定' : '固定'} ${agent.name}`} title={isPinned ? '取消固定席位' : '固定当前席位'}>{isPinned ? <PinOff size={11} /> : <Pin size={11} />}</button>

                  {showThinking && status === 'working' && runtime?.thinking && !isDimmed && <div className="workflow-thinking-stream" role="status" aria-live="polite"><span><i /> THINKING STREAM {telemetry[agent.id]?.eventCount ? `#${telemetry[agent.id].eventCount}` : ''}</span><strong>{runtime.thinking}</strong></div>}
                </div>
              );
            })}

            <div className={`workflow-brain ${brainActive ? 'is-active' : ''} ${phaseIndex > 4 ? 'is-complete' : ''}`} style={{ left: layout.points.collectiveBrain.x, top: layout.points.collectiveBrain.y }}>
              {showArtifacts && <div className="workflow-brain-memories" aria-label="智脑阶段成果">{brainMemories.map((memory, index) => <div key={memory.label} style={{ '--memory-index': index, animationDelay: `${index * 85}ms` } as React.CSSProperties}><span>{memory.label}</span><strong>{memory.value}</strong></div>)}</div>}
              <span className="workflow-brain-ring ring-one" aria-hidden="true" /><span className="workflow-brain-ring ring-two" aria-hidden="true" /><span className="workflow-brain-ring ring-three" aria-hidden="true" />
              {brainActive && <div className="workflow-brain-evidence-orbit" aria-hidden="true">{[0, 1, 2, 3, 4, 5].map((dot) => <span key={dot} style={{ '--dot-angle': `${dot * 60}deg`, '--dot-delay': `${dot * -0.32}s` } as React.CSSProperties} />)}</div>}
              <div className="workflow-brain-image" aria-hidden="true"><BrainCircuit size={82} strokeWidth={1.25} /></div><strong>群体 AI 智脑</strong><span>{orchestraThinking || `${researchComplete + pmComplete}/${agents.length} 份成果已汇入`}</span>
            </div>

            <div className={`workflow-decision ${decisionActive ? 'is-active' : ''} ${decision ? 'is-complete' : ''}`} style={{ left: layout.points.decision.x, top: layout.points.decision.y }}>
              {showArtifacts && decision && <div className="workflow-decision-pages" aria-hidden="true"><span /><span /><span /></div>}<FileCheck2 size={21} /><div><strong>投决结论</strong><span>{decision ? '决议已生成' : '等待收敛'}</span></div>
            </div>
          </div>
        </div>
      </div>

      <div className={`workflow-replay-dock ${replayEventIndex === null ? 'is-live' : 'is-replaying'}`} aria-label="运行回放控制台">
        {replayEventIndex === null ? (
          <>
            <button type="button" onClick={startReplay} disabled={replayFrames.length === 0} aria-label="从头回放运行" title="从头回放运行"><Rewind size={15} /></button>
            <span className="workflow-replay-live"><Radio size={11} />实时</span>
            <small>{events.length > 0 ? `${events.length} 条可审计事件` : '等待运行事件'}</small>
          </>
        ) : (
          <>
            <button type="button" onClick={() => onReplayEventIndexChange(null)} aria-label="返回实时状态" title="返回实时状态"><Radio size={15} /></button>
            <button type="button" onClick={() => jumpReplayKey(-1)} disabled={!replayFrames.slice(0, selectedReplayFramePosition).some((frame) => frame.isKey)} aria-label="上一个关键事件" title="上一个关键事件"><SkipBack size={14} /></button>
            <button type="button" className="workflow-replay-play" onClick={() => setIsReplayPlaying((value) => !value)} aria-label={isReplayPlaying ? '暂停回放' : '继续回放'} title={isReplayPlaying ? '暂停回放' : '继续回放'}>{isReplayPlaying ? <Pause size={14} /> : <Play size={14} />}</button>
            <button type="button" onClick={() => jumpReplayKey(1)} disabled={!replayFrames.slice(selectedReplayFramePosition + 1).some((frame) => frame.isKey)} aria-label="下一个关键事件" title="下一个关键事件"><SkipForward size={14} /></button>
            <div className="workflow-replay-event">
              <span><b>#{selectedReplayFrame?.seq || 0}</b>{replayActor} · {selectedReplayFrame?.label || '准备回放'}</span>
              <time>{selectedReplayFrame ? new Date(selectedReplayFrame.createdAt).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--'}</time>
            </div>
            <input
              type="range"
              min="0"
              max={Math.max(0, replayFrames.length - 1)}
              value={Math.max(0, selectedReplayFramePosition)}
              onChange={(event) => {
                setIsReplayPlaying(false);
                const frame = replayFrames[Number(event.target.value)];
                if (frame) onReplayEventIndexChange(frame.eventIndex);
              }}
              aria-label="运行回放时间轴"
            />
            <div className="workflow-replay-speed" aria-label="回放速度">
              {[1, 2, 4].map((rate) => <button type="button" key={rate} className={playbackRate === rate ? 'is-active' : ''} onClick={() => setPlaybackRate(rate)} aria-label={`${rate}倍速`}>{rate}x</button>)}
            </div>
          </>
        )}
      </div>

      <div className="workflow-minimap" aria-label="画布小地图" role="navigation">
        <svg viewBox={`0 0 ${MINI_WIDTH} ${MINI_HEIGHT}`} onPointerDown={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          scrollToWorld({ x: ((event.clientX - rect.left) / rect.width) * CANVAS_WIDTH, y: ((event.clientY - rect.top) / rect.height) * layout.canvasHeight });
        }}>
          {layout.zones.map((zone) => <rect key={zone.group} className={`mini-${zone.className}`} x={zone.x * minimapScaleX} y={zone.y * minimapScaleY} width={zone.width * minimapScaleX} height={zone.height * minimapScaleY} rx="2" />)}
          {layout.visibleAgents.map((agent) => { const point = layout.points[agent.id]; return <circle key={agent.id} className={`${groupClass[agent.group] || ''} ${focusedAgentId === agent.id ? 'is-focused' : ''}`} cx={point.x * minimapScaleX} cy={point.y * minimapScaleY} r={focusedAgentId === agent.id ? 2.8 : 1.7} />; })}
          {layout.summaries.map((summary) => <rect key={summary.group} x={summary.point.x * minimapScaleX - 3} y={summary.point.y * minimapScaleY - 2} width="6" height="4" rx="1" />)}
          <rect className="workflow-minimap-viewport" x={(viewport.left / zoom) * minimapScaleX} y={(viewport.top / zoom) * minimapScaleY} width={Math.min(MINI_WIDTH, (viewport.width / zoom) * minimapScaleX)} height={Math.min(MINI_HEIGHT, (viewport.height / zoom) * minimapScaleY)} rx="2" />
        </svg>
      </div>

      <div className="workflow-controls" aria-label="画布缩放">
        <button type="button" onClick={() => setZoomAround(zoom - 0.06)} aria-label="缩小"><ZoomOut size={16} /></button><span>{Math.round(zoom * 100)}%</span><button type="button" onClick={() => setZoomAround(zoom + 0.06)} aria-label="放大"><ZoomIn size={16} /></button><button type="button" onClick={fitCanvas} aria-label="适应画布"><Maximize2 size={15} /></button>
      </div>
    </div>
  );
};

export default WorkflowCanvas;
