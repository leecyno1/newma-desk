import {
  BarChart3,
  Binary,
  BookOpenText,
  Bot,
  Boxes,
  CalendarDays,
  CandlestickChart,
  ChevronRight,
  Folder,
  FolderOpen,
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
import {
  moveSidebarDirectory,
  moveSidebarModule,
  toggleSidebarDirectoryPinned,
  toggleSidebarModulePinned,
  type SidebarDirectoryItem,
  type SidebarGroupItem,
  type SidebarModuleItem,
  type SidebarNavigationModel,
} from "../lib/sidebarNavigation";
import { sidebarGroupTone } from "../lib/sidebarGroupTheme";
import type { SidebarNavigationPreferences } from "../lib/workspacePreferences";

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
  | { type: "module"; id: string }
  | { type: "directory"; id: string; groupLabel: string };

const categoryIcons = {
  today: CalendarDays,
  research: BookOpenText,
  market: BarChart3,
  quant: Binary,
  trading: CandlestickChart,
  settings: Settings,
  module: Boxes,
} as const;

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
  selected,
  onSelect,
  onPin,
  onDragStart,
  onDragEnd,
  onDrop,
}: {
  item: SidebarModuleItem;
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
        aria-current={selected ? "page" : undefined}
        onClick={onSelect}
      >
        {item.label}
      </button>
      <PinButton label={item.label} pinned={item.pinned} onClick={onPin} />
    </div>
  );
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
  const { groups, preferences } = navigation;
  const selectedItem = useMemo(
    () => selectedId ? navigation.modulesById.get(selectedId) : undefined,
    [navigation, selectedId],
  );
  const [openDirectoryId, setOpenDirectoryId] = useState<string>();
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  const [dragged, setDragged] = useState<DraggedItem>();

  useEffect(() => {
    setOpenDirectoryId(
      suiteSettingsDirectoryId ?? selectedItem?.directory?.id,
    );
  }, [selectedItem?.directory?.id, suiteSettingsDirectoryId]);

  const activeDirectory = openDirectoryId
    ? navigation.directoriesById.get(openDirectoryId)
    : undefined;

  const collapseNavigation = () => setNavigationCollapsed(true);
  const expandNavigation = () => setNavigationCollapsed(false);

  const activateDirectory = (directory: SidebarDirectoryItem) => {
    if (directory.id === activeDirectory?.id) {
      setOpenDirectoryId(undefined);
      return;
    }

    setOpenDirectoryId(directory.id);
    expandNavigation();
    const defaultModule = (
      directory.modules[0] ?? directory.settingsModule
    )?.module;
    if (defaultModule && defaultModule.moduleId !== selectedId) {
      onSelect(defaultModule);
    }
  };

  const beginModuleDrag = (event: DragEvent<HTMLDivElement>, item: SidebarModuleItem) => {
    if (item.pinned) {
      event.preventDefault();
      return;
    }
    setDragged({ type: "module", id: item.module.moduleId });
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", item.module.moduleId);
  };

  const beginDirectoryDrag = (
    event: DragEvent<HTMLDivElement>,
    group: SidebarGroupItem,
    directory: SidebarDirectoryItem,
  ) => {
    if (directory.pinned) {
      event.preventDefault();
      return;
    }
    setDragged({ type: "directory", id: directory.id, groupLabel: group.label });
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", directory.id);
  };

  const dropModule = (
    event: DragEvent,
    group: SidebarGroupItem,
    directory: SidebarDirectoryItem | null,
    beforeModuleId?: string,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    if (dragged?.type !== "module") return;
    onNavigationPreferencesChange(moveSidebarModule(
      preferences,
      groups,
      dragged.id,
      {
        groupLabel: group.label,
        directory: directory ? { id: directory.id, label: directory.label } : null,
        ...(beforeModuleId ? { beforeModuleId } : {}),
      },
    ));
    setDragged(undefined);
  };

  const dropDirectory = (
    event: DragEvent,
    group: SidebarGroupItem,
    beforeDirectoryId?: string,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    if (dragged?.type !== "directory" || dragged.groupLabel !== group.label) return;
    onNavigationPreferencesChange(moveSidebarDirectory(
      preferences,
      group,
      dragged.id,
      beforeDirectoryId,
    ));
    setDragged(undefined);
  };

  return (
    <div
      className="sidebar-shell"
      data-navigation-collapsed={navigationCollapsed ? "true" : "false"}
      data-secondary-open={activeDirectory && !navigationCollapsed ? "true" : "false"}
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
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true"><Boxes size={20} /></span>
          <span><strong>Newma-Dock</strong><small>智能模组工作台</small></span>
          <button
            type="button"
            className="sidebar-collapse-button"
            aria-label="收起一级与二级导航"
            title="收起导航"
            onClick={collapseNavigation}
          >
            <PanelLeftClose size={15} aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="Newma-Dock Mod 导航" className="module-nav">
          {groups.map((group) => {
            const Icon = categoryIcons[group.icon] ?? Boxes;
            const headingId = `category-${group.id}`;
            return (
              <section
                className="module-group"
                role="group"
                aria-labelledby={headingId}
                data-group-tone={sidebarGroupTone(group.label)}
                key={group.id}
              >
                <h2
                  id={headingId}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => dropModule(event, group, null)}
                >
                  <Icon size={14} aria-hidden="true" />{group.label}
                </h2>
                {group.directories.map((directory) => (
                  <div
                    className="directory-nav-row"
                    data-active={directory.id === activeDirectory?.id || undefined}
                    data-pinned={directory.pinned || undefined}
                    draggable={!directory.pinned}
                    key={directory.id}
                    onDragStart={(event) => beginDirectoryDrag(event, group, directory)}
                    onDragEnd={() => setDragged(undefined)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      if (dragged?.type === "directory") dropDirectory(event, group, directory.id);
                      else dropModule(event, group, directory);
                    }}
                  >
                    <GripVertical className="sidebar-drag-handle" size={12} aria-hidden="true" />
                    <button
                      type="button"
                      className="directory-button"
                      aria-expanded={directory.id === activeDirectory?.id}
                      onClick={() => activateDirectory(directory)}
                    >
                      {directory.id === activeDirectory?.id ? <FolderOpen size={13} aria-hidden="true" /> : <Folder size={13} aria-hidden="true" />}
                      <span>{directory.label}</span><small>{directory.modules.length + (directory.settingsModule ? 1 : 0)}</small><ChevronRight size={12} aria-hidden="true" />
                    </button>
                    <PinButton
                      label={`${directory.label}目录`}
                      pinned={directory.pinned}
                      onClick={() => onNavigationPreferencesChange(toggleSidebarDirectoryPinned(preferences, directory.id))}
                    />
                  </div>
                ))}
                {group.modules.map((item) => (
                  <ModuleRow
                    key={`${item.module.moduleId}@${item.module.revision}`}
                    item={item}
                    selected={item.module.moduleId === selectedId}
                    onSelect={() => onSelect(item.module)}
                    onPin={() => onNavigationPreferencesChange(toggleSidebarModulePinned(preferences, item.module.moduleId))}
                    onDragStart={(event) => beginModuleDrag(event, item)}
                    onDragEnd={() => setDragged(undefined)}
                    onDrop={(event) => dropModule(event, group, null, item.module.moduleId)}
                  />
                ))}
              </section>
            );
          })}
        </nav>
        <div className="sidebar-tools">
          <button className="sidebar-tool-button" type="button" onClick={onOpenStore} aria-current={storeActive ? "page" : undefined}><Store size={15} aria-hidden="true" />Mod 商店</button>
          <button className="sidebar-tool-button" type="button" onClick={onOpenInterfaceSettings} aria-current={interfaceSettingsActive ? "page" : undefined}><Palette size={15} aria-hidden="true" />界面设置</button>
          <button className="sidebar-tool-button" type="button" onClick={onOpenAgentSettings} aria-current={agentSettingsActive ? "page" : undefined}><Bot size={15} aria-hidden="true" />Agent 设置</button>
        </div>
        <button className="reload-button" type="button" onClick={onReload} disabled={loading}><RefreshCw size={15} aria-hidden="true" />{loading ? "正在加载" : "重新加载 Mod"}</button>
      </aside>

      {activeDirectory ? (
        <aside className="secondary-sidebar" aria-label={`${activeDirectory.label} 二级导航`}>
          <header>
            <div><FolderOpen size={15} aria-hidden="true" /><span><strong>{activeDirectory.label}</strong><small>{activeDirectory.modules.length + (activeDirectory.settingsModule ? 1 : 0)} 个页面</small></span></div>
            <button type="button" aria-label="收起一级与二级导航" onClick={collapseNavigation}><PanelLeftClose size={14} aria-hidden="true" /></button>
          </header>
          <div
            className="secondary-module-list"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              const group = groups.find((item) => item.label === activeDirectory.groupLabel);
              if (group) dropModule(event, group, activeDirectory);
            }}
          >
            {activeDirectory.modules.map((item) => {
              const group = groups.find((candidate) => candidate.label === activeDirectory.groupLabel)!;
              return (
                <ModuleRow
                  key={`${item.module.moduleId}@${item.module.revision}`}
                  item={item}
                  selected={item.module.moduleId === selectedId}
                  onSelect={() => onSelect(item.module)}
                  onPin={() => onNavigationPreferencesChange(toggleSidebarModulePinned(preferences, item.module.moduleId))}
                  onDragStart={(event) => beginModuleDrag(event, item)}
                  onDragEnd={() => setDragged(undefined)}
                  onDrop={(event) => dropModule(event, group, activeDirectory, item.module.moduleId)}
                />
              );
            })}
          </div>
          <footer className="secondary-sidebar-footer">
            {activeDirectory.settingsModule ? (
              <button
                type="button"
                className="secondary-settings-button"
                aria-current={activeDirectory.settingsModule.module.moduleId === selectedId ? "page" : undefined}
                onClick={() => onSelect(activeDirectory.settingsModule!.module)}
              >
                <Settings size={14} aria-hidden="true" />
                {activeDirectory.settingsModule.label}
              </button>
            ) : null}
            <button
              type="button"
              className="secondary-settings-button"
              aria-current={suiteSettingsDirectoryId === activeDirectory.id ? "page" : undefined}
              onClick={() => onOpenSuiteSettings(activeDirectory)}
            >
              <Settings size={14} aria-hidden="true" />
              {activeDirectory.settingsModule ? "Desk 项目配置" : "项目设置"}
            </button>
            <small>拖拽页面可排序；拖到一级分类标题可移出目录。</small>
          </footer>
        </aside>
      ) : null}
    </div>
  );
}
