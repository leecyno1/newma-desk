import type {
  AgentProfile,
  AgentRuntime,
  DecisionEvent,
  EvidenceRecord,
  RunStatus,
} from '@/types/orchestra';

export type InvestmentStance = 'bullish' | 'cautious' | 'bearish' | 'abstain' | 'unknown';
export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'unknown';

export type ReportSignal = {
  stance: InvestmentStance;
  confidence: ConfidenceLevel;
  rawVote: string;
};

export type ReplayedRunState = {
  runtimes: Record<string, AgentRuntime>;
  phase: string;
  status: RunStatus;
  plan: string;
  consensus: string;
  decision: string;
  orchestraThinking: string;
  event: DecisionEvent | null;
};

export type ReplayFrame = {
  eventIndex: number;
  seq: number;
  createdAt: string;
  type: string;
  agentId: string | null;
  label: string;
  isKey: boolean;
};

export const stanceLabels: Record<InvestmentStance, string> = {
  bullish: '看多',
  cautious: '谨慎',
  bearish: '看空',
  abstain: '弃权',
  unknown: '待表态',
};

export const confidenceLabels: Record<ConfidenceLevel, string> = {
  high: '高置信',
  medium: '中置信',
  low: '低置信',
  unknown: '置信待核',
};

const REPLAY_PHASE_ORDER: Record<string, number> = {
  queued: 0,
  planning: 1,
  research: 2,
  deliberation: 3,
  convergence: 4,
  decision: 5,
  completed: 6,
  failed: 6,
  cancelled: 6,
  intervention: 7,
};

const voteFromText = (text: string) => {
  const match = text.match(/【投票】\s*([^\n\r]+)/);
  return match?.[1]?.trim() || '';
};

const stanceFromValue = (value: string): InvestmentStance => {
  const normalized = value.replace(/\s+/g, '');
  if (!normalized) return 'unknown';
  if (['bullish', 'cautious', 'bearish', 'abstain'].includes(normalized)) {
    return normalized as InvestmentStance;
  }
  if (/弃权|回避|不投票/.test(normalized)) return 'abstain';
  if (/有条件赞成|谨慎|中性|观望|小仓位/.test(normalized)) return 'cautious';
  if (/反对|看空|否决|减持|不配置/.test(normalized)) return 'bearish';
  if (/赞成|看多|支持|增持|超配/.test(normalized)) return 'bullish';
  return 'unknown';
};

const confidenceFromText = (text: string): ConfidenceLevel => {
  const match = text.match(/【置信度】\s*([^\n\r]+)/);
  const value = match?.[1] || '';
  if (/高/.test(value)) return 'high';
  if (/中/.test(value)) return 'medium';
  if (/低/.test(value)) return 'low';
  return 'unknown';
};

export const extractReportSignal = (text: string): ReportSignal => {
  const rawVote = voteFromText(text);
  return {
    stance: stanceFromValue(rawVote),
    confidence: confidenceFromText(text),
    rawVote,
  };
};

const emptyRuntime = (profile: AgentProfile): AgentRuntime => ({
  id: profile.id,
  status: 'idle',
  phase: null,
  output: '',
  thinking: '',
  thinking_stage: null,
  thoughts: [],
  tools: [],
  required_skills: [...profile.skills],
  registered_skills: [],
  used_skills: [],
  evidence: [],
  started_at: null,
  completed_at: null,
  error: null,
});

const pushUnique = (values: string[], value: unknown) => {
  const normalized = String(value || '').trim();
  if (normalized && !values.includes(normalized)) values.push(normalized);
};

const evidenceFromPayload = (payload: Record<string, unknown>): EvidenceRecord | null => {
  if (!payload.id || !payload.source_name || !payload.retrieved_at || !payload.tool_name) return null;
  return {
    id: String(payload.id),
    source_name: String(payload.source_name),
    source_url: payload.source_url ? String(payload.source_url) : null,
    observed_at: payload.observed_at ? String(payload.observed_at) : null,
    retrieved_at: String(payload.retrieved_at),
    tool_name: String(payload.tool_name),
    interface_name: payload.interface_name ? String(payload.interface_name) : null,
    params: payload.params && typeof payload.params === 'object'
      ? payload.params as Record<string, unknown>
      : {},
    status: String(payload.status || 'success'),
    excerpt: String(payload.excerpt || ''),
    content_hash: String(payload.content_hash || ''),
  };
};

