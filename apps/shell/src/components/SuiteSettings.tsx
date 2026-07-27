import {
  Bot,
  Check,
  CircleAlert,
  Database,
  LoaderCircle,
  Save,
  Settings2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  loadDataServiceCatalog,
  loadDataServicePreferences,
  saveDataServicePreferences,
  type DataServiceCatalog,
  type DataServicePreferences,
} from "../api/dataServices";
import type { StoredMod } from "../api/modules";

interface SuiteSettingsProps {
  suiteId: string;
  suiteLabel: string;
  modules: StoredMod[];
  userId: string;
  workspaceId: string;
  onOpenAgentSettings: () => void;
}

interface DataRequirement {
  capabilityId: string;
  permissions: string[];
  moduleNames: string[];
  fixedServices: string[];
  unified: boolean;
}

export function collectSuiteDataRequirements(
  modules: StoredMod[],
): DataRequirement[] {
  const requirements = new Map<string, {
    permissions: Set<string>;
    moduleNames: Set<string>;
    fixedServices: Set<string>;
    unified: boolean;
  }>();
  for (const module of modules) {
    if (module.manifest.schemaVersion !== "1.1") continue;
    for (const [actionId, action] of Object.entries(module.manifest.actions)) {
      if (action.binding.type !== "data") continue;
      const capabilityId = action.binding.capability ?? actionId;
      const requirement = requirements.get(capabilityId) ?? {
        permissions: new Set<string>(),
        moduleNames: new Set<string>(),
        fixedServices: new Set<string>(),
        unified: false,
      };
      requirement.permissions.add(action.permission);
      requirement.moduleNames.add(
        module.manifest.navigation?.label || module.manifest.name,
      );
      if (action.binding.service) requirement.fixedServices.add(action.binding.service);
      else requirement.unified = true;
      requirements.set(capabilityId, requirement);
    }
  }
  return [...requirements.entries()]
    .map(([capabilityId, value]) => ({
      capabilityId,
      permissions: [...value.permissions].sort(),
      moduleNames: [...value.moduleNames].sort((left, right) =>
        left.localeCompare(right, "zh-CN"),
      ),
      fixedServices: [...value.fixedServices].sort(),
      unified: value.unified,
    }))
    .sort((left, right) => left.capabilityId.localeCompare(right.capabilityId));
}

