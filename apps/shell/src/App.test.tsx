import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { INVESTMENT_DOMAINS } from "@newma-desk/contracts";

import { App, isEmbeddedShellContext } from "./App";
import type { StoredMod } from "./api/modules";
import { ShellEventBus } from "./events/ShellEventBus";
import { server } from "./test/server";

const marketModule = storedModule({
  id: "market-daily",
  name: "市场行情",
  category: "market",
  entry: { type: "structured", url: "/modules/market-daily/" },
});

const researchModule = storedModule({
  id: "research-news",
  name: "研究资讯",
  category: "research",
  entry: { type: "static", url: "/modules/research-news" },
});

const quantModule = storedModule({
  id: "quant-lab",
  name: "量化实验室",
  category: "quant",
  entry: { type: "structured", url: "/modules/quant-lab/" },
});

const investmentDomainLabels = INVESTMENT_DOMAINS.map(
  (domain) => `${domain.name} 项目`,
);

function projectRailLabels(navigation: HTMLElement) {
  return within(navigation)
    .getAllByRole("button")
    .filter((button) => button.classList.contains("project-rail-button"))
    .map((button) => button.getAttribute("aria-label"));
}

function storedModule({
  id,
  name,
  category,
  entry,
  navigation,
  revision = 1,
  status = "published",
}: {
  id: string;
  name: string;
  category: string;
  entry:
    | { type: "structured" | "static"; url: string }
    | { type: "external"; url: string };
  navigation?: StoredMod["manifest"]["navigation"];
  revision?: number;
  status?: StoredMod["status"];
}): StoredMod {
  return {
    moduleId: id,
    revision,
    status,
    manifest: {
      schemaVersion: "1.0",
      id,
      name,
      version: "0.1.0",
      category,
      ...(navigation ? { navigation } : {}),
      entry,
      permissions: ["market.read"],
      dataServices: ["market-data"],
      agentCapabilities: ["market.refresh"],
      events: {
        emits: ["security.selected"],
        accepts: ["date.changed"],
      },
      refresh: { mode: "manual" },
    },
    createdAt: "2026-07-20T00:00:00Z",
  };
}

