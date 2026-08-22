import {
  Bot,
  GripVertical,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  PinOff,
  RefreshCw,
  Settings,
  Store,
} from "lucide-react";
import { useEffect, useMemo, useState, type DragEvent } from "react";

import type { StoredMod } from "../api/modules";
import newmaMarkUrl from "../assets/newma-mark.svg";
import {
  moveSidebarProject,
  moveSidebarModule,
  sidebarProjectMark,
  toggleSidebarModulePinned,
  toggleSidebarProjectPinned,
  type SidebarDirectoryItem,
  type SidebarModuleItem,
  type SidebarNavigationModel,
  type SidebarProjectItem,
} from "../lib/sidebarNavigation";
import { sidebarGroupTone } from "../lib/sidebarGroupTheme";
import type {
  SidebarDirectoryRef,
  SidebarNavigationPreferences,
} from "../lib/workspacePreferences";

interface SidebarProps {
  navigation: SidebarNavigationModel;
  selectedId: string | undefined;
  onSelect: (mod: StoredMod) => void;
  onReload: () => void;
  loading: boolean;
  agentSettingsActive: boolean;
  onOpenAgentSettings: () => void;
  interfaceSettingsActive: boolean;
  onOpenInterfaceSettings: () => void;
  storeActive: boolean;
  onOpenStore: () => void;
  suiteSettingsDirectoryId: string | undefined;
  onOpenSuiteSettings: (directory: SidebarDirectoryItem) => void;
  onNavigationPreferencesChange: (preferences: SidebarNavigationPreferences) => void;
}

type DraggedItem =
  | { type: "module"; id: string; projectId: string }
  | { type: "project"; id: string };

const MOBILE_NAVIGATION_QUERY = "(max-width: 720px)";

function isMobileNavigationViewport() {
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia(MOBILE_NAVIGATION_QUERY).matches;
}

function ProjectMark({
  project,
}: {
  project: SidebarProjectItem;
}) {
  return (
    <span className="project-letter-mark" aria-hidden="true">
      {sidebarProjectMark(project)}
    </span>
  );
}

function PinButton({
  label,
  pinned,
  onClick,
}: {
  label: string;
  pinned: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="sidebar-pin-button"
      aria-label={`${pinned ? "取消冻结" : "冻结"} ${label}`}
      title={pinned ? "取消冻结" : "冻结位置"}
      onClick={onClick}
    >
      {pinned ? <PinOff size={12} aria-hidden="true" /> : <Pin size={12} aria-hidden="true" />}
    </button>
  );
}

