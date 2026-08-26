import { useCallback, useEffect, useRef, useState } from 'react';
import {
  cancelCommitteeRun,
  createCommitteeRun,
  getAgents,
  getCurrentUser,
  getUsers,
  createUser,
  createAuthSession,
  deleteAuthSession,
  getCommitteeRun,
  getCommitteeRunEvents,
  getCommitteeRuns,
  getRunArtifacts,
  getRunEvidence,
  getHealth,
  getSkillCatalog,
  getSystemOverview,
  getQueueJobs,
  getPortfolios,
  getSecrets,
  createPortfolio,
  getPortfolioDetail,
  createPortfolioTransaction,
  createPortfolioValuation,
  createSecret,
  deleteSecret,
  compareCommitteeRuns,
  reconsiderCommitteeRun,
  createAgentProfile,
  deleteAgentProfile,
  startAgentIntervention,
} from '@/services/orchestraApi';
import type {
  AgentProfile,
  AgentRuntime,
  DecisionEvent,
  ExecutionMode,
  HealthStatus,
  RunSnapshot,
  RunSummary,
  Portfolio,
  PortfolioDetail,
  CreatePortfolioTransactionPayload,
  CreatePortfolioValuationPayload,
  CreateUserResponse,
  QueueJob,
  RunComparison,
  RunArtifact,
  RunEvidence,
  SecretMetadata,
  SkillCatalogItem,
  SystemOverview,
  UserProfile,
  CreateAgentPayload,
  AgentInterventionAction,
} from '@/types/orchestra';

const EVENT_TYPES = [
  'run.started',
  'run.completed',
  'run.failed',
  'run.cancelled',
  'phase.started',
  'phase.completed',
  'orchestra.plan',
  'orchestra.consensus',
  'orchestra.decision',
  'agent.queued',
  'agent.started',
  'agent.output.delta',
  'agent.completed',
  'agent.failed',
  'agent.tool.started',
  'agent.tool.input',
  'agent.tool.completed',
  'agent.thinking',
  'agent.progress',
  'agent.report.section',
  'agent.skill.registered',
  'agent.skill.used',
  'agent.skill.required',
  'agent.evidence.recorded',
  'agent.intervention.requested',
  'agent.intervention.started',
  'agent.intervention.completed',
  'agent.intervention.failed',
  'run.recovered',
  'run.interrupted',
  'orchestra.agent.output.delta',
  'orchestra.agent.tool.started',
  'orchestra.agent.thinking',
  'orchestra.agent.tool.input',
  'orchestra.agent.tool.completed',
  'orchestra.agent.report.section',
  'data.foundation.started',
  'data.foundation.completed',
  'data.foundation.failed',
  'data.thinking',
  'data.tool.started',
  'data.tool.input',
  'data.tool.completed',
  'data.evidence.recorded',
  'data.report.section',
  'data.output.delta',
];

const emptyRuntime = (id: string): AgentRuntime => ({
  id,
  status: 'idle',
  phase: null,
  output: '',
  thinking: '',
  thinking_stage: null,
  thoughts: [],
  tools: [],
  required_skills: [],
  registered_skills: [],
  used_skills: [],
  evidence: [],
  started_at: null,
  completed_at: null,
  error: null,
});

