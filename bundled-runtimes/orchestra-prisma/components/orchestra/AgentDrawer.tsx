import React, { useEffect, useMemo, useState } from 'react';
import {
  BrainCircuit,
  Bot,
  CheckCircle2,
  Database,
  DatabaseZap,
  FileText,
  Layers3,
  Link2,
  Maximize2,
  Network,
  Pencil,
  MessageCircleQuestion,
  Radio,
  RefreshCcw,
  Save,
  Search,
  Send,
  ServerCog,
  Trash2,
  X,
} from 'lucide-react';
import type {
  AgentConnection,
  AgentInterventionAction,
  AgentProfile,
  AgentRuntime,
  ProfileUpdate,
  SecretMetadata,
  SkillCatalogItem,
} from '@/types/orchestra';

const defaultConnection: AgentConnection = {
  kind: 'orchestra',
  endpoint: null,
  model: null,
  secret_id: null,
  timeout_seconds: 180,
};

const connectionLabel = {
  orchestra: 'Orchestra',
  external_http: '外部 Agent',
  openai_compatible: '独立模型',
};

const AgentDrawer = ({
  profile,
  runtime,
  skillCatalog,
  secrets = [],
  onSave,
  onDelete,
  deleteDisabled,
  onOpenReport,
  onIntervene,
  interventionDisabled,
  onClose,
}: {
  profile: AgentProfile | null;
  runtime?: AgentRuntime;
  skillCatalog: SkillCatalogItem[];
  secrets?: SecretMetadata[];
  onSave: (agentId: string, updates: ProfileUpdate) => Promise<AgentProfile>;
  onDelete?: (agentId: string) => Promise<unknown>;
  deleteDisabled?: boolean;
  onOpenReport?: () => void;
  onIntervene?: (agentId: string, action: AgentInterventionAction, instruction: string) => Promise<unknown>;
  interventionDisabled?: boolean;
  onClose: () => void;
}) => {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [skillQuery, setSkillQuery] = useState('');
  const [draft, setDraft] = useState<ProfileUpdate | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [interventionAction, setInterventionAction] = useState<AgentInterventionAction>('follow_up');
  const [interventionInstruction, setInterventionInstruction] = useState('');
  const [intervening, setIntervening] = useState(false);
  const [interventionError, setInterventionError] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    setDraft({
      name: profile.name,
      title: profile.title,
      focus: profile.focus,
      persona: profile.persona,
      style: profile.style,
      default_prompt: profile.default_prompt,
      skills: [...profile.skills],
      connection: { ...(profile.connection || defaultConnection) },
    });
    setEditing(false);
    setSkillQuery('');
    setSaveError(null);
    setConfirmDelete(false);
    setInterventionAction('follow_up');
    setInterventionInstruction('');
    setIntervening(false);
    setInterventionError(null);
  }, [profile]);

  const visibleSkills = useMemo(() => {
    const needle = skillQuery.trim().toLowerCase();
    if (!needle) return skillCatalog;
    return skillCatalog.filter((skill) => `${skill.name} ${skill.description}`.toLowerCase().includes(needle));
  }, [skillCatalog, skillQuery]);

  if (!profile || !draft) return null;

  const updateField = <K extends keyof ProfileUpdate>(key: K, value: ProfileUpdate[K]) => {
    setDraft((current) => current ? { ...current, [key]: value } : current);
  };

  const toggleSkill = (skill: string) => {
    const selected = draft.skills.includes(skill);
    if (!selected && draft.skills.length >= 5) return;
    updateField('skills', selected ? draft.skills.filter((item) => item !== skill) : [...draft.skills, skill]);
  };

  const updateConnection = <K extends keyof AgentConnection>(key: K, value: AgentConnection[K]) => {
    updateField('connection', { ...(draft.connection || defaultConnection), [key]: value });
  };

  const save = async () => {
    if (!draft.name.trim() || !draft.title.trim() || !draft.focus.trim() || draft.skills.length < 3 || draft.skills.length > 5 || !connectionReady) return;
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(profile.id, {
        ...draft,
        name: draft.name.trim(),
        title: draft.title.trim(),
        focus: draft.focus.trim(),
        persona: draft.persona.trim(),
        style: draft.style.trim(),
        default_prompt: draft.default_prompt.trim(),
      });
      setEditing(false);
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : 'Profile 保存失败');
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!onDelete || !profile.is_custom || deleteDisabled) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await onDelete(profile.id);
      onClose();
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : 'Agent 删除失败');
      setConfirmDelete(false);
    } finally {
      setSaving(false);
    }
  };

  const activeConnection = draft.connection || defaultConnection;
  const storedSecret = secrets.find((secret) => secret.id === activeConnection.secret_id);
  const selectableSecrets = secrets.filter((secret) => activeConnection.kind === 'external_http'
    ? secret.provider === 'agent'
    : secret.provider === 'openai' || secret.provider === 'agent');
  const connectionReady = activeConnection.kind === 'orchestra'
    || (activeConnection.kind === 'external_http' && Boolean(activeConnection.endpoint?.trim()))
    || (activeConnection.kind === 'openai_compatible' && Boolean(activeConnection.model?.trim()));
  const interventionRunning = runtime?.status === 'working' && runtime.phase === 'intervention';
  const interventionLabels: Record<AgentInterventionAction, string> = {
    follow_up: '追问',
    supplement: '补充数据',
    rereview: '重新审视',
  };
  const interventionPlaceholders: Record<AgentInterventionAction, string> = {
    follow_up: '输入需要该席位单独回答的问题',
    supplement: '输入需补齐的数据、口径或时间区间',
    rereview: '输入需重新审视的假设、反方观点或风险',
  };

  const intervene = async () => {
    if (!onIntervene || !interventionInstruction.trim() || interventionDisabled || interventionRunning) return;
    setIntervening(true);
    setInterventionError(null);
    try {
      await onIntervene(profile.id, interventionAction, interventionInstruction.trim());
      setInterventionInstruction('');
    } catch (reason) {
      setInterventionError(reason instanceof Error ? reason.message : '单席干预发起失败');
    } finally {
      setIntervening(false);
    }
  };

  return (
    <div className="orchestra-drawer-backdrop" onMouseDown={onClose}>
      <aside
        className={`orchestra-drawer ${editing ? 'is-editing' : ''}`}
        onMouseDown={(event) => event.stopPropagation()}
        aria-label={`${profile.name} 详情`}
      >
        <header>
          <div>
            <span>{profile.id} · {profile.group}</span>
            <h2>{profile.name}</h2>
            <p>{profile.persona}</p>
            <b className={`orchestra-connection-badge is-${profile.connection?.kind || 'orchestra'}`}>{connectionLabel[profile.connection?.kind || 'orchestra']}{profile.is_custom ? ' · 自定义' : ''}</b>
          </div>
          <div className="orchestra-drawer-actions">
            <button type="button" onClick={() => setEditing((value) => !value)} aria-label={editing ? '取消编辑 Profile' : '编辑 Profile'}>
              {editing ? <X size={17} /> : <Pencil size={16} />}
            </button>
            <button type="button" onClick={onClose} aria-label="关闭详情"><X size={18} /></button>
          </div>
        </header>

        {editing ? (
          <div className="orchestra-profile-editor">
            <section>
              <h3>基础身份</h3>
              <label><span>显示名称</span><input value={draft.name} onChange={(event) => updateField('name', event.target.value)} /></label>
              <label><span>角色标题</span><input value={draft.title} onChange={(event) => updateField('title', event.target.value)} /></label>
              <label><span>研究方向</span><input value={draft.focus} onChange={(event) => updateField('focus', event.target.value)} /></label>
            </section>
            <section>
              <h3>角色与默认提示词</h3>
              <label><span>角色定位</span><textarea rows={4} value={draft.persona} onChange={(event) => updateField('persona', event.target.value)} /></label>
              <label><span>研究风格</span><textarea rows={4} value={draft.style} onChange={(event) => updateField('style', event.target.value)} /></label>
              <label><span>自定义默认提示词</span><textarea rows={7} value={draft.default_prompt} onChange={(event) => updateField('default_prompt', event.target.value)} placeholder="在系统角色卡之后追加的长期执行要求" /></label>
            </section>
            <section className="orchestra-profile-skills">
              <div className="orchestra-profile-section-title"><h3>Skills 选择</h3><span className={draft.skills.length >= 3 && draft.skills.length <= 5 ? 'is-ready' : ''}>{draft.skills.length}/5</span></div>
              <label className="orchestra-profile-skill-search"><Search size={14} /><input value={skillQuery} onChange={(event) => setSkillQuery(event.target.value)} placeholder="搜索已安装 Skills" /></label>
              <div className="orchestra-profile-skill-list">
                {visibleSkills.map((skill) => {
                  const selected = draft.skills.includes(skill.name);
                  return (
                    <button type="button" key={skill.name} className={selected ? 'is-selected' : ''} onClick={() => toggleSkill(skill.name)}>
                      <i>{selected ? <CheckCircle2 size={14} /> : null}</i>
                      <span><strong>{skill.name}</strong><small>{skill.description || '暂无描述'}</small></span>
                    </button>
                  );
                })}
              </div>
            </section>
            <section>
              <h3>执行接入</h3>
              <div className="orchestra-connection-segments" role="group" aria-label="Agent 执行类型">
                <button type="button" className={activeConnection.kind === 'orchestra' ? 'is-active' : ''} onClick={() => updateConnection('kind', 'orchestra')}><Network size={14} />Orchestra</button>
                <button type="button" className={activeConnection.kind === 'external_http' ? 'is-active' : ''} onClick={() => updateConnection('kind', 'external_http')}><ServerCog size={14} />外部 Agent</button>
                <button type="button" className={activeConnection.kind === 'openai_compatible' ? 'is-active' : ''} onClick={() => updateConnection('kind', 'openai_compatible')}><Bot size={14} />独立模型</button>
              </div>
              {activeConnection.kind !== 'orchestra' && (
                <div className="orchestra-connection-fields">
                  <label><span>Endpoint</span><input value={activeConnection.endpoint || ''} onChange={(event) => updateConnection('endpoint', event.target.value || null)} placeholder={activeConnection.kind === 'external_http' ? 'https://agent.example.com/run' : 'https://api.openai.com/v1'} /></label>
                  {activeConnection.kind === 'openai_compatible' && <label><span>模型名称</span><input value={activeConnection.model || ''} onChange={(event) => updateConnection('model', event.target.value || null)} placeholder="gpt-5.2 / deepseek-chat / qwen-max" /></label>}
                  <div className="orchestra-create-grid two-columns">
                    <label><span>隔离密钥</span><select value={activeConnection.secret_id || ''} onChange={(event) => updateConnection('secret_id', event.target.value || null)}><option value="">使用默认或无鉴权</option>{selectableSecrets.map((secret) => <option key={secret.id} value={secret.id}>{secret.label}</option>)}</select></label>
                    <label><span>超时秒数</span><input type="number" min={5} max={600} value={activeConnection.timeout_seconds} onChange={(event) => updateConnection('timeout_seconds', Math.min(600, Math.max(5, Number(event.target.value) || 5)))} /></label>
                  </div>
                </div>
              )}
            </section>
            <div className="orchestra-profile-savebar">
              {saveError && <span>{saveError}</span>}
              {profile.is_custom && <button type="button" className={`orchestra-profile-delete ${confirmDelete ? 'is-confirming' : ''}`} onClick={() => void remove()} disabled={saving || deleteDisabled} title={deleteDisabled ? '运行中不能删除席位' : '删除自定义 Agent'}><Trash2 size={14} />{confirmDelete ? '确认删除' : '删除'}</button>}
              <button type="button" onClick={() => setEditing(false)}>取消</button>
              <button type="button" onClick={() => void save()} disabled={saving || !draft.name.trim() || !draft.title.trim() || !draft.focus.trim() || draft.skills.length < 3 || draft.skills.length > 5 || !connectionReady}>
                <Save size={15} />{saving ? '保存中' : '保存 Profile'}
              </button>
            </div>
          </div>
        ) : (
          <>
            <section>
              <h3>研究风格</h3>
              <p>{profile.style}</p>
            </section>

            <section className="orchestra-connection-summary">
              <h3>{profile.connection?.kind === 'external_http' ? <ServerCog size={15} /> : profile.connection?.kind === 'openai_compatible' ? <Bot size={15} /> : <Network size={15} />} 执行接入</h3>
              <div><span>执行源</span><strong>{connectionLabel[profile.connection?.kind || 'orchestra']}</strong></div>
              {profile.connection?.endpoint && <div><span>Endpoint</span><code>{profile.connection.endpoint}</code></div>}
              {profile.connection?.model && <div><span>模型</span><strong>{profile.connection.model}</strong></div>}
              {profile.connection?.kind !== 'orchestra' && <div><span>密钥</span><strong>{storedSecret?.label || (profile.connection?.secret_id ? '已隔离保存' : '默认或无鉴权')}</strong></div>}
            </section>

            {profile.default_prompt && (
              <section>
                <h3><BrainCircuit size={15} /> 自定义默认提示词</h3>
                <p>{profile.default_prompt}</p>
              </section>
            )}

            <section>
              <h3><Layers3 size={15} /> Skills 注入</h3>
              <div className="orchestra-tag-list">
                {profile.skills.map((skill) => (
                  <span key={skill} className={profile.missing_skills.includes(skill) ? 'is-missing' : ''}>{skill}</span>
                ))}
              </div>
              {profile.missing_skills.length > 0 && <p className="orchestra-warning">缺失 {profile.missing_skills.length} 个 Skills，live 模式会跳过。</p>}
            </section>

            <section className="orchestra-skill-audit">
              <h3><CheckCircle2 size={15} /> Skill 使用审计</h3>
              <div><span>必选</span><p>{runtime?.required_skills.length ? runtime.required_skills.join('、') : '尚未运行'}</p></div>
              <div><span>已注册</span><p>{runtime?.registered_skills.length ? runtime.registered_skills.join('、') : '推演模式或尚未注册'}</p></div>
              <div className="is-used"><span>实际读取</span><p>{runtime?.used_skills.length ? runtime.used_skills.join('、') : '尚无 Skill 查看器读取记录'}</p></div>
            </section>

            <section>
              <h3><Database size={15} /> Tushare 接口</h3>
              <div className="orchestra-tag-list compact">{profile.tushare_endpoints.map((endpoint) => <span key={endpoint}>{endpoint}</span>)}</div>
            </section>

            <section>
              <h3><Radio size={15} /> 研究渠道</h3>
              <p>{profile.research_channels.join('、')}</p>
            </section>

            {runtime?.thoughts && runtime.thoughts.length > 0 && (
              <section>
                <h3><BrainCircuit size={15} /> 可审计思考摘要</h3>
                <ol className="orchestra-thought-list">{runtime.thoughts.map((thought, index) => <li key={`${index}-${thought}`}>{thought}</li>)}</ol>
              </section>
            )}

            {onIntervene && (
              <section className="orchestra-agent-intervention">
                <h3><MessageCircleQuestion size={15} /> 人类干预</h3>
                <div className="orchestra-intervention-segments" role="group" aria-label="单席干预类型">
                  <button type="button" className={interventionAction === 'follow_up' ? 'is-active' : ''} onClick={() => setInterventionAction('follow_up')}><MessageCircleQuestion size={13} />追问</button>
                  <button type="button" className={interventionAction === 'supplement' ? 'is-active' : ''} onClick={() => setInterventionAction('supplement')}><DatabaseZap size={13} />补充数据</button>
                  <button type="button" className={interventionAction === 'rereview' ? 'is-active' : ''} onClick={() => setInterventionAction('rereview')}><RefreshCcw size={13} />重新审视</button>
                </div>
                <textarea
                  rows={4}
                  aria-label="干预指令"
                  value={interventionInstruction}
                  onChange={(event) => setInterventionInstruction(event.target.value)}
                  placeholder={interventionPlaceholders[interventionAction]}
                  disabled={interventionDisabled || interventionRunning}
                />
                <div className="orchestra-intervention-submit">
                  <span className={interventionRunning ? 'is-running' : ''}>
                    {interventionError || (interventionRunning ? `${interventionLabels[runtime?.intervention_action || interventionAction]}执行中` : '')}
                  </span>
                  <button
                    type="button"
                    onClick={() => void intervene()}
                    disabled={intervening || interventionDisabled || interventionRunning || !interventionInstruction.trim()}
                  >
                    <Send size={13} />{intervening ? '提交中' : '发起干预'}
                  </button>
                </div>
              </section>
            )}

            <section>
              <h3><Link2 size={15} /> 证据链</h3>
              {runtime?.evidence.length ? (
                <div className="orchestra-evidence-list">
                  {runtime.evidence.map((item) => (
                    <article key={item.id}>
                      <div><strong>{item.source_name}</strong><span>{item.interface_name || item.tool_name}</span></div>
                      <p>数据日期 {item.observed_at || '未标注'} · 抓取 {new Date(item.retrieved_at).toLocaleString('zh-CN')}</p>
                      {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">查看来源</a>}
                      <code>{item.content_hash.slice(0, 16)}</code>
                    </article>
                  ))}
                </div>
              ) : <p>本席位尚无外部数据证据记录。</p>}
            </section>

            <section className="orchestra-drawer-output">
              <div className="orchestra-drawer-output-heading">
                <h3><FileText size={15} /> 阶段成果报告</h3>
                {runtime?.output && onOpenReport && (
                  <button type="button" onClick={onOpenReport}><Maximize2 size={14} /> 放大阅读</button>
                )}
              </div>
              <pre>{runtime?.output || '尚未生成阶段成果。'}</pre>
              {runtime?.error && <p className="orchestra-warning">{runtime.error}</p>}
            </section>
          </>
        )}
      </aside>
    </div>
  );
};

export default AgentDrawer;
