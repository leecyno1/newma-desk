import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Copy,
  Download,
  FileDown,
  FileText,
  Link2,
  ListTree,
  X,
} from 'lucide-react';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import type {
  AgentProfile,
  RunArtifact,
  RunEvidence,
  RunSnapshot,
} from '@/types/orchestra';
import { confidenceLabels, extractReportSignal, stanceLabels } from '@/utils/orchestraReplay';

type Heading = { level: number; text: string; id: string };

const kindLabel: Record<string, string> = {
  decision: '正式投委会决议',
  consensus: '分歧收敛纪要',
  data_foundation: '共享数据基座',
  deliberation_report: '基金经理审议',
  research_report: '研究员报告',
};

const extractHeadings = (content: string): Heading[] => content
  .split('\n')
  .map((line) => line.match(/^(#{1,4})\s+(.+)$/))
  .filter((match): match is RegExpMatchArray => Boolean(match))
  .map((match, index) => ({
    level: match[1].length,
    text: match[2].replace(/[*_`]/g, '').trim(),
    id: `report-heading-${index}`,
  }));

const safeFilename = (value: string) => value.replace(/[\\/:*?"<>|]/g, '-').slice(0, 80);

const ReportReader = ({
  artifact,
  artifacts,
  evidence,
  snapshot,
  agents,
  onSelectArtifact,
  onExport,
  onClose,
}: {
  artifact: RunArtifact;
  artifacts: RunArtifact[];
  evidence: RunEvidence[];
  snapshot: RunSnapshot | null;
  agents: AgentProfile[];
  onSelectArtifact: (artifact: RunArtifact) => void;
  onExport: (format: 'pdf' | 'docx') => void;
  onClose: () => void;
}) => {
  const [copied, setCopied] = useState(false);
  const [compareArtifactId, setCompareArtifactId] = useState<string | null>(null);
  const documentRef = useRef<HTMLDivElement | null>(null);
  const headings = useMemo(() => extractHeadings(artifact.content), [artifact.content]);
  const names = useMemo(() => new Map(agents.map((agent) => [agent.id, agent.name])), [agents]);
  const artifactIndex = artifacts.findIndex((item) => item.id === artifact.id);
  const previous = artifactIndex > 0 ? artifacts[artifactIndex - 1] : null;
  const next = artifactIndex >= 0 && artifactIndex < artifacts.length - 1 ? artifacts[artifactIndex + 1] : null;
  const comparisonOptions = artifacts.filter((item) => item.id !== artifact.id);
  const compareArtifact = comparisonOptions.find((item) => item.id === compareArtifactId) || null;
  const primarySignal = extractReportSignal(artifact.content);
  const compareSignal = compareArtifact ? extractReportSignal(compareArtifact.content) : null;
  const visibleEvidence = useMemo(() => {
    if (artifact.agent_id) return evidence.filter((item) => item.agent_id === artifact.agent_id);
    return evidence.slice(0, 80);
  }, [artifact.agent_id, evidence]);
  const compareEvidence = useMemo(() => {
    if (!compareArtifact) return [];
    if (compareArtifact.agent_id) return evidence.filter((item) => item.agent_id === compareArtifact.agent_id);
    return evidence.slice(0, 80);
  }, [compareArtifact, evidence]);

  useEffect(() => {
    const root = documentRef.current;
    if (!root) return;
    const primaryDocument = root.querySelector('[data-primary-report]') || root;
    primaryDocument.querySelectorAll('h1, h2, h3, h4').forEach((heading, index) => {
      heading.id = headings[index]?.id || `report-heading-${index}`;
    });
    root.scrollTop = 0;
  }, [artifact.id, headings]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'ArrowLeft' && previous) onSelectArtifact(previous);
      if (event.key === 'ArrowRight' && next) onSelectArtifact(next);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [next, onClose, onSelectArtifact, previous]);

  const copyReport = async () => {
    await navigator.clipboard.writeText(artifact.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  const downloadMarkdown = () => {
    const blob = new Blob([artifact.content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${safeFilename(artifact.title)}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const scrollToHeading = (heading: Heading) => {
    documentRef.current?.querySelector(`#${heading.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const toggleComparison = () => {
    if (compareArtifact) {
      setCompareArtifactId(null);
      return;
    }
    setCompareArtifactId(
      comparisonOptions.find((item) => item.agent_id && names.has(item.agent_id) && item.content.trim())?.id
      || comparisonOptions.find((item) => item.content.trim())?.id
      || comparisonOptions[0]?.id
      || null,
    );
  };

  return (
    <div className="orchestra-report-reader" role="dialog" aria-modal="true" aria-label={`${artifact.title} Markdown 阅读器`}>
      <header className="orchestra-report-toolbar">
        <div className="orchestra-report-toolbar-title">
          <FileText size={17} />
          <span><small>研究成果 / {kindLabel[artifact.kind] || artifact.kind}</small><strong>{artifact.title}</strong></span>
        </div>
        <div className="orchestra-report-toolbar-actions">
          <button type="button" disabled={!previous} onClick={() => previous && onSelectArtifact(previous)} title="上一篇报告"><ChevronLeft size={17} /></button>
          <button type="button" disabled={!next} onClick={() => next && onSelectArtifact(next)} title="下一篇报告"><ChevronRight size={17} /></button>
          <button type="button" className={compareArtifact ? 'is-active' : ''} disabled={comparisonOptions.length === 0} onClick={toggleComparison} title="并排比较报告" aria-label="并排比较报告"><Columns3 size={16} /></button>
          {compareArtifact && (
            <select value={compareArtifact.id} onChange={(event) => setCompareArtifactId(event.target.value)} aria-label="选择对比报告">
              {comparisonOptions.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            </select>
          )}
          <button type="button" onClick={() => void copyReport()} title="复制 Markdown">{copied ? <Check size={16} /> : <Copy size={16} />}</button>
          <button type="button" onClick={downloadMarkdown} title="下载 Markdown"><FileDown size={16} /></button>
          <button type="button" className="has-label" onClick={() => onExport('pdf')}><Download size={15} /> PDF</button>
          <button type="button" className="has-label" onClick={() => onExport('docx')}><Download size={15} /> Word</button>
          <button type="button" className="orchestra-report-close" onClick={onClose} aria-label="关闭报告阅读器"><X size={18} /></button>
        </div>
      </header>

      <div className={`orchestra-report-reader-grid ${compareArtifact ? 'is-comparing' : ''}`}>
        <aside className="orchestra-report-navigator" aria-label="报告导航">
          <section>
            <header><FileText size={14} /><span>研究成果</span><b>{artifacts.length}</b></header>
            <div className="orchestra-report-document-list">
              {artifacts.map((item) => (
                <button type="button" key={item.id} className={`${item.id === artifact.id ? 'is-active' : ''} ${item.id === compareArtifact?.id ? 'is-compare-target' : ''}`} onClick={() => compareArtifact ? setCompareArtifactId(item.id === artifact.id ? compareArtifact.id : item.id) : onSelectArtifact(item)}>
                  <span>{item.title}</span>
                  <small>{item.agent_id ? names.get(item.agent_id) || item.agent_id : 'Orchestra'} · {item.content.length.toLocaleString('zh-CN')} 字</small>
                </button>
              ))}
            </div>
          </section>
          <section className="orchestra-report-outline">
            <header><ListTree size={14} /><span>目录</span><b>{headings.length}</b></header>
            <nav>
              {headings.length ? headings.map((heading) => (
                <button type="button" key={heading.id} className={`is-level-${heading.level}`} onClick={() => scrollToHeading(heading)}>{heading.text}</button>
              )) : <p>该报告未使用 Markdown 标题。</p>}
            </nav>
          </section>
        </aside>

        {compareArtifact ? (
          <main ref={documentRef} className="orchestra-report-compare" aria-label="报告并排比较">
            <section className="orchestra-report-compare-column is-primary" data-primary-report>
              <header>
                <span>主报告</span>
                <h1>{artifact.title}</h1>
                <div>
                  <b>{artifact.agent_id ? names.get(artifact.agent_id) || artifact.agent_id : 'Orchestra 主席'}</b>
                  <i>v{artifact.version}</i>
                  <em>{artifact.content.length.toLocaleString('zh-CN')} 字</em>
                  <em>{visibleEvidence.length} 条证据</em>
                  {primarySignal.stance !== 'unknown' && <strong className={`is-${primarySignal.stance}`}>{stanceLabels[primarySignal.stance]} · {confidenceLabels[primarySignal.confidence]}</strong>}
                </div>
              </header>
              <MarkdownRenderer content={artifact.content} className="orchestra-report-markdown" />
            </section>
            <section className="orchestra-report-compare-column is-secondary">
              <header>
                <span>对比报告</span>
                <h1>{compareArtifact.title}</h1>
                <div>
                  <b>{compareArtifact.agent_id ? names.get(compareArtifact.agent_id) || compareArtifact.agent_id : 'Orchestra 主席'}</b>
                  <i>v{compareArtifact.version}</i>
                  <em>{compareArtifact.content.length.toLocaleString('zh-CN')} 字</em>
                  <em>{compareEvidence.length} 条证据</em>
                  {compareSignal && compareSignal.stance !== 'unknown' && <strong className={`is-${compareSignal.stance}`}>{stanceLabels[compareSignal.stance]} · {confidenceLabels[compareSignal.confidence]}</strong>}
                </div>
              </header>
              <MarkdownRenderer content={compareArtifact.content} className="orchestra-report-markdown" />
            </section>
          </main>
        ) : (
          <main ref={documentRef} className="orchestra-report-document">
            <article data-primary-report>
              <header>
                <span>{kindLabel[artifact.kind] || artifact.kind}</span>
                <h1>{artifact.title}</h1>
                <div>
                  <b>{artifact.agent_id ? names.get(artifact.agent_id) || artifact.agent_id : 'Orchestra 主席'}</b>
                  <i>v{artifact.version}</i>
                  <time>{new Date(artifact.created_at).toLocaleString('zh-CN')}</time>
                  {snapshot && <em>运行 {snapshot.id.slice(0, 8)}</em>}
                </div>
              </header>
              <MarkdownRenderer content={artifact.content} className="orchestra-report-markdown" />
            </article>
          </main>
        )}

        {!compareArtifact && (
          <aside className="orchestra-report-evidence" aria-label="报告证据链">
            <header><Link2 size={14} /><span>证据链</span><b>{visibleEvidence.length}</b></header>
            <div>
              {visibleEvidence.length ? visibleEvidence.map((item) => (
                <article key={item.id}>
                  <header><strong>{item.source_name}</strong><span>{item.status}</span></header>
                  <p>{item.interface_name || item.tool_name}</p>
                  <small>数据 {item.observed_at || '日期待核'} · 抓取 {new Date(item.retrieved_at).toLocaleString('zh-CN')}</small>
                  {item.excerpt && <blockquote>{item.excerpt.slice(0, 360)}</blockquote>}
                  {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">打开原始来源</a>}
                  <code>{item.content_hash.slice(0, 16)}</code>
                </article>
              )) : <p>该成果未绑定独立外部证据，结论来自群体研究包。</p>}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};

export default ReportReader;
