import { describe, expect, it } from "vitest";
import { INVESTMENT_DOMAIN_IDS } from "@newma-desk/contracts";

import type { StoredMod } from "../api/modules";
import {
  automaticProjectMark,
  buildSidebarNavigation,
  compileSidebarNavigation,
  moveSidebarModule,
  moveSidebarProject,
  rebaseSidebarNavigationPreferences,
  toggleSidebarDirectoryPinned,
  toggleSidebarModulePinned,
  toggleSidebarProjectPinned,
} from "./sidebarNavigation";
import { EMPTY_SIDEBAR_NAVIGATION } from "./workspacePreferences";

function storedMod(
  id: string,
  name: string,
  itemOrder: number,
  directory?: { id: string; label: string; order: number },
  role?: "page" | "settings",
  project: {
    id: string;
    name: string;
    order: number;
  } | null = { id: "market-suite", name: "行情工具", order: 10 },
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
        ...(project ? { project } : {}),
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
  const investmentDomainIds = new Set<string>(INVESTMENT_DOMAIN_IDS);
  const importedProjectIds = (model: ReturnType<typeof compileSidebarNavigation>) => (
    model.projects
      .map((project) => project.id)
      .filter((id) => !investmentDomainIds.has(id))
  );

  it.each([
    ["Vibe Research", "vibe-research", "投研"],
    ["Newma-Desk", "newma-desk", "新桌"],
    ["OpenTerminalUI", "open-terminal-ui", "终端"],
    ["DeepSee", "deepsee", "深瞳"],
    ["InStock Analysis", "instock-suite", "股析"],
    ["AIResearch", "ai-research", "智研"],
    ["Terminal", "market-terminal", "终端"],
    ["行情工具", "market-suite", "行情"],
    ["牛马 Agent", "numa-agent", "牛马"],
    ["自定义 Mod", "custom-module", "自定"],
    ["纯中文", "x", "纯中"],
  ])("derives the host project mark for %s", (name, id, expected) => {
    const mark = automaticProjectMark(name, id);
    expect(mark).toBe(expected);
    expect(mark).toMatch(/^[\u3400-\u9fff]{1,2}$/u);
  });

  it("ignores legacy manifest logo declarations when deriving the project mark", () => {
    expect(automaticProjectMark("Vibe Research", "vibe-research")).toBe("投研");
  });

  it("falls back to the Chinese icon meaning for an unknown English project", () => {
    expect(automaticProjectMark("Nebula Cloud", "nebula-cloud", {
      icon: "research",
    })).toBe("研究");
  });

  it("groups manifest directory members into a secondary navigation panel", () => {
    const [group] = buildSidebarNavigation(modules, {}, EMPTY_SIDEBAR_NAVIGATION);
    expect(group?.directories[0]).toMatchObject({ id: "market-suite", label: "行情工具" });
    expect(group?.directories[0]?.modules.map((item) => item.label)).toEqual(["终端", "扫描器"]);
    expect(group?.modules.map((item) => item.label)).toEqual(["自选股"]);
  });

  it("compiles project identities for the logo rail and falls back to a standalone Mod", () => {
    const standalone = storedMod(
      "event-timeline",
      "日线时间轴",
      40,
      undefined,
      undefined,
      null,
    );
    const model = compileSidebarNavigation(
      [...modules, standalone],
      {},
      EMPTY_SIDEBAR_NAVIGATION,
    );

    expect(importedProjectIds(model)).toEqual(["market-suite", "event-timeline"]);
    expect(model.projects.filter((project) => investmentDomainIds.has(project.id))).toHaveLength(0);
    expect(model.projectsById.get("market-suite")?.modules.map((item) => item.label)).toEqual([
      "终端",
      "扫描器",
      "自选股",
    ]);
    expect(model.modulesById.get("event-timeline")?.projectId).toBe("event-timeline");
  });

  it("uses the stable project id when equal-order project names change", () => {
    const compileIds = (alphaName: string, zetaName: string) => compileSidebarNavigation(
      [
        storedMod("zeta-page", zetaName, 40, undefined, undefined, null),
        storedMod("alpha-page", alphaName, 40, undefined, undefined, null),
      ],
      {},
      EMPTY_SIDEBAR_NAVIGATION,
    );

    expect(importedProjectIds(compileIds("最后项目", "最先项目"))).toEqual(["alpha-page", "zeta-page"]);
    expect(importedProjectIds(compileIds("Alpha", "Zeta"))).toEqual(["alpha-page", "zeta-page"]);
  });

  it("does not move a standalone page into a complete project group", () => {
    const groups = buildSidebarNavigation(modules, {}, EMPTY_SIDEBAR_NAVIGATION);
    const next = moveSidebarModule(EMPTY_SIDEBAR_NAVIGATION, groups, "watchlist", {
      projectId: "market-suite",
      directory: { id: "market-suite", label: "行情工具" },
      beforeModuleId: "market-scan",
    });
    expect(next).toBe(EMPTY_SIDEBAR_NAVIGATION);
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
        projectId: "market-suite",
        directory: { id: "market-suite", label: "行情工具" },
      }),
    ).toBe(preferences);
  });

  it("does not move a page into a different project", () => {
    const standalone = storedMod(
      "event-timeline",
      "日线时间轴",
      40,
      undefined,
      undefined,
      null,
    );
    const groups = buildSidebarNavigation(
      [...modules, standalone],
      {},
      EMPTY_SIDEBAR_NAVIGATION,
    );
    expect(moveSidebarModule(
      EMPTY_SIDEBAR_NAVIGATION,
      groups,
      "event-timeline",
      {
        projectId: "market-suite",
        directory: { id: "market-suite", label: "行情工具" },
      },
    )).toBe(EMPTY_SIDEBAR_NAVIGATION);
  });

  it("clears legacy page moves that split a complete project", () => {
    const preferences = {
      ...EMPTY_SIDEBAR_NAVIGATION,
      modules: {
        watchlist: {
          directory: { id: "custom-focus", label: "重点观察" },
        },
      },
    };
    const rebuilt = compileSidebarNavigation(modules, {}, preferences);
    expect(rebuilt.preferences.modules.watchlist).toBeUndefined();
    expect(rebuilt.projectsById.get("market-suite")?.sections).toEqual([]);
    expect(rebuilt.projectsById.get("market-suite")?.modules.map((item) => item.module.moduleId)).toEqual([
      "market-home",
      "market-scan",
      "watchlist",
    ]);
  });

  it("persists first-level project pinning and ordering", () => {
    const trading = storedMod(
      "alpha-lab",
      "因子实验室",
      10,
      undefined,
      undefined,
      { id: "vibe-trading", name: "Vibe Trading", order: 20 },
    );
    const model = compileSidebarNavigation(
      [...modules, trading],
      {},
      EMPTY_SIDEBAR_NAVIGATION,
    );
    const moved = moveSidebarProject(
      model.preferences,
      model.projects,
      "vibe-trading",
      "market-suite",
    );
    const pinned = toggleSidebarProjectPinned(moved, "vibe-trading");
    const rebuilt = compileSidebarNavigation([...modules, trading], {}, pinned);

    expect(importedProjectIds(rebuilt)).toEqual([
      "vibe-trading",
      "market-suite",
    ]);
    expect(rebuilt.projects[0]?.pinned).toBe(true);
    expect(rebuilt.preferences.projects?.["vibe-trading"]?.order).toBe(10);
  });

  it("uses a local first-level title without changing the stable project identity", () => {
    const preferences = {
      version: 1 as const,
      modules: {},
      directories: {},
      projects: {
        "market-suite": { label: "Alpha Board" },
      },
    };
    const model = compileSidebarNavigation(modules, {}, preferences);
    const project = model.projectsById.get("market-suite");

    expect(project).toMatchObject({
      id: "market-suite",
      name: "Alpha Board",
      defaultName: "行情工具",
    });
    expect(project?.settingsDirectory.label).toBe("Alpha Board");
    expect(automaticProjectMark(project!.name, project!.id, {
      defaultName: project!.defaultName,
      icon: project!.icon,
    })).toBe("因板");

    const moved = moveSidebarProject(
      model.preferences,
      model.projects,
      "market-suite",
    );
    expect(moved.projects?.["market-suite"]?.label).toBe("Alpha Board");
  });

  it("keeps legacy project-title preferences behind the project-level override", () => {
    const legacy = compileSidebarNavigation(modules, {}, {
      version: 1,
      modules: {},
      directories: { "market-suite": { label: "Legacy Market" } },
    });
    expect(legacy.projectsById.get("market-suite")?.name).toBe("Legacy Market");

    const overridden = compileSidebarNavigation(modules, {}, {
      version: 1,
      modules: {},
      directories: { "market-suite": { label: "Legacy Market" } },
      projects: { "market-suite": { label: "Market Studio" } },
    });
    expect(overridden.projectsById.get("market-suite")?.name).toBe("Market Studio");
  });

  it("keeps standalone and declared project identities separate when their ids collide", () => {
    const declared = storedMod(
      "declared-page",
      "声明项目页面",
      10,
      undefined,
      undefined,
      { id: "event-timeline", name: "事件项目", order: 10 },
    );
    const standalone = storedMod(
      "event-timeline",
      "独立事件轴",
      20,
      undefined,
      undefined,
      null,
    );
    const model = compileSidebarNavigation(
      [declared, standalone],
      {},
      EMPTY_SIDEBAR_NAVIGATION,
    );

    expect(importedProjectIds(model)).toEqual([
      "event-timeline",
      "standalone-event-timeline",
    ]);
    expect(model.modulesById.get("declared-page")?.projectId).toBe("event-timeline");
    expect(model.modulesById.get("event-timeline")?.projectId).toBe(
      "standalone-event-timeline",
    );
  });

  it("keeps uninstalled project domains out of the default rail", () => {
    const model = compileSidebarNavigation([], {}, EMPTY_SIDEBAR_NAVIGATION);

    expect(model.projects).toEqual([]);
    expect(model.projectsById.size).toBe(0);
  });

  it("scopes equal section ids to their owning project", () => {
    const first = storedMod(
      "first-page",
      "第一项目页面",
      10,
      { id: "overview", label: "总览", order: 10 },
      undefined,
      { id: "first-project", name: "第一项目", order: 10 },
    );
    const second = storedMod(
      "second-page",
      "第二项目页面",
      10,
      { id: "overview", label: "总览", order: 10 },
      undefined,
      { id: "second-project", name: "第二项目", order: 20 },
    );
    const model = compileSidebarNavigation([first, second], {}, {
      version: 1,
      modules: {},
      directories: { overview: { pinned: true, label: "旧版共享名称" } },
      sections: {
        "first-project": { overview: { pinned: true, label: "第一项目总览" } },
        "second-project": { overview: { label: "第二项目总览" } },
      },
    });

    expect(model.projectsById.get("first-project")?.sections[0]).toMatchObject({
      label: "第一项目总览",
      pinned: true,
    });
    expect(model.projectsById.get("second-project")?.sections[0]).toMatchObject({
      label: "第二项目总览",
      pinned: false,
    });
  });

  it("migrates an unambiguous legacy directory preference into its project section", () => {
    const projectPage = storedMod(
      "project-page",
      "项目页面",
      10,
      { id: "overview", label: "总览", order: 30 },
      undefined,
      { id: "project-suite", name: "Project Suite", order: 10 },
    );
    const model = compileSidebarNavigation([projectPage], {}, {
      version: 1,
      modules: {},
      directories: {
        overview: { label: "旧版总览", order: 5, pinned: true },
      },
    });

    expect(model.projectsById.get("project-suite")?.sections[0]).toMatchObject({
      label: "旧版总览",
      order: 5,
      pinned: true,
    });
  });

  it("does not leak an ambiguous legacy directory preference across projects", () => {
    const first = storedMod(
      "first-page",
      "第一项目页面",
      10,
      { id: "overview", label: "第一总览", order: 10 },
      undefined,
      { id: "first-project", name: "First Project", order: 10 },
    );
    const second = storedMod(
      "second-page",
      "第二项目页面",
      10,
      { id: "overview", label: "第二总览", order: 20 },
      undefined,
      { id: "second-project", name: "Second Project", order: 20 },
    );
    const model = compileSidebarNavigation([first, second], {}, {
      version: 1,
      modules: {},
      directories: {
        overview: { label: "旧版共享名称", order: 1, pinned: true },
      },
    });

    expect(model.projectsById.get("first-project")?.sections[0]).toMatchObject({
      label: "第一总览",
      order: 10,
      pinned: false,
    });
    expect(model.projectsById.get("second-project")?.sections[0]).toMatchObject({
      label: "第二总览",
      order: 20,
      pinned: false,
    });
  });

  it("compiles a declared settings page as the project settings entry", () => {
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
      "watchlist",
    ]);
    expect(directory?.settingsModule?.module.moduleId).toBe("market-settings");
    expect(model.modulesById.get("market-settings")?.role).toBe("settings");
  });

  it("keeps a custom project's pages and settings in its first-level entry", () => {
    const domain = { id: "deepsee-suite", name: "DeepSee", order: 160 };
    const overview = storedMod(
      "deepsee-overview",
      "总览",
      10,
      { id: "deepsee-suite", label: "DeepSee", order: 10 },
      undefined,
      domain,
    );
    const settings = storedMod(
      "deepsee-settings",
      "设置",
      90,
      { id: "deepsee-suite", label: "DeepSee", order: 10 },
      "settings",
      domain,
    );
    const model = compileSidebarNavigation(
      [overview, settings],
      {},
      EMPTY_SIDEBAR_NAVIGATION,
    );
    const deepsee = model.projectsById.get("deepsee-suite");

    expect(deepsee?.sections).toHaveLength(0);
    expect(deepsee?.modules.map((item) => item.module.moduleId)).toEqual([
      "deepsee-overview",
    ]);
    expect(deepsee?.settingsModule?.module.moduleId).toBe("deepsee-settings");
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
