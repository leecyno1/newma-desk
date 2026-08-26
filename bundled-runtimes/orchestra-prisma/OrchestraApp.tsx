import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  BookOpen,
  BriefcaseBusiness,
  Database,
  History,
  Layers3,
  Network,
  Play,
  Plus,
  RotateCcw,
  Settings2,
  Square,
  UsersRound,
} from 'lucide-react';
import AgentDrawer from '@/components/orchestra/AgentDrawer';
import IntelligenceRail from '@/components/orchestra/IntelligenceRail';
import NavigationPanel, { type NavigationView } from '@/components/orchestra/NavigationPanel';
import ReportReader from '@/components/orchestra/ReportReader';
import StageTimeline from '@/components/orchestra/StageTimeline';
import WorkflowCanvas from '@/components/orchestra/WorkflowCanvas';
import { useCommitteeRun } from '@/hooks/useCommitteeRun';
import { useOrchestraWorkspace } from '@/hooks/useOrchestraWorkspace';
import { buildOrchestraPageContext, useVibeDeskBridge } from '@/hooks/useVibeDeskBridge';
import { getCommitteeRunReplayEvents, runExportUrl, updateAgentProfile } from '@/services/orchestraApi';
import type { AgentProfile, DecisionEvent, ExecutionMode, ProfileUpdate, RunArtifact, RunSnapshot } from '@/types/orchestra';
import { runningStateLabel } from '@/utils/orchestraStatus';
import { replayRunAt } from '@/utils/orchestraReplay';

const phaseLabels: Record<string, string> = {
  queued: '待命',
  planning: '议题拆解',
  research: '独立研究',
  deliberation: '经理审议',
  convergence: '分歧收敛',
  decision: '主席决议',
  completed: '已完成',
  failed: '执行失败',
  cancelled: '已停止',
};

const navigationItems: Array<{
  view: NavigationView;
  label: string;
  icon: typeof Activity;
}> = [
  { view: 'committee', label: '投委会', icon: Activity },
  { view: 'history', label: '历史讨论', icon: History },
  { view: 'reports', label: '研究成果', icon: BookOpen },
  { view: 'agents', label: '研究席位', icon: UsersRound },
  { view: 'skills', label: 'Skills', icon: Layers3 },
  { view: 'data', label: '数据工具', icon: Database },
  { view: 'workspace', label: '账户与组合', icon: BriefcaseBusiness },
  { view: 'settings', label: '运行设置', icon: Settings2 },
];

