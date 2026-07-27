import { describe, expect, it } from "vitest";

import type { StoredMod } from "../api/modules";
import {
  buildSidebarNavigation,
  compileSidebarNavigation,
  moveSidebarDirectory,
  moveSidebarModule,
  rebaseSidebarNavigationPreferences,
  toggleSidebarDirectoryPinned,
  toggleSidebarModulePinned,
} from "./sidebarNavigation";
import { EMPTY_SIDEBAR_NAVIGATION } from "./workspacePreferences";

function storedMod(
  id: string,
  name: string,
  itemOrder: number,
  directory?: { id: string; label: string; order: number },
  role?: "page" | "settings",
): StoredMod {
  return {
    moduleId: id,
    revision: 1,
    status: "published",
    createdAt: "2026-07-24T00:00:00Z",
    manifest: {
      schemaVersion: "1.0",
      id,
      name,
      version: "0.1.0",
      category: "market",
      navigation: {
        groupLabel: "市场",
        groupOrder: 10,
        itemOrder,
        label: name,
        ...(directory ? { directory } : {}),
        icon: "market",
        ...(role ? { role } : {}),
      },
      entry: { type: "static", url: `/mods/${id}/` },
      permissions: [],
      dataServices: [],
      agentCapabilities: [],
      events: { emits: [], accepts: [] },
    },
  };
}

describe("sidebar navigation model", () => {
  const modules = [
    storedMod("market-home", "终端", 10, { id: "market-suite", label: "行情工具", order: 5 }),
    storedMod("market-scan", "扫描器", 20, { id: "market-suite", label: "行情工具", order: 5 }),
    storedMod("watchlist", "自选股", 30),
  ];

  it("groups manifest directory members into a secondary navigation panel", () => {
    const [group] = buildSidebarNavigation(modules, {}, EMPTY_SIDEBAR_NAVIGATION);
    expect(group?.directories[0]).toMatchObject({ id: "market-suite", label: "行情工具" });
    expect(group?.directories[0]?.modules.map((item) => item.label)).toEqual(["终端", "扫描器"]);
    expect(group?.modules.map((item) => item.label)).toEqual(["自选股"]);
  });

  it("moves an unpinned module into another secondary directory and persists order", () => {
    const groups = buildSidebarNavigation(modules, {}, EMPTY_SIDEBAR_NAVIGATION);
    const next = moveSidebarModule(EMPTY_SIDEBAR_NAVIGATION, groups, "watchlist", {
      groupLabel: "市场",
      directory: { id: "market-suite", label: "行情工具" },
      beforeModuleId: "market-scan",
    });
    expect(next.modules.watchlist?.directory).toEqual({ id: "market-suite", label: "行情工具" });
    const rebuilt = buildSidebarNavigation(modules, {}, next);
    expect(rebuilt[0]?.directories[0]?.modules.map((item) => item.module.moduleId)).toEqual([
      "market-home",
      "watchlist",
      "market-scan",
    ]);
  });

  it("freezes a directory ahead of unpinned directories", () => {
    const preferences = toggleSidebarDirectoryPinned(EMPTY_SIDEBAR_NAVIGATION, "market-suite");
    expect(preferences.directories["market-suite"]?.pinned).toBe(true);
  });

  it("does not move a frozen module", () => {
    const preferences = toggleSidebarModulePinned(
      EMPTY_SIDEBAR_NAVIGATION,
      "watchlist",
    );
    const groups = buildSidebarNavigation(modules, {}, preferences);
    expect(
      moveSidebarModule(preferences, groups, "watchlist", {
        groupLabel: "市场",
        directory: { id: "market-suite", label: "行情工具" },
      }),
    ).toBe(preferences);
  });

  it("moves a module between two secondary directories", () => {
    const preferences = {
      ...EMPTY_SIDEBAR_NAVIGATION,
      modules: {
        watchlist: {
          directory: { id: "custom-focus", label: "重点观察" },
        },
      },
    };
    const groups = buildSidebarNavigation(modules, {}, preferences);
    const next = moveSidebarModule(preferences, groups, "market-scan", {
      groupLabel: "市场",
      directory: { id: "custom-focus", label: "重点观察" },
    });
    const rebuilt = buildSidebarNavigation(modules, {}, next);
    expect(
      rebuilt[0]?.directories
        .find((directory) => directory.id === "custom-focus")
        ?.modules.map((item) => item.module.moduleId),
    ).toEqual(["watchlist", "market-scan"]);
  });

  it("reorders secondary directories inside their primary group", () => {
    const preferences = {
      ...EMPTY_SIDEBAR_NAVIGATION,
      modules: {
        watchlist: {
          directory: { id: "custom-focus", label: "重点观察" },
        },
      },
    };
    const [group] = buildSidebarNavigation(modules, {}, preferences);
    expect(group).toBeDefined();
    const next = moveSidebarDirectory(
      preferences,
      group!,
      "custom-focus",
      "market-suite",
    );
    const rebuilt = buildSidebarNavigation(modules, {}, next);
    expect(rebuilt[0]?.directories.map((directory) => directory.id)).toEqual([
      "custom-focus",
      "market-suite",
    ]);
  });

  it("compiles a declared settings page as the directory settings entry", () => {
    const settings = storedMod(
      "market-settings",
      "行情设置",
      90,
      { id: "market-suite", label: "行情工具", order: 5 },
      "settings",
    );
    const model = compileSidebarNavigation(
      [...modules, settings],
      {},
      EMPTY_SIDEBAR_NAVIGATION,
    );
    const directory = model.directoriesById.get("market-suite");
    expect(directory?.modules.map((item) => item.module.moduleId)).toEqual([
      "market-home",
      "market-scan",
    ]);
    expect(directory?.settingsModule?.module.moduleId).toBe("market-settings");
    expect(model.modulesById.get("market-settings")?.role).toBe("settings");
  });

  it("rebases stale preference deltas without copying new Suite pages", () => {
    const preferences = {
      version: 1 as const,
      modules: {
        watchlist: { pinned: true },
        "removed-page": { order: 10 },
      },
      directories: {
        "market-suite": { pinned: true },
        "removed-suite": { order: 20 },
      },
    };
    expect(rebaseSidebarNavigationPreferences(modules, preferences)).toEqual({
      version: 1,
      modules: { watchlist: { pinned: true } },
      directories: { "market-suite": { pinned: true } },
    });
  });

  it("does not clear preference deltas while the Mod registry is still loading", () => {
    const preferences = {
      version: 1 as const,
      modules: { watchlist: { pinned: true } },
      directories: { "market-suite": { pinned: true } },
    };
    expect(rebaseSidebarNavigationPreferences([], preferences)).toBe(preferences);
  });
});
