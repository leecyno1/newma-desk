import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowDownToLine,
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  CircleDot,
  Database,
  FileText,
  GitMerge,
  Globe2,
  Layers3,
  Radio,
  Search,
  Wrench,
} from 'lucide-react';
import type {
  AgentProfile,
  DecisionEvent,
  HealthStatus,
  RunSnapshot,
} from '@/types/orchestra';

type WaterfallTone = 'system' | 'action' | 'tool' | 'evidence' | 'draft' | 'skill' | 'success' | 'error';

type WaterfallEntry = {
  id: string;
  seq: number;
  createdAt: string;
  title: string;
  detail: string;
  meta: string;
  tone: WaterfallTone;
  icon: React.ComponentType<{ size?: number }>;
};

const compactText = (value: unknown, limit = 520) => {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
};

const compactJson = (value: unknown, limit = 520) => {
  if (!value || typeof value !== 'object') return compactText(value, limit);
  return compactText(JSON.stringify(value, null, 2), limit);
};

const resultSummary = (excerpt: unknown) => {
  const raw = String(excerpt || '');
  try {
    const payload = JSON.parse(raw) as Record<string, unknown>;
    const parts = [
      payload.source,
      payload.api_name || payload.action || payload.query,
      typeof payload.row_count === 'number' ? `${payload.row_count} 条记录` : null,
      payload.error,
    ].filter(Boolean);
    const rows = Array.isArray(payload.rows) ? payload.rows : Array.isArray(payload.results) ? payload.results : [];
    const sample = rows.length > 0 ? compactJson(rows[0], 300) : '';
    return compactText(`${parts.join(' · ')}${sample ? ` | 样本 ${sample}` : ''}`, 620);
  } catch {
    return compactText(raw, 620);
  }
};

const OUTPUT_TYPES = new Set([
  'agent.output.delta',
  'data.output.delta',
  'orchestra.agent.output.delta',
]);

const coalesceOutputEvents = (events: DecisionEvent[]) => {
  const coalesced: DecisionEvent[] = [];
  for (const event of events) {
    const previous = coalesced.at(-1);
    const canMerge = previous
      && OUTPUT_TYPES.has(event.type)
      && previous.type === event.type
      && previous.agent_id === event.agent_id
      && previous.phase === event.phase
      && String(previous.payload.delta || '').length < 720;
    if (canMerge && previous) {
      coalesced[coalesced.length - 1] = {
        ...event,
        payload: {
          ...event.payload,
          delta: `${String(previous.payload.delta || '')}${String(event.payload.delta || '')}`,
        },
      };
    } else {
      coalesced.push(event);
    }
  }
  return coalesced;
};

