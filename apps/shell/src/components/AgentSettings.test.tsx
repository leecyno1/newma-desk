import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import type { AgentPreferences } from "../api/agents";
import type { StoredMod } from "../api/modules";
import { server } from "../test/server";
import { AgentSettings } from "./AgentSettings";

const modules: StoredMod[] = ([
  ["news-radar", "新闻与舆情"],
  ["market-daily", "行情"],
  ["quick-only", "快速观察"],
] as const).map(([id, name]) => ({
  moduleId: id,
  revision: 1,
  status: "published",
  createdAt: "2026-09-09T00:00:00Z",
  manifest: {
    schemaVersion: "1.0",
    id,
    name,
    version: "1.0.0",
    category: "research",
    entry: { type: "static", url: `/modules/${id}/` },
    permissions: [],
    dataServices: [],
    agentCapabilities: id === "quick-only" ? [] : ["module.explain"],
    events: { emits: [], accepts: [] },
    refresh: { mode: "manual" },
  },
}));

function serveSettings() {
  let saved: AgentPreferences = {
    userId: "settings-test",
    defaultAdapter: "codex-cli",
    moduleOverrides: { "news-radar": "newma-runtime" },
    profileTargets: { deep: "codex-cli", batch: "newma-runtime" },
    moduleProfileOverrides: { "quick-only": { quick: "fast-model" } },
    updatedAt: null,
  };
  server.use(
    http.get("/api/capabilities", () => HttpResponse.json({
      adapters: [
        { id: "codex-cli", name: "Codex", kind: "local-cli", available: true,
          capabilities: ["module.explain", "module.analyze"], default: true },
        { id: "newma-runtime", name: "Newma", kind: "agent-gateway", available: true,
          capabilities: ["module.explain", "module.analyze"], default: false },
      ],
      moduleActions: [],
    })),
    http.get("/api/model/providers", () => HttpResponse.json({ providers: [
      { id: "fast-model", name: "快速模型", available: true, default: true, capabilities: [] },
    ] })),
    http.get("/api/agent/preferences", () => HttpResponse.json(saved)),
    http.put("/api/agent/preferences", async ({ request }) => {
      saved = { ...saved, ...await request.json() as Partial<AgentPreferences> };
      return HttpResponse.json(saved);
    }),
  );
  return () => saved;
}

it("preserves edits and hidden overrides through search, collapse and save", async () => {
  const saved = serveSettings();
  const user = userEvent.setup();
  render(<AgentSettings modules={modules} userId="settings-test" runtimePreference="local" />);

  const disclosure = await screen.findByRole("button", { name: /Mod Agent 覆盖/ });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  expect(disclosure).toHaveTextContent("已单独配置 2 / 3 个 Mod");
  expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  await user.click(disclosure);
  await user.click(screen.getByRole("checkbox", { name: "仅看已单独配置" }));
  expect(screen.queryByRole("combobox", { name: "行情深度研究执行器" })).not.toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "快速观察快速问答执行器" })).toHaveValue("fast-model");

  const search = screen.getByRole("searchbox", { name: "搜索 Mod 名称或 ID" });
  await user.type(search, "NEWS-RADAR");
  const newsRoute = screen.getByRole("combobox", { name: "新闻与舆情深度研究执行器" });
  expect(newsRoute).toHaveValue("newma-runtime");
  expect(within(newsRoute).getByRole("option", { name: /Newma.*已保存/ })).toBeDisabled();
  await user.selectOptions(newsRoute, "codex-cli");
  await user.click(disclosure);
  await user.click(disclosure);
  expect(screen.getByRole("combobox", { name: "新闻与舆情深度研究执行器" })).toHaveValue("codex-cli");
  await user.click(screen.getByRole("button", { name: "保存设置" }));
  await screen.findByText(/运行方式与 Agent 路由已保存/);
  expect(saved().moduleOverrides).toEqual({});
  expect(saved().moduleProfileOverrides).toEqual({
    "news-radar": { deep: "codex-cli" },
    "quick-only": { quick: "fast-model" },
  });
});

it("keeps saved routes visible across runtime switches and restores global inheritance explicitly", async () => {
  const saved = serveSettings();
  const user = userEvent.setup();
  render(<AgentSettings modules={modules} userId="settings-test" runtimePreference="local" />);
  await screen.findByRole("button", { name: /Mod Agent 覆盖/ });
  const batchRoute = screen.getByRole("combobox", { name: "批量处理执行器" });
  expect(batchRoute).toHaveValue("newma-runtime");
  expect(within(batchRoute).getByRole("option", { name: /Newma.*已保存/ })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: /Newma Runtime/ }));
  expect(batchRoute).toHaveValue("newma-runtime");
  expect(within(batchRoute).getByRole("option", { name: "Newma" })).not.toBeDisabled();

  await user.click(screen.getByRole("button", { name: /Mod Agent 覆盖/ }));
  await user.click(screen.getByRole("checkbox", { name: "仅看已单独配置" }));
  await user.selectOptions(screen.getByRole("combobox", { name: "新闻与舆情深度研究执行器" }), "");
  await user.selectOptions(screen.getByRole("combobox", { name: "快速观察快速问答执行器" }), "");
  expect(screen.getByText("所有 Mod 当前都继承全局配置。")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "查看全部" }));
  expect(screen.getByRole("combobox", { name: "行情深度研究执行器" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "保存设置" }));
  await screen.findByText(/运行方式与 Agent 路由已保存/);
  expect(saved().moduleOverrides).toEqual({});
  expect(saved().moduleProfileOverrides).toEqual({});
});
