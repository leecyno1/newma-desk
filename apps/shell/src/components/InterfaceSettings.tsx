import {
  FolderCog,
  Monitor,
  Moon,
  RotateCcw,
  Save,
  Sun,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { StoredMod } from "../api/modules";
import {
  defaultCategoryLabel,
  type ThemeMode,
} from "../lib/workspacePreferences";

interface InterfaceSettingsProps {
  modules: StoredMod[];
  themeMode: ThemeMode;
  onThemeModeChange: (mode: ThemeMode) => void;
  categoryOverrides: Record<string, string>;
  onCategoryOverridesChange: (overrides: Record<string, string>) => void;
}

const themeOptions = [
  {
    id: "system" as const,
    label: "跟随系统",
    description: "自动响应电脑的浅色或深色外观",
    icon: Monitor,
  },
  {
    id: "light" as const,
    label: "浅色",
    description: "保持清晰的白色工作台",
    icon: Sun,
  },
  {
    id: "dark" as const,
    label: "深色",
    description: "使用中性的深蓝黑工作台",
    icon: Moon,
  },
];

export function InterfaceSettings({
  modules,
  themeMode,
  onThemeModeChange,
  categoryOverrides,
  onCategoryOverridesChange,
}: InterfaceSettingsProps) {
  const [draft, setDraft] = useState(categoryOverrides);
  const [saved, setSaved] = useState(false);

  useEffect(() => setDraft(categoryOverrides), [categoryOverrides]);

  const categorySuggestions = useMemo(
    () =>
      [...new Set([
        ...modules.map(defaultCategoryLabel),
        ...Object.values(draft).map((label) => label.trim()).filter(Boolean),
      ])].sort((left, right) => left.localeCompare(right, "zh-CN")),
    [draft, modules],
  );

  const updateCategory = (moduleId: string, value: string) => {
    setSaved(false);
    setDraft((current) => ({ ...current, [moduleId]: value }));
  };

  const useDefault = (moduleId: string) => {
    setSaved(false);
    setDraft((current) => {
      const next = { ...current };
      delete next[moduleId];
      return next;
    });
  };

  const save = () => {
    const normalized = Object.fromEntries(
      Object.entries(draft).flatMap(([moduleId, label]) => {
        const trimmed = label.trim();
        return trimmed ? ([[moduleId, trimmed]] as const) : [];
      }),
    );
    setDraft(normalized);
    onCategoryOverridesChange(normalized);
    setSaved(true);
  };

  const reset = () => {
    setDraft({});
    onCategoryOverridesChange({});
    setSaved(true);
  };

  return (
    <div className="interface-settings-page">
      <header className="settings-page-header">
        <div>
          <h1>界面设置</h1>
          <p>统一主题、字体和导航结构，所有选择只保存在当前浏览器。</p>
        </div>
      </header>

      <section className="settings-section" aria-labelledby="theme-heading">
        <div className="settings-section-heading">
          <div>
            <h2 id="theme-heading">主题</h2>
            <p>浅色、深色和系统外观共享同一套字号、间距与组件比例。</p>
          </div>
        </div>
        <div className="theme-option-grid">
          {themeOptions.map(({ id, label, description, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className="theme-option"
              aria-label={label}
              aria-pressed={themeMode === id}
              onClick={() => onThemeModeChange(id)}
            >
              <Icon size={18} aria-hidden="true" />
              <span>
                <strong>{label}</strong>
                <small>{description}</small>
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="settings-section" aria-labelledby="category-heading">
        <div className="settings-section-heading category-heading">
          <div>
            <h2 id="category-heading">侧边栏分类</h2>
            <p>输入任意分类名称。相同名称的 Mod 会归入同一组，不再受预设分类限制。</p>
          </div>
          <div className="settings-actions">
            <button type="button" className="secondary-action" onClick={reset}>
              <RotateCcw size={14} aria-hidden="true" />
              恢复默认
            </button>
            <button type="button" className="primary-action" onClick={save}>
              <Save size={14} aria-hidden="true" />
              保存分类
            </button>
          </div>
        </div>

        {saved ? (
          <div className="settings-notice settings-success" role="status">
            分类已保存，左侧导航已立即更新。
          </div>
        ) : null}

        <datalist id="category-suggestions">
          {categorySuggestions.map((category) => (
            <option value={category} key={category} />
          ))}
        </datalist>

        <div className="category-editor-list">
          {modules.map((module) => {
            const defaultLabel = defaultCategoryLabel(module);
            return (
              <div className="category-editor-row" key={module.moduleId}>
                <span className="category-module-name">
                  <FolderCog size={16} aria-hidden="true" />
                  <span>
                    <strong>{module.manifest.name}</strong>
                    <small>{module.moduleId} · 默认：{defaultLabel}</small>
                  </span>
                </span>
                <label>
                  <span className="sr-only">{module.manifest.name}分类</span>
                  <input
                    aria-label={`${module.manifest.name}分类`}
                    list="category-suggestions"
                    value={draft[module.moduleId] ?? ""}
                    placeholder={defaultLabel}
                    onChange={(event) =>
                      updateCategory(module.moduleId, event.target.value)
                    }
                  />
                </label>
                <button
                  type="button"
                  className="row-reset-action"
                  onClick={() => useDefault(module.moduleId)}
                  disabled={!draft[module.moduleId]}
                >
                  使用默认
                </button>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
