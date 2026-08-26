import React, { useMemo, useState } from 'react';
import {
  Activity,
  BookOpen,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronRight,
  Database,
  Download,
  FileText,
  GitCompareArrows,
  History,
  Layers3,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  UsersRound,
  X,
} from 'lucide-react';
import type {
  AgentProfile,
  AgentRuntime,
  DecisionEvent,
  ExecutionMode,
  HealthStatus,
  Portfolio,
  PortfolioDetail,
  CreatePortfolioTransactionPayload,
  CreatePortfolioValuationPayload,
  CreateUserResponse,
  QueueJob,
  RunComparison,
  RunArtifact,
  RunSnapshot,
  RunSummary,
  SecretMetadata,
  SystemOverview,
  UserProfile,
  CreateAgentPayload,
  SkillCatalogItem,
} from '@/types/orchestra';
import WorkspacePanel from '@/components/orchestra/WorkspacePanel';
import HistoryArchive from '@/components/orchestra/HistoryArchive';
import ReportLibrary from '@/components/orchestra/ReportLibrary';
import AgentCreateDialog from '@/components/orchestra/AgentCreateDialog';

export type NavigationView = 'committee' | 'history' | 'reports' | 'agents' | 'skills' | 'data' | 'workspace' | 'settings';

const viewMeta = {
  committee: { title: '投委会控制台', subtitle: '当前运行与历史决议', icon: Activity },
  history: { title: '历史讨论', subtitle: '按运行轮次回看完整讨论链路', icon: History },
  reports: { title: '研究成果', subtitle: '阅读、检索与导出 Markdown 报告', icon: BookOpen },
  agents: { title: '研究席位名册', subtitle: '研究分工、状态与能力配置', icon: UsersRound },
  skills: { title: 'Skills 能力矩阵', subtitle: '技能注入、覆盖与缺失审计', icon: Layers3 },
  data: { title: '数据工具', subtitle: '模型、数据源与接口覆盖', icon: Database },
  workspace: { title: '账户与组合', subtitle: '用户、基金组合与密钥隔离', icon: BriefcaseBusiness },
  settings: { title: '运行设置', subtitle: '执行模式与画布信息密度', icon: Settings2 },
};

const statusLabel: Record<string, string> = {
  queued: '排队',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已停止',
  idle: '待命',
  working: '研究中',
};

const dateLabel = (value: string) => new Date(value).toLocaleString('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const Toggle = ({
  checked,
  label,
  description,
  onChange,
}: {
  checked: boolean;
  label: string;
  description: string;
  onChange: (checked: boolean) => void;
}) => (
  <button
    type="button"
    className="orchestra-setting-row"
    role="switch"
    aria-checked={checked}
    onClick={() => onChange(!checked)}
  >
    <span><strong>{label}</strong><small>{description}</small></span>
    <i className={checked ? 'is-on' : ''}><b /></i>
  </button>
);