function ModuleRow({
  item,
  index,
  selected,
  onSelect,
  onPin,
  onDragStart,
  onDragEnd,
  onDrop,
}: {
  item: SidebarModuleItem;
  index: number;
  selected: boolean;
  onSelect: () => void;
  onPin: () => void;
  onDragStart: (event: DragEvent<HTMLDivElement>) => void;
  onDragEnd: () => void;
  onDrop: (event: DragEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className="module-nav-row"
      data-module-id={item.module.moduleId}
      data-tone={(index % 5) + 1}
      data-pinned={item.pinned || undefined}
      draggable={!item.pinned}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
    >
      <GripVertical className="sidebar-drag-handle" size={12} aria-hidden="true" />
      <button
        className="module-button"
        type="button"
        aria-label={item.label}
        aria-current={selected ? "page" : undefined}
        onClick={onSelect}
      >
        <span className="module-nav-label">{item.label}</span>
      </button>
      <PinButton label={item.label} pinned={item.pinned} onClick={onPin} />
    </div>
  );
}

function projectPageCount(project: SidebarProjectItem) {
  return project.settingsDirectory.modules.length + (project.settingsModule ? 1 : 0);
}

export function Sidebar({
  navigation,
  selectedId,
  onSelect,
  onReload,
  loading,
  agentSettingsActive,
  onOpenAgentSettings,
  interfaceSettingsActive,
  onOpenInterfaceSettings,
  storeActive,
  onOpenStore,
  suiteSettingsDirectoryId,
  onOpenSuiteSettings,
  onNavigationPreferencesChange,
}: SidebarProps) {
  const { groups, preferences, projects } = navigation;
  const selectedItem = useMemo(
    () => selectedId ? navigation.modulesById.get(selectedId) : undefined,
    [navigation, selectedId],
  );
  const settingsProject = useMemo(
    () => projects.find((project) => (
      project.settingsDirectory.id === suiteSettingsDirectoryId
      || project.sections.some((section) => section.id === suiteSettingsDirectoryId)
    )),
    [projects, suiteSettingsDirectoryId],
  );
  const [activeProjectId, setActiveProjectId] = useState<string>();
  const [navigationCollapsed, setNavigationCollapsed] = useState(
    () => isMobileNavigationViewport(),
  );
  const [dragged, setDragged] = useState<DraggedItem>();

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(MOBILE_NAVIGATION_QUERY);
    const collapseOnMobile = (event: MediaQueryListEvent | MediaQueryList) => {
      if (event.matches) setNavigationCollapsed(true);
    };
    collapseOnMobile(media);
    media.addEventListener("change", collapseOnMobile);
    return () => media.removeEventListener("change", collapseOnMobile);
  }, []);

  useEffect(() => {
    const requestedProjectId = settingsProject?.id ?? selectedItem?.projectId;
    setActiveProjectId((current) => {
      if (requestedProjectId && navigation.projectsById.has(requestedProjectId)) {
        return requestedProjectId;
      }
      if (current && navigation.projectsById.has(current)) return current;
      return projects[0]?.id;
    });
  }, [navigation.projectsById, projects, selectedItem?.projectId, settingsProject?.id]);

  const activeProject = activeProjectId
    ? navigation.projectsById.get(activeProjectId)
    : undefined;
  const showProjectDataSettings = Boolean(
    activeProject &&
    (activeProject.modules.length > 0 || activeProject.sections.length > 0),
  );

  const collapseNavigation = () => setNavigationCollapsed(true);
  const expandNavigation = () => setNavigationCollapsed(false);
  const selectModule = (module: StoredMod) => {
    onSelect(module);
    if (isMobileNavigationViewport()) collapseNavigation();
  };

  const activateProject = (project: SidebarProjectItem) => {
    setActiveProjectId(project.id);
    expandNavigation();
    const defaultModule = (
      project.settingsDirectory.modules[0] ?? project.settingsModule
    )?.module;
    if (defaultModule && defaultModule.moduleId !== selectedId) {
      onSelect(defaultModule);
    } else if (!defaultModule) {
      onOpenSuiteSettings(project.settingsDirectory);
    }
  };

  const beginModuleDrag = (
    event: DragEvent<HTMLDivElement>,
    item: SidebarModuleItem,
  ) => {
    if (item.pinned) {
      event.preventDefault();
      return;
    }
    setDragged({ type: "module", id: item.module.moduleId, projectId: item.projectId });
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", item.module.moduleId);
  };

  const dropModule = (
    event: DragEvent,
    project: SidebarProjectItem,
    directory: SidebarDirectoryRef | null,
    beforeModuleId?: string,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    if (!dragged || dragged.type !== "module" || dragged.projectId !== project.id) return;
    onNavigationPreferencesChange(moveSidebarModule(
      preferences,
      groups,
      dragged.id,
      {
        projectId: project.id,
        directory: directory ? { id: directory.id, label: directory.label } : null,
        ...(beforeModuleId ? { beforeModuleId } : {}),
      },
    ));
    setDragged(undefined);
  };

  const beginProjectDrag = (
    event: DragEvent<HTMLDivElement>,
    project: SidebarProjectItem,
  ) => {
    if (project.pinned) {
      event.preventDefault();
      return;
    }
    setDragged({ type: "project", id: project.id });
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", project.id);
  };

  const dropProject = (
    event: DragEvent,
    beforeProjectId?: string,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    if (!dragged || dragged.type !== "project") return;
    onNavigationPreferencesChange(moveSidebarProject(
      preferences,
      projects,
      dragged.id,
      beforeProjectId,
    ));
    setDragged(undefined);
  };

  const renderModule = (
    item: SidebarModuleItem,
    project: SidebarProjectItem,
    directory: SidebarDirectoryRef | null,
  ) => (
    <ModuleRow
      key={`${item.module.moduleId}@${item.module.revision}`}
      item={item}
      index={Math.max(0, project.settingsDirectory.modules.findIndex((member) => member.module.moduleId === item.module.moduleId))}
      selected={item.module.moduleId === selectedId}
      onSelect={() => selectModule(item.module)}
      onPin={() => onNavigationPreferencesChange(
        toggleSidebarModulePinned(preferences, item.module.moduleId),
      )}
      onDragStart={(event) => beginModuleDrag(event, item)}
      onDragEnd={() => setDragged(undefined)}
      onDrop={(event) => dropModule(
        event,
        project,
        directory ?? item.directory,
        item.module.moduleId,
      )}
    />
  );

  return (
    <div
      className="sidebar-shell"
      data-navigation-collapsed={navigationCollapsed ? "true" : "false"}
      data-secondary-open={activeProject && !navigationCollapsed ? "true" : "false"}
    >
      <button
        type="button"
        className="sidebar-restore-button"
        aria-label="展开一级与二级导航"
        title="展开导航"
        onClick={expandNavigation}
      >
        <PanelLeftOpen size={16} aria-hidden="true" />
      </button>

      <aside className="sidebar" aria-label="Newma-Desk 项目导航">
        <div className="project-rail">
          <div className="desk-rail-mark" title="Newma-Desk · 智能模组工作台">
            <img src={newmaMarkUrl} alt="Newma-Desk" />
          </div>
          <nav
            aria-label="Newma-Desk Mod 导航"
            className="project-rail-nav"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => dropProject(event)}
          >
            {projects.map((project) => (
              <div
                className="project-rail-item"
                data-pinned={project.pinned || undefined}
                draggable={!project.pinned}
                key={project.id}
                onDragStart={(event) => beginProjectDrag(event, project)}
                onDragEnd={() => setDragged(undefined)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => dropProject(event, project.id)}
              >
                <button
                  type="button"
                  className="project-rail-button"
                  data-tone={sidebarGroupTone(project.name)}
                  disabled={loading}
                  aria-label={`${project.name} 项目`}
                  aria-expanded={project.id === activeProject?.id}
                  aria-current={project.id === activeProject?.id ? "page" : undefined}
                  title={`${project.name} · ${projectPageCount(project)} 个页面`}
                  onClick={() => activateProject(project)}
                >
                  <ProjectMark project={project} />
                </button>
                <button
                  type="button"
                  className="project-rail-pin"
                  aria-label={`${project.pinned ? "取消冻结" : "冻结"} ${project.name} 项目`}
                  title={project.pinned ? "取消冻结项目" : "冻结项目位置"}
                  onClick={() => onNavigationPreferencesChange(
                    toggleSidebarProjectPinned(preferences, project.id),
                  )}
                >
                  {project.pinned ? <PinOff size={10} aria-hidden="true" /> : <Pin size={10} aria-hidden="true" />}
                </button>
              </div>
            ))}
          </nav>
          <div className="project-rail-tools">
            <button type="button" aria-label="Mod 商店" title="Mod 商店" aria-current={storeActive ? "page" : undefined} onClick={onOpenStore}><Store size={17} aria-hidden="true" /></button>
            <button type="button" aria-label="界面设置" title="界面设置" aria-current={interfaceSettingsActive ? "page" : undefined} onClick={onOpenInterfaceSettings}><Palette size={17} aria-hidden="true" /></button>
            <button type="button" aria-label="Agent 设置" title="Agent 设置" aria-current={agentSettingsActive ? "page" : undefined} onClick={onOpenAgentSettings}><Bot size={17} aria-hidden="true" /></button>
            <button type="button" aria-label={loading ? "正在加载 Mod" : "重新加载 Mod"} title={loading ? "正在加载 Mod" : "重新加载 Mod"} disabled={loading} onClick={onReload}><RefreshCw className={loading ? "spin" : undefined} size={17} aria-hidden="true" /></button>
          </div>
        </div>

        {activeProject ? (
          <div
            className="project-panel secondary-sidebar"
            role="complementary"
            aria-label={`${activeProject.name} 二级导航`}
          >
            <header className="project-panel-header">
              <div className="project-panel-identity">
                <span className="project-panel-product">Newma-Desk</span>
                <strong>{activeProject.name}</strong>
                <small>{projectPageCount(activeProject)} 个页面</small>
              </div>
              <button
                type="button"
                aria-label="收起一级与二级导航"
                title="收起导航"
                onClick={collapseNavigation}
              >
                <PanelLeftClose size={15} aria-hidden="true" />
              </button>
            </header>

            {activeProject.description ? (
              <p className="project-panel-description">{activeProject.description}</p>
            ) : null}

            <nav
              className="project-module-list secondary-module-list"
              aria-label={`${activeProject.name} 页面`}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => dropModule(event, activeProject, null)}
            >
              {activeProject.settingsDirectory.modules.map((item) => (
                renderModule(item, activeProject, item.directory)
              ))}
              {activeProject.modules.length === 0 && activeProject.sections.length === 0 ? (
                <div className="project-panel-no-pages">
                  <strong>暂无页面</strong>
                  <small>后续接入此领域的 Mod 会自动显示在这里。</small>
                </div>
              ) : null}
            </nav>

            {activeProject.settingsModule || showProjectDataSettings ? (
              <footer className="project-panel-footer secondary-sidebar-footer">
                {activeProject.settingsModule ? (
                  <button
                    type="button"
                    className="secondary-settings-button"
                    aria-current={activeProject.settingsModule.module.moduleId === selectedId ? "page" : undefined}
                    onClick={() => selectModule(activeProject.settingsModule!.module)}
                  >
                    <Settings size={14} aria-hidden="true" />
                    模组设置
                  </button>
                ) : null}
                {showProjectDataSettings ? (
                  <button
                    type="button"
                    className="secondary-settings-button"
                    aria-current={suiteSettingsDirectoryId === activeProject.settingsDirectory.id ? "page" : undefined}
                    onClick={() => onOpenSuiteSettings(activeProject.settingsDirectory)}
                  >
                    <Settings size={14} aria-hidden="true" />
                    栏目数据与能力
                  </button>
                ) : null}
                <small>模组设置管理业务参数；数据与能力管理 Desk 接入。页面仅可在项目内排序。</small>
              </footer>
            ) : null}
          </div>
        ) : (
          <div className="project-panel project-panel-empty">
            <strong>暂无项目</strong>
            <small>安装或发布 Mod 后会自动接入。</small>
          </div>
        )}
      </aside>
    </div>
  );
}
