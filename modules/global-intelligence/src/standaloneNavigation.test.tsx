import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";
import { GlobalIntelligenceApp } from "./App";
import type { GlobalIntelDataSource } from "./data";

vi.mock("./IntelligenceMap", () => ({ IntelligenceMap: () => <div>地图测试替身</div> }));
vi.mock("@newma-desk/mod-sdk", async importOriginal => ({
  ...await importOriginal<typeof import("@newma-desk/mod-sdk")>(), connectModHost: vi.fn(),
}));
const source: GlobalIntelDataSource = {
  health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}),
  crucixSnapshot: async () => ({}), subscribe: () => () => {},
};
const pages = [
  { mod: "global-situation", title: "全球情报", topic: null },
  { mod: "fed-rates", title: "联储加息", topic: "fed-rates" },
  { mod: "hormuz-conflict", title: "美伊战争", topic: "hormuz" },
  { mod: "us-china-trade", title: "中美贸易", topic: "us-china-trade" },
];
beforeEach(() => {
  vi.mocked(connectModHost).mockReset().mockResolvedValue({ embedded: false, close() {} });
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value) });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const topicId = new URL(url).pathname.split("/").at(-1);
    return Response.json({ topicId, title: "导航测试", subtitle: "", question: "", accent: "cyan",
      metrics: [{ label: "合成来源观测", value: topicId, change: "仅验证入口" }], factors: [], series: [],
      observations: [], events: [], transmission: [], sources: [], dataMode: "source-observations",
      forecast: { probabilities: [], dominantScenario: "", confidence: 0, method: "测试", disclaimer: "测试" } });
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test.each(pages)("standalone $mod opens the matching page and data endpoint", async page => {
  history.replaceState({}, "", `/?mod=${page.mod}`);
  render(<GlobalIntelligenceApp dataSource={source} />);
  await waitFor(() => expect(document.title).toBe(`${page.title} · Newma-Desk`));
  const nav = screen.getByRole("navigation", { name: "全球研究" });
  expect(within(nav).getByRole("link", { current: "page" })).toHaveTextContent(page.title);
  expect(within(nav).getAllByRole("link")).toHaveLength(4);
  await waitFor(() => expect(connectModHost).toHaveBeenCalled());
  expect(vi.mocked(connectModHost).mock.calls[0]![0].modId).toBe(page.mod);
  if (page.topic) {
    await screen.findByText("合成来源观测");
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(fetch).mock.calls[0]![0]).toBe(`${location.origin}/api/global-topics/${page.topic}`);
  } else expect(fetch).not.toHaveBeenCalled();
});

test("all four links reopen their own page under a deployment prefix without losing unrelated URL fields", async () => {
  history.replaceState({}, "", "/mods/global-intelligence/?topic=hormuz&mod=hormuz-conflict&extra=keep#evidence");
  let app = render(<GlobalIntelligenceApp dataSource={source} />);
  for (const page of pages) {
    const link = within(screen.getByRole("navigation", { name: "全球研究" })).getByRole("link", { name: page.title });
    const url = new URL(link.getAttribute("href")!, location.origin);
    expect(url.pathname).toBe("/mods/global-intelligence/");
    expect(url.searchParams.get("mod")).toBe(page.mod);
    expect(url.searchParams.get("topic")).toBe(page.topic);
    expect(url.searchParams.get("extra")).toBe("keep");
    expect(url.hash).toBe("#evidence");
    app.unmount();
    history.replaceState({}, "", url);
    app = render(<GlobalIntelligenceApp dataSource={source} />);
    await waitFor(() => expect(document.title).toBe(`${page.title} · Newma-Desk`));
    expect(within(screen.getByRole("navigation", { name: "全球研究" })).getByRole("link", { current: "page" })).toHaveTextContent(page.title);
  }
});

test("legacy topic links still take precedence over mod and invalid topics fall back to mod", async () => {
  history.replaceState({}, "", "/?topic=us-china-trade&mod=fed-rates");
  const app = render(<GlobalIntelligenceApp dataSource={source} />);
  await waitFor(() => expect(document.title).toBe("中美贸易 · Newma-Desk"));
  app.unmount();
  history.replaceState({}, "", "/?topic=unknown&mod=hormuz-conflict");
  render(<GlobalIntelligenceApp dataSource={source} />);
  await waitFor(() => expect(document.title).toBe("美伊战争 · Newma-Desk"));
});

test("the real iframe entry waits for its host and hides standalone chrome without needing an embedded prop", async () => {
  history.replaceState({}, "", "/?mod=fed-rates");
  vi.spyOn(window, "parent", "get").mockReturnValue({} as Window);
  type Host = Extract<ModHostConnection, { embedded: true }>;
  let authorize!: (connection: Host) => void;
  vi.mocked(connectModHost).mockImplementation(() => new Promise(resolve => { authorize = resolve; }));
  render(<GlobalIntelligenceApp />);
  expect(screen.queryByRole("navigation", { name: "全球研究" })).toBeNull();
  expect(screen.queryByRole("button", { name: "刷新情报" })).toBeNull();
  expect(document.querySelector("main")?.getAttribute("data-embedded")).toBe("true");
  expect(fetch).not.toHaveBeenCalled();
  authorize({ embedded: true, config: { modId: "fed-rates", instanceId: "test-instance",
    user: { id: "test-user" }, workspace: { id: "test-workspace" },
    session: { accessToken: "synthetic-token" }, environment: { theme: "light" },
    gateways: { data: `${location.origin}/api/data` }, grants: { permissions: ["market.read"] } },
    subscribe: () => () => {}, close() {}, publishContext() {},
    setContextProvider: () => () => {}, setUiActionHandler: () => () => {},
  } as unknown as Host);
  await screen.findByText("合成来源观测");
  expect(screen.queryByRole("navigation", { name: "全球研究" })).toBeNull();
  expect(screen.queryByRole("button", { name: "刷新情报" })).toBeNull();
  const headers = new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers);
  expect(headers.get("Authorization")).toBe("Bearer synthetic-token");
  expect(headers.get("X-Newma-Desk-Instance-Id")).toBe("test-instance");
  expect(vi.mocked(connectModHost).mock.calls[0]![0].modId).toBe("fed-rates");
  expect(location.search).toBe("?mod=fed-rates");
});
