import {
  Bot,
  Check,
  CircleAlert,
  LoaderCircle,
  MemoryStick,
  Play,
  Save,
  Terminal,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  displayModuleName,
  loadAgentSettings,
  probeAgent,
  saveAgentPreferences,
  type AgentAdapterDescription,
} from "../api/agents";
import type { StoredMod } from "../api/modules";

interface AgentSettingsProps {
  modules: StoredMod[];
  userId: string;
}

function adapterName(adapter: AgentAdapterDescription): string {
  return adapter.name || adapter.id;
}

export function AgentSettings({ modules, userId }: AgentSettingsProps) {
  const [adapters, setAdapters] = useState<AgentAdapterDescription[]>([]);
  const [defaultAdapter, setDefaultAdapter] = useState("");
  const [moduleOverrides, setModuleOverrides] = useState<Record<string, string>>(
    {},
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string>();
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    loadAgentSettings(userId)
      .then(({ adapters: rows, preferences }) => {
        if (!active) return;
        setAdapters(rows);
        setDefaultAdapter(preferences.defaultAdapter);
        setModuleOverrides(preferences.moduleOverrides);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Agent 设置加载失败");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [userId]);

  const availableAdapters = useMemo(
    () => adapters.filter((adapter) => adapter.available !== false),
    [adapters],
  );
  const probeModuleId = useMemo(
    () => modules.find((module) => module.status === "published")?.moduleId,
    [modules],
  );

  const save = async () => {
    setSaving(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const saved = await saveAgentPreferences(userId, {
        defaultAdapter,
        moduleOverrides,
      });
      setModuleOverrides(saved.moduleOverrides);
      setMessage("Agent 选择已保存，所有 Mod 的下一次 AI 请求会立即使用新配置。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agent 设置保存失败");
    } finally {
      setSaving(false);
    }
  };

  const test = async (adapter: AgentAdapterDescription) => {
    if (!probeModuleId) {
      setError("当前没有可用于 Agent 连通测试的已发布 Mod。");
      return;
    }
    setTesting(adapter.id);
    setError(undefined);
    setMessage(undefined);
    try {
      const answer = await probeAgent(userId, adapter.id, probeModuleId);
      setMessage(`${adapterName(adapter)} 已连通：${answer.trim().slice(0, 120)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agent 测试失败");
    } finally {
      setTesting(undefined);
    }
  };

  if (loading) {
    return (
      <div className="agent-settings-state" role="status">
        <LoaderCircle className="spin" size={20} aria-hidden="true" />
        正在发现本机 Agent…
      </div>
    );
  }

  return (
    <section className="agent-settings-page">
      <header className="agent-settings-header">
        <div>
          <h1>Agent 设置</h1>
          <p>直接使用本机已登录的 CLI，或连接已经运行的 Hermes WebUI。</p>
        </div>
        <button
          className="primary-action"
          type="button"
          onClick={() => void save()}
          disabled={saving || !defaultAdapter}
        >
          {saving ? (
            <LoaderCircle className="spin" size={15} aria-hidden="true" />
          ) : (
            <Save size={15} aria-hidden="true" />
          )}
          保存设置
        </button>
      </header>

      {error ? (
        <div className="settings-notice settings-error" role="alert">
          <CircleAlert size={16} aria-hidden="true" />
          {error}
        </div>
      ) : null}
      {message ? (
        <div className="settings-notice settings-success" role="status">
          <Check size={16} aria-hidden="true" />
          {message}
        </div>
      ) : null}

      <div className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>全局默认 Agent</h2>
            <p>未单独指定的 Mod 都使用这里选择的 Agent。</p>
          </div>
          <span>{availableAdapters.length} 个 Agent 入口可用</span>
        </div>
        <div className="agent-card-grid">
          {adapters.map((adapter) => {
            const selected = adapter.id === defaultAdapter;
            const available = adapter.available !== false;
            return (
              <article
                className={`agent-card${selected ? " is-selected" : ""}${available ? "" : " is-disabled"}`}
                key={adapter.id}
              >
                <button
                  className="agent-card-select"
                  type="button"
                  onClick={() => setDefaultAdapter(adapter.id)}
                  disabled={!available}
                  aria-pressed={selected}
                >
                  <span className="agent-icon">
                    {adapter.kind === "local-cli" ? (
                      <Terminal size={18} aria-hidden="true" />
                    ) : (
                      <Bot size={18} aria-hidden="true" />
                    )}
                  </span>
                  <span>
                    <strong>{adapterName(adapter)}</strong>
                    <small>{adapter.description || "Agent Gateway Adapter"}</small>
                  </span>
                  <span className={`availability ${available ? "ready" : "missing"}`}>
                    {available
                      ? "已发现"
                      : adapter.kind === "agent-gateway"
                        ? "未连接"
                        : "未安装"}
                  </span>
                </button>
                <div className="agent-card-footer">
                  <span>
                    <MemoryStick size={13} aria-hidden="true" />
                    {adapter.supportsMemory ? "按 Mod 长期记忆" : "会话由上游管理"}
                  </span>
                  <button
                    type="button"
                    onClick={() => void test(adapter)}
                    disabled={!available || testing !== undefined || !probeModuleId}
                  >
                    {testing === adapter.id ? (
                      <LoaderCircle className="spin" size={13} aria-hidden="true" />
                    ) : (
                      <Play size={13} aria-hidden="true" />
                    )}
                    测试
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>Mod 绑定</h2>
            <p>只有需要不同 Agent 的模块才单独设置；留空即继承全局默认。</p>
          </div>
        </div>
        <div className="module-agent-list">
          {modules.map((module) => (
            <label className="module-agent-row" key={module.moduleId}>
              <span>
                <strong>{displayModuleName(module)}</strong>
                <small>{module.moduleId}</small>
              </span>
              <select
                value={moduleOverrides[module.moduleId] || ""}
                onChange={(event) => {
                  const value = event.target.value;
                  setModuleOverrides((current) => {
                    const next = { ...current };
                    if (value) next[module.moduleId] = value;
                    else delete next[module.moduleId];
                    return next;
                  });
                }}
              >
                <option value="">使用全局默认</option>
                {availableAdapters.map((adapter) => (
                  <option value={adapter.id} key={adapter.id}>
                    {adapterName(adapter)}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </div>
    </section>
  );
}