const OrchestraApp = () => {
  const {
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
  } = useCommitteeRun();
  const [topic, setTopic] = useState('');
  const [mode, setMode] = useState<ExecutionMode>('demo');
  const [selectedAgent, setSelectedAgent] = useState<AgentProfile | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState<RunArtifact | null>(null);
  const { workspace, activePanel, setActivePanel } = useOrchestraWorkspace();
  const [showThinking, setShowThinking] = useState(true);
  const [showArtifacts, setShowArtifacts] = useState(true);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string>('');
  const [replayEventIndex, setReplayEventIndex] = useState<number | null>(null);
  const [replayEvents, setReplayEvents] = useState<DecisionEvent[] | null>(null);
  const syncedRunIdRef = useRef<string | null>(null);
  const isRunning = snapshot?.status === 'queued' || snapshot?.status === 'running';

  useEffect(() => {
    if (!snapshot || syncedRunIdRef.current === snapshot.id) return;
    syncedRunIdRef.current = snapshot.id;
    setTopic(snapshot.topic);
    setMode(snapshot.mode);
    setSelectedPortfolioId(snapshot.portfolio_id || '');
    setReplayEventIndex(null);
    setReplayEvents(null);
  }, [snapshot]);

  useEffect(() => {
    if (selectedPortfolioId && portfolios.length > 0 && !portfolios.some((portfolio) => portfolio.id === selectedPortfolioId)) {
      setSelectedPortfolioId('');
    }
  }, [portfolios, selectedPortfolioId]);

  const statusCounts = useMemo(() => {
    const values = Object.values(snapshot?.agents || {});
    return {
      working: values.filter((item) => item.status === 'working').length,
      completed: values.filter((item) => item.status === 'completed').length,
      failed: values.filter((item) => item.status === 'failed').length,
    };
  }, [snapshot]);

  const displayArtifacts = useMemo(() => {
    const result = [...artifacts];
    agents.forEach((agent) => {
      const output = snapshot?.agents[agent.id]?.output;
      if (!output) return;
      const recordedIndex = result.findIndex((artifact) => artifact.agent_id === agent.id);
      if (recordedIndex >= 0 && result[recordedIndex].content.trim()) return;
      if (recordedIndex >= 0) {
        result[recordedIndex] = {
          ...result[recordedIndex],
          content: output,
          title: `${agent.id} ${agent.name} 阶段成果`,
          created_at: snapshot?.updated_at || result[recordedIndex].created_at,
        };
        return;
      }
      result.push({
        id: `${snapshot?.id || 'current'}-${agent.id}-runtime`,
        run_id: snapshot?.id || 'current',
        agent_id: agent.id,
        kind: agent.group === '基金经理组' ? 'deliberation_report' : 'research_report',
        title: `${agent.id} ${agent.name} 阶段成果`,
        content: output,
        version: snapshot?.revision || 1,
        created_at: snapshot?.updated_at || new Date().toISOString(),
      });
    });
    if (snapshot?.consensus && !result.some((artifact) => artifact.kind === 'consensus')) {
      result.push({
        id: `${snapshot.id}-consensus-runtime`,
        run_id: snapshot.id,
        agent_id: null,
        kind: 'consensus',
        title: '分歧收敛纪要',
        content: snapshot.consensus,
        version: snapshot.revision,
        created_at: snapshot.updated_at,
      });
    }
    if (snapshot?.decision && !result.some((artifact) => artifact.kind === 'decision')) {
      result.push({
        id: `${snapshot.id}-decision-runtime`,
        run_id: snapshot.id,
        agent_id: null,
        kind: 'decision',
        title: '正式投委会决议',
        content: snapshot.decision,
        version: snapshot.revision,
        created_at: snapshot.updated_at,
      });
    }
    return result;
  }, [agents, artifacts, snapshot]);

  const timelineEvents = replayEvents || events;
  const replayedState = useMemo(
    () => replayEventIndex === null ? null : replayRunAt(agents, timelineEvents, replayEventIndex),
    [agents, replayEventIndex, timelineEvents],
  );
  const visibleSnapshot = useMemo<RunSnapshot | null>(() => {
    if (!snapshot || !replayedState) return snapshot;
    return {
      ...snapshot,
      status: replayedState.status,
      phase: replayedState.phase,
      agents: replayedState.runtimes,
      plan: replayedState.plan,
      consensus: replayedState.consensus,
      decision: replayedState.decision,
      orchestra_thinking: replayedState.orchestraThinking,
      updated_at: replayedState.event?.created_at || snapshot.updated_at,
      last_event_seq: replayedState.event?.seq || 0,
    };
  }, [replayedState, snapshot]);
  const visibleEvents = useMemo(
    () => replayEventIndex === null ? events : timelineEvents.slice(0, replayEventIndex + 1),
    [events, replayEventIndex, timelineEvents],
  );

  const selectedPortfolio = useMemo(
    () => portfolios.find((portfolio) => portfolio.id === selectedPortfolioId) ?? null,
    [portfolios, selectedPortfolioId],
  );
  const pageContext = useMemo(() => buildOrchestraPageContext({
    workspace,
    topic,
    mode,
    snapshot,
    health,
    selectedPortfolio,
    selectedAgentId: selectedAgent?.id,
    selectedArtifactId: selectedArtifact?.id,
    eventCount: events.length,
    artifactCount: displayArtifacts.length,
    showThinking,
    showArtifacts,
  }), [
    workspace,
    topic,
    mode,
    snapshot,
    health,
    selectedPortfolio,
    selectedAgent?.id,
    selectedArtifact?.id,
    events.length,
    displayArtifacts.length,
    showThinking,
    showArtifacts,
  ]);
  useVibeDeskBridge(workspace, pageContext);

  useEffect(() => {
    if (selectedArtifact && snapshot && selectedArtifact.run_id !== snapshot.id) setSelectedArtifact(null);
  }, [selectedArtifact, snapshot]);

  const handleStart = async () => {
    if (!topic.trim() || isRunning) return;
    try {
      setReplayEventIndex(null);
      setReplayEvents(null);
      await startRun(topic.trim(), mode, selectedPortfolioId || null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '启动失败');
    }
  };

  const handleNewTask = () => {
    if (isRunning) return;
    newRun();
    syncedRunIdRef.current = null;
    setTopic('');
    setMode(health?.default_mode || 'demo');
    setSelectedPortfolioId('');
    setSelectedAgent(null);
    setSelectedArtifact(null);
    setReplayEventIndex(null);
    setReplayEvents(null);
    setActivePanel(null);
  };

  const handleLoadRun = async (runId: string) => {
    try {
      setReplayEventIndex(null);
      setReplayEvents(null);
      const next = await loadRun(runId);
      setTopic(next.topic);
      setMode(next.mode);
      setSelectedPortfolioId(next.portfolio_id || '');
      if (activePanel !== 'history') setActivePanel(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法打开历史运行');
    }
  };

  const handleSelectAgent = (agent: AgentProfile) => {
    setSelectedAgent(agent);
    setActivePanel(null);
  };

  const handleOpenArtifact = (artifact: RunArtifact) => {
    setSelectedArtifact(artifact);
    setSelectedAgent(null);
    setActivePanel(null);
  };

  const handleSelectPortfolio = async (portfolioId: string) => {
    setSelectedPortfolioId(portfolioId);
    await loadPortfolioDetail(portfolioId);
  };

  const handleSaveProfile = async (agentId: string, updates: ProfileUpdate) => {
    const updated = await updateAgentProfile(agentId, updates);
    await refreshProfiles();
    setSelectedAgent(updated);
    return updated;
  };

  const handleDeleteProfile = async (agentId: string) => {
    await removeAgent(agentId);
    setSelectedAgent(null);
  };

  const handleReconsider = async (note: string) => {
    try {
      const response = await reconsiderRun(note);
      setActivePanel(null);
      return response;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建复议版本失败');
      throw reason;
    }
  };

  const handleExport = (format: 'pdf' | 'docx') => {
    if (!snapshot) return;
    window.open(runExportUrl(snapshot.id, format), '_blank', 'noopener,noreferrer');
  };

  const handleReplayEventIndexChange = (eventIndex: number | null) => {
    if (eventIndex === null) {
      setReplayEventIndex(null);
      return;
    }
    if (replayEvents || !snapshot) {
      setReplayEventIndex(eventIndex);
      return;
    }
    setReplayEventIndex(0);
    void getCommitteeRunReplayEvents(snapshot.id)
      .then((nextEvents) => {
        setReplayEvents(nextEvents);
        setReplayEventIndex(nextEvents.length > 0 ? 0 : null);
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : '无法载入运行回放');
      });
  };

  return (
    <div className="orchestra-shell">
      <aside className="orchestra-rail" aria-label="主导航">
        <div className="orchestra-mark" title="Orchestra">
          <Network size={21} />
        </div>
        <nav>
          {navigationItems.map((item) => {
            const Icon = item.icon;
            const isActive = activePanel === item.view || (!activePanel && item.view === 'committee');
            return (
              <button
                key={item.view}
                className={isActive ? 'is-active' : ''}
                type="button"
                aria-label={item.label}
                aria-expanded={activePanel === item.view}
                title={item.label}
                onClick={() => setActivePanel((current) => current === item.view ? null : item.view)}
              >
                <Icon size={19} />
              </button>
            );
          })}
        </nav>
        <div className="orchestra-rail-health" title={health ? '服务已连接' : '服务未连接'}>
          <span className={health ? 'is-online' : ''} />
        </div>
      </aside>

      <main className="orchestra-workspace">
        <header className="orchestra-commandbar">
          <div className="orchestra-wordmark">
            <strong>Orchestra</strong>
            <span>INVESTMENT OS</span>
          </div>
          <label className="orchestra-topic-field">
            <span>议题</span>
            <input
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              aria-label="投委会议题"
              placeholder="输入新的投委会议题"
            />
          </label>
          <div className="orchestra-command-actions">
            <button
              className="orchestra-new-task"
              type="button"
              onClick={handleNewTask}
              disabled={isRunning}
              title={isRunning ? '请先停止当前任务' : '新建空白投委会任务'}
            >
              <Plus size={15} />
              新建任务
            </button>
            <label className="orchestra-portfolio-select" title="基金组合">
              <BriefcaseBusiness size={14} />
              <select value={selectedPortfolioId} onChange={(event) => {
                const portfolioId = event.target.value;
                setSelectedPortfolioId(portfolioId);
                if (portfolioId) void loadPortfolioDetail(portfolioId);
              }} aria-label="基金组合">
                <option value="">未绑定组合</option>
                {portfolios.map((portfolio) => <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>)}
              </select>
            </label>
            <div className="orchestra-mode" role="group" aria-label="执行模式">
              <button
                type="button"
                className={mode === 'demo' ? 'is-active' : ''}
                onClick={() => setMode('demo')}
              >
                推演
              </button>
              <button
                type="button"
                className={mode === 'live' ? 'is-active' : ''}
                disabled={!health?.live_ready}
                onClick={() => setMode('live')}
              >
                真实
              </button>
            </div>
            <div className={`orchestra-run-state ${isRunning ? 'is-running' : ''}`}>
              <span />
              {isRunning
                ? runningStateLabel(snapshot?.phase, statusCounts.working)
                : phaseLabels[snapshot?.phase || 'queued']}
            </div>
            {isRunning ? (
              <button className="orchestra-stop" type="button" onClick={() => void cancelRun()}>
                <Square size={15} fill="currentColor" />
                停止
              </button>
            ) : (
              <button
                className="orchestra-launch"
                type="button"
                onClick={() => void handleStart()}
                disabled={loading || !topic.trim()}
              >
                {snapshot?.status === 'completed' ? <RotateCcw size={16} /> : <Play size={16} />}
                {snapshot?.status === 'completed' ? '重新运行' : '启动投决会'}
              </button>
            )}
          </div>
        </header>

        {error && (
          <button className="orchestra-alert" type="button" onClick={() => setError(null)}>
            {error}
          </button>
        )}

        {activePanel && (
          <NavigationPanel
            key={activePanel}
            view={activePanel}
            agents={agents}
            skillCatalog={skillCatalog}
            runtimes={snapshot?.agents || {}}
            snapshot={snapshot}
            events={events}
            artifacts={displayArtifacts}
            recentRuns={recentRuns}
            health={health}
            overview={overview}
            queueJobs={queueJobs}
            currentUser={currentUser}
            users={users}
            portfolios={portfolios}
            selectedPortfolioId={selectedPortfolioId}
            portfolioDetail={portfolioDetail}
            secrets={secrets}
            comparison={comparison}
            mode={mode}
            showThinking={showThinking}
            showArtifacts={showArtifacts}
            onModeChange={setMode}
            onShowThinkingChange={setShowThinking}
            onShowArtifactsChange={setShowArtifacts}
            onSelectAgent={handleSelectAgent}
            onSelectRun={(runId) => void handleLoadRun(runId)}
            onOpenArtifact={handleOpenArtifact}
            onRefresh={refreshSystemData}
            onReconsider={handleReconsider}
            onCompareRuns={compareRuns}
            onCreatePortfolio={addPortfolio}
            onSelectPortfolio={handleSelectPortfolio}
            onCreateTransaction={addPortfolioTransaction}
            onCreateValuation={addPortfolioValuation}
            onCreateUser={addUser}
            onLogin={login}
            onLogout={logout}
            onCreateSecret={addSecret}
            onDeleteSecret={removeSecret}
            onCreateAgent={addAgent}
            onExport={handleExport}
            onClose={() => setActivePanel(null)}
          />
        )}

        <div className="orchestra-surface">
          <section className="orchestra-canvas-panel" aria-label="投委会工作流">
            <WorkflowCanvas
              agents={agents}
              runtimes={visibleSnapshot?.agents || {}}
              events={timelineEvents}
              maxConcurrency={overview?.max_concurrency}
              phase={visibleSnapshot?.phase || 'queued'}
              topic={topic}
              plan={visibleSnapshot?.plan || ''}
              consensus={visibleSnapshot?.consensus || ''}
              decision={visibleSnapshot?.decision || ''}
              orchestraThinking={visibleSnapshot?.orchestra_thinking || ''}
              showThinking={showThinking}
              showArtifacts={showArtifacts}
              replayEventIndex={replayEventIndex}
              onReplayEventIndexChange={handleReplayEventIndexChange}
              onSelect={setSelectedAgent}
              onOpenReport={(agent) => {
                const report = [...displayArtifacts].reverse().find((artifact) => artifact.agent_id === agent.id);
                if (report) handleOpenArtifact(report);
              }}
            />
            <StageTimeline phase={visibleSnapshot?.phase || 'queued'} />
          </section>

          <IntelligenceRail
            agents={agents}
            events={visibleEvents}
            snapshot={visibleSnapshot}
            health={health}
          />
        </div>
      </main>

      <AgentDrawer
        profile={selectedAgent}
        runtime={selectedAgent ? visibleSnapshot?.agents[selectedAgent.id] : undefined}
        skillCatalog={skillCatalog}
        secrets={secrets}
        onSave={handleSaveProfile}
        onDelete={handleDeleteProfile}
        deleteDisabled={isRunning}
        onIntervene={interveneAgent}
        interventionDisabled={!snapshot || isRunning || replayEventIndex !== null}
        onOpenReport={selectedAgent ? () => {
          const report = [...displayArtifacts].reverse().find((artifact) => artifact.agent_id === selectedAgent.id);
          if (report) handleOpenArtifact(report);
        } : undefined}
        onClose={() => setSelectedAgent(null)}
      />

      {selectedArtifact && (
        <ReportReader
          artifact={selectedArtifact}
          artifacts={displayArtifacts}
          evidence={runEvidence}
          snapshot={snapshot}
          agents={agents}
          onSelectArtifact={setSelectedArtifact}
          onExport={handleExport}
          onClose={() => setSelectedArtifact(null)}
        />
      )}
    </div>
  );
};

export default OrchestraApp;
