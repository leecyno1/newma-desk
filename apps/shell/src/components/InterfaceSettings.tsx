import {
  FolderTree,
  GripVertical,
  Layers3,
  Monitor,
  Moon,
  PanelLeft,
  Pin,
  RotateCcw,
  Save,
  Sun,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { StoredMod } from "../api/modules";
import {
  sidebarProjectMark,
  compileSidebarNavigation,
  type SidebarProjectItem,
} from "../lib/sidebarNavigation";
import {
  EMPTY_SIDEBAR_NAVIGATION,
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
    description: "暖纸底色与深绿文字，适合长时间阅读",
    icon: Sun,
  },
  {
    id: "dark" as const,
    label: "深色",
    description: "Verdigris 深绿工作台与克制的暖金强调",
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
    ...(preferences.projects ? {
      projects: Object.fromEntries(
        Object.entries(preferences.projects).map(([projectId, preference]) => [
          projectId,
          { ...preference },
        ]),
      ),
    } : {}),
    ...(preferences.sections ? {
      sections: Object.fromEntries(
        Object.entries(preferences.sections).map(([projectId, sections]) => [
          projectId,
          Object.fromEntries(
            Object.entries(sections).map(([sectionId, preference]) => [
              sectionId,
              { ...preference },
            ]),
          ),
        ]),
      ),
    } : {}),
  };
}

function projectPages(project: SidebarProjectItem) {
  return [
    ...project.modules,
    ...project.sections.flatMap((section) => [
      ...section.modules,
      ...(section.settingsModule ? [section.settingsModule] : []),
    ]),
    ...(project.settingsModule ? [project.settingsModule] : []),
  ];
}

function projectMark(project: SidebarProjectItem) {
  return sidebarProjectMark(project);
}

function projectTitleDraft(
  preferences: SidebarNavigationPreferences,
  project: SidebarProjectItem,
) {
  const preference = preferences.projects?.[project.id];
  return preference && Object.hasOwn(preference, "label")
    ? preference.label ?? ""
    : project.name;
}

function hasProjectTitleOverride(
  preferences: SidebarNavigationPreferences,
  project: SidebarProjectItem,
) {
  const preference = preferences.projects?.[project.id];
  return (
    (preference !== undefined && Object.hasOwn(preference, "label")) ||
    project.name !== project.defaultName
  );
}

function removePreferenceLabel(
  preferences: Record<
    string,
    { label?: string; order?: number; pinned?: boolean }
  >,
  id: string,
) {
  const preference = preferences[id];
  if (!preference) return;
  delete preference.label;
  if (Object.keys(preference).length === 0) delete preferences[id];
}

