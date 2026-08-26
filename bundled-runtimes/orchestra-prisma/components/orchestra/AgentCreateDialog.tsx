import React, { useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  KeyRound,
  Network,
  Plus,
  Search,
  ServerCog,
  X,
} from 'lucide-react';
import type {
  AgentConnectionKind,
  AgentProfile,
  CreateAgentPayload,
  SecretMetadata,
  SkillCatalogItem,
} from '@/types/orchestra';

const groups: CreateAgentPayload['group'][] = ['宏观组', '配置组', '股票组', '基金经理组'];

const connectionMeta: Array<{
  kind: AgentConnectionKind;
  label: string;
  icon: typeof Network;
}> = [
  { kind: 'orchestra', label: 'Orchestra', icon: Network },
  { kind: 'external_http', label: '外部 Agent', icon: ServerCog },
  { kind: 'openai_compatible', label: '独立模型', icon: Bot },
];

const AgentCreateDialog = ({
  skillCatalog,
  secrets,
  onCreate,
  onCreated,
  onClose,
}: {
  skillCatalog: SkillCatalogItem[];
  secrets: SecretMetadata[];
  onCreate: (payload: CreateAgentPayload) => Promise<AgentProfile>;
  onCreated: (profile: AgentProfile) => void;
  onClose: () => void;
}) => {
  const [name, setName] = useState('');
  const [title, setTitle] = useState('');
  const [group, setGroup] = useState<CreateAgentPayload['group']>('股票组');
  const [focus, setFocus] = useState('');
  const [persona, setPersona] = useState('');
  const [style, setStyle] = useState('');
  const [defaultPrompt, setDefaultPrompt] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [skillQuery, setSkillQuery] = useState('');
  const [connectionKind, setConnectionKind] = useState<AgentConnectionKind>('orchestra');
  const [endpoint, setEndpoint] = useState('');
  const [model, setModel] = useState('');
  const [secretId, setSecretId] = useState('');
  const [timeoutSeconds, setTimeoutSeconds] = useState(180);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const visibleSkills = useMemo(() => {
    const needle = skillQuery.trim().toLowerCase();
    return (needle
      ? skillCatalog.filter((skill) => `${skill.name} ${skill.description}`.toLowerCase().includes(needle))
      : skillCatalog
    ).slice(0, 120);
  }, [skillCatalog, skillQuery]);

  const connectionSecrets = useMemo(() => secrets.filter((secret) => (
    connectionKind === 'external_http'
      ? secret.provider === 'agent'
      : secret.provider === 'openai' || secret.provider === 'agent'
  )), [connectionKind, secrets]);

  const toggleSkill = (skill: string) => {
    setSkills((current) => {
      if (current.includes(skill)) return current.filter((item) => item !== skill);
      if (current.length >= 5) return current;
      return [...current, skill];
    });
  };

  const connectionValid = connectionKind === 'orchestra'
    || (connectionKind === 'external_http' && endpoint.trim())
    || (connectionKind === 'openai_compatible' && model.trim());
  const formValid = Boolean(
    name.trim()
    && title.trim()
    && focus.trim()
    && persona.trim()
    && style.trim()
    && skills.length >= 3
    && skills.length <= 5
    && connectionValid,
  );

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!formValid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await onCreate({
        name: name.trim(),
        title: title.trim(),
        group,
        focus: focus.trim(),
        persona: persona.trim(),
        style: style.trim(),
        default_prompt: defaultPrompt.trim(),
        skills,
        connection: {
          kind: connectionKind,
          endpoint: endpoint.trim() || null,
          model: model.trim() || null,
          secret_id: secretId || null,
          timeout_seconds: timeoutSeconds,
        },
      });
      onCreated(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Agent 创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="orchestra-dialog-backdrop" onMouseDown={onClose}>
      <form className="orchestra-agent-create" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="新增研究 Agent">
        <header>
          <div><Plus size={17} /><span><strong>新增研究 Agent</strong><small>扩展常设研究席位</small></span></div>
          <button type="button" onClick={onClose} aria-label="关闭新增 Agent"><X size={17} /></button>
        </header>

        <div className="orchestra-agent-create-body">
          <section>
            <div className="orchestra-profile-section-title"><h3>身份与分组</h3><span>{group}</span></div>
            <div className="orchestra-create-grid two-columns">
              <label><span>显示名称</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：半导体 林舟" /></label>
              <label><span>角色标题</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：半导体产业研究员" /></label>
            </div>
            <label><span>所属研究组</span><select value={group} onChange={(event) => setGroup(event.target.value as CreateAgentPayload['group'])}>{groups.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label><span>研究边界</span><input value={focus} onChange={(event) => setFocus(event.target.value)} placeholder="该席位独立负责的变量、资产或产业范围" /></label>
          </section>

          <section>
            <h3>研究框架</h3>
            <div className="orchestra-create-grid two-columns">
              <label><span>角色定位</span><textarea rows={4} value={persona} onChange={(event) => setPersona(event.target.value)} placeholder="长期稳定的身份、判断偏好与能力边界" /></label>
              <label><span>报告风格</span><textarea rows={4} value={style} onChange={(event) => setStyle(event.target.value)} placeholder="证据组织、反证方式与报告结构" /></label>
            </div>
            <label><span>默认提示词</span><textarea rows={4} value={defaultPrompt} onChange={(event) => setDefaultPrompt(event.target.value)} placeholder="追加到角色卡后的长期执行要求" /></label>
          </section>

          <section className="orchestra-profile-skills">
            <div className="orchestra-profile-section-title"><h3>Skills 注入</h3><span className={skills.length >= 3 ? 'is-ready' : ''}>{skills.length}/5</span></div>
            <label className="orchestra-profile-skill-search"><Search size={14} /><input value={skillQuery} onChange={(event) => setSkillQuery(event.target.value)} placeholder="搜索已安装 Skills" /></label>
            <div className="orchestra-profile-skill-list orchestra-create-skill-list">
              {visibleSkills.map((skill) => {
                const selected = skills.includes(skill.name);
                const disabled = !selected && skills.length >= 5;
                return (
                  <button type="button" key={skill.name} className={selected ? 'is-selected' : ''} disabled={disabled} onClick={() => toggleSkill(skill.name)} aria-label={`${selected ? '移除' : '添加'} ${skill.name}`}>
                    <i>{selected ? <CheckCircle2 size={14} /> : null}</i>
                    <span><strong>{skill.name}</strong><small>{skill.description || '暂无描述'}</small></span>
                  </button>
                );
              })}
            </div>
          </section>

          <section>
            <div className="orchestra-profile-section-title"><h3>执行接入</h3><span>{connectionMeta.find((item) => item.kind === connectionKind)?.label}</span></div>
            <div className="orchestra-connection-segments" role="group" aria-label="Agent 执行类型">
              {connectionMeta.map((item) => {
                const Icon = item.icon;
                return <button type="button" key={item.kind} className={connectionKind === item.kind ? 'is-active' : ''} onClick={() => { setConnectionKind(item.kind); setSecretId(''); }}><Icon size={14} />{item.label}</button>;
              })}
            </div>
            {connectionKind !== 'orchestra' && (
              <div className="orchestra-connection-fields">
                <label><span>Endpoint</span><input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder={connectionKind === 'external_http' ? 'https://agent.example.com/run' : 'https://api.openai.com/v1'} /></label>
                {connectionKind === 'openai_compatible' && <label><span>模型名称</span><input value={model} onChange={(event) => setModel(event.target.value)} placeholder="gpt-5.2 / deepseek-chat / qwen-max" /></label>}
                <div className="orchestra-create-grid two-columns">
                  <label><span><KeyRound size={12} /> 隔离密钥</span><select value={secretId} onChange={(event) => setSecretId(event.target.value)}><option value="">使用默认或无鉴权</option>{connectionSecrets.map((secret) => <option key={secret.id} value={secret.id}>{secret.label}</option>)}</select></label>
                  <label><span>超时秒数</span><input type="number" min={5} max={600} value={timeoutSeconds} onChange={(event) => setTimeoutSeconds(Math.min(600, Math.max(5, Number(event.target.value) || 5)))} /></label>
                </div>
              </div>
            )}
          </section>
        </div>

        <footer>
          <span>{error || (skills.length < 3 ? '请选择至少 3 个 Skills' : '')}</span>
          <button type="button" onClick={onClose}>取消</button>
          <button type="submit" disabled={!formValid || submitting}><Plus size={15} />{submitting ? '创建中' : '创建 Agent'}</button>
        </footer>
      </form>
    </div>
  );
};

export default AgentCreateDialog;
