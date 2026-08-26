import React, { useMemo, useState } from 'react';
import {
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  FileText,
  GitMerge,
  Layers3,
  Search,
  Wrench,
} from 'lucide-react';
import type {
  AgentProfile,
  DecisionEvent,
  RunSnapshot,
  RunSummary,
} from '@/types/orchestra';

type ArchiveFilter = 'all' | 'analysis' | 'data' | 'decision';

const dateTime = (value: string) => new Date(value).toLocaleString('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const timeOnly = (value: string) => new Date(value).toLocaleTimeString('zh-CN', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const compact = (value: unknown, limit = 360) => {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
};

const eventCategory = (event: DecisionEvent): ArchiveFilter => {
  if (event.type.includes('tool') || event.type.includes('evidence') || event.type.startsWith('data.')) return 'data';
  if (event.type.startsWith('orchestra.') || event.type === 'phase.started' || event.type.startsWith('run.')) return 'decision';
  return 'analysis';
};

const eventPresentation = (event: DecisionEvent) => {
  if (event.type === 'phase.started') return {
    title: '工作流阶段切换',
    detail: compact(event.payload.label || event.phase || '阶段推进'),
    icon: GitMerge,
  };
  if (event.type.endsWith('thinking') || event.type === 'agent.progress') return {
    title: '动作摘要',
    detail: compact(event.payload.summary || '执行研究与证据核验'),
    icon: BrainCircuit,
  };
  if (event.type.endsWith('skill.used') || event.type.endsWith('skill.required')) return {
    title: '研究框架装载',
    detail: compact(event.payload.skill || (Array.isArray(event.payload.skills) ? event.payload.skills.join(' · ') : '专属 Skills')),
    icon: Layers3,
  };
  if (event.type.endsWith('tool.started') || event.type.endsWith('tool.input')) return {
    title: '数据调用',
    detail: compact(`${event.payload.tool || '数据工具'} ${event.payload.params ? JSON.stringify(event.payload.params) : ''}`),
    icon: Wrench,
  };
  if (event.type.endsWith('tool.completed') || event.type.endsWith('evidence.recorded')) return {
    title: '证据返回',
    detail: compact(event.payload.excerpt || event.payload.source_name || event.payload.source || '证据已持久化'),
    icon: Database,
  };
  if (event.type.endsWith('report.section')) return {
    title: '报告章节推进',
    detail: compact(event.payload.section || '阶段章节'),
    icon: FileText,
  };
  if (event.type === 'agent.completed') return {
    title: '席位报告完成',
    detail: compact(event.payload.output || '完整阶段成果已归档'),
    icon: CheckCircle2,
  };
  if (event.type === 'orchestra.consensus') return {
    title: '分歧收敛',
    detail: compact(event.payload.consensus),
    icon: GitMerge,
  };
  if (event.type === 'orchestra.decision') return {
    title: '主席正式决议',
    detail: compact(event.payload.decision),
    icon: CheckCircle2,
  };
  if (event.type === 'run.completed') return {
    title: '本轮讨论完成',
    detail: '讨论、成果、证据和正式决议已持久化。',
    icon: CheckCircle2,
  };
  return null;
};

const HistoryArchive = ({
  agents,
  recentRuns,
  snapshot,
  events,
  onSelectRun,
}: {
  agents: AgentProfile[];
  recentRuns: RunSummary[];
  snapshot: RunSnapshot | null;
  events: DecisionEvent[];
  onSelectRun: (runId: string) => void;
}) => {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<ArchiveFilter>('all');
  const names = useMemo(() => new Map(agents.map((agent) => [agent.id, agent.name])), [agents]);
  const filteredRuns = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return recentRuns.filter((run) => !needle || `${run.topic} ${run.id}`.toLowerCase().includes(needle));
  }, [query, recentRuns]);
  const discussion = useMemo(() => events
    .map((event) => ({ event, presentation: eventPresentation(event) }))
    .filter((item): item is { event: DecisionEvent; presentation: NonNullable<ReturnType<typeof eventPresentation>> } => Boolean(item.presentation))
    .filter(({ event }) => filter === 'all' || eventCategory(event) === filter)
    .slice(-260), [events, filter]);

  return (
    <div className="orchestra-history-layout">
      <section className="orchestra-history-runs" aria-label="历史讨论轮次">
        <label className="orchestra-console-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索议题或运行编号" />
        </label>
        <div className="orchestra-history-run-list">
          {filteredRuns.map((run) => (
            <button
              type="button"
              key={run.id}
              className={snapshot?.id === run.id ? 'is-active' : ''}
              onClick={() => onSelectRun(run.id)}
            >
              <span className={`orchestra-run-status is-${run.status}`} />
              <span>
                <strong>{run.topic}</strong>
                <small>{dateTime(run.updated_at)} · v{run.revision} · {run.completed_agents}/{run.total_agents} 席</small>
                <em>{run.mode === 'live' ? '真实研究' : '流程推演'} · 证据 {run.evidence_count}</em>
              </span>
              <ChevronRight size={14} />
            </button>
          ))}
        </div>
      </section>

      <section className="orchestra-history-discussion" aria-label="讨论记录">
        <header>
          <div>
            <span><Clock3 size={14} /> 讨论档案</span>
            <h3>{snapshot?.topic || '选择一轮历史讨论'}</h3>
            {snapshot && <p>{dateTime(snapshot.created_at)} · v{snapshot.revision} · 事件 #{snapshot.last_event_seq}</p>}
          </div>
          <div className="orchestra-history-filters" role="tablist" aria-label="讨论记录筛选">
            {([
              ['all', '全部'],
              ['analysis', '观点'],
              ['data', '数据'],
              ['decision', '投决'],
            ] as Array<[ArchiveFilter, string]>).map(([value, label]) => (
              <button type="button" role="tab" aria-selected={filter === value} className={filter === value ? 'is-active' : ''} key={value} onClick={() => setFilter(value)}>{label}</button>
            ))}
          </div>
        </header>

        <div className="orchestra-history-timeline">
          {discussion.length === 0 ? (
            <div className="orchestra-console-empty">该轮尚无可展示的讨论记录</div>
          ) : discussion.map(({ event, presentation }) => {
            const Icon = presentation.icon;
            const actor = event.agent_id ? names.get(event.agent_id) || event.agent_id : 'Orchestra';
            return (
              <article key={event.id} className={`is-${eventCategory(event)}`}>
                <div className="orchestra-history-marker"><Icon size={13} /></div>
                <div>
                  <header><strong>{actor} · {presentation.title}</strong><time>{timeOnly(event.created_at)}</time></header>
                  <p>{presentation.detail}</p>
                  <footer>{event.phase || 'system'} · #{event.seq}</footer>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
};

export default HistoryArchive;