const reduceSnapshotEvent = (current: RunSnapshot, event: DecisionEvent): RunSnapshot => {
  const next: RunSnapshot = {
    ...current,
    agents: { ...current.agents },
    updated_at: event.created_at,
    last_event_seq: Math.max(current.last_event_seq, event.seq),
  };
  const agentId = event.agent_id;
  if (agentId && event.type.startsWith('agent.')) {
    const runtime = { ...(next.agents[agentId] || emptyRuntime(agentId)) };
    if (event.type === 'agent.intervention.requested') {
      runtime.intervention_id = String(event.payload.intervention_id || '') || null;
      runtime.intervention_action = event.payload.action as AgentInterventionAction;
    }
    if (event.type === 'agent.queued') runtime.status = 'queued';
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
      runtime.intervention_id = String(event.payload.intervention_id || '') || null;
      runtime.intervention_action = event.payload.action as AgentInterventionAction;
      runtime.required_skills = Array.isArray(event.payload.required_skills)
        ? event.payload.required_skills.map(String)
        : runtime.required_skills;
    }
    if (event.type === 'agent.output.delta') {
      runtime.output += String(event.payload.delta || '');
    }
    if (event.type === 'agent.thinking') {
      const summary = String(event.payload.summary || '');
      runtime.thinking = summary;
      runtime.thinking_stage = String(event.payload.stage || '') || null;
      if (summary && runtime.thoughts.at(-1) !== summary) {
        runtime.thoughts = [...runtime.thoughts.slice(-3), summary];
      }
    }
    if (event.type === 'agent.progress') {
      runtime.thinking = String(event.payload.summary || runtime.thinking);
      runtime.thinking_stage = String(event.payload.stage || runtime.thinking_stage || '') || null;
    }
    if (event.type === 'agent.tool.started') {
      const tool = String(event.payload.tool || '');
      if (tool && !runtime.tools.includes(tool)) runtime.tools = [...runtime.tools, tool];
    }
    if (event.type === 'agent.skill.registered') {
      const skill = String(event.payload.skill || '');
      if (skill && !runtime.registered_skills.includes(skill)) {
        runtime.registered_skills = [...runtime.registered_skills, skill];
      }
    }
    if (event.type === 'agent.skill.required') {
      runtime.required_skills = Array.isArray(event.payload.skills)
        ? event.payload.skills.map(String)
        : [];
    }
    if (event.type === 'agent.skill.used') {
      const skill = String(event.payload.skill || '');
      if (skill && !runtime.used_skills.includes(skill)) {
        runtime.used_skills = [...runtime.used_skills, skill];
      }
    }
    if (event.type === 'agent.evidence.recorded') {
      const evidence = event.payload as AgentRuntime['evidence'][number];
      if (evidence.id && !runtime.evidence.some((item) => item.id === evidence.id)) {
        runtime.evidence = [...runtime.evidence, evidence];
      }
    }
    if (event.type === 'agent.completed') {
      runtime.status = 'completed';
      runtime.completed_at = event.created_at;
      runtime.output = String(event.payload.output || runtime.output);
    }
    if (event.type === 'agent.failed') {
      runtime.status = 'failed';
      runtime.completed_at = event.created_at;
      runtime.error = String(event.payload.error || '执行失败');
    }
    if (event.type === 'agent.intervention.completed') {
      runtime.status = 'completed';
      runtime.completed_at = event.created_at;
      runtime.output = String(event.payload.output || runtime.output);
      runtime.error = null;
    }
    if (event.type === 'agent.intervention.failed') {
      runtime.status = 'failed';
      runtime.completed_at = event.created_at;
      runtime.error = String(event.payload.error || '单席干预失败');
    }
    runtime.phase = event.phase;
    next.agents[agentId] = runtime;
  }
  if (event.type === 'run.started') next.status = 'running';
  if (event.type === 'run.completed') {
    next.status = 'completed';
    next.phase = 'completed';
  }
  if (event.type === 'run.failed') {
    next.status = 'failed';
    next.phase = 'failed';
    next.error = String(event.payload.error || '运行失败');
  }
  if (event.type === 'run.cancelled') {
    next.status = 'cancelled';
    next.phase = 'cancelled';
  }
  if (event.type === 'phase.started') next.phase = event.phase || next.phase;
  if (event.type === 'orchestra.plan') next.plan = String(event.payload.plan || '');
  if (event.type === 'orchestra.consensus') next.consensus = String(event.payload.consensus || '');
  if (event.type === 'orchestra.decision') next.decision = String(event.payload.decision || '');
  if (event.type === 'orchestra.agent.thinking') {
    next.orchestra_thinking = String(event.payload.summary || '');
    next.orchestra_thinking_stage = String(event.payload.stage || '') || null;
  }
  return next;
};

