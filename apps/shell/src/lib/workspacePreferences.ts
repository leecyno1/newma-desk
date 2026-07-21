import type { StoredMod } from "../api/modules";

export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const THEME_KEY = "vibedesk.themeMode";
const CATEGORY_KEY = "vibedesk.moduleCategories.v1";

const legacyNavigation = {
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

export function navigationFor(module: StoredMod) {
  return (
    module.manifest.navigation ??
    legacyNavigation[
      module.manifest.category as keyof typeof legacyNavigation
    ] ?? {
      groupLabel: module.manifest.category,
      groupOrder: 100,
      itemOrder: 100,
      icon: "module" as const,
    }
  );
}

export function defaultCategoryLabel(module: StoredMod): string {
  return navigationFor(module).groupLabel;
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

