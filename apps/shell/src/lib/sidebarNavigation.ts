import type { StoredMod } from "../api/modules";
import {
  navigationFor,
  type SidebarDirectoryRef,
  type SidebarNavigationPreferences,
} from "./workspacePreferences";

export interface SidebarModuleItem {
  module: StoredMod;
  label: string;
  groupLabel: string;
  groupOrder: number;
  icon: ReturnType<typeof navigationFor>["icon"];
  order: number;
  pinned: boolean;
  directory: SidebarDirectoryRef | null;
  role: "page" | "settings";
}

export interface SidebarDirectoryItem extends SidebarDirectoryRef {
  groupLabel: string;
  order: number;
  pinned: boolean;
  modules: SidebarModuleItem[];
  settingsModule?: SidebarModuleItem;
}

export interface SidebarGroupItem {
  id: string;
  label: string;
  order: number;
  icon: ReturnType<typeof navigationFor>["icon"];
  modules: SidebarModuleItem[];
  directories: SidebarDirectoryItem[];
}

export interface SidebarNavigationModel {
  groups: SidebarGroupItem[];
  modulesById: ReadonlyMap<string, SidebarModuleItem>;
  directoriesById: ReadonlyMap<string, SidebarDirectoryItem>;
  preferences: SidebarNavigationPreferences;
}

export interface SidebarModuleDropTarget {
  groupLabel: string;
  directory: SidebarDirectoryRef | null;
  beforeModuleId?: string;
}

function sameDirectory(
  left: SidebarDirectoryRef | null,
  right: SidebarDirectoryRef | null,
) {
  return left?.id === right?.id && (left !== null) === (right !== null);
}

function comparePinnedOrderLabel(
  left: { pinned: boolean; order: number; label: string },
  right: { pinned: boolean; order: number; label: string },
) {
  if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
  return left.order - right.order || left.label.localeCompare(right.label, "zh-CN");
}

function compareSidebarModules(
  left: SidebarModuleItem,
  right: SidebarModuleItem,
) {
  if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
  return (
    left.order - right.order ||
    left.module.moduleId.localeCompare(right.module.moduleId)
  );
}

function buildSidebarGroups(
  modules: StoredMod[],
  categoryOverrides: Record<string, string>,
  preferences: SidebarNavigationPreferences,
): SidebarGroupItem[] {
  const items = modules.map<SidebarModuleItem>((module) => {
    const navigation = navigationFor(module);
    const preference = preferences.modules[module.moduleId];
    const groupLabel = categoryOverrides[module.moduleId]?.trim() || navigation.groupLabel;
    const directory = preference && Object.hasOwn(preference, "directory")
      ? preference.directory ?? null
      : navigation.directory
        ? { id: navigation.directory.id, label: navigation.directory.label }
        : null;
    return {
      module,
      label: navigation.label || module.manifest.name,
      groupLabel,
      groupOrder: navigation.groupOrder,
      icon: navigation.icon,
      order: preference?.order ?? navigation.itemOrder,
      pinned: preference?.pinned === true,
      directory,
      role: navigation.role ?? "page",
    };
  });

  const groups = new Map<string, SidebarModuleItem[]>();
  for (const item of items) {
    const group = groups.get(item.groupLabel) ?? [];
    group.push(item);
    groups.set(item.groupLabel, group);
  }

  return [...groups.entries()].map(([label, groupItems]) => {
    const directoryMap = new Map<string, SidebarDirectoryItem>();
    const directModules: SidebarModuleItem[] = [];
    for (const item of groupItems) {
      if (!item.directory) {
        directModules.push(item);
        continue;
      }
      const directoryPreference = preferences.directories[item.directory.id];
      const navigationDirectory = navigationFor(item.module).directory;
      const directory = directoryMap.get(item.directory.id) ?? {
        id: item.directory.id,
        label: directoryPreference?.label || item.directory.label,
        groupLabel: label,
        order: directoryPreference?.order ?? navigationDirectory?.order ?? 100,
        pinned: directoryPreference?.pinned === true,
        modules: [],
      };
      directory.modules.push(item);
      directoryMap.set(directory.id, directory);
    }
    const representative = [...groupItems].sort((left, right) => (
      left.groupOrder - right.groupOrder || left.order - right.order
    ))[0];
    return {
      id: label,
      label,
      order: representative?.groupOrder ?? 100,
      icon: representative?.icon ?? "module",
      modules: directModules.sort(compareSidebarModules),
      directories: [...directoryMap.values()]
        .map((directory) => {
          const members = directory.modules.sort(compareSidebarModules);
          const settingsModule = members.find((item) => item.role === "settings");
          return {
            ...directory,
            modules: settingsModule
              ? members.filter((item) => item !== settingsModule)
              : members,
            ...(settingsModule ? { settingsModule } : {}),
          };
        })
        .sort(comparePinnedOrderLabel),
    };
  }).sort((left, right) => left.order - right.order || left.label.localeCompare(right.label, "zh-CN"));
}