const NavigationPanel = ({
  view,
  agents,
  skillCatalog,
  runtimes,
  snapshot,
  events,
  artifacts,
  recentRuns,
  health,
  overview,
  queueJobs,
  currentUser,
  users,
  portfolios,
  selectedPortfolioId,
  portfolioDetail,
  secrets,
  comparison,
  mode,
  showThinking,
  showArtifacts,
  onModeChange,
  onShowThinkingChange,
  onShowArtifactsChange,
  onSelectAgent,
  onSelectRun,
  onOpenArtifact,
  onRefresh,
  onReconsider,
  onCompareRuns,
  onCreatePortfolio,
  onSelectPortfolio,
  onCreateTransaction,
  onCreateValuation,
  onCreateUser,
  onLogin,
  onLogout,
  onCreateSecret,
  onDeleteSecret,
  onCreateAgent,
  onExport,
  onClose,
}: {
  view: NavigationView;
  agents: AgentProfile[];
  skillCatalog: SkillCatalogItem[];
  runtimes: Record<string, AgentRuntime>;
  snapshot: RunSnapshot | null;
  events: DecisionEvent[];
  artifacts: RunArtifact[];
  recentRuns: RunSummary[];
  health: HealthStatus | null;
  overview: SystemOverview | null;
  queueJobs: QueueJob[];
  currentUser: UserProfile | null;
  users: UserProfile[];
  portfolios: Portfolio[];
  selectedPortfolioId: string;
  portfolioDetail: PortfolioDetail | null;
  secrets: SecretMetadata[];
  comparison: RunComparison | null;
  mode: ExecutionMode;
  showThinking: boolean;
  showArtifacts: boolean;
  onModeChange: (mode: ExecutionMode) => void;
  onShowThinkingChange: (checked: boolean) => void;
  onShowArtifactsChange: (checked: boolean) => void;
  onSelectAgent: (agent: AgentProfile) => void;
  onSelectRun: (runId: string) => void;
  onOpenArtifact: (artifact: RunArtifact) => void;
  onRefresh: () => Promise<unknown>;
  onReconsider: (note: string) => Promise<unknown>;
  onCompareRuns: (runIds: string[]) => Promise<unknown>;
  onCreatePortfolio: (payload: { name: string; description: string; base_currency: string }) => Promise<Portfolio>;
  onSelectPortfolio: (portfolioId: string) => Promise<unknown>;
  onCreateTransaction: (portfolioId: string, payload: CreatePortfolioTransactionPayload) => Promise<unknown>;
  onCreateValuation: (portfolioId: string, payload: CreatePortfolioValuationPayload) => Promise<unknown>;
  onCreateUser: (name: string, role: UserProfile['role']) => Promise<CreateUserResponse>;
  onLogin: (userId: string, apiToken: string) => Promise<unknown>;
  onLogout: () => Promise<unknown>;
  onCreateSecret: (payload: { provider: SecretMetadata['provider']; label: string; value: string }) => Promise<unknown>;
  onDeleteSecret: (secretId: string) => Promise<unknown>;
  onCreateAgent: (payload: CreateAgentPayload) => Promise<AgentProfile>;
  onExport: (format: 'pdf' | 'docx') => void;
  onClose: () => void;
}) => {
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState('全部');
  const [refreshing, setRefreshing] = useState(false);
  const [revisionNote, setRevisionNote] = useState('基于新增数据和证据链重新审议');
  const [selectedRuns, setSelectedRuns] = useState<string[]>([]);
  const [creatingAgent, setCreatingAgent] = useState(false);
  const meta = viewMeta[view];
  const Icon = meta.icon;

  const skills = useMemo(() => {
    const map = new Map<string, { agents: AgentProfile[]; missing: number }>();
    agents.forEach((agent) => {
      agent.skills.forEach((skill) => {
        const current = map.get(skill) || { agents: [], missing: 0 };
        current.agents.push(agent);
        if (agent.missing_skills.includes(skill)) current.missing += 1;
        map.set(skill, current);
      });
    });
    return [...map.entries()]
      .map(([name, value]) => ({ name, ...value }))
      .sort((left, right) => right.agents.length - left.agents.length || left.name.localeCompare(right.name));
  }, [agents]);

  const endpoints = useMemo(() => {
    const map = new Map<string, AgentProfile[]>();
    agents.forEach((agent) => {
      agent.tushare_endpoints.forEach((endpoint) => {
        map.set(endpoint, [...(map.get(endpoint) || []), agent]);
      });
    });
    return [...map.entries()]
      .map(([name, assigned]) => ({ name, assigned }))
      .sort((left, right) => right.assigned.length - left.assigned.length || left.name.localeCompare(right.name));
  }, [agents]);

  const visibleAgents = agents.filter((agent) => {
    const matchesGroup = group === '全部' || agent.group === group;
    const needle = query.trim().toLowerCase();
    return matchesGroup && (!needle || `${agent.id} ${agent.name} ${agent.focus}`.toLowerCase().includes(needle));
  });
  const visibleSkills = skills.filter((skill) => skill.name.toLowerCase().includes(query.trim().toLowerCase()));
  const stageReports = agents.filter((agent) => Boolean(runtimes[agent.id]?.output));

  const refresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  const toggleRun = (runId: string) => {
    setSelectedRuns((current) => current.includes(runId)
      ? current.filter((item) => item !== runId)
      : [...current.slice(-4), runId]);
  };

  return (
    <>
    <div className="orchestra-console-layer" onMouseDown={onClose}>
      <aside className={`orchestra-console ${view === 'history' || view === 'reports' ? 'is-wide' : ''}`} onMouseDown={(event) => event.stopPropagation()} aria-label={meta.title}>
        <header>
          <div className="orchestra-console-title">
            <Icon size={18} />
            <div><strong>{meta.title}</strong><span>{meta.subtitle}</span></div>
          </div>
          <div className="orchestra-console-actions">
            {view === 'agents' && <button type="button" onClick={() => setCreatingAgent(true)} aria-label="新增研究 Agent" title="新增研究 Agent"><Plus size={17} /></button>}
            <button type="button" onClick={onClose} aria-label="关闭侧边面板"><X size={17} /></button>
          </div>
        </header>

        {view === 'history' && (
          <div className="orchestra-console-body">
            <HistoryArchive
              agents={agents}
              recentRuns={recentRuns}
              snapshot={snapshot}
              events={events}
              onSelectRun={onSelectRun}
            />
          </div>
        )}

        {view === 'reports' && (
          <div className="orchestra-console-body">
            <ReportLibrary
              agents={agents}
              artifacts={artifacts}
              snapshot={snapshot}
              onOpenArtifact={onOpenArtifact}
            />
          </div>
        )}

        {view === 'committee' && (
          <div className="orchestra-console-body">
            <section className="orchestra-console-section">
              <h3>当前运行</h3>
              {snapshot ? (
                <div className="orchestra-current-run">
                  <div><span>{snapshot.mode === 'live' ? '真实' : '推演'} · v{snapshot.revision}</span><b className={`is-${snapshot.status}`}>{statusLabel[snapshot.status]}</b></div>
                  <strong>{snapshot.topic}</strong>
                  <p>{Object.values(snapshot.agents).filter((item) => item.status === 'completed').length}/{agents.length} 席完成 · 事件 #{snapshot.last_event_seq} · 证据 {Object.values(snapshot.agents).reduce((sum, item) => sum + item.evidence.length, 0)}</p>
                  {snapshot.status === 'completed' && (
                    <div className="orchestra-run-actions">
                      <button type="button" onClick={() => onExport('pdf')}><Download size={13} /> PDF</button>
                      <button type="button" onClick={() => onExport('docx')}><Download size={13} /> Word</button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="orchestra-console-empty">尚未启动投决会</div>
              )}
            </section>
            {snapshot?.status === 'completed' && (
              <section className="orchestra-console-section">
                <h3>版本复议</h3>
                <div className="orchestra-revision-form">
                  <textarea rows={3} value={revisionNote} onChange={(event) => setRevisionNote(event.target.value)} aria-label="复议说明" />
                  <button type="button" onClick={() => void onReconsider(revisionNote)} disabled={!revisionNote.trim()}><RotateCcw size={14} /> 创建 v{snapshot.revision + 1}</button>
                </div>
              </section>
            )}
            <section className="orchestra-console-section grow">
              <div className="orchestra-section-heading"><h3>阶段成果报告</h3><span>{stageReports.length}</span></div>
              <div className="orchestra-report-list">
                {stageReports.length === 0 ? <div className="orchestra-console-empty">运行后可查看各席位完整报告</div> : stageReports.map((agent) => (
                  <button type="button" key={agent.id} onClick={() => onSelectAgent(agent)}>
                    <FileText size={14} />
                    <span><strong>{agent.name}</strong><small>{runtimes[agent.id]?.output.replace(/【[^】]+】/g, '').replace(/\s+/g, ' ').slice(0, 64)}</small></span>
                    <ChevronRight size={14} />
                  </button>
                ))}
              </div>
            </section>
            <section className="orchestra-console-section grow">
              <div className="orchestra-section-heading"><h3>历史运行</h3><span>{recentRuns.length}</span></div>
              <div className="orchestra-run-list orchestra-run-select-list">
                {recentRuns.length === 0 ? <div className="orchestra-console-empty">暂无历史记录</div> : recentRuns.map((run) => (
                  <div key={run.id}>
                    <label title="加入报告对比"><input type="checkbox" checked={selectedRuns.includes(run.id)} onChange={() => toggleRun(run.id)} /></label>
                    <button type="button" onClick={() => onSelectRun(run.id)}>
                      <span className={`orchestra-run-status is-${run.status}`} />
                      <span><strong>{run.topic}</strong><small>{dateLabel(run.updated_at)} · v{run.revision} · 证据 {run.evidence_count} · {run.mode === 'live' ? '真实' : '推演'}</small></span>
                      <ChevronRight size={15} />
                    </button>
                  </div>
                ))}
              </div>
              {selectedRuns.length >= 2 && (
                <button type="button" className="orchestra-compare-button" onClick={() => void onCompareRuns(selectedRuns)}><GitCompareArrows size={14} /> 对比 {selectedRuns.length} 份报告</button>
              )}
              {comparison && (
                <div className="orchestra-comparison-result">
                  <strong>版本差异</strong>
                  {comparison.comparisons.map((item) => (
                    <div key={item.target_run_id}>
                      <span>证据变化 {item.evidence_delta >= 0 ? '+' : ''}{item.evidence_delta} · 共识{item.consensus_changed ? '已变化' : '未变化'}</span>
                      <pre>{item.decision_diff.join('\n') || '正式决议无文本差异'}</pre>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        {view === 'agents' && (
          <div className="orchestra-console-body">
            <div className="orchestra-directory-summary"><span>当前常设席位</span><strong>{agents.length}</strong><button type="button" onClick={() => setCreatingAgent(true)}><Plus size={14} /> 添加席位</button></div>
            <label className="orchestra-console-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索姓名、席位或研究方向" /></label>
            <div className="orchestra-group-tabs" role="tablist">
              {['全部', '宏观组', '配置组', '股票组', '基金经理组'].map((item) => (
                <button type="button" role="tab" aria-selected={group === item} className={group === item ? 'is-active' : ''} key={item} onClick={() => setGroup(item)}>{item.replace('基金经理组', '经理')}</button>
              ))}
            </div>
            <div className="orchestra-agent-directory">
              {visibleAgents.map((agent) => {
                const runtime = runtimes[agent.id];
                return (
                  <button type="button" key={agent.id} onClick={() => onSelectAgent(agent)}>
                    <span className={`orchestra-directory-status is-${runtime?.status || 'idle'}`} />
                    <span className="orchestra-directory-id">{agent.id}</span>
                    <span><strong>{agent.name}</strong><small>{agent.focus}</small></span>
                    <span className="orchestra-directory-skills">{agent.skills.length}</span>
                    <ChevronRight size={14} />
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {view === 'skills' && (
          <div className="orchestra-console-body">
            <div className="orchestra-metric-strip">
              <div><span>已安装</span><strong>{overview?.skills.installed ?? '—'}</strong></div>
              <div><span>已分配</span><strong>{overview?.skills.assigned ?? skills.length}</strong></div>
              <div><span>缺失</span><strong className={overview?.skills.missing ? 'is-warning' : ''}>{overview?.skills.missing ?? 0}</strong></div>
            </div>
            <label className="orchestra-console-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 Skill" /></label>
            <div className="orchestra-skill-matrix">
              <header><span>Skill</span><span>席位</span><span>状态</span></header>
              {visibleSkills.map((skill) => (
                <div key={skill.name}>
                  <span><strong>{skill.name}</strong><small>{skill.agents.slice(0, 3).map((agent) => agent.name).join('、')}{skill.agents.length > 3 ? ` +${skill.agents.length - 3}` : ''}</small></span>
                  <b>{skill.agents.length}</b>
                  <i className={skill.missing ? 'is-missing' : ''}>{skill.missing ? `缺失 ${skill.missing}` : 'READY'}</i>
                </div>
              ))}
            </div>
          </div>
        )}

        {view === 'data' && (
          <div className="orchestra-console-body">
            <section className="orchestra-console-section">
              <h3>服务状态</h3>
              <div className="orchestra-service-list">
                {[
                  ['LLM', health?.model || '未配置', overview?.data.llm_ready],
                  ['Tushare Pro', `${overview?.data.tushare_endpoints ?? endpoints.length} 个接口`, health?.data_tools.tushare],
                  ['A Stock Data', 'A股行情、资金与研报', health?.data_tools.a_stock],
                  ['Global Stock Data', '美股与港股数据', health?.data_tools.global_stock],
                  ['Tavily', '网络检索', health?.data_tools.tavily],
                  ['IMA', '中心知识库', health?.data_tools.ima],
                ].map(([name, detail, ready]) => (
                  <div key={String(name)}><span><Database size={14} /><strong>{name}</strong><small>{detail}</small></span><b className={ready ? 'is-ready' : ''}>{ready ? 'READY' : 'OFFLINE'}</b></div>
                ))}
              </div>
            </section>
            <section className="orchestra-console-section grow">
              <div className="orchestra-section-heading"><h3>Tushare 接口覆盖</h3><span>{endpoints.length}</span></div>
              <div className="orchestra-endpoint-list">
                {endpoints.map((endpoint) => (
                  <div key={endpoint.name}><code>{endpoint.name}</code><span>{endpoint.assigned.length} 席</span></div>
                ))}
              </div>
            </section>
          </div>
        )}

        {view === 'workspace' && (
          <WorkspacePanel
            currentUser={currentUser}
            users={users}
            portfolios={portfolios}
            selectedPortfolioId={selectedPortfolioId}
            portfolioDetail={portfolioDetail}
            secrets={secrets}
            onCreateUser={onCreateUser}
            onLogin={onLogin}
            onLogout={onLogout}
            onCreatePortfolio={onCreatePortfolio}
            onSelectPortfolio={onSelectPortfolio}
            onCreateTransaction={onCreateTransaction}
            onCreateValuation={onCreateValuation}
            onCreateSecret={onCreateSecret}
            onDeleteSecret={onDeleteSecret}
          />
        )}

        {view === 'settings' && (
          <div className="orchestra-console-body">
            <section className="orchestra-console-section">
              <h3>执行模式</h3>
              <div className="orchestra-settings-mode">
                <button type="button" className={mode === 'demo' ? 'is-active' : ''} onClick={() => onModeChange('demo')}>推演</button>
                <button type="button" className={mode === 'live' ? 'is-active' : ''} disabled={!health?.live_ready} onClick={() => onModeChange('live')}>真实</button>
              </div>
            </section>
            <section className="orchestra-console-section">
              <h3>画布信息层</h3>
              <Toggle checked={showThinking} label="Agent 思考流" description="显示可审计的流式思考摘要" onChange={onShowThinkingChange} />
              <Toggle checked={showArtifacts} label="成果纵深栈" description="显示方法、证据与阶段成果" onChange={onShowArtifactsChange} />
            </section>
            <section className="orchestra-console-section">
              <h3>运行环境</h3>
              <dl className="orchestra-system-facts">
                <div><dt>后端版本</dt><dd>v{overview?.version || '—'}</dd></div>
                <div><dt>并发席位</dt><dd>{overview?.max_concurrency ?? '—'}</dd></div>
                <div><dt>运行存储</dt><dd>{overview?.persistence === 'sqlite' ? 'SQLite WAL' : overview?.persistence === 'postgresql' ? 'PostgreSQL' : overview?.persistence || '—'}</dd></div>
                <div><dt>Schema 版本</dt><dd>v{overview?.schema_version ?? '—'}</dd></div>
                <div><dt>任务队列</dt><dd>{overview?.queue_backend || '—'}</dd></div>
                <div><dt>密钥保险箱</dt><dd>{overview?.secret_vault ? `${overview.secret_vault.backend} · ${overview.secret_vault.key_id}` : '—'}</dd></div>
                <div><dt>数据库位置</dt><dd title={overview?.database_path}>{overview?.database_path || '—'}</dd></div>
                <div><dt>历史上限</dt><dd>{overview?.run_history_limit ?? '—'}</dd></div>
              </dl>
            </section>
            <section className="orchestra-console-section grow">
              <div className="orchestra-section-heading"><h3>任务队列</h3><span>{overview?.queue?.total ?? queueJobs.length}</span></div>
              <div className="orchestra-queue-metrics">
                <div><span>排队</span><strong>{overview?.queue?.queued ?? 0}</strong></div>
                <div><span>执行</span><strong>{overview?.queue?.running ?? 0}</strong></div>
                <div><span>失败</span><strong>{overview?.queue?.failed ?? 0}</strong></div>
                <div><span>Worker</span><strong>{overview?.queue?.workers ?? '—'}</strong></div>
              </div>
              {overview?.queue?.fallback_reason ? <p className="orchestra-queue-warning">Redis 回退：{overview.queue.fallback_reason}</p> : null}
              <div className="orchestra-queue-jobs">
                {queueJobs.length === 0 ? <div className="orchestra-console-empty">暂无后台任务</div> : queueJobs.map((job) => (
                  <button type="button" key={job.run_id} onClick={() => onSelectRun(job.run_id)}>
                    <span className={`orchestra-run-status is-${job.status}`} />
                    <span><strong>{job.run_id.slice(0, 12)}</strong><small>{dateLabel(job.updated_at)} · 尝试 {job.attempts}{job.last_error ? ` · ${job.last_error}` : ''}</small></span>
                    <b>{statusLabel[job.status]}</b>
                  </button>
                ))}
              </div>
            </section>
            <button type="button" className="orchestra-refresh-button" onClick={() => void refresh()} disabled={refreshing}>
              {refreshing ? <RefreshCw size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              {refreshing ? '正在刷新' : '刷新系统状态'}
            </button>
          </div>
        )}
      </aside>
    </div>
    {creatingAgent && (
      <AgentCreateDialog
        skillCatalog={skillCatalog}
        secrets={secrets}
        onCreate={onCreateAgent}
        onCreated={(profile) => {
          setCreatingAgent(false);
          onSelectAgent(profile);
        }}
        onClose={() => setCreatingAgent(false)}
      />
    )}
    </>
  );
};

export default NavigationPanel;
