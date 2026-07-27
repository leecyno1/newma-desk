import {
  FolderCog,
  GripVertical,
  Monitor,
  Moon,
  Pin,
  RotateCcw,
  Save,
  Sun,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { StoredMod } from "../api/modules";
import {
  customSidebarDirectory,
  defaultCategoryLabel,
  defaultDirectory,
  EMPTY_SIDEBAR_NAVIGATION,
  type SidebarDirectoryRef,
  type SidebarNavigationPreferences,
  type ThemeMode,
} from "../lib/workspacePreferences";

interface InterfaceSettingsProps {
  modules: StoredMod[];
  themeMode: ThemeMode;
  onThemeModeChange: (mode: ThemeMode) => void;
  categoryOverrides: Record<string, string>;
  onCategoryOverridesChange: (overrides: Record<string, string>) => void;
  navigationPreferences: SidebarNavigationPreferences;
  onNavigationPreferencesChange: (
    preferences: SidebarNavigationPreferences,
  ) => void;
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

function copyNavigationPreferences(
  preferences: SidebarNavigationPreferences,
): SidebarNavigationPreferences {
  return {
    version: 1,
    modules: Object.fromEntries(
      Object.entries(preferences.modules).map(([moduleId, preference]) => [
        moduleId,
        {
          ...preference,
          ...(preference.directory
            ? { directory: { ...preference.directory } }
            : {}),
        },
      ]),
    ),
    directories: Object.fromEntries(
      Object.entries(preferences.directories).map(([directoryId, preference]) => [
        directoryId,
        { ...preference },
      ]),
    ),
  };
}

function hasDirectoryOverride(
  preferences: SidebarNavigationPreferences,
  moduleId: string,
) {
  return Object.hasOwn(preferences.modules[moduleId] ?? {}, "directory");
}

function effectiveDirectory(
  module: StoredMod,
  preferences: SidebarNavigationPreferences,
): SidebarDirectoryRef | null {
  const preference = preferences.modules[module.moduleId];
  if (preference && Object.hasOwn(preference, "directory")) {
    return preference.directory ?? null;
  }
  return defaultDirectory(module);
}

export function InterfaceSettings({
  modules,
  themeMode,
  onThemeModeChange,
  categoryOverrides,
  onCategoryOverridesChange,
  navigationPreferences,
  onNavigationPreferencesChange,
}: InterfaceSettingsProps) {
  const [categoryDraft, setCategoryDraft] = useState(categoryOverrides);
  const [navigationDraft, setNavigationDraft] = useState(
    navigationPreferences,
  );
  const [saved, setSaved] = useState(false);

  useEffect(() => setCategoryDraft(categoryOverrides), [categoryOverrides]);
  useEffect(
    () => setNavigationDraft(navigationPreferences),
    [navigationPreferences],
  );

  const categorySuggestions = useMemo(
    () =>
      [...new Set([
        ...modules.map(defaultCategoryLabel),
        ...Object.values(categoryDraft)
          .map((label) => label.trim())
          .filter(Boolean),
      ])].sort((left, right) => left.localeCompare(right, "zh-CN")),
    [categoryDraft, modules],
  );

  const directoryCandidates = useMemo(() => {
    const candidates = new Map<string, SidebarDirectoryRef>();
    for (const module of modules) {
      const groupLabel =
        categoryDraft[module.moduleId]?.trim() || defaultCategoryLabel(module);
      const directory = effectiveDirectory(module, navigationDraft);
      if (directory) {
        candidates.set(`${groupLabel}\u0000${directory.label}`, directory);
      }
    }
    return candidates;
  }, [categoryDraft, modules, navigationDraft]);

  const directorySuggestions = useMemo(
    () =>
      [...new Set(
        [...directoryCandidates.keys()].map((key) => key.split("\u0000")[1]),
      )]
        .filter((label): label is string => Boolean(label))
        .sort((left, right) => left.localeCompare(right, "zh-CN")),
    [directoryCandidates],
  );

  const updateCategory = (moduleId: string, value: string) => {
    setSaved(false);
    setCategoryDraft((current) => ({ ...current, [moduleId]: value }));
  };

  const useDefaultCategory = (moduleId: string) => {
    setSaved(false);
    setCategoryDraft((current) => {
      const next = { ...current };
      delete next[moduleId];
      return next;
    });
  };

  const updateDirectory = (module: StoredMod, value: string) => {
    setSaved(false);
    const label = value.trim();
    const groupLabel =
      categoryDraft[module.moduleId]?.trim() || defaultCategoryLabel(module);
    const directory = label
      ? directoryCandidates.get(`${groupLabel}\u0000${label}`) ??
        customSidebarDirectory(groupLabel, label)
      : null;
    setNavigationDraft((current) => {
      const next = copyNavigationPreferences(current);
      next.modules[module.moduleId] = {
        ...next.modules[module.moduleId],
        directory,
      };
      return next;
    });
  };

  const useDefaultDirectory = (moduleId: string) => {
    setSaved(false);
    setNavigationDraft((current) => {
      const next = copyNavigationPreferences(current);
      const preference = next.modules[moduleId];
      if (!preference) return next;
      delete preference.directory;
      if (Object.keys(preference).length === 0) delete next.modules[moduleId];
      return next;
    });
  };

  const showAtPrimaryLevel = (moduleId: string) => {
    setSaved(false);
    setNavigationDraft((current) => {
      const next = copyNavigationPreferences(current);
      next.modules[moduleId] = {
        ...next.modules[moduleId],
        directory: null,
      };
      return next;
    });
  };

  const save = () => {
    const normalizedCategories = Object.fromEntries(
      Object.entries(categoryDraft).flatMap(([moduleId, label]) => {
        const trimmed = label.trim();
        return trimmed ? ([[moduleId, trimmed]] as const) : [];
      }),
    );
    const normalizedNavigation = copyNavigationPreferences(navigationDraft);
    setCategoryDraft(normalizedCategories);
    setNavigationDraft(normalizedNavigation);
    onCategoryOverridesChange(normalizedCategories);
    onNavigationPreferencesChange(normalizedNavigation);
    setSaved(true);
  };

  const reset = () => {
    setCategoryDraft({});
    setNavigationDraft(EMPTY_SIDEBAR_NAVIGATION);
    onCategoryOverridesChange({});
    onNavigationPreferencesChange(EMPTY_SIDEBAR_NAVIGATION);
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
            <h2 id="category-heading">侧边栏与二级目录</h2>
            <p>
              一级分类和二级目录均可自定义。排序、跨目录拖放和冻结可直接在左侧导航完成。
            </p>
          </div>
          <div className="settings-actions">
            <button type="button" className="secondary-action" onClick={reset}>
              <RotateCcw size={14} aria-hidden="true" />
              恢复全部默认
            </button>
            <button type="button" className="primary-action" onClick={save}>
              <Save size={14} aria-hidden="true" />
              保存导航
            </button>
          </div>
        </div>

        <div className="sidebar-customization-help">
          <span><GripVertical size={13} aria-hidden="true" />拖拽页面或目录调整顺序</span>
          <span><Pin size={13} aria-hidden="true" />冻结后保持位置并禁止拖动</span>
          <span><FolderCog size={13} aria-hidden="true" />同名目录会自动合并</span>
        </div>

        {saved ? (
          <div className="settings-notice settings-success" role="status">
            导航设置已保存，左侧边栏已立即更新。
          </div>
        ) : null}

        <datalist id="category-suggestions">
          {categorySuggestions.map((category) => (
            <option value={category} key={category} />
          ))}
        </datalist>
        <datalist id="directory-suggestions">
          {directorySuggestions.map((directory) => (
            <option value={directory} key={directory} />
          ))}
        </datalist>

        <div className="category-editor-list">
          {modules.map((module) => {
            const defaultLabel = defaultCategoryLabel(module);
            const manifestDirectory = defaultDirectory(module);
            const directory = effectiveDirectory(module, navigationDraft);
            const directoryOverridden = hasDirectoryOverride(
              navigationDraft,
              module.moduleId,
            );
            return (
              <div className="category-editor-row" key={module.moduleId}>
                <span className="category-module-name">
                  <FolderCog size={16} aria-hidden="true" />
                  <span>
                    <strong>{module.manifest.name}</strong>
                    <small>
                      {module.moduleId} · 默认：{defaultLabel}
                      {manifestDirectory ? ` / ${manifestDirectory.label}` : " / 一级"}
                    </small>
                  </span>
                </span>
                <label className="navigation-field">
                  <span>一级分类</span>
                  <input
                    aria-label={`${module.manifest.name}分类`}
                    list="category-suggestions"
                    value={categoryDraft[module.moduleId] ?? ""}
                    placeholder={defaultLabel}
                    onChange={(event) =>
                      updateCategory(module.moduleId, event.target.value)
                    }
                  />
                </label>
                <label className="navigation-field">
                  <span>二级目录</span>
                  <input
                    aria-label={`${module.manifest.name}二级目录`}
                    list="directory-suggestions"
                    value={directory?.label ?? ""}
                    placeholder="一级直接显示"
                    onChange={(event) => updateDirectory(module, event.target.value)}
                  />
                </label>
                <span className="row-navigation-actions">
                  <button
                    type="button"
                    className="row-reset-action"
                    onClick={() => showAtPrimaryLevel(module.moduleId)}
                    disabled={directoryOverridden && directory === null}
                  >
                    一级显示
                  </button>
                  <button
                    type="button"
                    className="row-reset-action"
                    onClick={() => {
                      useDefaultCategory(module.moduleId);
                      useDefaultDirectory(module.moduleId);
                    }}
                    disabled={
                      !categoryDraft[module.moduleId] && !directoryOverridden
                    }
                  >
                    使用默认
                  </button>
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
