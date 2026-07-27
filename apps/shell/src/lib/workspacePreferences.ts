import type { StoredMod } from "../api/modules";

export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export interface SidebarDirectoryRef {
  id: string;
  label: string;
}

export interface SidebarModulePreference {
  directory?: SidebarDirectoryRef | null;
  order?: number;
  pinned?: boolean;
}

export interface SidebarDirectoryPreference {
  label?: string;
  order?: number;
  pinned?: boolean;
}

export interface SidebarNavigationPreferences {
  version: 1;
  modules: Record<string, SidebarModulePreference>;
  directories: Record<string, SidebarDirectoryPreference>;
}

const THEME_KEY = "vibedesk.themeMode";
const CATEGORY_KEY = "vibedesk.moduleCategories.v1";
const SIDEBAR_NAVIGATION_KEY = "vibedesk.sidebarNavigation.v1";

export const EMPTY_SIDEBAR_NAVIGATION: SidebarNavigationPreferences = {
  version: 1,
  modules: {},
  directories: {},
};

type SidebarNavigationConfig = NonNullable<
  StoredMod["manifest"]["navigation"]
>;

const legacyNavigation: Record<
  "research" | "market" | "quant",
  SidebarNavigationConfig
> = {
  research: {
    groupLabel: "研究",
    groupOrder: 0,
    itemOrder: 100,
    icon: "research" as const,
  },
  market: {
    groupLabel: "市场",
    groupOrder: 10,
    itemOrder: 100,
    icon: "market" as const,
  },
  quant: {
    groupLabel: "量化",
    groupOrder: 20,
    itemOrder: 100,
    icon: "quant" as const,
  },
};

export function navigationFor(module: StoredMod): SidebarNavigationConfig {
  if (module.manifest.navigation) return module.manifest.navigation;

  const legacy = legacyNavigation[
    module.manifest.category as keyof typeof legacyNavigation
  ];
  return legacy ?? {
    groupLabel: module.manifest.category,
    groupOrder: 100,
    itemOrder: 100,
    icon: "module",
  };
}

export function defaultCategoryLabel(module: StoredMod): string {
  return navigationFor(module).groupLabel;
}

export function defaultDirectory(module: StoredMod): SidebarDirectoryRef | null {
  const directory = navigationFor(module).directory;
  return directory ? { id: directory.id, label: directory.label } : null;
}

function finiteOrder(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

function directoryRef(value: unknown): SidebarDirectoryRef | null | undefined {
  if (value === null) return null;
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  if (
    typeof record.id !== "string" ||
    !/^[a-z][a-z0-9-]{1,47}$/.test(record.id) ||
    typeof record.label !== "string" ||
    !record.label.trim()
  ) return undefined;
  return { id: record.id, label: record.label.trim().slice(0, 40) };
}

export function loadSidebarNavigationPreferences(): SidebarNavigationPreferences {
  try {
    const raw = window.localStorage.getItem(SIDEBAR_NAVIGATION_KEY);
    if (!raw) return EMPTY_SIDEBAR_NAVIGATION;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return EMPTY_SIDEBAR_NAVIGATION;
    }
    const record = parsed as Record<string, unknown>;
    const rawModules = typeof record.modules === "object" && record.modules !== null && !Array.isArray(record.modules)
      ? record.modules as Record<string, unknown>
      : {};
    const modules = Object.fromEntries(Object.entries(rawModules).flatMap(([moduleId, value]) => {
      if (!moduleId || typeof value !== "object" || value === null || Array.isArray(value)) return [];
      const source = value as Record<string, unknown>;
      const preference: SidebarModulePreference = {};
      if (Object.hasOwn(source, "directory")) {
        const parsedDirectory = directoryRef(source.directory);
        if (parsedDirectory !== undefined) preference.directory = parsedDirectory;
      }
      const order = finiteOrder(source.order);
      if (order !== undefined) preference.order = order;
      if (typeof source.pinned === "boolean") preference.pinned = source.pinned;
      return [[moduleId, preference] as const];
    }));
    const rawDirectories = typeof record.directories === "object" && record.directories !== null && !Array.isArray(record.directories)
      ? record.directories as Record<string, unknown>
      : {};
    const directories = Object.fromEntries(Object.entries(rawDirectories).flatMap(([directoryId, value]) => {
      if (!/^[a-z][a-z0-9-]{1,47}$/.test(directoryId) || typeof value !== "object" || value === null || Array.isArray(value)) return [];
      const source = value as Record<string, unknown>;
      const preference: SidebarDirectoryPreference = {};
      if (typeof source.label === "string" && source.label.trim()) preference.label = source.label.trim().slice(0, 40);
      const order = finiteOrder(source.order);
      if (order !== undefined) preference.order = order;
      if (typeof source.pinned === "boolean") preference.pinned = source.pinned;
      return [[directoryId, preference] as const];
    }));
    return { version: 1, modules, directories };
  } catch {
    return EMPTY_SIDEBAR_NAVIGATION;
  }
}

export function saveSidebarNavigationPreferences(preferences: SidebarNavigationPreferences) {
  try {
    window.localStorage.setItem(SIDEBAR_NAVIGATION_KEY, JSON.stringify(preferences));
  } catch {
    // Sidebar customization remains active in memory.
  }
}

export function customSidebarDirectory(groupLabel: string, label: string): SidebarDirectoryRef {
  const normalized = `${groupLabel}:${label}`.normalize("NFKC").trim().toLocaleLowerCase();
  let hash = 2166136261;
  for (const character of normalized) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  const slug = label
    .normalize("NFKD")
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 24) || "directory";
  return { id: `custom-${slug}-${(hash >>> 0).toString(36)}`.slice(0, 48), label: label.trim().slice(0, 40) };
}

export function loadThemeMode(): ThemeMode {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    return saved === "light" || saved === "dark" || saved === "system"
      ? saved
      : "system";
  } catch {
    return "system";
  }
}

export function saveThemeMode(mode: ThemeMode) {
  try {
    window.localStorage.setItem(THEME_KEY, mode);
  } catch {
    // Theme selection remains usable for the current session.
  }
}

export function systemPrefersDark(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

export function resolveTheme(
  mode: ThemeMode,
  prefersDark = systemPrefersDark(),
): ResolvedTheme {
  if (mode === "system") return prefersDark ? "dark" : "light";
  return mode;
}

export function loadCategoryOverrides(): Record<string, string> {
  try {
    const raw = window.localStorage.getItem(CATEGORY_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(
          ([moduleId, label]) =>
            moduleId.length > 0 &&
            typeof label === "string" &&
            label.trim().length > 0,
        )
        .map(([moduleId, label]) => [moduleId, String(label).trim()]),
    );
  } catch {
    return {};
  }
}

export function saveCategoryOverrides(overrides: Record<string, string>) {
  try {
    window.localStorage.setItem(CATEGORY_KEY, JSON.stringify(overrides));
  } catch {
    // Navigation continues with the in-memory preferences.
  }
}