export const replayRunAt = (
  agents: AgentProfile[],
  events: DecisionEvent[],
  throughEventIndex: number,
): ReplayedRunState => {
  const runtimes = Object.fromEntries(agents.map((profile) => [profile.id, emptyRuntime(profile)]));
  const limit = Math.min(events.length - 1, Math.max(-1, throughEventIndex));
  let phase = 'queued';
  let status: RunStatus = 'queued';
  let plan = '';
  let consensus = '';
  let decision = '';
  let orchestraThinking = '';
  let lastActivePhase = 'queued';
  let awaitingRecovery = false;

  const resetAttempt = () => {
    agents.forEach((profile) => {
      runtimes[profile.id] = emptyRuntime(profile);
    });
    status = 'running';
    plan = '';
    consensus = '';
    decision = '';
    orchestraThinking = '';
  };

  for (let index = 0; index <= limit; index += 1) {
    const event = events[index];
    const payload = event.payload || {};

    if (
      awaitingRecovery
      && event.phase
      && (REPLAY_PHASE_ORDER[event.phase] ?? 0) < (REPLAY_PHASE_ORDER[lastActivePhase] ?? 0)
    ) {
      resetAttempt();
      phase = event.phase;
      lastActivePhase = event.phase;
      awaitingRecovery = false;
    }

    if (event.type === 'run.started') {
      resetAttempt();
      phase = 'queued';
      lastActivePhase = 'queued';
      awaitingRecovery = false;
    }
    const runtime = event.agent_id ? runtimes[event.agent_id] : undefined;
    if (event.type === 'run.completed') {
      status = 'completed';
      phase = 'completed';
    }
    if (event.type === 'run.failed') {
      status = 'failed';
      phase = 'failed';
      awaitingRecovery = true;
    }
    if (event.type === 'run.cancelled') {
      status = 'cancelled';
      phase = 'cancelled';
    }
    if (event.type === 'run.interrupted') {
      status = 'queued';
      phase = 'queued';
    }
    if (event.type === 'phase.started' && event.phase) {
      phase = event.phase;
      lastActivePhase = event.phase;
    }
    if (event.type === 'orchestra.plan') plan = String(payload.plan || '');
    if (event.type === 'orchestra.consensus') consensus = String(payload.consensus || '');
    if (event.type === 'orchestra.decision') decision = String(payload.decision || '');
    if (event.type === 'orchestra.agent.thinking') {
      orchestraThinking = String(payload.summary || '');
    }

    if (!runtime) continue;
    if (event.phase) runtime.phase = event.phase;
    if (event.type === 'agent.skill.required' && Array.isArray(payload.skills)) {
      runtime.required_skills = payload.skills.map(String);
    }
    if (event.type === 'agent.queued') runtime.status = 'queued';
    if (event.type === 'agent.intervention.requested') {
      runtime.intervention_id = String(payload.intervention_id || '') || null;
      runtime.intervention_action = payload.action as AgentRuntime['intervention_action'];
    }
    if (event.type === 'agent.started') {
      runtime.status = 'working';
      runtime.started_at = event.created_at;
    }
    if (event.type === 'agent.intervention.started') {
      runtime.status = 'working';
      runtime.phase = 'intervention';
      runtime.output = '';
      runtime.error = null;
      runtime.started_at = event.created_at;
      runtime.completed_at = null;
      runtime.tools = [];
      runtime.registered_skills = [];
      runtime.used_skills = [];
      runtime.intervention_id = String(payload.intervention_id || '') || null;
      runtime.intervention_action = payload.action as AgentRuntime['intervention_action'];
      if (Array.isArray(payload.required_skills)) runtime.required_skills = payload.required_skills.map(String);
    }
    if (event.type === 'agent.thinking') {
      const summary = String(payload.summary || '');
      runtime.thinking = summary;
      runtime.thinking_stage = String(payload.stage || '') || null;
      if (summary && runtime.thoughts.at(-1) !== summary) runtime.thoughts.push(summary);
    }
    if (event.type === 'agent.progress') {
      const summary = String(payload.summary || '');
      if (summary) runtime.thinking = summary;
      runtime.thinking_stage = String(payload.stage || '') || runtime.thinking_stage;
    }
    if (event.type === 'agent.output.delta') runtime.output += String(payload.delta || '');
    if (event.type === 'agent.tool.started') pushUnique(runtime.tools, payload.tool);
    if (event.type === 'agent.skill.registered') pushUnique(runtime.registered_skills, payload.skill);
    if (event.type === 'agent.skill.used') pushUnique(runtime.used_skills, payload.skill);
    if (event.type === 'agent.evidence.recorded') {
      const evidence = evidenceFromPayload(payload);
      if (evidence && !runtime.evidence.some((item) => item.id === evidence.id)) runtime.evidence.push(evidence);
    }
    if (event.type === 'agent.completed') {
      runtime.status = 'completed';
      runtime.output = String(payload.output || runtime.output);
      runtime.completed_at = event.created_at;
    }
    if (event.type === 'agent.failed') {
      runtime.status = 'failed';
      runtime.error = String(payload.error || '执行失败');
      runtime.completed_at = event.created_at;
    }
    if (event.type === 'agent.intervention.completed') {
      runtime.status = 'completed';
      runtime.output = String(payload.output || runtime.output);
      runtime.error = null;
      runtime.completed_at = event.created_at;
    }
    if (event.type === 'agent.intervention.failed') {
      runtime.status = 'failed';
      runtime.error = String(payload.error || '单席干预失败');
      runtime.completed_at = event.created_at;
    }
  }

  return {
    runtimes,
    phase,
    status,
    plan,
    consensus,
    decision,
    orchestraThinking,
    event: limit >= 0 ? events[limit] : null,
  };
};

