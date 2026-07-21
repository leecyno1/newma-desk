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

import { App } from "./App";
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
  it("opens the project Mod store and installs a selected Mod from Git", async () => {
    let installed = false;
    let installRequests = 0;
    serveRegistry([marketModule]);
    server.use(
      http.get("/api/store/mods", () =>
        HttpResponse.json({
          id: "vibedesk-official",
          name: "VibeDesk 官方 Mod 商店",
          repository: "https://github.com/leecyno1/vibedesk",
          ref: "main",
          mods: [
            {
              id: "daily-review",
              name: "每日复盘",
              description: "汇总每日市场变化和复盘结论。",
              version: "0.1.0",
              publisher: "VibeDesk",
              upstream: "https://github.com/simonlin1212/Vibe-Research",
              category: "今日",
              tags: ["投研", "复盘"],
              defaultInstall: true,
              installState: installed ? "installed" : "available",
              ...(installed ? { installedRevision: 2 } : {}),
              sourceUrl:
                "https://github.com/leecyno1/vibedesk/blob/main/mods/daily-review/mod.json",
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
              "https://github.com/leecyno1/vibedesk/blob/main/mods/daily-review/mod.json",
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

  it("switches themes and lets the user define sidebar categories", async () => {
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

    await userEvent.type(
      screen.getByRole("combobox", { name: "市场行情分类" }),
      "我的关注",
    );
    await userEvent.type(
      screen.getByRole("combobox", { name: "研究资讯分类" }),
      "我的关注",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "保存分类" }),
    );

    const navigation = screen.getByRole("navigation", {
      name: "VibeDesk Mod 导航",
    });
    const customGroup = within(navigation).getByRole("group", {
      name: "我的关注",
    });
    expect(
      within(customGroup)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(["市场行情", "研究资讯"]);
    expect(
      JSON.parse(
        window.localStorage.getItem("vibedesk.moduleCategories.v1") || "{}",
      ),
    ).toEqual({
      "market-daily": "我的关注",
      "research-news": "我的关注",
    });
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

  it("uses Mod navigation metadata for the VibeDesk sidebar", async () => {
    const laterResearch = storedModule({
      id: "research-later",
      name: "后置研究",
      category: "research-custom",
      navigation: {
        groupLabel: "研究工作",
        groupOrder: 30,
        itemOrder: 20,
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

    expect(await screen.findByText("VibeDesk")).toBeVisible();
    expect(screen.getByText("智能模组工作台")).toBeVisible();
    const navigation = screen.getByRole("navigation", {
      name: "VibeDesk Mod 导航",
    });
    expect(
      within(navigation)
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual(["量化工作", "研究工作", "custom"]);
    expect(
      within(
        screen.getByRole("group", { name: "研究工作" }),
      ).getAllByRole("button").map((button) => button.textContent),
    ).toEqual(["前置研究", "后置研究"]);
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

    expect(await screen.findByTitle("量化实验室")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "量化实验室" }),
    ).toHaveAttribute("aria-current", "page");

    await userEvent.click(screen.getByRole("button", { name: "市场行情" }));
    expect(window.location.search).toBe("?mod=market-daily");
    expect(window.localStorage.getItem("vibedesk.activeMod")).toBe(
      "market-daily",
    );

    window.history.replaceState(null, "", "/?mod=research-news");
    window.dispatchEvent(new PopStateEvent("popstate"));

    expect(await screen.findByTitle("研究资讯")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "研究资讯" }),
    ).toHaveAttribute("aria-current", "page");
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
      screen.queryByRole("button", { name: "草稿实验室" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "市场行情" }),
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
      "Mod 服务必须使用与 VibeDesk 不同的 origin",
    );
    expect(screen.queryByRole("iframe")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "市场行情" }),
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
      "Mod 页面必须使用与 VibeDesk 不同的 origin",
    );
    expect(screen.queryByRole("iframe")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "同源外部 Mod" }),
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
        screen.getByRole("button", { name: "市场行情" }),
      ).toBeVisible();
    },
  );

  it("orders category groups and module buttons deterministically", async () => {
    const secondMarket = storedModule({
      id: "market-alpha",
      name: "A 股总览",
      category: "market",
      entry: { type: "static", url: "/modules/market-alpha/" },
    });
    serveRegistry([quantModule, marketModule, researchModule, secondMarket]);
    render(<App />);

    await screen.findByRole("button", { name: "市场行情" });
    expect(
      screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent),
    ).toEqual(["研究", "市场", "量化"]);

    const marketGroup = screen.getByRole("group", { name: "市场" });
    expect(
      within(marketGroup)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(["A 股总览", "市场行情"]);
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