function serveRegistry(modules: StoredMod[]) {
  server.use(http.get("/api/mods", () => HttpResponse.json(modules)));
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("App", () => {
  it("detects framed Desk shells without inspecting the parent document", () => {
    const topLevel = {};
    expect(
      isEmbeddedShellContext({ self: topLevel, top: topLevel }),
    ).toBe(false);
    expect(
      isEmbeddedShellContext({ self: {}, top: {} }),
    ).toBe(true);
  });

  it("opens the project Mod store and installs a selected Mod from Git", async () => {
    let installed = false;
    let installRequests = 0;
    serveRegistry([marketModule]);
    server.use(
      http.get("/api/store/mods", () =>
        HttpResponse.json({
          id: "newma-desk-official",
          name: "Newma-Desk 官方 Mod 商店",
          repository: "https://github.com/leecyno1/newma-dock",
          ref: "main",
          mods: [
            {
              id: "daily-review",
              name: "每日复盘",
              description: "汇总每日市场变化和复盘结论。",
              version: "0.1.0",
              publisher: "Newma-Desk",
              upstream: "https://github.com/simonlin1212/Vibe-Research",
              category: "今日",
              tags: ["投研", "复盘"],
              defaultInstall: true,
              installState: installed ? "installed" : "available",
              ...(installed ? { installedRevision: 2 } : {}),
              sourceUrl:
                "https://github.com/leecyno1/newma-dock/blob/main/mods/research-suite/suite.json",
            },
          ],
        }),
      ),
      http.post("/api/store/mods/daily-review/install", () => {
        installRequests += 1;
        installed = true;
        return HttpResponse.json(
          {
            action: "installed",
            sourceUrl:
              "https://github.com/leecyno1/newma-dock/blob/main/mods/research-suite/suite.json",
            mod: {
              ...researchModule,
              moduleId: "daily-review",
              revision: 2,
            },
          },
          { status: 201 },
        );
      }),
    );
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Mod 商店" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Mod 商店" }),
    ).toBeVisible();
    expect(screen.getByText("1 / 1 个 Mod")).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: "从 Git 安装 每日复盘" }),
    );

    expect(
      await screen.findByText("每日复盘 已从 Git 安装并加入左侧导航。"),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "已安装 每日复盘" }),
    ).toBeDisabled();
    expect(installRequests).toBe(1);
  });

  it("switches themes and shows immutable complete-project ownership", async () => {
    serveRegistry([marketModule, researchModule]);
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "界面设置" }),
    );
    expect(
      await screen.findByRole("heading", { name: "界面设置" }),
    ).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: /深色/ }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("vibedesk.themeMode")).toBe("dark");
    expect(screen.getAllByText("所属栏目").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("完整项目").length).toBeGreaterThanOrEqual(2);

    await userEvent.click(
      screen.getByRole("button", { name: "保存导航" }),
    );

    const navigation = screen.getByRole("navigation", {
      name: "Newma-Desk Mod 导航",
    });
    expect(projectRailLabels(navigation)).toEqual([
      ...investmentDomainLabels.slice(0, 10),
      "研究资讯 项目",
      ...investmentDomainLabels.slice(10),
      "市场行情 项目",
    ]);
    await userEvent.click(
      within(navigation).getByRole("button", { name: "市场行情 项目" }),
    );
    let projectPanel = screen.getByRole("complementary", {
      name: "市场行情 二级导航",
    });
    expect(within(projectPanel).getByRole("button", { name: "市场行情" })).toBeVisible();
    await userEvent.click(
      within(navigation).getByRole("button", { name: "研究资讯 项目" }),
    );
    projectPanel = screen.getByRole("complementary", {
      name: "研究资讯 二级导航",
    });
    expect(within(projectPanel).getByRole("button", { name: "研究资讯" })).toBeVisible();
    const navigationPreferences = JSON.parse(
      window.localStorage.getItem("vibedesk.sidebarNavigation.v1") || "{}",
    );
    expect(navigationPreferences.modules["market-daily"]?.directory).toBeUndefined();
    expect(navigationPreferences.modules["research-news"]?.directory).toBeUndefined();
  });

  it("customizes and restores a first-level project title", async () => {
    serveRegistry([marketModule]);
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "界面设置" }),
    );
    const titleInput = screen.getByRole("textbox", {
      name: "市场行情 一级标题",
    });
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, "Market Pulse");
    await userEvent.click(screen.getByRole("button", { name: "保存导航" }));

    const navigation = screen.getByRole("navigation", {
      name: "Newma-Desk Mod 导航",
    });
    expect(
      within(navigation).getByRole("button", { name: "Market Pulse 项目" }),
    ).toBeVisible();
    expect(within(navigation).getByText("行情")).toBeVisible();
    expect(
      JSON.parse(
        window.localStorage.getItem("vibedesk.sidebarNavigation.v1") || "{}",
      ).projects["market-daily"].label,
    ).toBe("Market Pulse");

    await userEvent.click(
      within(navigation).getByRole("button", { name: "Market Pulse 项目" }),
    );
    expect(
      screen.getByRole("complementary", { name: "Market Pulse 二级导航" }),
    ).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "界面设置" }));
    await userEvent.click(
      screen.getByRole("button", { name: "恢复 市场行情 默认标题" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "保存导航" }));

    expect(
      within(navigation).getByRole("button", { name: "市场行情 项目" }),
    ).toBeVisible();
    const restoredPreferences = JSON.parse(
      window.localStorage.getItem("vibedesk.sidebarNavigation.v1") || "{}",
    );
    expect(restoredPreferences.projects?.["market-daily"]?.label).toBeUndefined();
  });

  it("opens Agent settings and persists a local CLI selection", async () => {
    let savedBody: unknown;
    serveRegistry([marketModule]);
    server.use(
      http.get("/api/capabilities", () =>
        HttpResponse.json({
          adapters: [
            {
              id: "codex-cli",
              name: "Codex CLI",
              description: "本机 Codex",
              kind: "local-cli",
              available: true,
              supportsMemory: true,
              capabilities: ["chat"],
              default: true,
            },
            {
              id: "claude-cli",
              name: "Claude Code",
              description: "本机 Claude",
              kind: "local-cli",
              available: true,
              supportsMemory: true,
              capabilities: ["chat"],
              default: false,
            },
          ],
          moduleActions: [],
        }),
      ),
      http.get("/api/agent/preferences", () =>
        HttpResponse.json({
          userId: "local-user",
          defaultAdapter: "codex-cli",
          moduleOverrides: {},
          updatedAt: null,
        }),
      ),
      http.put("/api/agent/preferences", async ({ request }) => {
        savedBody = await request.json();
        return HttpResponse.json({
          userId: "local-user",
          ...(savedBody as object),
          updatedAt: "2026-07-21T00:00:00Z",
        });
      }),
    );
    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Agent 设置" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Agent 设置" }),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: /Claude Code/ }),
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "claude-cli");
    await userEvent.click(
      screen.getByRole("button", { name: "保存设置" }),
    );

    await waitFor(() =>
      expect(savedBody).toEqual({
        defaultAdapter: "claude-cli",
        moduleOverrides: { "market-daily": "claude-cli" },
      }),
    );
    expect(
      screen.getByText(/Agent 选择已保存/),
    ).toBeVisible();
  });

  it("uses Mod navigation metadata for the Newma-Desk sidebar", async () => {
    const laterResearch = storedModule({
      id: "research-later",
      name: "后置研究",
      category: "research-custom",
      navigation: {
        groupLabel: "研究工作",
        groupOrder: 30,
        itemOrder: 20,
        project: {
          id: "research-work",
          name: "研究工作",
          order: 30,
          logo: { type: "letter", text: "研" },
        },
        icon: "research",
      },
      entry: { type: "static", url: "/modules/research-later/" },
    });
    const firstResearch = storedModule({
      id: "research-first",
      name: "前置研究",
      category: "research-custom",
      navigation: {
        groupLabel: "研究工作",
        groupOrder: 30,
        itemOrder: 10,
        project: {
          id: "research-work",
          name: "研究工作",
          order: 30,
          logo: { type: "letter", text: "研" },
        },
        icon: "research",
      },
      entry: { type: "static", url: "/modules/research-first/" },
    });
    const firstGroup = storedModule({
      id: "quant-first",
      name: "量化入口",
      category: "quant-custom",
      navigation: {
        groupLabel: "量化工作",
        groupOrder: 10,
        itemOrder: 10,
        project: {
          id: "quant-work",
          name: "量化工作",
          order: 10,
          logo: { type: "icon", name: "quant" },
        },
        icon: "quant",
      },
      entry: { type: "structured", url: "/modules/quant-first/" },
    });
    const fallback = storedModule({
      id: "custom-module",
      name: "自定义 Mod",
      category: "custom",
      entry: { type: "structured", url: "/modules/custom-module/" },
    });
    serveRegistry([laterResearch, fallback, firstGroup, firstResearch]);

    render(<App />);

    expect(await screen.findByRole("img", { name: "Newma-Desk" })).toBeVisible();
    const navigation = screen.getByRole("navigation", {
      name: "Newma-Desk Mod 导航",
    });
    expect(projectRailLabels(navigation)).toEqual([
      investmentDomainLabels[0],
      "量化工作 项目",
      ...investmentDomainLabels.slice(1, 3),
      "研究工作 项目",
      ...investmentDomainLabels.slice(3),
      "自定义 Mod 项目",
    ]);
    expect(
      within(navigation).getByRole("button", { name: "量化工作 项目" }),
    ).toHaveTextContent("量化");
    expect(
      within(navigation).getByRole("button", { name: "研究工作 项目" }),
    ).toHaveTextContent("研究");
    expect(
      within(navigation).getByRole("button", { name: "自定义 Mod 项目" }),
    ).toHaveTextContent("自定");
    expect(within(navigation).queryByText("研")).not.toBeInTheDocument();
    await userEvent.click(
      within(navigation).getByRole("button", { name: "研究工作 项目" }),
    );
    const projectPanel = screen.getByRole("complementary", {
      name: "研究工作 二级导航",
    });
    expect(
      within(projectPanel)
        .getAllByRole("button")
        .filter((button) => button.classList.contains("module-button"))
        .map((button) => button.textContent),
    ).toEqual(["前置研究", "后置研究"]);
  });

  it("opens secondary navigation and persists pinning and drag placement", async () => {
    const watchlist = storedModule({
      id: "watchlist",
      name: "自选股",
      category: "market",
      navigation: {
        groupLabel: "市场",
        groupOrder: 10,
        itemOrder: 30,
        label: "自选股",
        project: { id: "market-suite", name: "行情工具", order: 10 },
        icon: "market",
      },
      entry: { type: "static", url: "/modules/watchlist/" },
    });
    const terminal = storedModule({
      id: "market-terminal",
      name: "市场终端",
      category: "market",
      navigation: {
        groupLabel: "市场",
        groupOrder: 10,
        itemOrder: 10,
        label: "终端",
        directory: { id: "market-suite", label: "行情工具", order: 5 },
        project: { id: "market-suite", name: "行情工具", order: 10 },
        icon: "market",
      },
      entry: { type: "static", url: "/modules/market-terminal/" },
    });
    const scanner = storedModule({
      id: "market-scanner",
      name: "市场扫描器",
      category: "market",
      navigation: {
        groupLabel: "市场",
        groupOrder: 10,
        itemOrder: 20,
        label: "扫描器",
        directory: { id: "market-suite", label: "行情工具", order: 5 },
        project: { id: "market-suite", name: "行情工具", order: 10 },
        icon: "market",
      },
      entry: { type: "static", url: "/modules/market-scanner/" },
    });
    serveRegistry([watchlist, terminal, scanner]);
    render(<App />);

    const projectButton = await screen.findByRole("button", {
      name: "行情工具 项目",
    });
    await userEvent.click(projectButton);
    const secondary = screen.getByRole("complementary", {
      name: "行情工具 二级导航",
    });
    expect(projectButton).toHaveAttribute("aria-expanded", "true");
    expect(within(secondary).getByRole("button", { name: "自选股" })).toBeVisible();
    expect(within(secondary).getByRole("button", { name: "终端" })).toBeVisible();
    expect(within(secondary).getByRole("button", { name: "终端" })).toBeVisible();
    expect(within(secondary).getByRole("button", { name: "扫描器" })).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: "冻结 行情工具 项目" }),
    );
    expect(projectButton.closest(".project-rail-item")).toHaveAttribute(
      "draggable",
      "false",
    );
    expect(
      JSON.parse(
        window.localStorage.getItem("vibedesk.sidebarNavigation.v1") || "{}",
      ).projects["market-suite"].pinned,
    ).toBe(true);

    await userEvent.click(
      within(secondary).getByRole("button", { name: "冻结 扫描器" }),
    );
    expect(
      within(secondary)
        .getByRole("button", { name: "扫描器" })
        .closest(".module-nav-row"),
    ).toHaveAttribute("draggable", "false");
    expect(
      JSON.parse(
        window.localStorage.getItem("vibedesk.sidebarNavigation.v1") || "{}",
      ).modules["market-scanner"].pinned,
    ).toBe(true);

    const dataTransfer = {
      effectAllowed: "",
      setData: vi.fn(),
      getData: vi.fn(),
    };
    fireEvent.dragStart(
      within(secondary).getByRole("button", { name: "自选股" }).closest(".module-nav-row")!,
      { dataTransfer },
    );
    fireEvent.drop(
      within(secondary).getByRole("button", { name: "扫描器" }).closest(".module-nav-row")!,
      {
      dataTransfer,
      },
    );

    await waitFor(() => expect(
      JSON.parse(
        window.localStorage.getItem("vibedesk.sidebarNavigation.v1") || "{}",
      ).modules.watchlist?.directory,
    ).toBeUndefined());
  });

  it("switches project logos to their first Mod without leaving the previous project active", async () => {
    const deepsee = storedModule({
      id: "deepsee-overview",
      name: "Deepsee 数据看板",
      category: "deepsee",
      navigation: {
        groupLabel: "Deepsee",
        groupOrder: 60,
        itemOrder: 10,
        label: "总览",
        directory: { id: "deepsee-suite", label: "Deepsee 功能", order: 5 },
        icon: "module",
      },
      entry: { type: "external", url: "http://127.0.0.1:8001/embed/dashboard" },
    });
    const terminal = storedModule({
      id: "market-terminal",
      name: "市场终端",
      category: "market",
      navigation: {
        groupLabel: "市场",
        groupOrder: 10,
        itemOrder: 10,
        label: "终端",
        directory: { id: "market-suite", label: "行情工具", order: 5 },
        icon: "market",
      },
      entry: { type: "static", url: "/modules/market-terminal/" },
    });
    window.history.replaceState(null, "", "/?mod=deepsee-overview");
    serveRegistry([deepsee, terminal]);
    render(<App />);

    const deepseeProject = await screen.findByRole("button", {
      name: "Deepsee 功能 项目",
    });
    const marketProject = screen.getByRole("button", {
      name: "行情工具 项目",
    });
    await waitFor(() =>
      expect(deepseeProject).toHaveAttribute("aria-expanded", "true"),
    );
    expect(screen.getByTitle("Deepsee 数据看板")).toBeVisible();

    await userEvent.click(deepseeProject);

    expect(deepseeProject).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("complementary", { name: "Deepsee 功能 二级导航" }),
    ).toBeVisible();
    expect(deepseeProject.closest(".sidebar-shell")).toHaveAttribute(
      "data-navigation-collapsed",
      "false",
    );

    await userEvent.click(marketProject);

    expect(await screen.findByTitle("市场终端")).toBeVisible();
    expect(window.location.search).toBe("?mod=market-terminal");
    expect(marketProject).toHaveAttribute("aria-expanded", "true");
    expect(deepseeProject).toHaveAttribute("aria-expanded", "false");
  });

  it("adds project settings to every secondary directory and saves unified data routing", async () => {
    let savedBody: unknown;
    const terminal: StoredMod = {
      moduleId: "market-terminal",
      revision: 1,
      status: "published",
      manifest: {
        schemaVersion: "1.1",
        id: "market-terminal",
        name: "市场终端",
        version: "1.0.0",
        category: "market",
        navigation: {
          groupLabel: "市场",
          groupOrder: 10,
          itemOrder: 10,
          label: "终端",
          directory: { id: "market-suite", label: "行情工具", order: 5 },
          project: {
            id: "market-surface",
            name: "市场面",
            order: 10,
            logo: { type: "letter", text: "市" },
          },
          icon: "market",
        },
        entry: { type: "static", url: "/modules/market-terminal/" },
        compatibility: { level: 2, bridgeProtocol: "1.0" },
        permissions: ["market.read"],
        dataServices: [],
        actions: {
          "market.quote": {
            binding: { type: "data" },
            execution: "request",
            permission: "market.read",
            confirmation: "none",
          },
        },
        events: { emits: [], accepts: [] },
      },
      createdAt: "2026-07-20T00:00:00Z",
    };
    const scanner = storedModule({
      id: "market-scanner",
      name: "市场扫描器",
      category: "market",
      navigation: {
        groupLabel: "市场",
        groupOrder: 10,
        itemOrder: 20,
        label: "扫描器",
        directory: { id: "market-suite", label: "行情工具", order: 5 },
        project: {
          id: "market-surface",
          name: "市场面",
          order: 10,
          logo: { type: "letter", text: "市" },
        },
        icon: "market",
      },
      entry: { type: "static", url: "/modules/market-scanner/" },
    });
    serveRegistry([terminal, scanner]);
    server.use(
      http.get("/api/data-services/catalog", () => HttpResponse.json({
        version: "1.0",
        capabilities: [
          {
            id: "market.quote",
            permissions: ["market.read"],
            providers: [
              {
                id: "market-data",
                name: "Newma-Desk 市场数据",
                description: "统一市场数据",
                priority: 10,
                transport: "rest",
              },
              {
                id: "backup-market",
                name: "备用行情",
                description: "备用市场数据",
                priority: 20,
                transport: "rest",
              },
            ],
          },
        ],
      })),
      http.get("/api/data-services/preferences/market-suite", () =>
        HttpResponse.json({
          userId: "local-user",
          workspaceId: "local-workspace",
          suiteId: "market-suite",
          capabilityServices: {},
          updatedAt: null,
        }),
      ),
      http.put(
        "/api/data-services/preferences/market-suite",
        async ({ request }) => {
          savedBody = await request.json();
          return HttpResponse.json({
            userId: "local-user",
            workspaceId: "local-workspace",
            suiteId: "market-suite",
            ...(savedBody as object),
            updatedAt: "2026-07-24T00:00:00Z",
          });
        },
      ),
    );
    render(<App />);

    const secondary = await screen.findByRole("complementary", {
      name: "市场面 二级导航",
    });
    expect(within(secondary).getByRole("heading", { name: /行情工具/ })).toBeVisible();
    await userEvent.click(
      within(secondary).getByRole("button", { name: "项目设置" }),
    );

    expect(
      await screen.findByRole("heading", { name: "行情工具 · 项目设置" }),
    ).toBeVisible();
    expect(window.location.search).toContain("view=suite-settings");
    expect(window.location.search).toContain("directory=market-suite");
    expect(
      screen.getByRole("complementary", { name: "市场面 二级导航" }),
    ).toBeVisible();
    expect(screen.getByText("market.quote")).toBeVisible();

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "market.quote Provider" }),
      "backup-market",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "保存数据路由" }),
    );

    await waitFor(() => expect(savedBody).toEqual({
      capabilityServices: { "market.quote": "backup-market" },
    }));
    expect(screen.getByText(/项目数据路由已保存/)).toBeVisible();
  });

  it("collapses and restores primary and secondary navigation together", async () => {
    const terminal = storedModule({
      id: "market-terminal",
      name: "市场终端",
      category: "market",
      navigation: {
        groupLabel: "市场",
        groupOrder: 10,
        itemOrder: 10,
        label: "终端",
        directory: { id: "market-suite", label: "行情工具", order: 5 },
        icon: "market",
      },
      entry: { type: "static", url: "/modules/market-terminal/" },
    });
    serveRegistry([terminal]);
    render(<App />);

    const secondary = await screen.findByRole("complementary", {
      name: "行情工具 二级导航",
    });
    const shell = secondary.closest(".sidebar-shell");
    expect(shell).toHaveAttribute("data-navigation-collapsed", "false");

    await userEvent.click(
      within(secondary).getByRole("button", { name: "收起一级与二级导航" }),
    );
    expect(shell).toHaveAttribute("data-navigation-collapsed", "true");

    await userEvent.click(
      screen.getByRole("button", { name: "展开一级与二级导航" }),
    );
    expect(shell).toHaveAttribute("data-navigation-collapsed", "false");
    expect(
      screen.getByRole("complementary", { name: "行情工具 二级导航" }),
    ).toBeInTheDocument();
  });

  it("closes its shell event bus on unmount", async () => {
    const close = vi.spyOn(ShellEventBus.prototype, "close");
    serveRegistry([marketModule]);
    const view = render(<App />);
    await screen.findByTitle("市场行情");

    view.unmount();

    expect(close).toHaveBeenCalledTimes(1);
  });

  it("renders registry modules and opens the selected URL", async () => {
    serveRegistry([marketModule]);
    render(<App />);

    const moduleButton = await screen.findByRole("button", {
      name: "市场行情",
    });
    expect(moduleButton).toBeVisible();

    await userEvent.click(moduleButton);

    const frame = screen.getByTitle("市场行情");
    expect(frame).toHaveAttribute(
      "src",
      "http://127.0.0.1:5891/modules/market-daily/",
    );
    expect(frame).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-forms allow-downloads allow-popups allow-same-origin",
    );
    expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(frame).toHaveAttribute(
      "allow",
      "clipboard-read; clipboard-write; fullscreen",
    );
  });

  it("keeps loaded modules visible when a manual registry reload fails", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/mods", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json([marketModule])
          : new HttpResponse(null, { status: 503 });
      }),
    );
    render(<App />);
    expect(
      await screen.findByRole("button", { name: "市场行情" }),
    ).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "重新加载 Mod" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "mod registry returned 503",
    );
    expect(
      screen.getByRole("button", { name: "市场行情" }),
    ).toBeVisible();
    expect(screen.getByTitle("市场行情")).toBeVisible();
    expect(screen.getByRole("button", { name: "重试" })).toBeVisible();
  });

  it("prefers the query selection, persists changes, and handles popstate", async () => {
    window.history.replaceState(null, "", "/?module=quant-lab");
    window.localStorage.setItem("vibedesk.activeMod", "market-daily");
    serveRegistry([marketModule, researchModule, quantModule]);
    render(<App />);

    const quantProject = await screen.findByRole("button", {
      name: "量化实验室 项目",
    });
    await waitFor(() =>
      expect(quantProject).toHaveAttribute("aria-current", "page"),
    );
    expect(
      await screen.findByRole("button", { name: "量化实验室" }),
    ).toHaveAttribute("aria-current", "page");

    await userEvent.click(screen.getByRole("button", { name: "市场行情 项目" }));
    expect(window.location.search).toBe("?mod=market-daily");
    expect(window.localStorage.getItem("vibedesk.activeMod")).toBe(
      "market-daily",
    );

    window.history.replaceState(null, "", "/?mod=research-news");
    window.dispatchEvent(new PopStateEvent("popstate"));

    expect(await screen.findByTitle("研究资讯")).toBeVisible();
    expect(
      await screen.findByRole("button", { name: "研究资讯" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("opens the Agent sidebar from a deep link and removes the URL flag on close", async () => {
    window.history.replaceState(null, "", "/?mod=market-daily&copilot=1");
    serveRegistry([marketModule]);
    server.use(
      http.get("/api/capabilities", () => HttpResponse.json({
        adapters: [
          {
            id: "codex-cli",
            name: "Codex CLI",
            kind: "local-cli",
            available: true,
            supportsMemory: true,
            capabilities: ["chat"],
            default: true,
          },
        ],
        moduleActions: [],
      })),
      http.get("/api/agent/preferences", () => HttpResponse.json({
        userId: "local-user",
        defaultAdapter: "codex-cli",
        moduleOverrides: {},
        updatedAt: null,
      })),
    );
    render(<App />);

    const toggle = await screen.findByRole("button", { name: "问当前 Mod" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(
      await screen.findByRole("button", { name: "关闭 Agent 侧栏" }),
    );

    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(window.location.search).toBe("?mod=market-daily");
  });

  it("reuses the host shell when embedded and renders only the selected Mod", async () => {
    window.history.replaceState(null, "", "/?mod=market-daily&copilot=1");
    serveRegistry([marketModule]);

    render(<App embedded />);

    expect(await screen.findByTitle("市场行情")).toBeVisible();
    expect(document.querySelector(".shell-layout")).toHaveAttribute(
      "data-embedded",
      "true",
    );
    expect(
      screen.queryByRole("navigation", { name: "Newma-Desk Mod 导航" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "问当前 Mod" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "关闭 Agent 侧栏" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "独立打开" })).not.toBeInTheDocument();
    expect(window.location.search).toBe("?mod=market-daily&copilot=1");
  });

  it("falls back to localStorage when the query module is invalid", async () => {
    window.history.replaceState(null, "", "/?module=missing");
    window.localStorage.setItem("vibe.shell.activeModule", "research-news");
    serveRegistry([marketModule, researchModule]);
    render(<App />);

    expect(await screen.findByTitle("研究资讯")).toBeVisible();
  });

  it("shows an empty state for an empty registry", async () => {
    serveRegistry([]);
    render(<App />);

    expect(await screen.findByText("尚无已发布 Mod")).toBeVisible();
  });

  it("loads an exact draft preview without adding it to the sidebar", async () => {
    const draft = storedModule({
      id: "preview-lab",
      name: "草稿实验室",
      category: "quant",
      entry: { type: "structured", url: "/modules/preview-lab/" },
      revision: 7,
      status: "draft",
    });
    window.history.replaceState(null, "", "/?preview=preview-lab@7");
    window.localStorage.setItem("vibedesk.activeMod", "market-daily");
    serveRegistry([marketModule]);
    server.use(
      http.get("/api/mods/preview-lab/revisions/7", () =>
        HttpResponse.json(draft),
      ),
    );
    render(<App />);

    expect(await screen.findByText("预览，尚未发布")).toBeVisible();
    expect(screen.getByTitle("草稿实验室")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "草稿实验室 项目" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "市场行情 项目" }),
    ).toBeVisible();
    expect(window.localStorage.getItem("vibedesk.activeMod")).toBe(
      "market-daily",
    );
  });

  it("shows a safe retry state for invalid preview syntax", async () => {
    window.history.replaceState(null, "", "/?preview=not-a-revision");
    serveRegistry([marketModule]);
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("预览地址无效");
    expect(screen.getByRole("button", { name: "重试" })).toBeVisible();
    expect(screen.queryByRole("iframe")).not.toBeInTheDocument();
  });

  it("renders a configuration error instead of a same-origin iframe", async () => {
    vi.stubEnv("VITE_MOD_ORIGIN", window.location.origin);
    serveRegistry([marketModule]);
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mod 服务必须使用与 Newma-Desk 不同的 origin",
    );
    expect(screen.queryByRole("iframe")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "市场行情 项目" }),
    ).toBeVisible();
  });

  it("rejects a same-origin external module without removing the sidebar", async () => {
    const sameOriginExternal = storedModule({
      id: "external-local",
      name: "同源外部 Mod",
      category: "research",
      entry: {
        type: "external",
        url: `${window.location.origin}/embedded`,
      },
    });
    serveRegistry([sameOriginExternal]);
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mod 页面必须使用与 Newma-Desk 不同的 origin",
    );
    expect(screen.queryByRole("iframe")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "同源外部 Mod 项目" }),
    ).toBeVisible();
  });

  it("keeps an external URL and exposes it through the open link", async () => {
    const external = storedModule({
      id: "external-research",
      name: "外部研究",
      category: "research",
      entry: { type: "external", url: "https://example.com/research?id=42" },
    });
    serveRegistry([external]);
    render(<App />);

    expect(await screen.findByTitle("外部研究")).toHaveAttribute(
      "src",
      "https://example.com/research?id=42",
    );
    expect(screen.getByRole("link", { name: "独立打开" })).toHaveAttribute(
      "href",
      "https://example.com/research?id=42",
    );
    expect(screen.getByRole("link", { name: "独立打开" })).toHaveAttribute(
      "rel",
      "noreferrer",
    );
  });

  it("turns a malformed registry row into a visible retryable error", async () => {
    server.use(
      http.get("/api/mods", () =>
        HttpResponse.json([{ ...marketModule, manifest: { id: "bad" } }]),
      ),
    );
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "mod registry returned malformed data",
    );
    expect(screen.getByRole("button", { name: "重试" })).toBeVisible();
  });

  it("ignores an older preview response after switching preview targets", async () => {
    const firstStarted = deferred();
    const releaseFirst = deferred();
    const firstDraft = storedModule({
      id: "preview-one",
      name: "预览一",
      category: "quant",
      entry: { type: "structured", url: "/modules/preview-one/" },
      revision: 1,
      status: "draft",
    });
    const secondDraft = storedModule({
      id: "preview-two",
      name: "预览二",
      category: "quant",
      entry: { type: "structured", url: "/modules/preview-two/" },
      revision: 2,
      status: "draft",
    });
    window.history.replaceState(null, "", "/?preview=preview-one@1");
    serveRegistry([marketModule]);
    server.use(
      http.get("/api/mods/preview-one/revisions/1", async () => {
        firstStarted.resolve();
        await releaseFirst.promise;
        return HttpResponse.json(firstDraft);
      }),
      http.get("/api/mods/preview-two/revisions/2", () =>
        HttpResponse.json(secondDraft),
      ),
    );
    render(<App />);
    await firstStarted.promise;

    window.history.replaceState(null, "", "/?preview=preview-two@2");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(await screen.findByTitle("预览二")).toBeVisible();

    await act(async () => releaseFirst.resolve());

    await waitFor(() => {
      expect(screen.getByTitle("预览二")).toBeVisible();
      expect(screen.queryByTitle("预览一")).not.toBeInTheDocument();
    });
  });

  it("ignores a stale preview error after returning to a published module", async () => {
    const previewStarted = deferred();
    const releasePreview = deferred();
    window.history.replaceState(null, "", "/?preview=preview-one@1");
    serveRegistry([marketModule]);
    server.use(
      http.get("/api/mods/preview-one/revisions/1", async () => {
        previewStarted.resolve();
        await releasePreview.promise;
        return new HttpResponse(null, { status: 503 });
      }),
    );
    render(<App />);
    await previewStarted.promise;

    window.history.replaceState(null, "", "/?mod=market-daily");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(await screen.findByTitle("市场行情")).toBeVisible();

    await act(async () => releasePreview.resolve());

    await waitFor(() => {
      expect(screen.getByTitle("市场行情")).toBeVisible();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.queryByText("预览，尚未发布")).not.toBeInTheDocument();
    });
  });

  it.each(["published", "disabled"] as const)(
    "rejects a %s revision as a draft preview",
    async (status) => {
      const nonDraft = storedModule({
        id: "preview-lab",
        name: "非草稿修订",
        category: "quant",
        entry: { type: "structured", url: "/modules/preview-lab/" },
        revision: 7,
        status,
      });
      window.history.replaceState(null, "", "/?preview=preview-lab@7");
      serveRegistry([marketModule]);
      server.use(
        http.get("/api/mods/preview-lab/revisions/7", () =>
          HttpResponse.json(nonDraft),
        ),
      );
      render(<App />);

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "仅草稿修订可预览",
      );
      expect(screen.queryByTitle("非草稿修订")).not.toBeInTheDocument();
      expect(screen.queryByText("预览，尚未发布")).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "市场行情 项目" }),
      ).toBeVisible();
    },
  );

  it("orders project logos deterministically and opens each project page", async () => {
    const secondMarket = storedModule({
      id: "market-alpha",
      name: "A 股总览",
      category: "market",
      entry: { type: "static", url: "/modules/market-alpha/" },
    });
    serveRegistry([quantModule, marketModule, researchModule, secondMarket]);
    render(<App />);

    const navigation = await screen.findByRole("navigation", {
      name: "Newma-Desk Mod 导航",
    });
    expect(projectRailLabels(navigation)).toEqual([
      ...investmentDomainLabels.slice(0, 10),
      "研究资讯 项目",
      ...investmentDomainLabels.slice(10),
      "A 股总览 项目",
      "市场行情 项目",
      "量化实验室 项目",
    ]);
    await userEvent.click(
      within(navigation).getByRole("button", { name: "A 股总览 项目" }),
    );
    const projectPanel = screen.getByRole("complementary", {
      name: "A 股总览 二级导航",
    });
    expect(within(projectPanel).getByRole("button", { name: "A 股总览" })).toBeVisible();
  });

  it("shows frame loading and error states without removing the sidebar", async () => {
    serveRegistry([marketModule]);
    render(<App />);

    const frame = await screen.findByTitle("市场行情");
    expect(screen.getByText("正在加载 Mod…")).toBeVisible();
    fireEvent.error(frame);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mod 页面可能未能加载",
    );
    expect(
      screen.getByRole("button", { name: "市场行情" }),
    ).toBeVisible();
  });
});
