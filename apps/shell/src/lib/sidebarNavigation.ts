import {
  INVESTMENT_DOMAINS,
  investmentDomainProject,
} from "@newma-desk/contracts";

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
  projectId: string;
  projectName: string;
  projectDescription?: string;
  projectLogo: SidebarProjectLogo;
  projectOrder: number;
  order: number;
  pinned: boolean;
  directory: SidebarDirectoryRef | null;
  role: "page" | "settings";
}

export type SidebarProjectLogo =
  | {
      type: "icon";
      name: ReturnType<typeof navigationFor>["icon"];
    }
  | { type: "letter"; text: string }
  | { type: "image"; src: string; alt?: string };

type SidebarIconName = ReturnType<typeof navigationFor>["icon"];

export interface AutomaticProjectMarkContext {
  defaultName?: string;
  icon?: SidebarIconName;
}

const CHINESE_PROJECT_MARK_BY_ICON: Record<SidebarIconName, string> = {
  today: "今日",
  research: "研究",
  market: "行情",
  quant: "量化",
  trading: "交易",
  settings: "设置",
  module: "模组",
};

const KNOWN_PROJECT_MARKS = [
  ["vibe research", "投研"],
  ["vibe trading", "量化"],
  ["newma desk", "新桌"],
  ["newma dock", "新桌"],
  ["numa agent", "牛马"],
  ["deep see", "深瞳"],
  ["deepsee", "深瞳"],
  ["in stock", "股析"],
  ["instock", "股析"],
  ["orchestra", "投委"],
  ["portfolio", "组合"],
  ["asset center", "组合"],
  ["open terminal ui", "终端"],
  ["terminal", "终端"],
  ["seven cycle", "周期"],
  ["event timeline", "事件"],
  ["ai research", "智研"],
  ["market", "行情"],
  ["trading", "量化"],
  ["quant", "量化"],
  ["research", "研究"],
  ["agent", "智能"],
] as const;

const CHINESE_PROJECT_WORDS: Readonly<Record<string, string>> = {
  ai: "智",
  alpha: "因",
  analysis: "析",
  board: "板",
  center: "中",
  custom: "自",
  data: "数",
  desk: "桌",
  event: "事",
  focus: "焦",
  lab: "验",
  market: "行",
  mod: "模",
  module: "模",
  my: "我",
  open: "开",
  platform: "台",
  portfolio: "组",
  project: "项",
  research: "研",
  stock: "股",
  suite: "组",
  system: "系",
  terminal: "终",
  timeline: "轴",
  tool: "工",
  tools: "工",
  trading: "交",
  ui: "界",
  workspace: "台",
};

function chineseMarkFrom(value: string | undefined) {
  return (value?.match(/[\u3400-\u9fff]/gu) ?? []).slice(0, 2).join("");
}

function latinProjectWords(value: string | undefined) {
  return (
    value
      ?.replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
      .match(/[A-Za-z]+/g) ?? []
  ).map((word) => word.toLowerCase());
}

function knownChineseProjectMark(words: string[]) {
  const identity = ` ${words.join(" ")} `;
  return KNOWN_PROJECT_MARKS.find(([phrase]) => (
    identity.includes(` ${phrase} `)
  ))?.[1];
}

function translatedChineseProjectMark(words: string[]) {
  return words
    .flatMap((word) => [...(CHINESE_PROJECT_WORDS[word] ?? "")])
    .slice(0, 2)
    .join("");
}

/**
 * Build the compact mark shown by the Desk project rail.
 *
 * The host owns this identity so imported projects never need to ship a logo
 * asset just to fit the navigation. The mark is always one or two Chinese
 * characters: Chinese display names win, known imported projects use a
 * stable semantic alias, and unknown projects fall back to their Desk icon.
 */
