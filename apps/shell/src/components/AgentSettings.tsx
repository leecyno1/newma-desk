import {
  Bot,
  Check,
  ChevronDown,
  CircleAlert,
  LoaderCircle,
  Save,
  Search,
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
import {
  adapterMatchesRuntimePreference,
  preferredAdapterForRuntime,
  saveAgentRuntimePreference,
  type AgentRuntimePreference,
} from "../lib/agentRuntime";

interface AgentSettingsProps {
  modules: StoredMod[];
  userId: string;
  runtimePreference?: AgentRuntimePreference;
  hostRuntimeAvailable?: boolean;
  onRuntimePreferenceChange?: (
    preference: AgentRuntimePreference,
  ) => void;
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

export function AgentSettings({
  modules,
  userId,
  runtimePreference = "auto",
  hostRuntimeAvailable = false,
  onRuntimePreferenceChange,
}: AgentSettingsProps) {
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
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [moduleQuery, setModuleQuery] = useState("");
  const [onlyOverridden, setOnlyOverridden] = useState(false);
  const [selectedRuntime, setSelectedRuntime] =
    useState<AgentRuntimePreference>(runtimePreference);

  useEffect(() => {
    setSelectedRuntime(runtimePreference);
  }, [runtimePreference]);

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
  const availableNewmaAdapters = useMemo(
    () =>
      availableAdapters.filter((adapter) =>
        adapterMatchesRuntimePreference(adapter, "newma"),
      ),
    [availableAdapters],
  );
  const availableLocalAdapters = useMemo(
    () =>
      availableAdapters.filter((adapter) =>
        adapterMatchesRuntimePreference(adapter, "local"),
      ),
    [availableAdapters],
  );
  const selectableAdapters = useMemo(
    () =>
      availableAdapters.filter((adapter) =>
        adapterMatchesRuntimePreference(adapter, selectedRuntime),
      ),
    [availableAdapters, selectedRuntime],
  );
  const adaptersFor = (capability: string) =>
    selectableAdapters.filter((adapter) =>
      adapter.capabilities.includes(capability),
    );
  const probeModuleId = useMemo(
    () => modules.find((module) => module.status === "published")?.moduleId,
    [modules],
  );
  const agentModules = useMemo(
    () => modules.flatMap((module) => {
      const profiles = new Set<ExecutionProfile>(agentProfilesForModule(module));
      if (moduleOverrides[module.moduleId]) profiles.add("deep");
      for (const profile of ["quick", "deep", "batch", "edit"] as const) {
        if (moduleProfileOverrides[module.moduleId]?.[profile]) {
          profiles.add(profile);
        }
      }
      const overridden = Boolean(moduleOverrides[module.moduleId]) ||
        Object.values(moduleProfileOverrides[module.moduleId] ?? {}).some(Boolean);
      return profiles.size > 0 ? [{ module, profiles: [...profiles], overridden }] : [];
    }),
    [moduleOverrides, moduleProfileOverrides, modules],
  );
  const overrideCount = agentModules.filter((item) => item.overridden).length;
  const query = moduleQuery.trim().toLocaleLowerCase();
  const visibleAgentModules = agentModules.filter(({ module, overridden }) =>
    (!onlyOverridden || overridden) &&
    (!query || `${displayModuleName(module)} ${module.moduleId}`.toLocaleLowerCase().includes(query)),
  );
  const savedTargetLabel = (id: string) =>
    adapters.find((adapter) => adapter.id === id)?.name ??
    modelProviders.find((provider) => provider.id === id)?.name ?? id;

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
      saveAgentRuntimePreference(selectedRuntime);
      onRuntimePreferenceChange?.(selectedRuntime);
      setMessage("运行方式与 Agent 路由已保存，下一次 AI 请求会立即使用新配置。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agent 设置保存失败");
    } finally {
      setSaving(false);
    }
  };

  const chooseRuntime = (preference: AgentRuntimePreference) => {
    setSelectedRuntime(preference);
    if (preference === "auto") return;
    const selected = preferredAdapterForRuntime(
      adapters,
      preference,
      defaultAdapter,
    );
    if (!selected) return;
    setDefaultAdapter(selected.id);
    if (selected.capabilities.includes("module.explain")) {
      setProfileTargets((current) => ({ ...current, deep: selected.id }));
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
      description: "优先使用快速模型；未配置模型时自动使用所选 Agent 的快速档",
      options: modelProviders
        .filter((provider) => provider.available !== false)
        .map((provider) => ({ id: provider.id, name: provider.name || provider.id })),
    },
    {
      profile: "deep",
      label: "深度研究",
      description: "复杂分析与长期上下文，可交给 Newma 或本地 Agent CLI",
      options: adaptersFor("module.explain").map((adapter) => ({
        id: adapter.id,
        name: adapterName(adapter),
      })),
    },
    {
      profile: "batch",
      label: "批量处理",
      description: "摘要、分类与结构化抽取，可单独指定执行入口",
      options: adaptersFor("module.analyze").map((adapter) => ({
        id: adapter.id,
        name: adapterName(adapter),
      })),
    },
    {
      profile: "edit",
      label: "编码修改",
      description: "受控工作区内修改与验证，仅显示具备写入能力的 Agent",
      options: selectableAdapters
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
          <p>统一配置 Newma Runtime、本地 Agent CLI、模型与任务路由。</p>
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
            <h2>运行方式</h2>
            <p>
              Mod 与 Copilot 始终使用同一入口；挂载 Newma 时宿主优先，独立运行时使用 Desk Gateway。
            </p>
          </div>
          <span>{hostRuntimeAvailable ? "当前已挂载 Newma" : "当前为独立运行"}</span>
        </div>
        <div className="agent-runtime-options" role="group" aria-label="Agent 运行方式">
          <button
            type="button"
            className={selectedRuntime === "auto" ? "is-selected" : ""}
            aria-pressed={selectedRuntime === "auto"}
            onClick={() => chooseRuntime("auto")}
          >
            <Bot size={18} aria-hidden="true" />
            <span>
              <strong>自动选择</strong>
              <small>Newma 挂载时使用宿主；独立运行时使用已配置的 Gateway Adapter。</small>
            </span>
            <em>{hostRuntimeAvailable ? "Newma 宿主" : "Desk Gateway"}</em>
          </button>
          <button
            type="button"
            className={selectedRuntime === "newma" ? "is-selected" : ""}
            aria-pressed={selectedRuntime === "newma"}
            onClick={() => chooseRuntime("newma")}
          >
            <Bot size={18} aria-hidden="true" />
            <span>
              <strong>Newma Runtime</strong>
              <small>挂载时直接交给宿主；独立运行时连接 Newma / Hermes 兼容 Adapter。</small>
            </span>
            <em>
              {hostRuntimeAvailable
                ? "已连接宿主"
                : availableNewmaAdapters.length
                  ? `${availableNewmaAdapters.length} 个可用`
                  : "未连接"}
            </em>
          </button>
          <button
            type="button"
            className={selectedRuntime === "local" ? "is-selected" : ""}
            aria-pressed={selectedRuntime === "local"}
            onClick={() => chooseRuntime("local")}
          >
            <Terminal size={18} aria-hidden="true" />
            <span>
              <strong>本地 Agent CLI</strong>
              <small>独立运行时调用本机已安装并登录的 Codex、Claude、Gemini 等 CLI。</small>
            </span>
            <em>
              {availableLocalAdapters.length
                ? `${availableLocalAdapters.length} 个可用`
                : "未发现"}
            </em>
          </button>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>任务路由</h2>
            <p>
              按任务复杂度选择执行入口；仅显示与当前运行方式兼容的 Agent，旧覆盖项会保留但不会跨运行方式执行。
            </p>
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
                {profileTargets[row.profile] && !row.options.some((option) => option.id === profileTargets[row.profile]) ? (
                  <option value={profileTargets[row.profile]} disabled>
                    {savedTargetLabel(profileTargets[row.profile]!)}（已保存，当前不在可选列表）
                  </option>
                ) : null}
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
            <p>检查本地 CLI 与 Newma / Hermes 兼容 Adapter 的发现、记忆和连通状态。</p>
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
                  onClick={() => {
                    setDefaultAdapter(adapter.id);
                    if (adapter.kind === "agent-gateway") {
                      setSelectedRuntime("newma");
                    } else if (adapter.kind === "local-cli") {
                      setSelectedRuntime("local");
                    }
                  }}
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

      <section className="settings-section module-agent-settings" aria-labelledby="module-agent-heading">
        <h2 id="module-agent-heading">
          <button
            className="module-agent-disclosure"
            type="button"
            aria-expanded={overridesOpen}
            aria-controls="module-agent-overrides"
            onClick={() => setOverridesOpen((open) => !open)}
          >
            <ChevronDown size={17} aria-hidden="true" />
            <span>Mod Agent 覆盖</span>
            <small>已单独配置 {overrideCount} / {agentModules.length} 个 Mod</small>
          </button>
        </h2>
        <p className="module-agent-description">按 Mod 单独指定执行入口；未指定时继承上方全局配置。</p>
        <div id="module-agent-overrides" hidden={!overridesOpen}>
          {overridesOpen ? (
            <>
              <div className="module-agent-toolbar">
                <label className="module-agent-search">
                  <Search size={15} aria-hidden="true" />
                  <input
                    type="search"
                    aria-label="搜索 Mod 名称或 ID"
                    placeholder="搜索 Mod 名称或 ID"
                    value={moduleQuery}
                    onChange={(event) => setModuleQuery(event.target.value)}
                  />
                </label>
                <label className="module-agent-filter">
                  <input
                    type="checkbox"
                    checked={onlyOverridden}
                    onChange={(event) => setOnlyOverridden(event.target.checked)}
                  />
                  仅看已单独配置
                </label>
                <span role="status">显示 {visibleAgentModules.length} / {agentModules.length}</span>
              </div>
              <div className="module-agent-list">
                {visibleAgentModules.map(({ module, profiles }) => (
                  <div className="module-agent-row" key={module.moduleId}>
                    <span>
                      <strong>{displayModuleName(module)}</strong>
                      <small>{module.moduleId}</small>
                    </span>
                    <div className="module-agent-selects">
                      {profiles.map((profile) => {
                        const route = routeRows.find((row) => row.profile === profile)!;
                        const label = profile === "quick" ? "快速问答" : route.label;
                        const selected =
                          moduleProfileOverrides[module.moduleId]?.[profile] ??
                          (profile === "deep" ? moduleOverrides[module.moduleId] : "") ??
                          "";
                        return (
                          <label className="module-agent-route" key={profile}>
                            <span>{label}</span>
                            <select
                              aria-label={`${displayModuleName(module)}${label}执行器`}
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
                              {selected && !route.options.some((option) => option.id === selected) ? (
                                <option value={selected} disabled>
                                  {savedTargetLabel(selected)}（已保存，当前不在可选列表）
                                </option>
                              ) : null}
                              {route.options.map((option) => (
                                <option value={option.id} key={option.id}>
                                  {option.name}
                                </option>
                              ))}
                            </select>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ))}
                {visibleAgentModules.length === 0 ? (
                  <div className="module-agent-empty">
                    <p>{agentModules.length === 0
                      ? "暂无可单独配置的 Mod，页面问答将使用全局设置。"
                      : query
                        ? "没有匹配的 Mod，请调整搜索或筛选条件。"
                        : "所有 Mod 当前都继承全局配置。"}</p>
                    {query || onlyOverridden ? (
                      <button className="secondary-action" type="button" onClick={() => {
                        setModuleQuery("");
                        setOnlyOverridden(false);
                      }}>查看全部</button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
      </section>
    </section>
  );
}