const buildEntry = (
  event: DecisionEvent,
  names: Map<string, string>,
): WaterfallEntry | null => {
  const isData = event.type.startsWith('data.');
  const isOrchestra = event.type.startsWith('orchestra.');
  const actor = isData
    ? '共享数据基座'
    : isOrchestra
      ? '群体 AI 智脑'
      : event.agent_id
        ? names.get(event.agent_id) || event.agent_id
        : 'Orchestra';
  const meta = `${actor} · ${event.phase || 'system'}`;
  const base = { id: event.id, seq: event.seq, createdAt: event.created_at, meta };

  if (event.type === 'agent.output.delta' || event.type === 'data.output.delta' || event.type === 'orchestra.agent.output.delta') {
    const detail = compactText(event.payload.delta, 720);
    if (!detail) return null;
    return { ...base, title: `${actor} · 草稿流`, detail, tone: 'draft', icon: FileText };
  }
  if (event.type === 'agent.thinking' || event.type === 'data.thinking' || event.type === 'orchestra.agent.thinking') {
    return {
      ...base,
      title: `${actor} · 动作摘要`,
      detail: compactText(event.payload.summary || '正在核对证据与分析边界'),
      tone: 'action',
      icon: BrainCircuit,
    };
  }
  if (event.type === 'agent.progress') {
    return {
      ...base,
      title: `${actor} · 执行心跳 ${Number(event.payload.elapsed_seconds || 0).toFixed(0)}s`,
      detail: compactText(
        `${event.payload.summary || '研究进行中'} · 证据 ${event.payload.evidence_count || 0} · 草稿 ${event.payload.output_chars || 0} 字`,
      ),
      tone: 'action',
      icon: Activity,
    };
  }
  if (event.type.endsWith('tool.started')) {
    return {
      ...base,
      title: `${actor} · 发起数据调用`,
      detail: String(event.payload.tool || '数据工具'),
      tone: 'tool',
      icon: Wrench,
    };
  }
  if (event.type.endsWith('tool.input')) {
    return {
      ...base,
      title: `${actor} · 请求参数`,
      detail: `${String(event.payload.tool || '数据工具')} ${compactJson(event.payload.params)}`,
      tone: 'tool',
      icon: Layers3,
    };
  }
  if (event.type.endsWith('tool.completed')) {
    return {
      ...base,
      title: `${actor} · 数据返回`,
      detail: resultSummary(event.payload.excerpt || event.payload.source),
      tone: 'evidence',
      icon: Database,
    };
  }
  if (event.type.endsWith('evidence.recorded')) {
    return {
      ...base,
      title: `${actor} · 证据入库`,
      detail: compactText(
        `${event.payload.source_name || '未知来源'} · ${event.payload.interface_name || event.payload.tool_name || '接口'} · ${event.payload.observed_at || '时间待核'} | ${resultSummary(event.payload.excerpt)}`,
        680,
      ),
      tone: 'evidence',
      icon: BookOpen,
    };
  }
  if (event.type === 'agent.skill.used') {
    const workflow = event.payload.workflow ? ` · ${String(event.payload.workflow)}` : '';
    return {
      ...base,
      title: `${actor} · Skill 激活`,
      detail: `${String(event.payload.skill || '专属框架')} · ${String(event.payload.source || 'orchestrator')}${workflow}`,
      tone: 'skill',
      icon: Layers3,
    };
  }
  if (event.type === 'agent.skill.required') {
    const skills = Array.isArray(event.payload.skills) ? event.payload.skills.map(String) : [];
    return {
      ...base,
      title: `${actor} · 装载专属框架`,
      detail: skills.join(' · '),
      tone: 'skill',
      icon: Layers3,
    };
  }
  if (event.type.endsWith('report.section')) {
    return {
      ...base,
      title: `${actor} · 报告推进`,
      detail: `开始生成「${String(event.payload.section || '阶段章节')}」`,
      tone: 'draft',
      icon: FileText,
    };
  }
  if (event.type === 'agent.intervention.requested') {
    const actionLabels: Record<string, string> = { follow_up: '追问', supplement: '补充数据', rereview: '重新审视' };
    const action = actionLabels[String(event.payload.action)] || '人类干预';
    return { ...base, title: `${actor} · ${action}已提交`, detail: compactText(event.payload.instruction), tone: 'system', icon: CircleDot };
  }
  if (event.type === 'agent.intervention.started') {
    const skills = Array.isArray(event.payload.required_skills) ? event.payload.required_skills.map(String) : [];
    return { ...base, title: `${actor} · 单席干预开始`, detail: skills.length ? `专属 Skills ${skills.join(' · ')}` : '正在读取已有报告与干预指令', tone: 'action', icon: Radio };
  }
  if (event.type === 'agent.intervention.completed') {
    return { ...base, title: `${actor} · 增量报告已沉淀`, detail: '新版报告、证据与观点变化已持久化', tone: 'success', icon: CheckCircle2 };
  }
  if (event.type === 'agent.intervention.failed') {
    return { ...base, title: `${actor} · 单席干预异常`, detail: compactText(event.payload.error || '未知错误'), tone: 'error', icon: AlertTriangle };
  }
  if (event.type === 'agent.started') {
    return { ...base, title: `${actor} · 开始执行`, detail: '角色边界、数据包与专属 Skills 已就绪', tone: 'action', icon: Radio };
  }
  if (event.type === 'agent.completed') {
    return { ...base, title: `${actor} · 成果已沉淀`, detail: '完整阶段报告已归档，可从席位卡片或报告中心查看', tone: 'success', icon: CheckCircle2 };
  }
  if (event.type === 'agent.failed' || event.type === 'run.failed' || event.type === 'data.foundation.failed') {
    return { ...base, title: `${actor} · 执行异常`, detail: compactText(event.payload.error || '未知错误'), tone: 'error', icon: AlertTriangle };
  }
  if (event.type === 'phase.started') {
    return { ...base, title: '工作流阶段切换', detail: String(event.payload.label || event.phase || '阶段推进'), tone: 'system', icon: Radio };
  }
  if (event.type === 'data.foundation.started') {
    const sources = Array.isArray(event.payload.sources) ? event.payload.sources.map(String) : [];
    return { ...base, title: '共享数据基座启动', detail: sources.join(' · '), tone: 'system', icon: Database };
  }
  if (event.type === 'data.foundation.completed') {
    return { ...base, title: '三端证据包完成', detail: `证据包 ${event.payload.characters || 0} 字，开始分发至研究席位`, tone: 'success', icon: CheckCircle2 };
  }
  if (event.type === 'orchestra.plan') {
    return { ...base, title: '主席完成议题拆解', detail: compactText(event.payload.plan), tone: 'system', icon: GitMerge };
  }
  if (event.type === 'orchestra.consensus') {
    return { ...base, title: '分歧收敛完成', detail: compactText(event.payload.consensus, 680), tone: 'success', icon: GitMerge };
  }
  if (event.type === 'orchestra.decision') {
    return { ...base, title: '正式投决生成', detail: compactText(event.payload.decision, 720), tone: 'success', icon: CheckCircle2 };
  }
  if (event.type === 'run.started') {
    return { ...base, title: '投决会开始运行', detail: `执行模式 ${String(event.payload.mode || '')}`, tone: 'system', icon: Radio };
  }
  if (event.type === 'run.completed') {
    return { ...base, title: '本轮投决会完成', detail: '全体席位成果、证据链与主席决议已持久化', tone: 'success', icon: CheckCircle2 };
  }
  if (event.type === 'run.cancelled') {
    return { ...base, title: '本轮投决会已停止', detail: '执行已取消', tone: 'error', icon: AlertTriangle };
  }
  return null;
};