export function automaticProjectMark(
  projectName: string,
  projectId: string,
  context: AutomaticProjectMarkContext = {},
) {
  const explicitChineseMark = chineseMarkFrom(projectName);
  if (explicitChineseMark) return explicitChineseMark;

  const nameWords = latinProjectWords(projectName);
  const knownNameMark = knownChineseProjectMark(nameWords);
  if (knownNameMark) return knownNameMark;

  const translatedNameMark = translatedChineseProjectMark(nameWords);
  if (translatedNameMark.length >= 2) return translatedNameMark;

  const defaultChineseMark = chineseMarkFrom(context.defaultName);
  if (defaultChineseMark) return defaultChineseMark;

  const identityWords = [
    ...latinProjectWords(context.defaultName),
    ...latinProjectWords(projectId),
  ];
  const knownIdentityMark = knownChineseProjectMark(identityWords);
  if (knownIdentityMark) return knownIdentityMark;

  if (translatedNameMark) return translatedNameMark;
  const translatedIdentityMark = translatedChineseProjectMark(identityWords);
  if (translatedIdentityMark) return translatedIdentityMark;

  return CHINESE_PROJECT_MARK_BY_ICON[context.icon ?? "module"];
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

export interface SidebarProjectSectionItem extends SidebarDirectoryItem {
  projectId: string;
}

export interface SidebarProjectItem {
  id: string;
  name: string;
  defaultName: string;
  description?: string;
  order: number;
  pinned: boolean;
  logo: SidebarProjectLogo;
  icon: ReturnType<typeof navigationFor>["icon"];
  modules: SidebarModuleItem[];
  sections: SidebarProjectSectionItem[];
  settingsModule?: SidebarModuleItem;
  settingsDirectory: SidebarDirectoryItem;
}

export interface SidebarNavigationModel {
  groups: SidebarGroupItem[];
  projects: SidebarProjectItem[];
  modulesById: ReadonlyMap<string, SidebarModuleItem>;
  directoriesById: ReadonlyMap<string, SidebarDirectoryItem>;
  projectsById: ReadonlyMap<string, SidebarProjectItem>;
  preferences: SidebarNavigationPreferences;
}

export interface SidebarModuleDropTarget {
  projectId: string;
  directory: SidebarDirectoryRef | null;
  beforeModuleId?: string;
}

interface ResolvedProject {
  id: string;
  name: string;
  description?: string;
  order: number;
  logo: SidebarProjectLogo;
}

interface ProjectIdReservations {
  explicit: ReadonlySet<string>;
  legacy: ReadonlySet<string>;
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

function comparePinnedProjectOrder(
  left: { pinned: boolean; order: number; id: string },
  right: { pinned: boolean; order: number; id: string },
) {
  if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
  return left.order - right.order || left.id.localeCompare(right.id);
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

function projectIdReservations(modules: StoredMod[]): ProjectIdReservations {
  const explicit = new Set<string>();
  const legacy = new Set<string>();
  for (const module of modules) {
    const navigation = navigationFor(module);
    if (navigation.project) explicit.add(navigation.project.id);
    else if (navigation.directory) legacy.add(navigation.directory.id);
  }
  return { explicit, legacy };
}

function collisionSafeProjectId(prefix: "legacy" | "standalone", id: string) {
  const candidate = `${prefix}-${id}`;
  if (candidate.length <= 48) return candidate;
  let hash = 2166136261;
  for (const character of candidate) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  const suffix = (hash >>> 0).toString(36);
  return `${prefix}-${id.slice(0, 46 - prefix.length - suffix.length)}-${suffix}`;
}

function resolveProject(
  module: StoredMod,
  navigation: ReturnType<typeof navigationFor>,
  reservations?: ProjectIdReservations,
): ResolvedProject {
  const project = navigation.project;
  if (project) {
    return {
      id: project.id,
      name: project.name,
      ...(project.description ? { description: project.description } : {}),
      order: project.order,
      logo: project.logo ?? { type: "icon", name: navigation.icon },
    };
  }

  // Legacy suites already expose a stable directory id. Treat that directory
  // as their project until the manifest opts into navigation.project.
  if (navigation.directory) {
    const id = reservations?.explicit.has(navigation.directory.id)
      ? collisionSafeProjectId("legacy", navigation.directory.id)
      : navigation.directory.id;
    return {
      id,
      name: navigation.directory.label,
      order: navigation.groupOrder * 1_000 + navigation.directory.order,
      logo: { type: "icon", name: navigation.icon },
    };
  }

  // A standalone Mod is a complete project of one. This makes every imported
  // project addressable without requiring Desk-specific manifest rewrites.
  return {
    id: reservations && (
      reservations.explicit.has(module.moduleId) ||
      reservations.legacy.has(module.moduleId)
    )
      ? collisionSafeProjectId("standalone", module.moduleId)
      : module.moduleId,
    name: module.manifest.name,
    order: navigation.groupOrder * 1_000 + navigation.itemOrder,
    logo: { type: "icon", name: navigation.icon },
  };
}

function buildSidebarItems(
  modules: StoredMod[],
  categoryOverrides: Record<string, string>,
  preferences: SidebarNavigationPreferences,
): SidebarModuleItem[] {
  const reservations = projectIdReservations(modules);
  return modules.map<SidebarModuleItem>((module) => {
    const navigation = navigationFor(module);
    const project = resolveProject(module, navigation, reservations);
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
      projectId: project.id,
      projectName: project.name,
      ...(project.description ? { projectDescription: project.description } : {}),
      projectLogo: project.logo,
      projectOrder: project.order,
      order: preference?.order ?? navigation.itemOrder,
      pinned: preference?.pinned === true,
      directory,
      role: navigation.role ?? "page",
    };
  });
}

function buildSidebarGroups(
  items: SidebarModuleItem[],
  preferences: SidebarNavigationPreferences,
): SidebarGroupItem[] {
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

function buildSidebarProjects(
  items: SidebarModuleItem[],
  preferences: SidebarNavigationPreferences,
): SidebarProjectItem[] {
  const projectItems = new Map<string, SidebarModuleItem[]>();
  const sectionOwners = new Map<string, Set<string>>();
  for (const item of items) {
    const members = projectItems.get(item.projectId) ?? [];
    members.push(item);
    projectItems.set(item.projectId, members);
    if (item.directory && item.directory.id !== item.projectId) {
      const owners = sectionOwners.get(item.directory.id) ?? new Set<string>();
      owners.add(item.projectId);
      sectionOwners.set(item.directory.id, owners);
    }
  }

  const projects = [...projectItems.entries()].map(([projectId, rawMembers]) => {
    const members = [...rawMembers].sort(compareSidebarModules);
    const representative = [...members].sort((left, right) => (
      left.projectOrder - right.projectOrder ||
      left.order - right.order ||
      left.module.moduleId.localeCompare(right.module.moduleId)
    ))[0]!;
    const project: ResolvedProject = {
      id: representative.projectId,
      name: representative.projectName,
      ...(representative.projectDescription
        ? { description: representative.projectDescription }
        : {}),
      order: representative.projectOrder,
      logo: representative.projectLogo,
    };
    const settingsModule = members.find((item) => (
      item.role === "settings" &&
      (!item.directory || item.directory.id === projectId)
    ));
    const pages = settingsModule
      ? members.filter((item) => item !== settingsModule)
      : members;
    const directModules: SidebarModuleItem[] = [];
    const sectionMap = new Map<string, SidebarProjectSectionItem>();

    for (const item of pages) {
      if (!item.directory || item.directory.id === projectId) {
        directModules.push(item);
        continue;
      }
      const legacySectionPreference = sectionOwners.get(item.directory.id)?.size === 1
        ? preferences.directories[item.directory.id]
        : undefined;
      const sectionPreference = preferences.sections?.[projectId]?.[item.directory.id];
      const navigationDirectory = navigationFor(item.module).directory;
      const section = sectionMap.get(item.directory.id) ?? {
        id: item.directory.id,
        label: (
          sectionPreference?.label ||
          legacySectionPreference?.label ||
          item.directory.label
        ),
        projectId,
        groupLabel: item.groupLabel,
        order: (
          sectionPreference?.order ??
          legacySectionPreference?.order ??
          navigationDirectory?.order ??
          100
        ),
        pinned: (
          sectionPreference?.pinned ??
          legacySectionPreference?.pinned ??
          false
        ),
        modules: [],
      };
      section.modules.push(item);
      sectionMap.set(section.id, section);
    }

    const legacyProjectPreference = sectionOwners.has(projectId)
      ? undefined
      : preferences.directories[projectId];
    const projectPreference = preferences.projects?.[projectId];
    const projectName = (
      projectPreference?.label?.trim() ||
      legacyProjectPreference?.label?.trim() ||
      project.name
    );
    const projectOrder = (
      projectPreference?.order ??
      legacyProjectPreference?.order ??
      project.order
    );
    const projectPinned = (
      projectPreference?.pinned ??
      legacyProjectPreference?.pinned ??
      false
    );
    const settingsDirectory: SidebarDirectoryItem = {
      id: projectId,
      label: projectName,
      groupLabel: representative.groupLabel,
      order: projectOrder,
      pinned: projectPinned,
      modules: pages,
      ...(settingsModule ? { settingsModule } : {}),
    };

    return {
      id: projectId,
      name: projectName,
      defaultName: project.name,
      ...(project.description ? { description: project.description } : {}),
      order: projectOrder,
      pinned: projectPinned,
      logo: project.logo,
      icon: representative.icon,
      modules: directModules.sort(compareSidebarModules),
      sections: [...sectionMap.values()]
        .map((section) => {
          const sectionMembers = section.modules.sort(compareSidebarModules);
          const sectionSettings = sectionMembers.find((item) => item.role === "settings");
          return {
            ...section,
            modules: sectionSettings
              ? sectionMembers.filter((item) => item !== sectionSettings)
              : sectionMembers,
            ...(sectionSettings ? { settingsModule: sectionSettings } : {}),
          };
        })
        .sort(comparePinnedOrderLabel),
      ...(settingsModule ? { settingsModule } : {}),
      settingsDirectory,
    };
  });

  const populatedProjectIds = new Set(projects.map((project) => project.id));
  for (const domain of INVESTMENT_DOMAINS) {
    if (populatedProjectIds.has(domain.id)) continue;
    const projectPreference = preferences.projects?.[domain.id];
    const project = investmentDomainProject(domain);
    const name = projectPreference?.label?.trim() || project.name;
    const order = projectPreference?.order ?? project.order;
    const pinned = projectPreference?.pinned ?? false;
    projects.push({
      id: project.id,
      name,
      defaultName: project.name,
      description: project.description,
      order,
      pinned,
      logo: project.logo,
      icon: domain.icon,
      modules: [],
      sections: [],
      settingsDirectory: {
        id: project.id,
        label: name,
        groupLabel: project.name,
        order,
        pinned,
        modules: [],
      },
    });
  }

  return projects.sort(comparePinnedProjectOrder);
}

export function rebaseSidebarNavigationPreferences(
  modules: StoredMod[],
  preferences: SidebarNavigationPreferences,
): SidebarNavigationPreferences {
  if (modules.length === 0) return preferences;
  const reservations = projectIdReservations(modules);
  const moduleIds = new Set(modules.map((module) => module.moduleId));
  const nextModules = Object.fromEntries(
    Object.entries(preferences.modules).flatMap(([moduleId, preference]) => {
      if (!moduleIds.has(moduleId)) return [];
      const nextPreference = { ...preference };
      delete nextPreference.directory;
      return Object.keys(nextPreference).length > 0
        ? [[moduleId, nextPreference] as const]
        : [];
    }),
  );
  const removedDirectoryOverride = Object.values(preferences.modules).some(
    (preference) => Object.hasOwn(preference, "directory"),
  );
  const directoryIds = new Set<string>();
  const projectIds = new Set<string>(INVESTMENT_DOMAINS.map((domain) => domain.id));
  for (const projectId of projectIds) directoryIds.add(projectId);
  const sectionIdsByProject = new Map<string, Set<string>>();
  for (const module of modules) {
    const navigation = navigationFor(module);
    const projectId = resolveProject(module, navigation, reservations).id;
    projectIds.add(projectId);
    directoryIds.add(projectId);
    const preference = nextModules[module.moduleId];
    if (preference && Object.hasOwn(preference, "directory")) {
      if (preference.directory) {
        directoryIds.add(preference.directory.id);
        if (preference.directory.id !== projectId) {
          const sectionIds = sectionIdsByProject.get(projectId) ?? new Set<string>();
          sectionIds.add(preference.directory.id);
          sectionIdsByProject.set(projectId, sectionIds);
        }
      }
      continue;
    }
    const directory = navigation.directory;
    if (directory) {
      directoryIds.add(directory.id);
      if (directory.id !== projectId) {
        const sectionIds = sectionIdsByProject.get(projectId) ?? new Set<string>();
        sectionIds.add(directory.id);
        sectionIdsByProject.set(projectId, sectionIds);
      }
    }
  }
  const nextDirectories = Object.fromEntries(
    Object.entries(preferences.directories).filter(([directoryId]) => (
      directoryIds.has(directoryId)
    )),
  );
  const nextProjects = preferences.projects
    ? Object.fromEntries(
        Object.entries(preferences.projects).filter(([projectId]) => (
          projectIds.has(projectId)
        )),
      )
    : undefined;
  const nextSections = preferences.sections
    ? Object.fromEntries(Object.entries(preferences.sections).flatMap(
        ([projectId, sections]) => {
          const validSectionIds = sectionIdsByProject.get(projectId);
          if (!validSectionIds) return [];
          const nextProjectSections = Object.fromEntries(
            Object.entries(sections).filter(([sectionId]) => (
              validSectionIds.has(sectionId)
            )),
          );
          return Object.keys(nextProjectSections).length > 0
            ? [[projectId, nextProjectSections] as const]
            : [];
        },
      ))
    : undefined;
  const sectionPreferenceCount = (
    sections: SidebarNavigationPreferences["sections"],
  ) => Object.values(sections ?? {}).reduce(
    (total, projectSections) => total + Object.keys(projectSections).length,
    0,
  );
  if (
    !removedDirectoryOverride &&
    Object.keys(nextModules).length === Object.keys(preferences.modules).length &&
    Object.keys(nextDirectories).length === Object.keys(preferences.directories).length &&
    Object.keys(nextProjects ?? {}).length === Object.keys(preferences.projects ?? {}).length &&
    sectionPreferenceCount(nextSections) === sectionPreferenceCount(preferences.sections)
  ) {
    return preferences;
  }
  return {
    version: 1,
    modules: nextModules,
    directories: nextDirectories,
    ...(nextProjects ? { projects: nextProjects } : {}),
    ...(nextSections ? { sections: nextSections } : {}),
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
  const items = buildSidebarItems(
    modules,
    categoryOverrides,
    rebasedPreferences,
  );
  const groups = buildSidebarGroups(items, rebasedPreferences);
  const projects = buildSidebarProjects(items, rebasedPreferences);
  const directoryItems = groups.flatMap((group) => group.directories);
  const projectDirectories = projects.map((project) => project.settingsDirectory);
  return {
    groups,
    projects,
    modulesById: new Map(items.map((item) => [item.module.moduleId, item])),
    directoriesById: new Map(
      [...directoryItems, ...projectDirectories].map((item) => [item.id, item]),
    ),
    projectsById: new Map(projects.map((project) => [project.id, project])),
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
    ...(preferences.projects ? {
      projects: Object.fromEntries(
        Object.entries(preferences.projects).map(([id, value]) => [id, { ...value }]),
      ),
    } : {}),
    ...(preferences.sections ? {
      sections: Object.fromEntries(
        Object.entries(preferences.sections).map(([projectId, sections]) => [
          projectId,
          Object.fromEntries(
            Object.entries(sections).map(([id, value]) => [id, { ...value }]),
          ),
        ]),
      ),
    } : {}),
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
  if (!source || source.pinned || source.projectId !== target.projectId) {
    return preferences;
  }
  const projectDirectory = navigationFor(source.module).directory;
  if (
    projectDirectory
      ? target.directory?.id !== projectDirectory.id
      : target.directory !== null
  ) {
    return preferences;
  }
  const next = clonePreferences(preferences);
  const sourceContainer = items.filter((item) => (
    item.projectId === source.projectId &&
    sameDirectory(item.directory, source.directory)
  ));
  const targetContainer = items.filter((item) => (
    item.module.moduleId !== sourceModuleId &&
    item.projectId === target.projectId &&
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

export function moveSidebarProject(
  preferences: SidebarNavigationPreferences,
  projects: SidebarProjectItem[],
  sourceProjectId: string,
  beforeProjectId?: string,
): SidebarNavigationPreferences {
  const source = projects.find((project) => project.id === sourceProjectId);
  if (!source || source.pinned || sourceProjectId === beforeProjectId) {
    return preferences;
  }
  const next = clonePreferences(preferences);
  const reordered = projects.filter((project) => project.id !== sourceProjectId);
  const insertionIndex = beforeProjectId
    ? Math.max(reordered.findIndex((project) => project.id === beforeProjectId), 0)
    : reordered.length;
  reordered.splice(insertionIndex, 0, source);
  next.projects = { ...(next.projects ?? {}) };
  reordered.forEach((project, index) => {
    next.projects![project.id] = {
      ...next.projects![project.id],
      order: (index + 1) * 10,
    };
  });
  return next;
}

export function toggleSidebarProjectPinned(
  preferences: SidebarNavigationPreferences,
  projectId: string,
): SidebarNavigationPreferences {
  const next = clonePreferences(preferences);
  next.projects = { ...(next.projects ?? {}) };
  const current = next.projects[projectId] ?? next.directories[projectId];
  next.projects[projectId] = {
    ...current,
    pinned: current?.pinned !== true,
  };
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