export function SuiteSettings({
  suiteId,
  suiteLabel,
  modules,
  userId,
  workspaceId,
  onOpenAgentSettings,
}: SuiteSettingsProps) {
  const requirements = useMemo(
    () => collectSuiteDataRequirements(modules),
    [modules],
  );
  const [catalog, setCatalog] = useState<DataServiceCatalog>();
  const [preferences, setPreferences] = useState<DataServicePreferences>();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(undefined);
    setMessage(undefined);
    Promise.all([
      loadDataServiceCatalog(),
      loadDataServicePreferences(suiteId, userId, workspaceId),
    ])
      .then(([nextCatalog, nextPreferences]) => {
        if (!active) return;
        setCatalog(nextCatalog);
        setPreferences(nextPreferences);
        setDraft(nextPreferences.capabilityServices);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "项目设置加载失败");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [suiteId, userId, workspaceId]);

  const save = async () => {
    setSaving(true);
    setError(undefined);
    setMessage(undefined);
    const next = { ...(preferences?.capabilityServices ?? {}) };
    for (const requirement of requirements) {
      if (!requirement.unified) continue;
      const serviceId = draft[requirement.capabilityId];
      if (serviceId) next[requirement.capabilityId] = serviceId;
      else delete next[requirement.capabilityId];
    }
    try {
      const saved = await saveDataServicePreferences(
        suiteId,
        userId,
        workspaceId,
        next,
      );
      setPreferences(saved);
      setDraft(saved.capabilityServices);
      setMessage("项目数据路由已保存，下一次请求立即生效。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目设置保存失败");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="agent-settings-state" role="status">
        <LoaderCircle className="spin" size={20} aria-hidden="true" />
        正在读取项目设置…
      </div>
    );
  }

  return (
    <section className="suite-settings-page">
      <header className="settings-page-header">
        <div>
          <h1>{suiteLabel} · 项目设置</h1>
          <p>
            该二级目录包含 {modules.length} 个 Mod。数据服务由 Newma-Dock 统一托管，
            Mod 无需保存 API 地址、Token 或密钥。
          </p>
        </div>
        <button
          className="primary-action"
          type="button"
          onClick={() => void save()}
          disabled={saving || requirements.every((item) => !item.unified)}
        >
          {saving ? (
            <LoaderCircle className="spin" size={15} aria-hidden="true" />
          ) : (
            <Save size={15} aria-hidden="true" />
          )}
          保存数据路由
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

      <section className="settings-section" aria-labelledby="suite-members-heading">
        <div className="settings-section-heading">
          <div>
            <h2 id="suite-members-heading">项目页面</h2>
            <p>这里展示当前被归入该二级目录的所有 Mod。</p>
          </div>
        </div>
        <div className="suite-member-list">
          {modules.map((module) => (
            <div className="suite-member-row" key={module.moduleId}>
              <Settings2 size={15} aria-hidden="true" />
              <span>
                <strong>{module.manifest.navigation?.label || module.manifest.name}</strong>
                <small>{module.moduleId} · v{module.manifest.version}</small>
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="settings-section" aria-labelledby="suite-data-heading">
        <div className="settings-section-heading">
          <div>
            <h2 id="suite-data-heading">统一数据接口</h2>
            <p>
              “自动选择”按 Provider 优先级路由；指定 Provider 只影响当前用户、工作区和项目。
            </p>
          </div>
          <span>{requirements.length} 项数据能力</span>
        </div>

        {requirements.length === 0 ? (
          <div className="suite-empty-state">
            <Database size={18} aria-hidden="true" />
            <span>
              <strong>当前项目尚未声明统一数据能力</strong>
              <small>现有页面继续使用项目自带接口；后续可将 Data Action 改为无 service 的统一路由。</small>
            </span>
          </div>
        ) : (
          <div className="data-routing-list">
            {requirements.map((requirement) => {
              const item = catalog?.capabilities.find(
                (capability) => capability.id === requirement.capabilityId,
              );
              return (
                <div className="data-routing-row" key={requirement.capabilityId}>
                  <div className="data-capability-copy">
                    <strong>{requirement.capabilityId}</strong>
                    <small>
                      {requirement.moduleNames.join("、")} · {requirement.permissions.join(" / ")}
                    </small>
                    {requirement.fixedServices.length ? (
                      <span>固定服务：{requirement.fixedServices.join("、")}</span>
                    ) : null}
                  </div>
                  {requirement.unified ? (
                    <label className="data-provider-field">
                      <span>Provider</span>
                      <select
                        aria-label={`${requirement.capabilityId} Provider`}
                        value={draft[requirement.capabilityId] ?? ""}
                        disabled={!item?.providers.length}
                        onChange={(event) => setDraft((current) => ({
                          ...current,
                          [requirement.capabilityId]: event.target.value,
                        }))}
                      >
                        <option value="">
                          {item?.providers.length
                            ? `自动选择（${item.providers[0]?.name}）`
                            : "暂无可用 Provider"}
                        </option>
                        {item?.providers.map((provider) => (
                          <option value={provider.id} key={provider.id}>
                            {provider.name} · 已注册
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <span className="data-routing-fixed">由 Mod 固定</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="settings-section suite-agent-section" aria-labelledby="suite-agent-heading">
        <div>
          <h2 id="suite-agent-heading">Agent</h2>
          <p>项目页面仍可继承全局 Agent，或在 Agent 设置中按 Mod 单独覆盖。</p>
        </div>
        <button className="secondary-action" type="button" onClick={onOpenAgentSettings}>
          <Bot size={15} aria-hidden="true" />
          打开 Agent 设置
        </button>
      </section>
    </section>
  );
}
