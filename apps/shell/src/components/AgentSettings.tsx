import {
  Bot,
  Check,
  CircleAlert,
  LoaderCircle,
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
  type AgentProfile,
  type ExecutionProfile,
} from "../api/agents";
import {
  loadModelProviders,
  type ModelProviderDescription,
} from "../api/models";
import type { StoredMod } from "../api/modules";

interface AgentSettingsProps {
  modules: StoredMod[];
  userId: string;
}

function adapterName(adapter: AgentAdapterDescription): string {
  return adapter.name || adapter.id;
}

function agentProfilesForModule(module: StoredMod): AgentProfile[] {
  if (module.manifest.schemaVersion === "1.0") {
    return module.manifest.agentCapabilities.length > 0 ? ["deep"] : [];
  }
  const profiles = new Set<AgentProfile>();
  for (const action of Object.values(module.manifest.actions)) {
    if (action.binding.type === "agent") {
      profiles.add(action.binding.profile ?? "deep");
    }
  }
  return [...profiles];
}

const PROFILE_META: Record<
  AgentProfile,
  { label: string; capability: string }
> = {
  deep: { label: "深度研究", capability: "module.explain" },
  batch: { label: "批量处理", capability: "module.analyze" },
  edit: { label: "编码修改", capability: "module.edit" },
};