export const useCommitteeRun = () => {
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [events, setEvents] = useState<DecisionEvent[]>([]);
  const [artifacts, setArtifacts] = useState<RunArtifact[]>([]);
  const [runEvidence, setRunEvidence] = useState<RunEvidence[]>([]);
  const [recentRuns, setRecentRuns] = useState<RunSummary[]>([]);
  const [overview, setOverview] = useState<SystemOverview | null>(null);
  const [queueJobs, setQueueJobs] = useState<QueueJob[]>([]);
  const [skillCatalog, setSkillCatalog] = useState<SkillCatalogItem[]>([]);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [portfolioDetail, setPortfolioDetail] = useState<PortfolioDetail | null>(null);
  const [secrets, setSecrets] = useState<SecretMetadata[]>([]);
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const pendingEventsRef = useRef<DecisionEvent[]>([]);
  const eventFrameRef = useRef<number | null>(null);

  const closeStream = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  const discardPendingEvents = useCallback(() => {
    pendingEventsRef.current = [];
    if (eventFrameRef.current !== null) {
      window.cancelAnimationFrame?.(eventFrameRef.current);
      eventFrameRef.current = null;
    }
  }, []);

  const clearRunSelection = useCallback(() => {
    closeStream();
    discardPendingEvents();
    setSnapshot(null);
    setEvents([]);
    setArtifacts([]);
    setRunEvidence([]);
    setComparison(null);
    setError(null);
  }, [closeStream, discardPendingEvents]);

  const newRun = useCallback(() => {
    clearRunSelection();
    const url = new URL(window.location.href);
    url.pathname = '/';
    url.searchParams.set('workspace', 'committee');
    window.history.pushState({}, '', url);
  }, [clearRunSelection]);

  const refreshSnapshot = useCallback(async (runId: string) => {
    const next = await getCommitteeRun(runId);
    setSnapshot(next);
    return next;
  }, []);

  const refreshRunMaterials = useCallback(async (runId: string) => {
    const [nextArtifacts, nextEvidence] = await Promise.all([
      getRunArtifacts(runId).catch(() => []),
      getRunEvidence(runId).catch(() => []),
    ]);
    setArtifacts(nextArtifacts);
    setRunEvidence(nextEvidence);
    return { artifacts: nextArtifacts, evidence: nextEvidence };
  }, []);

  const refreshSystemData = useCallback(async () => {
    const [nextOverview, nextRuns, nextQueueJobs] = await Promise.all([
      getSystemOverview(),
      getCommitteeRuns(),
      getQueueJobs().catch(() => []),
    ]);
    setOverview(nextOverview);
    setRecentRuns(nextRuns);
    setQueueJobs(nextQueueJobs);
    return { overview: nextOverview, runs: nextRuns, queueJobs: nextQueueJobs };
  }, []);

  const refreshProfiles = useCallback(async () => {
    const [nextAgents, nextSkills, nextOverview] = await Promise.all([
      getAgents(),
      getSkillCatalog(),
      getSystemOverview(),
    ]);
    setAgents(nextAgents);
    setSkillCatalog(nextSkills);
    setOverview(nextOverview);
    return nextAgents;
  }, []);

  const refreshWorkspaceData = useCallback(async () => {
    const user = await getCurrentUser();
    const [nextPortfolios, nextSecrets, nextUsers] = await Promise.all([
      getPortfolios(),
      getSecrets(),
      user.role === 'owner' ? getUsers() : Promise.resolve([]),
    ]);
    setCurrentUser(user);
    setUsers(nextUsers);
    setPortfolios(nextPortfolios);
    setSecrets(nextSecrets);
    setPortfolioDetail((current) => (
      current && nextPortfolios.some((portfolio) => portfolio.id === current.portfolio.id)
        ? current
        : null
    ));
    return { user, portfolios: nextPortfolios, secrets: nextSecrets, users: nextUsers };
  }, []);

  useEffect(() => {
    let active = true;
    Promise.allSettled([
      getAgents(),
      getHealth(),
      getSystemOverview(),
      getCommitteeRuns(),
      getSkillCatalog(),
      getCurrentUser(),
      getPortfolios(),
      getSecrets(),
      getUsers().catch(() => []),
      getQueueJobs().catch(() => []),
    ])
      .then((results) => {
        if (!active) return;
        const [
          agentResult,
          healthResult,
          overviewResult,
          runsResult,
          skillsResult,
          userResult,
          portfoliosResult,
          secretsResult,
          usersResult,
          queueJobsResult,
        ] = results;

        if (agentResult.status === 'fulfilled') setAgents(agentResult.value);
        if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
        if (overviewResult.status === 'fulfilled') setOverview(overviewResult.value);
        if (runsResult.status === 'fulfilled') setRecentRuns(runsResult.value);
        if (skillsResult.status === 'fulfilled') setSkillCatalog(skillsResult.value);
        if (userResult.status === 'fulfilled') setCurrentUser(userResult.value);
        if (portfoliosResult.status === 'fulfilled') setPortfolios(portfoliosResult.value);
        if (secretsResult.status === 'fulfilled') setSecrets(secretsResult.value);
        if (usersResult.status === 'fulfilled') setUsers(usersResult.value);
        if (queueJobsResult.status === 'fulfilled') setQueueJobs(queueJobsResult.value);

        const criticalFailures = [
          ['Agent 名册', agentResult],
          ['服务状态', healthResult],
          ['历史运行', runsResult],
        ].filter(([, result]) => result.status === 'rejected');

        if (criticalFailures.length > 0) {
          setError(`核心数据加载失败：${criticalFailures.map(([label]) => label).join('、')}。请确认访问的是 127.0.0.1:3001。`);
        } else {
          setError(null);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      closeStream();
      discardPendingEvents();
    };
  }, [closeStream, discardPendingEvents]);

  const flushPendingEvents = useCallback(() => {
    if (eventFrameRef.current !== null) {
      window.cancelAnimationFrame?.(eventFrameRef.current);
      eventFrameRef.current = null;
    }
    const batch = pendingEventsRef.current.splice(0);
    if (batch.length === 0) return;
    setEvents((current) => {
      const known = new Set(current.map((item) => item.seq));
      const additions = batch.filter((event) => !known.has(event.seq));
      return additions.length > 0 ? [...current, ...additions].slice(-800) : current;
    });
    setSnapshot((current) => (
      current ? batch.reduce(reduceSnapshotEvent, current) : current
    ));
  }, []);

  const applyEvent = useCallback((event: DecisionEvent) => {
    pendingEventsRef.current.push(event);
    if (eventFrameRef.current !== null) return;
    if (typeof window.requestAnimationFrame === 'function') {
      eventFrameRef.current = window.requestAnimationFrame(flushPendingEvents);
    } else {
      eventFrameRef.current = window.setTimeout(flushPendingEvents, 16);
    }
  }, [flushPendingEvents]);

  const openStream = useCallback(
    (runId: string, after = 0) => {
      closeStream();
      const source = new EventSource(`/api/runs/${runId}/events?after=${after}`, {
        withCredentials: true,
      });
      let terminalEventReceived = false;
      eventSourceRef.current = source;
      const handler = (raw: Event) => {
        const message = raw as MessageEvent<string>;
        try {
          const event = JSON.parse(message.data) as DecisionEvent;
          applyEvent(event);
          if (['run.completed', 'run.failed', 'run.cancelled'].includes(event.type)) {
            terminalEventReceived = true;
            flushPendingEvents();
            setError(null);
            void Promise.all([
              refreshSnapshot(runId),
              refreshSystemData(),
              refreshRunMaterials(runId),
            ]).finally(closeStream);
          }
          if (['agent.intervention.completed', 'agent.intervention.failed'].includes(event.type)) {
            terminalEventReceived = true;
            flushPendingEvents();
            setError(event.type.endsWith('.failed') ? String(event.payload.error || '单席干预失败') : null);
            void Promise.all([
              refreshSnapshot(runId),
              refreshSystemData(),
              refreshRunMaterials(runId),
            ]).finally(closeStream);
          }
        } catch {
          setError('收到无法解析的运行事件。');
        }
      };
      EVENT_TYPES.forEach((type) => source.addEventListener(type, handler));
      source.onerror = () => {
        if (terminalEventReceived || source.readyState === EventSource.CLOSED) return;
        setError('实时事件连接中断，正在等待浏览器重连。');
      };
    },
    [applyEvent, closeStream, flushPendingEvents, refreshRunMaterials, refreshSnapshot, refreshSystemData],
  );

  const startRun = useCallback(
    async (topic: string, mode: ExecutionMode, portfolioId?: string | null) => {
      setError(null);
      discardPendingEvents();
      setEvents([]);
      setArtifacts([]);
      setRunEvidence([]);
      const response = await createCommitteeRun(topic, mode, portfolioId);
      const initialAgents = Object.fromEntries(agents.map((agent) => [agent.id, emptyRuntime(agent.id)]));
      const now = new Date().toISOString();
      setSnapshot({
        id: response.run_id,
        topic,
        mode,
        status: 'queued',
        phase: 'queued',
        created_at: now,
        updated_at: now,
        last_event_seq: 0,
        agents: initialAgents,
        plan: '',
        consensus: '',
        decision: '',
        orchestra_thinking: '',
        orchestra_thinking_stage: null,
        error: null,
        owner_id: currentUser?.id || 'local-user',
        portfolio_id: portfolioId || null,
        parent_run_id: null,
        revision: 1,
        revision_note: '',
        secret_refs: {},
      });
      window.history.pushState({}, '', `/runs/${response.run_id}`);
      openStream(response.run_id);
      void refreshSystemData();
    },
    [agents, currentUser?.id, discardPendingEvents, openStream, refreshSystemData],
  );

  const loadRun = useCallback(
    async (runId: string) => {
      closeStream();
      discardPendingEvents();
      setError(null);
      const [next, history, nextArtifacts, nextEvidence] = await Promise.all([
        getCommitteeRun(runId),
        getCommitteeRunEvents(runId).catch(() => []),
        getRunArtifacts(runId).catch(() => []),
        getRunEvidence(runId).catch(() => []),
      ]);
      setSnapshot(next);
      setEvents(history);
      setArtifacts(nextArtifacts);
      setRunEvidence(nextEvidence);
      if (window.location.pathname !== `/runs/${runId}`) {
        window.history.pushState({}, '', `/runs/${runId}`);
      }
      if (next.status === 'queued' || next.status === 'running') {
        openStream(runId, history.at(-1)?.seq || 0);
      }
      return next;
    },
    [closeStream, discardPendingEvents, openStream],
  );

  const cancelRun = useCallback(async () => {
    if (!snapshot) return;
    await cancelCommitteeRun(snapshot.id);
  }, [snapshot]);

  useEffect(() => {
    const routeRunId = window.location.pathname.match(/^\/runs\/([^/]+)$/)?.[1];
    if (routeRunId) {
      void loadRun(routeRunId).catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : '无法打开指定的历史运行');
      });
    }
    const handlePopState = () => {
      const nextRunId = window.location.pathname.match(/^\/runs\/([^/]+)$/)?.[1];
      if (nextRunId) {
        void loadRun(nextRunId).catch((reason: unknown) => {
          setError(reason instanceof Error ? reason.message : '无法打开指定的历史运行');
        });
      } else {
        clearRunSelection();
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [clearRunSelection, loadRun]);

  const reconsiderRun = useCallback(async (note: string) => {
    if (!snapshot) throw new Error('尚未选择运行');
    const response = await reconsiderCommitteeRun(snapshot.id, note, snapshot.mode);
    await loadRun(response.run_id);
    await refreshSystemData();
    return response;
  }, [loadRun, refreshSystemData, snapshot]);

  const interveneAgent = useCallback(async (
    agentId: string,
    action: AgentInterventionAction,
    instruction: string,
  ) => {
    if (!snapshot) throw new Error('尚未选择运行');
    if (snapshot.status === 'queued' || snapshot.status === 'running') {
      throw new Error('主投委会执行期间不能发起单席干预');
    }
    setError(null);
    const cursor = snapshot.last_event_seq;
    const response = await startAgentIntervention(
      snapshot.id,
      agentId,
      action,
      instruction.trim(),
    );
    openStream(snapshot.id, cursor);
    return response;
  }, [openStream, snapshot]);

  const compareRuns = useCallback(async (runIds: string[]) => {
    const result = await compareCommitteeRuns(runIds);
    setComparison(result);
    return result;
  }, []);

  const addPortfolio = useCallback(async (payload: {
    name: string;
    description: string;
    base_currency: string;
  }) => {
    const portfolio = await createPortfolio(payload);
    await refreshWorkspaceData();
    return portfolio;
  }, [refreshWorkspaceData]);

  const loadPortfolioDetail = useCallback(async (portfolioId: string) => {
    const detail = await getPortfolioDetail(portfolioId);
    setPortfolioDetail(detail);
    return detail;
  }, []);

  const addPortfolioTransaction = useCallback(async (
    portfolioId: string,
    payload: CreatePortfolioTransactionPayload,
  ) => {
    const transaction = await createPortfolioTransaction(portfolioId, payload);
    await Promise.all([loadPortfolioDetail(portfolioId), refreshWorkspaceData()]);
    return transaction;
  }, [loadPortfolioDetail, refreshWorkspaceData]);

  const addPortfolioValuation = useCallback(async (
    portfolioId: string,
    payload: CreatePortfolioValuationPayload,
  ) => {
    const valuation = await createPortfolioValuation(portfolioId, payload);
    await Promise.all([loadPortfolioDetail(portfolioId), refreshWorkspaceData()]);
    return valuation;
  }, [loadPortfolioDetail, refreshWorkspaceData]);

  const addUser = useCallback(async (
    name: string,
    role: UserProfile['role'],
  ): Promise<CreateUserResponse> => {
    const created = await createUser({ name, role });
    setUsers(await getUsers());
    return created;
  }, []);

  const login = useCallback(async (userId: string, apiToken: string) => {
    const session = await createAuthSession(userId, apiToken);
    closeStream();
    setSnapshot(null);
    setEvents([]);
    setPortfolioDetail(null);
    window.history.pushState({}, '', '/');
    await Promise.all([refreshWorkspaceData(), refreshSystemData()]);
    return session;
  }, [closeStream, refreshSystemData, refreshWorkspaceData]);

  const logout = useCallback(async () => {
    await deleteAuthSession();
    closeStream();
    setSnapshot(null);
    setEvents([]);
    setPortfolioDetail(null);
    window.history.pushState({}, '', '/');
    await Promise.all([refreshWorkspaceData(), refreshSystemData()]);
  }, [closeStream, refreshSystemData, refreshWorkspaceData]);

  const addSecret = useCallback(async (payload: {
    provider: SecretMetadata['provider'];
    label: string;
    value: string;
  }) => {
    const secret = await createSecret(payload);
    await refreshWorkspaceData();
    return secret;
  }, [refreshWorkspaceData]);

  const removeSecret = useCallback(async (secretId: string) => {
    await deleteSecret(secretId);
    await refreshWorkspaceData();
  }, [refreshWorkspaceData]);

  const addAgent = useCallback(async (payload: CreateAgentPayload) => {
    const created = await createAgentProfile(payload);
    await refreshProfiles();
    return created;
  }, [refreshProfiles]);

  const removeAgent = useCallback(async (agentId: string) => {
    await deleteAgentProfile(agentId);
    await refreshProfiles();
  }, [refreshProfiles]);

  return {
    agents,
    health,
    overview,
    queueJobs,
    skillCatalog,
    currentUser,
    users,
    portfolios,
    portfolioDetail,
    secrets,
    comparison,
    recentRuns,
    snapshot,
    events,
    artifacts,
    runEvidence,
    loading,
    error,
    setError,
    newRun,
    startRun,
    cancelRun,
    loadRun,
    refreshSystemData,
    refreshProfiles,
    refreshWorkspaceData,
    reconsiderRun,
    interveneAgent,
    compareRuns,
    addPortfolio,
    loadPortfolioDetail,
    addPortfolioTransaction,
    addPortfolioValuation,
    addUser,
    login,
    logout,
    addSecret,
    removeSecret,
    addAgent,
    removeAgent,
  };
};