const IntelligenceRail = ({
  agents,
  events,
  snapshot,
  health,
}: {
  agents: AgentProfile[];
  events: DecisionEvent[];
  snapshot: RunSnapshot | null;
  health: HealthStatus | null;
}) => {
  const names = useMemo(() => new Map(agents.map((agent) => [agent.id, agent.name])), [agents]);
  const entries = useMemo(
    () => coalesceOutputEvents(events)
      .map((event) => buildEntry(event, names))
      .filter((entry): entry is WaterfallEntry => Boolean(entry))
      .slice(-360),
    [events, names],
  );
  const streamRef = useRef<HTMLDivElement | null>(null);
  const [followLive, setFollowLive] = useState(true);
  const isRunning = snapshot?.status === 'queued' || snapshot?.status === 'running';

  useEffect(() => {
    if (!followLive) return;
    const element = streamRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [entries.length, followLive]);

  const services = [
    { label: 'Tushare', ready: health?.data_tools.tushare, icon: Database },
    { label: 'A股', ready: health?.data_tools.a_stock, icon: Activity },
    { label: '全球', ready: health?.data_tools.global_stock, icon: Globe2 },
    { label: 'Tavily', ready: health?.data_tools.tavily, icon: Search },
    { label: 'IMA', ready: health?.data_tools.ima, icon: BrainCircuit },
  ];

  return (
    <aside className="intelligence-rail" aria-label="实时情报流">
      <header>
        <div>
          <span className={isRunning ? 'is-live' : ''}>LIVE TRACE</span>
          <h2>可审计执行瀑布</h2>
        </div>
        <strong>{entries.length}</strong>
      </header>

      <div className="intelligence-health" aria-label="数据基座状态">
        {services.map(({ label, ready, icon: Icon }) => (
          <div key={label} title={`${label} ${ready ? 'READY' : 'OFFLINE'}`}>
            <Icon size={13} />
            <span>{label}</span>
            <i className={ready ? 'is-ready' : ''} />
          </div>
        ))}
      </div>

      <div
        ref={streamRef}
        className="intelligence-events"
        aria-live="polite"
        onScroll={(event) => {
          const element = event.currentTarget;
          const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
          setFollowLive(distance < 90);
        }}
      >
        {entries.length === 0 ? (
          <div className="intelligence-empty">
            <Radio size={17} />
            <span>{isRunning ? '连接执行总线...' : '启动投决后显示完整动作链路'}</span>
          </div>
        ) : (
          entries.map((entry) => {
            const Icon = entry.icon || CircleDot;
            return (
              <article key={entry.id} className={`is-${entry.tone}`}>
                <div className="intelligence-event-line" />
                <div className="intelligence-event-icon"><Icon size={13} /></div>
                <div className="intelligence-event-body">
                  <header>
                    <strong>{entry.title}</strong>
                    <time>{new Date(entry.createdAt).toLocaleTimeString('zh-CN', { hour12: false })}</time>
                  </header>
                  <p>{entry.detail}</p>
                  <footer><span>{entry.meta}</span><b>#{entry.seq}</b></footer>
                </div>
              </article>
            );
          })
        )}
      </div>

      {!followLive && entries.length > 0 && (
        <button className="intelligence-follow" type="button" onClick={() => setFollowLive(true)} title="回到最新事件">
          <ArrowDownToLine size={14} />
          <span>回到实时</span>
        </button>
      )}
    </aside>
  );
};

export default IntelligenceRail;