const KEY_EVENT_TYPES = new Set([
  'run.started',
  'run.completed',
  'run.failed',
  'run.cancelled',
  'phase.started',
  'phase.completed',
  'agent.started',
  'agent.completed',
  'agent.failed',
  'agent.intervention.requested',
  'agent.intervention.started',
  'agent.intervention.completed',
  'agent.intervention.failed',
  'agent.vote.recorded',
  'orchestra.consensus',
  'orchestra.decision',
]);

const eventLabel = (event: DecisionEvent) => {
  if (event.type === 'run.started') return '投委会开始';
  if (event.type === 'run.completed') return '投委会完成';
  if (event.type === 'run.failed') return '运行异常';
  if (event.type === 'run.cancelled') return '运行停止';
  if (event.type === 'phase.started') return String(event.payload.label || '阶段开始');
  if (event.type === 'phase.completed') return '阶段完成';
  if (event.type === 'agent.queued') return '进入调度队列';
  if (event.type === 'agent.started') return '开始执行';
  if (event.type === 'agent.completed') return '成果已沉淀';
  if (event.type === 'agent.failed') return '执行异常';
  if (event.type === 'agent.intervention.requested') return '人类干预已提交';
  if (event.type === 'agent.intervention.started') return '单席干预开始';
  if (event.type === 'agent.intervention.completed') return '增量报告已沉淀';
  if (event.type === 'agent.intervention.failed') return '单席干预异常';
  if (event.type === 'agent.tool.started') return `调用 ${String(event.payload.tool || '工具')}`;
  if (event.type === 'agent.skill.used') return `使用 ${String(event.payload.skill || 'Skill')}`;
  if (event.type === 'agent.evidence.recorded') return '证据已记录';
  if (event.type === 'agent.vote.recorded') return '经理完成投票';
  if (event.type === 'orchestra.consensus') return '分歧收敛完成';
  if (event.type === 'orchestra.decision') return '正式决议生成';
  if (event.type.endsWith('thinking')) return '分析路径更新';
  if (event.type.endsWith('report.section')) return '报告章节生成';
  if (event.type.endsWith('output.delta')) return '报告流式生成';
  if (event.type === 'agent.progress') return '执行进度更新';
  return event.type;
};