export function AgentSettings({ modules, userId }: AgentSettingsProps) {
  const [adapters, setAdapters] = useState<AgentAdapterDescription[]>([]);
  const [modelProviders, setModelProviders] = useState<ModelProviderDescription[]>([]);
  const [defaultAdapter, setDefaultAdapter] = useState("");
  const [moduleOverrides, setModuleOverrides] = useState<Record<string, string>>(
    {},
  );
  const [profileTargets, setProfileTargets] = useState<
    Partial<Record<ExecutionProfile, string>>
  >({});
  const [moduleProfileOverrides, setModuleProfileOverrides] = useState<
    Record<string, Partial<Record<ExecutionProfile, string>>>
  >({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string>();
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    Promise.all([
      loadAgentSettings(userId),
      loadModelProviders().catch(() => [] as ModelProviderDescription[]),
    ])
      .then(([{ adapters: rows, preferences }, providers]) => {
        if (!active) return;
        setAdapters(rows);
        setModelProviders(providers);
        setDefaultAdapter(preferences.defaultAdapter);
        setModuleOverrides(preferences.moduleOverrides);
        setModuleProfileOverrides(preferences.moduleProfileOverrides ?? {});
        const defaultModel =
          providers.find(
            (provider) => provider.default && provider.available !== false,
          ) ?? providers.find((provider) => provider.available !== false);
        const editable = rows.find(
          (adapter) =>
            adapter.available !== false &&
            adapter.capabilities.includes("module.edit"),
        );
        const batch = rows.find(
          (adapter) =>
            adapter.available !== false &&
            adapter.capabilities.includes("module.analyze"),
        );
        setProfileTargets({
          quick: preferences.profileTargets?.quick ?? defaultModel?.id,
          deep: preferences.profileTargets?.deep ?? preferences.defaultAdapter,
          batch:
            preferences.profileTargets?.batch ??
            batch?.id ??
            preferences.defaultAdapter,
          edit:
            preferences.profileTargets?.edit ??
            editable?.id ??
            preferences.defaultAdapter,
        });
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
  const adaptersFor = (capability: string) =>
    availableAdapters.filter((adapter) =>
      adapter.capabilities.includes(capability),
    );
  const probeModuleId = useMemo(
    () => modules.find((module) => module.status === "published")?.moduleId,
    [modules],
  );
  const agentModules = useMemo(
    () => modules.flatMap((module) => {
      const profiles = new Set(agentProfilesForModule(module));
      if (moduleOverrides[module.moduleId]) profiles.add("deep");
      for (const profile of ["deep", "batch", "edit"] as const) {
        if (moduleProfileOverrides[module.moduleId]?.[profile]) {
          profiles.add(profile);
        }
      }
      return profiles.size > 0 ? [{ module, profiles: [...profiles] }] : [];
    }),
    [moduleOverrides, moduleProfileOverrides, modules],
  );

  const save = async () => {
    setSaving(true);
    setError(undefined);
    setMessage(undefined);
    try {
      const saved = await saveAgentPreferences(userId, {
        defaultAdapter,
        moduleOverrides,
        profileTargets,
        moduleProfileOverrides,
      });
      setModuleOverrides(saved.moduleOverrides);
      setProfileTargets(saved.profileTargets);
      setModuleProfileOverrides(saved.moduleProfileOverrides);
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

  const routeRows: Array<{
    profile: ExecutionProfile;
    label: string;
    description: string;
    options: Array<{ id: string; name: string }>;
  }> = [
    {
      profile: "quick",
      label: "快速问答（模型网关）",
      description: "页面即时解释，走 Desk 模型网关，不占用 CLI 会话",
      options: modelProviders
        .filter((provider) => provider.available !== false)
        .map((provider) => ({ id: provider.id, name: provider.name || provider.id })),
    },
    {
      profile: "deep",
      label: "深度研究",
      description: "复杂分析与长期上下文，走本机 CLI",
      options: adaptersFor("module.explain").map((adapter) => ({
        id: adapter.id,
        name: adapterName(adapter),
      })),
    },
    {
      profile: "batch",
      label: "批量处理",
      description: "摘要、分类与结构化抽取，优先低成本 CLI",
      options: adaptersFor("module.analyze").map((adapter) => ({
        id: adapter.id,
        name: adapterName(adapter),
      })),
    },
    {
      profile: "edit",
      label: "编码修改",
      description: "受控工作区内修改与验证，仅允许写入型 CLI",
      options: availableAdapters
        .filter((adapter) => adapter.capabilities.includes("module.edit"))
        .map((adapter) => ({ id: adapter.id, name: adapterName(adapter) })),
    },
  ];

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
          <p>配置 CLI 与任务路由。</p>
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
            <h2>任务路由</h2>
            <p>按任务复杂度选择执行入口，所有 Mod 默认继承。</p>
          </div>
        </div>
        <div className="agent-profile-list">
          {routeRows.map((row) => (
            <label className="agent-profile-row" key={row.profile}>
              <span>
                <strong>{row.label}</strong>
                <small>{row.description}</small>
              </span>
              <select
                aria-label={`${row.label}执行器`}
                value={profileTargets[row.profile] ?? ""}
                onChange={(event) => {
                  const value = event.target.value;
                  setProfileTargets((current) => ({
                    ...current,
                    [row.profile]: value || undefined,
                  }));
                  if (row.profile === "deep" && value) {
                    setDefaultAdapter(value);
                  }
                }}
              >
                <option value="">使用系统默认</option>
                {row.options.map((option) => (
                  <option value={option.id} key={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>可用 Agent</h2>
            <p>检查本机 CLI 与 Hermes 的发现、记忆和连通状态。</p>
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
                    <small>
                      {adapter.description || "Agent Gateway Adapter"}
                      {adapter.executable ? ` · ${adapter.executable}` : ""}
                    </small>
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
                    {adapter.supportsMemory ? "按 Mod 长期记忆" : "会话由上游管理"}
                  </span>
                  <span>
                    {adapter.commandProfiles?.length
                      ? `档位 ${adapter.commandProfiles.join(" / ")}`
                      : "默认命令档位"}
                  </span>
                  <span title={adapter.modelSource === "cli" ? "由 CLI 实时发现" : "来自适配器注册信息"}>
                    {adapter.models?.length
                      ? `${adapter.models.length} 个模型${adapter.modelSource === "cli" ? " · 实时" : ""}`
                      : "模型由 CLI 默认"}
                  </span>
                  <button
                    type="button"
                    onClick={() => void test(adapter)}
                    disabled={!available || testing !== undefined || !probeModuleId}
                  >
                    {testing === adapter.id ? (
                      <LoaderCircle className="spin" size={13} aria-hidden="true" />
                    ) : null}
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
            <h2>Mod Agent 覆盖</h2>
            <p>只显示 Mod 已声明的任务档位；留空时继承上方全局配置。</p>
          </div>
        </div>
        <div className="module-agent-list">
          {agentModules.map(({ module, profiles }) => (
            <div className="module-agent-row" key={module.moduleId}>
              <span>
                <strong>{displayModuleName(module)}</strong>
                <small>{module.moduleId}</small>
              </span>
              <div className="module-agent-selects">
                {profiles.map((profile) => {
                  const meta = PROFILE_META[profile];
                  const selected =
                    moduleProfileOverrides[module.moduleId]?.[profile] ??
                    (profile === "deep" ? moduleOverrides[module.moduleId] : "") ??
                    "";
                  return (
                    <label className="module-agent-route" key={profile}>
                      <span>{meta.label}</span>
                      <select
                        aria-label={`${displayModuleName(module)}${meta.label}执行器`}
                        value={selected}
                        onChange={(event) => {
                          const value = event.target.value;
                          setModuleProfileOverrides((current) => {
                            const next = { ...current };
                            const targets = { ...(next[module.moduleId] ?? {}) };
                            if (value) targets[profile] = value;
                            else delete targets[profile];
                            if (Object.keys(targets).length > 0) {
                              next[module.moduleId] = targets;
                            } else {
                              delete next[module.moduleId];
                            }
                            return next;
                          });
                          if (profile === "deep") {
                            setModuleOverrides((current) => {
                              const next = { ...current };
                              delete next[module.moduleId];
                              return next;
                            });
                          }
                        }}
                      >
                        <option value="">继承全局配置</option>
                        {adaptersFor(meta.capability).map((adapter) => (
                          <option value={adapter.id} key={adapter.id}>
                            {adapterName(adapter)}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