function normalizeProjectTitles(
  preferences: SidebarNavigationPreferences,
  projects: SidebarProjectItem[],
) {
  const next = copyNavigationPreferences(preferences);
  for (const project of projects) {
    const preference = next.projects?.[project.id];
    if (!preference || !Object.hasOwn(preference, "label")) continue;
    const label = preference.label?.trim().slice(0, 40) ?? "";
    if (label) {
      preference.label = label;
      continue;
    }
    removePreferenceLabel(next.projects!, project.id);
    removePreferenceLabel(next.directories, project.id);
  }
  if (next.projects && Object.keys(next.projects).length === 0) {
    delete next.projects;
  }
  return next;
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
  const [navigationDraft, setNavigationDraft] = useState(
    navigationPreferences,
  );
  const [saved, setSaved] = useState(false);

  useEffect(
    () => setNavigationDraft(navigationPreferences),
    [navigationPreferences],
  );

  const navigation = useMemo(
    () => compileSidebarNavigation(modules, categoryOverrides, navigationDraft),
    [categoryOverrides, modules, navigationDraft],
  );

  const updateProjectTitle = (projectId: string, value: string) => {
    setSaved(false);
    setNavigationDraft((current) => {
      const next = copyNavigationPreferences(current);
      next.projects = { ...(next.projects ?? {}) };
      next.projects[projectId] = {
        ...next.projects[projectId],
        label: value.slice(0, 40),
      };
      return next;
    });
  };

  const useDefaultProjectTitle = (projectId: string) => {
    setSaved(false);
    setNavigationDraft((current) => {
      const next = copyNavigationPreferences(current);
      if (next.projects) {
        removePreferenceLabel(next.projects, projectId);
        if (Object.keys(next.projects).length === 0) delete next.projects;
      }
      removePreferenceLabel(next.directories, projectId);
      return next;
    });
  };

  const save = () => {
    const normalizedNavigation = normalizeProjectTitles(
      navigation.preferences,
      navigation.projects,
    );
    setNavigationDraft(normalizedNavigation);
    onNavigationPreferencesChange(normalizedNavigation);
    setSaved(true);
  };

  const reset = () => {
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
          <p>统一主题与项目式导航，所有选择只保存在当前浏览器。</p>
        </div>
      </header>

      <section className="settings-section" aria-labelledby="theme-heading">
        <div className="settings-section-heading">
          <div>
            <h2 id="theme-heading">主题</h2>
            <p>Desk 与 Numa Agent 共用 Verdigris 深绿、暖金和紧凑的信息密度。</p>
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

      <section className="settings-section" aria-labelledby="project-navigation-heading">
        <div className="settings-section-heading category-heading">
          <div>
            <h2 id="project-navigation-heading">项目导航</h2>
            <p>
              一级只显示中文项目短标；项目标题可在本机自定义，二级标题与中文短标会自动同步。
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
          <span><PanelLeft size={13} aria-hidden="true" />项目标志与页面面板一体折叠</span>
          <span><GripVertical size={13} aria-hidden="true" />拖拽项目或项目内页面排序</span>
          <span><Pin size={13} aria-hidden="true" />冻结后保持位置并禁止拖动</span>
          <span><FolderTree size={13} aria-hidden="true" />页面不会被拖离所属项目</span>
          <span><Layers3 size={13} aria-hidden="true" />自定义标题仅保存在当前浏览器</span>
        </div>

        {Object.keys(categoryOverrides).length > 0 ? (
          <div className="settings-notice settings-warning" role="status">
            检测到 {Object.keys(categoryOverrides).length} 项旧版分类设置。项目式导航不再使用它们。
            <button
              type="button"
              className="inline-settings-action"
              onClick={() => onCategoryOverridesChange({})}
            >
              清除旧设置
            </button>
          </div>
        ) : null}

        {saved ? (
          <div className="settings-notice settings-success" role="status">
            项目导航已保存，左侧栏已立即更新。
          </div>
        ) : null}

        <div className="project-navigation-editor">
          {navigation.projects.map((project) => (
            <section className="project-navigation-card" key={project.id}>
              <header className="project-navigation-card-header">
                <span className="project-navigation-mark" aria-hidden="true">
                  {projectMark(project)}
                </span>
                <span>
                  <strong>{project.name}</strong>
                  <small>{project.id} · {projectPages(project).length} 个页面</small>
                </span>
                <span className="project-navigation-source">
                  <Layers3 size={12} aria-hidden="true" />
                  {hasProjectTitleOverride(navigationDraft, project)
                    ? "本地标题"
                    : "Manifest 默认"}
                </span>
              </header>

              <div className="project-title-editor">
                <label className="project-title-field">
                  <span>一级标题</span>
                  <input
                    type="text"
                    aria-label={`${project.defaultName} 一级标题`}
                    aria-describedby={`project-title-hint-${project.id}`}
                    aria-invalid={!projectTitleDraft(navigationDraft, project).trim()}
                    maxLength={40}
                    value={projectTitleDraft(navigationDraft, project)}
                    onChange={(event) => updateProjectTitle(
                      project.id,
                      event.target.value,
                    )}
                  />
                  <small
                    id={`project-title-hint-${project.id}`}
                    className="project-title-hint"
                    data-invalid={!projectTitleDraft(navigationDraft, project).trim() || undefined}
                  >
                    {projectTitleDraft(navigationDraft, project).trim()
                      ? `默认：${project.defaultName} · 标志：${projectMark(project)}`
                      : `标题不能为空；保存后将恢复“${project.defaultName}”`}
                  </small>
                </label>
                <button
                  type="button"
                  className="row-reset-action project-title-reset"
                  aria-label={`恢复 ${project.defaultName} 默认标题`}
                  disabled={!hasProjectTitleOverride(navigationDraft, project)}
                  onClick={() => useDefaultProjectTitle(project.id)}
                >
                  <RotateCcw size={12} aria-hidden="true" />
                  恢复默认
                </button>
              </div>

              <div className="category-editor-list">
                {projectPages(project).map((item) => {
                  const isSettings = item.role === "settings";
                  return (
                    <div className="category-editor-row project-page-editor-row" key={item.module.moduleId}>
                      <span className="category-module-name">
                        <FolderTree size={16} aria-hidden="true" />
                        <span>
                          <strong>{item.label}</strong>
                          <small>
                            {item.module.moduleId} · {isSettings ? "模组设置" : "项目页面"}
                          </small>
                        </span>
                      </span>
                      <span className="navigation-static-field">
                        <small>所属栏目</small>
                        <strong>{project.name}</strong>
                      </span>
                      <span className="navigation-static-field">
                        <small>完整项目</small>
                        <strong>{item.directory?.label ?? "独立 Mod"}</strong>
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}