export const buildReplayFrames = (events: DecisionEvent[]): ReplayFrame[] => {
  const frames: ReplayFrame[] = [];
  const outputCounts = new Map<string, number>();
  const progressCounts = new Map<string, number>();
  let lastActivePhase = 'queued';
  let awaitingRecovery = false;

  events.forEach((event, eventIndex) => {
    const actor = event.agent_id || event.type.split('.')[0];
    const isRecovery = Boolean(
      awaitingRecovery
      && event.phase
      && (REPLAY_PHASE_ORDER[event.phase] ?? 0) < (REPLAY_PHASE_ORDER[lastActivePhase] ?? 0),
    );
    if (isRecovery && event.phase) {
      lastActivePhase = event.phase;
      awaitingRecovery = false;
    }
    if (event.type === 'phase.started' && event.phase) lastActivePhase = event.phase;
    if (event.type === 'run.started') {
      lastActivePhase = 'queued';
      awaitingRecovery = false;
    }
    if (event.type === 'run.failed') awaitingRecovery = true;

    let include = isRecovery || KEY_EVENT_TYPES.has(event.type)
      || event.type === 'agent.queued'
      || event.type === 'agent.tool.started'
      || event.type === 'agent.tool.completed'
      || event.type === 'agent.skill.used'
      || event.type === 'agent.evidence.recorded'
      || event.type.endsWith('thinking')
      || event.type.endsWith('report.section');

    if (event.type.endsWith('output.delta')) {
      const count = (outputCounts.get(actor) || 0) + 1;
      outputCounts.set(actor, count);
      include = count === 1 || count % 30 === 0;
    }
    if (event.type === 'agent.progress') {
      const count = (progressCounts.get(actor) || 0) + 1;
      progressCounts.set(actor, count);
      include = count === 1 || count % 3 === 0;
    }
    if (!include) return;
    frames.push({
      eventIndex,
      seq: event.seq,
      createdAt: event.created_at,
      type: event.type,
      agentId: event.agent_id,
      label: isRecovery ? '恢复执行' : eventLabel(event),
      isKey: isRecovery || KEY_EVENT_TYPES.has(event.type),
    });
  });

  if (events.length > 0 && frames.at(-1)?.eventIndex !== events.length - 1) {
    const event = events.at(-1)!;
    frames.push({
      eventIndex: events.length - 1,
      seq: event.seq,
      createdAt: event.created_at,
      type: event.type,
      agentId: event.agent_id,
      label: eventLabel(event),
      isKey: KEY_EVENT_TYPES.has(event.type),
    });
  }
  return frames;
};

export const stanceHistoryFor = (
  events: DecisionEvent[],
  agentId: string,
  throughEventIndex = events.length - 1,
) => {
  const history: Array<{ seq: number; stance: InvestmentStance }> = [];
  let output = '';
  let lastActivePhase = 'queued';
  let awaitingRecovery = false;
  const record = (seq: number, stance: InvestmentStance) => {
    if (stance === 'unknown' || history.at(-1)?.stance === stance) return;
    history.push({ seq, stance });
  };

  for (let index = 0; index <= Math.min(throughEventIndex, events.length - 1); index += 1) {
    const event = events[index];
    const isRecovery = Boolean(
      awaitingRecovery
      && event.phase
      && (REPLAY_PHASE_ORDER[event.phase] ?? 0) < (REPLAY_PHASE_ORDER[lastActivePhase] ?? 0),
    );
    if (event.type === 'run.started' || isRecovery) {
      history.length = 0;
      output = '';
      awaitingRecovery = false;
      lastActivePhase = event.phase || 'queued';
    }
    if (event.type === 'phase.started' && event.phase) lastActivePhase = event.phase;
    if (event.type === 'run.failed') awaitingRecovery = true;
    if (event.agent_id !== agentId) continue;
    if (event.type === 'agent.intervention.started') output = '';
    if (event.type === 'agent.output.delta') output += String(event.payload.delta || '');
    if (event.type === 'agent.completed') output = String(event.payload.output || output);
    if (event.type === 'agent.intervention.completed') output = String(event.payload.output || output);
    if (event.type === 'agent.vote.recorded') {
      record(event.seq, stanceFromValue(String(event.payload.stance || event.payload.vote || '')));
    } else if (event.type === 'agent.output.delta' || event.type === 'agent.completed' || event.type === 'agent.intervention.completed') {
      record(event.seq, extractReportSignal(output).stance);
    }
  }
  return history;
};
