import React, { useMemo, useState } from 'react';
import {
  BookOpen,
  BrainCircuit,
  ChevronRight,
  FileCheck2,
  FileText,
  Search,
  ShieldCheck,
} from 'lucide-react';
import type { AgentProfile, RunArtifact, RunSnapshot } from '@/types/orchestra';

const kindMeta: Record<string, { label: string; icon: typeof FileText; order: number }> = {
  decision: { label: '正式决议', icon: FileCheck2, order: 0 },
  consensus: { label: '分歧收敛', icon: ShieldCheck, order: 1 },
  data_foundation: { label: '数据基座', icon: BrainCircuit, order: 2 },
  intervention_report: { label: '增量复审', icon: BrainCircuit, order: 3 },
  deliberation_report: { label: '经理审议', icon: BookOpen, order: 4 },
  research_report: { label: '研究报告', icon: FileText, order: 5 },
};

const dateLabel = (value: string) => new Date(value).toLocaleString('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const ReportLibrary = ({
  agents,
  artifacts,
  snapshot,
  onOpenArtifact,
}: {
  agents: AgentProfile[];
  artifacts: RunArtifact[];
  snapshot: RunSnapshot | null;
  onOpenArtifact: (artifact: RunArtifact) => void;
}) => {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const names = useMemo(() => new Map(agents.map((agent) => [agent.id, agent.name])), [agents]);
  const visibleArtifacts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...artifacts]
      .filter((artifact) => kind === 'all' || artifact.kind === kind)
      .filter((artifact) => !needle || `${artifact.title} ${artifact.content} ${artifact.agent_id || ''}`.toLowerCase().includes(needle))
      .sort((left, right) => {
        const orderDelta = (kindMeta[left.kind]?.order ?? 9) - (kindMeta[right.kind]?.order ?? 9);
        return orderDelta || left.title.localeCompare(right.title);
      });
  }, [artifacts, kind, query]);
  const counts = useMemo(() => artifacts.reduce<Record<string, number>>((result, artifact) => {
    result[artifact.kind] = (result[artifact.kind] || 0) + 1;
    return result;
  }, {}), [artifacts]);

  return (
    <div className="orchestra-report-library">
      <header>
        <div>
          <span>当前运行成果</span>
          <h3>{snapshot?.topic || '尚未选择运行'}</h3>
          <p>{artifacts.length} 份 Markdown 成果 · v{snapshot?.revision || 1}</p>
        </div>
        <strong>{artifacts.reduce((sum, artifact) => sum + artifact.content.length, 0).toLocaleString('zh-CN')} 字</strong>
      </header>

      <div className="orchestra-report-library-controls">
        <label className="orchestra-console-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索报告标题或正文" />
        </label>
        <div className="orchestra-report-kind-tabs" role="tablist" aria-label="成果类型">
          <button type="button" role="tab" aria-selected={kind === 'all'} className={kind === 'all' ? 'is-active' : ''} onClick={() => setKind('all')}>全部 <span>{artifacts.length}</span></button>
          {Object.entries(kindMeta).map(([value, meta]) => counts[value] ? (
            <button type="button" role="tab" aria-selected={kind === value} className={kind === value ? 'is-active' : ''} key={value} onClick={() => setKind(value)}>{meta.label} <span>{counts[value]}</span></button>
          ) : null)}
        </div>
      </div>

      <div className="orchestra-report-library-list">
        {visibleArtifacts.length === 0 ? (
          <div className="orchestra-console-empty">当前筛选条件下暂无成果</div>
        ) : visibleArtifacts.map((artifact) => {
          const meta = kindMeta[artifact.kind] || { label: artifact.kind, icon: FileText, order: 9 };
          const Icon = meta.icon;
          return (
            <button type="button" key={artifact.id} onClick={() => onOpenArtifact(artifact)}>
              <i><Icon size={16} /></i>
              <span>
                <strong>{artifact.title}</strong>
                <small>{artifact.agent_id ? names.get(artifact.agent_id) || artifact.agent_id : 'Orchestra'} · {meta.label} · {artifact.content.length.toLocaleString('zh-CN')} 字</small>
                <p>{artifact.content.replace(/[#>*_`【】]/g, '').replace(/\s+/g, ' ').slice(0, 110)}</p>
              </span>
              <em>{dateLabel(artifact.created_at)}</em>
              <ChevronRight size={15} />
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default ReportLibrary;