export function rebaseSidebarNavigationPreferences(
  modules: StoredMod[],
  preferences: SidebarNavigationPreferences,
): SidebarNavigationPreferences {
  if (modules.length === 0) return preferences;
  const moduleIds = new Set(modules.map((module) => module.moduleId));
  const nextModules = Object.fromEntries(
    Object.entries(preferences.modules).filter(([moduleId]) => moduleIds.has(moduleId)),
  );
  const directoryIds = new Set<string>();
  for (const module of modules) {
    const preference = nextModules[module.moduleId];
    if (preference && Object.hasOwn(preference, "directory")) {
      if (preference.directory) directoryIds.add(preference.directory.id);
      continue;
    }
    const directory = navigationFor(module).directory;
    if (directory) directoryIds.add(directory.id);
  }
  const nextDirectories = Object.fromEntries(
    Object.entries(preferences.directories).filter(([directoryId]) => (
      directoryIds.has(directoryId)
    )),
  );
  if (
    Object.keys(nextModules).length === Object.keys(preferences.modules).length &&
    Object.keys(nextDirectories).length === Object.keys(preferences.directories).length
  ) {
    return preferences;
  }
  return {
    version: 1,
    modules: nextModules,
    directories: nextDirectories,
  };
}

export function compileSidebarNavigation(
  modules: StoredMod[],
  categoryOverrides: Record<string, string>,
  preferences: SidebarNavigationPreferences,
): SidebarNavigationModel {
  const rebasedPreferences = rebaseSidebarNavigationPreferences(
    modules,
    preferences,
  );
  const groups = buildSidebarGroups(
    modules,
    categoryOverrides,
    rebasedPreferences,
  );
  const directoryItems = groups.flatMap((group) => group.directories);
  const moduleItems = groups.flatMap((group) => [
    ...group.modules,
    ...group.directories.flatMap((directory) => [
      ...directory.modules,
      ...(directory.settingsModule ? [directory.settingsModule] : []),
    ]),
  ]);
  return {
    groups,
    modulesById: new Map(moduleItems.map((item) => [item.module.moduleId, item])),
    directoriesById: new Map(directoryItems.map((item) => [item.id, item])),
    preferences: rebasedPreferences,
  };
}

export function buildSidebarNavigation(
  modules: StoredMod[],
  categoryOverrides: Record<string, string>,
  preferences: SidebarNavigationPreferences,
): SidebarGroupItem[] {
  return compileSidebarNavigation(
    modules,
    categoryOverrides,
    preferences,
  ).groups;
}

function directoryMembers(directory: SidebarDirectoryItem): SidebarModuleItem[] {
  return [
    ...directory.modules,
    ...(directory.settingsModule ? [directory.settingsModule] : []),
  ];
}

function clonePreferences(
  preferences: SidebarNavigationPreferences,
): SidebarNavigationPreferences {
  return {
    version: 1,
    modules: Object.fromEntries(Object.entries(preferences.modules).map(([id, value]) => [id, { ...value, ...(value.directory ? { directory: { ...value.directory } } : {}) }])),
    directories: Object.fromEntries(Object.entries(preferences.directories).map(([id, value]) => [id, { ...value }])),
  };
}

function assignModuleOrders(
  next: SidebarNavigationPreferences,
  modules: SidebarModuleItem[],
) {
  modules.forEach((item, index) => {
    next.modules[item.module.moduleId] = {
      ...next.modules[item.module.moduleId],
      order: (index + 1) * 10,
    };
  });
}

export function moveSidebarModule(
  preferences: SidebarNavigationPreferences,
  groups: SidebarGroupItem[],
  sourceModuleId: string,
  target: SidebarModuleDropTarget,
): SidebarNavigationPreferences {
  const items = groups.flatMap((group) => [
    ...group.modules,
    ...group.directories.flatMap(directoryMembers),
  ]);
  const source = items.find((item) => item.module.moduleId === sourceModuleId);
  if (!source || source.pinned || source.groupLabel !== target.groupLabel) return preferences;
  const next = clonePreferences(preferences);
  const sourceContainer = items.filter((item) => (
    item.groupLabel === source.groupLabel && sameDirectory(item.directory, source.directory)
  ));
  const targetContainer = items.filter((item) => (
    item.module.moduleId !== sourceModuleId &&
    item.groupLabel === target.groupLabel &&
    sameDirectory(item.directory, target.directory)
  ));
  const insertionIndex = target.beforeModuleId
    ? Math.max(targetContainer.findIndex((item) => item.module.moduleId === target.beforeModuleId), 0)
    : targetContainer.length;
  const moved: SidebarModuleItem = { ...source, directory: target.directory };
  targetContainer.splice(insertionIndex, 0, moved);
  if (!sameDirectory(source.directory, target.directory)) {
    assignModuleOrders(next, sourceContainer.filter((item) => item.module.moduleId !== sourceModuleId));
  }
  assignModuleOrders(next, targetContainer);
  next.modules[sourceModuleId] = {
    ...next.modules[sourceModuleId],
    directory: target.directory ? { ...target.directory } : null,
  };
  return next;
}

export function moveSidebarDirectory(
  preferences: SidebarNavigationPreferences,
  group: SidebarGroupItem,
  sourceDirectoryId: string,
  beforeDirectoryId?: string,
): SidebarNavigationPreferences {
  const source = group.directories.find((directory) => directory.id === sourceDirectoryId);
  if (!source || source.pinned) return preferences;
  if (sourceDirectoryId === beforeDirectoryId) return preferences;
  const next = clonePreferences(preferences);
  const directories = group.directories.filter((directory) => directory.id !== sourceDirectoryId);
  const insertionIndex = beforeDirectoryId
    ? Math.max(directories.findIndex((directory) => directory.id === beforeDirectoryId), 0)
    : directories.length;
  directories.splice(insertionIndex, 0, source);
  directories.forEach((directory, index) => {
    next.directories[directory.id] = {
      ...next.directories[directory.id],
      label: directory.label,
      order: (index + 1) * 10,
    };
  });
  return next;
}

export function toggleSidebarModulePinned(
  preferences: SidebarNavigationPreferences,
  moduleId: string,
): SidebarNavigationPreferences {
  const next = clonePreferences(preferences);
  next.modules[moduleId] = {
    ...next.modules[moduleId],
    pinned: next.modules[moduleId]?.pinned !== true,
  };
  return next;
}

export function toggleSidebarDirectoryPinned(
  preferences: SidebarNavigationPreferences,
  directoryId: string,
): SidebarNavigationPreferences {
  const next = clonePreferences(preferences);
  next.directories[directoryId] = {
    ...next.directories[directoryId],
    pinned: next.directories[directoryId]?.pinned !== true,
  };
  return next;
}
