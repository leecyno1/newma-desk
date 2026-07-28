import { expect, test } from "@playwright/test";

const shellOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN;
const apiOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_API_ORIGIN;

const oldRuntimePort = /:(?:5899|5901|8900|8899)(?:\/|$)/;

const embeddedMods = [
  {
    id: "daily-review",
    name: "每日复盘",
    route: "/mod-runtime/research/daily-review",
    content: /每日复盘/,
  },
  {
    id: "industry-map",
    name: "产业链研究",
    route: "/mod-runtime/research/sectors",
    content: /板块中心/,
  },
  {
    id: "quant-overview",
    name: "量化总览",
    route: "/mod-runtime/trading/",
    content: /AI 驱动的量化策略研究|AI-Powered Quant Strategy Research/i,
  },
  {
    id: "alpha-lab",
    name: "因子实验室",
    route: "/mod-runtime/trading/alpha-zoo",
    content: /Alpha/,
  },
  {
    id: "backtest-lab",
    name: "回测实验室",
    route: "/mod-runtime/trading/reports",
    content: /回测报告库|Backtest Reports/i,
  },
] as const;

test.describe("Newma-Desk integrated Research and Trading runtimes", () => {
  test.skip(
    !shellOrigin || !apiOrigin,
    "Run with playwright.domain-suites.config.ts against the unified Newma-Desk stack",
  );

  test("serves both domain APIs from the Newma-Desk API process", async ({
    request,
  }) => {
    const suites = await request.get(`${apiOrigin}/api/domain-suites`);
    expect(suites.status()).toBe(200);
    await expect(suites.json()).resolves.toEqual({
      ok: true,
      suites: { research: true, trading: true },
    });

    const research = await request.get(`${apiOrigin}/api/research/health`);
    expect(research.status()).toBe(200);
    await expect(research.json()).resolves.toMatchObject({
      ok: true,
      service: "vibe-research-api",
    });

    const trading = await request.get(`${apiOrigin}/api/trading/health`);
    expect(trading.status()).toBe(200);
    await expect(trading.json()).resolves.toMatchObject({
      status: "healthy",
      service: "Vibe-Trading API",
    });

    const globalStock = await request.get(
      `${apiOrigin}/api/research/global/stock?symbol=AAPL`,
      { timeout: 30_000 },
    );
    expect(globalStock.status()).toBe(200);
    await expect(globalStock.json()).resolves.toMatchObject({
      data: {
        code: "AAPL",
        market: "US",
      },
    });
  });

  test("embeds first-party Mods without reaching any retired service port", async ({
    page,
  }) => {
    const retiredRequests: string[] = [];
    page.on("request", (request) => {
      if (oldRuntimePort.test(request.url())) retiredRequests.push(request.url());
    });

    await page.route("https://fonts.googleapis.com/**", (route) =>
      route.fulfill({ status: 200, contentType: "text/css", body: "" }),
    );
    await page.route("https://fonts.gstatic.com/**", (route) =>
      route.fulfill({ status: 204, body: "" }),
    );

    for (const mod of embeddedMods) {
      await page.goto(`${shellOrigin}/?mod=${mod.id}`, {
        waitUntil: "domcontentloaded",
      });

      const frameElement = page.locator(`iframe[title="${mod.name}"]`);
      await expect(frameElement).toHaveAttribute(
        "src",
        `${apiOrigin}${mod.route}`,
      );

      const frame = page.frameLocator(`iframe[title="${mod.name}"]`);
      await expect(frame.locator("body")).toContainText(mod.content);

      if (mod.id === "industry-map") {
        await page.screenshot({
          path: "/tmp/vibedesk-industry-map-integrated.png",
          fullPage: true,
        });
      }
    }

    expect(retiredRequests).toEqual([]);
  });

  test("shares watchlist groups, securities, events, and Agent context across the workspace", async ({
    page,
    request,
  }) => {
    test.slow();
    const userId = "e2e-watchlist-user";
    const workspaceId = "e2e-watchlist-workspace";
    const groupName = `E2E 半导体组合 ${Date.now()}`;
    let agentPayload: Record<string, unknown> | undefined;

    const quoteNames: Record<string, string> = {
      "600519": "贵州茅台",
      "688981": "中芯国际",
    };
    await page.route("**/api/research/market-terminal/quotes**", async (route) => {
      const symbols = new URL(route.request().url()).searchParams
        .get("symbols")
        ?.split(",")
        .filter(Boolean) ?? [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            items: symbols.map((identity) => {
              const [market, symbol] = identity.split(":");
              return {
                symbol,
                name: quoteNames[symbol] ?? symbol,
                market,
                exchange: market === "CN" ? "SH" : undefined,
                currency: market === "CN" ? "CNY" : "USD",
                price: 100,
                change: 0,
                changePct: 0,
                source: "e2e-fixture",
                asOf: "2026-07-27T08:00:00Z",
              };
            }),
            asOf: "2026-07-27T08:00:00Z",
          },
        }),
      });
    });

    await page.addInitScript(({ user, workspace }) => {
      localStorage.setItem("vibedesk.userId.v1", user);
      localStorage.setItem("vibedesk.workspaceId.v1", workspace);
    }, { user: userId, workspace: workspaceId });
    await page.route("**/api/agent/tasks**", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (
        route.request().method() === "POST" &&
        requestUrl.pathname === "/api/agent/tasks"
      ) {
        agentPayload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({ id: "watchlist-e2e-task", status: "queued" }),
        });
        return;
      }
      if (
        route.request().method() === "GET" &&
        requestUrl.pathname === "/api/agent/tasks/watchlist-e2e-task"
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "watchlist-e2e-task",
            status: "completed",
            result: { answer: "WATCHLIST_CONTEXT_OK" },
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto(`${shellOrigin}/?mod=watchlist`, {
      waitUntil: "domcontentloaded",
    });
    const frame = page.frameLocator('iframe[title="自选股"]');
    await expect(frame.getByRole("heading", { name: "自选股" })).toBeVisible();
    await expect(frame.getByText("Desk 已同步")).toBeVisible();

    await frame.getByRole("button", { name: "新建分组" }).click();
    await frame.getByRole("textbox", { name: "分组名称" }).fill(groupName);
    await frame.getByRole("button", { name: "保存", exact: true }).click();
    await expect(frame.getByRole("button", { name: new RegExp(groupName) })).toBeVisible();
    await frame.getByPlaceholder(/600519/).fill("600519 688981");
    await frame.getByRole("button", { name: "添加", exact: true }).click();
    await expect(frame.getByRole("button", { name: "贵州茅台" })).toBeVisible();
    await expect(frame.getByRole("button", { name: "中芯国际" })).toBeVisible();
    await expect(frame.getByText("Desk 已同步")).toBeVisible();

    const remoteResponse = await request.get(`${apiOrigin}/api/watchlists`, {
      headers: {
        "X-User-Id": userId,
        "X-Workspace-Id": workspaceId,
      },
    });
    expect(remoteResponse.status()).toBe(200);
    const remote = await remoteResponse.json() as {
      groups: Array<{
        name: string;
        symbols: Array<{ market: string; symbol: string }>;
      }>;
    };
    expect(remote.groups).toEqual(expect.arrayContaining([
      expect.objectContaining({
        name: groupName,
        symbols: expect.arrayContaining([
          expect.objectContaining({ market: "CN", symbol: "600519" }),
          expect.objectContaining({ market: "CN", symbol: "688981" }),
        ]),
      }),
    ]));

    await page.reload({ waitUntil: "domcontentloaded" });
    const restoredGroup = frame.getByRole("button", { name: new RegExp(groupName) });
    await expect(restoredGroup).toBeVisible();
    await restoredGroup.click();
    await frame.getByRole("button", { name: "贵州茅台" }).click();
    await expect(page.getByLabel("Mod 事件日志")).toContainText(
      "security.selected · 600519",
    );

    await page.getByRole("button", { name: "问当前 Mod" }).click();
    const drawer = page.getByRole("complementary", { name: "自选股 Agent" });
    await drawer.getByPlaceholder("就当前页面提问…").fill("概括当前自选组合");
    await drawer.getByRole("button", { name: "发送" }).click();
    await expect(drawer).toContainText("WATCHLIST_CONTEXT_OK");
    expect(agentPayload).toMatchObject({
      moduleId: "watchlist",
      context: {
        vibedesk: {
          source: "mod-bridge",
          page: {
            selection: {
              symbol: "600519",
              groupName,
            },
            data: {
              source: "vibedesk-watchlist-service",
              summary: {
                activeGroupSecurityCount: 2,
              },
            },
          },
        },
      },
    });

    await page.screenshot({
      path: "/tmp/vibedesk-watchlist-shared.png",
      fullPage: true,
    });

    await page.getByRole("button", { name: "个股研究", exact: true }).click();
    const researchFrame = page.frameLocator('iframe[title="个股研究"]');
    await expect(researchFrame.getByPlaceholder(/A 股 6 位代码/)).toHaveValue("600519");

    await page.locator("button.directory-button").filter({ hasText: "组合资产中心" }).click();
    const portfolioNavigation = page.getByRole("complementary", {
      name: "组合资产中心 二级导航",
    });
    await portfolioNavigation.getByRole("button", { name: "总览", exact: true }).click();
    const portfolioFrame = page.frameLocator('iframe[title="组合总览"]');
    await expect(portfolioFrame.getByText("联动标的 CN:600519")).toBeVisible();
  });

  test("uses the shared Desk Agent drawer with live Research and Trading page context", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await page.route("https://fonts.googleapis.com/**", (route) =>
      route.fulfill({ status: 200, contentType: "text/css", body: "" }),
    );
    await page.route("https://fonts.gstatic.com/**", (route) =>
      route.fulfill({ status: 204, body: "" }),
    );

    const scenarios = [
      {
        id: "industry-map",
        name: "产业链研究",
        marker: "RESEARCH_SIDE_PANEL_OK",
        contextSource: "vibe-research-rendered-page",
      },
      {
        id: "alpha-lab",
        name: "因子实验室",
        marker: "TRADING_SIDE_PANEL_OK",
        contextSource: "vibe-trading-rendered-page",
      },
    ] as const;

    for (const scenario of scenarios) {
      await page.goto(`${shellOrigin}/?mod=${scenario.id}`, {
        waitUntil: "domcontentloaded",
      });
      await expect(page).toHaveTitle(/Newma-Desk/);
      await expect(page.locator(`iframe[title="${scenario.name}"]`)).toBeVisible();
      await page.getByRole("button", { name: "问当前 Mod" }).click();
      const drawer = page.getByRole("complementary", {
        name: `${scenario.name} Agent`,
      });
      await expect(drawer).toBeVisible();
      await expect(drawer).toContainText("Codex CLI");

      const prompt = `只回复 ${scenario.marker}`;
      await drawer.getByPlaceholder("就当前页面提问…").fill(prompt);
      const createResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname === "/api/agent/tasks",
        { timeout: 20_000 },
      );
      await drawer.getByRole("button", { name: "发送" }).click();
      const createResponse = await createResponsePromise;
      expect(createResponse.status()).toBe(202);
      const body = createResponse.request().postDataJSON();
      expect(body).toMatchObject({
        moduleId: scenario.id,
        capability: "module.explain",
        context: {
          vibedesk: {
            mode: "ask",
            source: "mod-bridge",
            page: { data: { source: scenario.contextSource } },
          },
        },
      });
      await expect(drawer).toContainText(scenario.marker, { timeout: 90_000 });
    }

    expect(consoleErrors).toEqual([]);
  });

  test("passes the cross-market Evidence Ledger from stock research to Desk Agent", async ({
    page,
  }) => {
    let agentPayload: Record<string, unknown> | undefined;
    const globalStock = {
      code: "AAPL",
      name: "Apple Inc.",
      market: "US",
      quote: {
        price: 231.42,
        change_pct: 1.18,
        mcap: 3_480_000_000_000,
        amount: 8_800_000_000,
        open: 229.5,
        high: 233.1,
        low: 228.8,
        prev_close: 228.72,
        pe: 34.2,
        pb: 52.1,
        source: "sina",
        sources: ["sina", "tencent"],
      },
      metrics: null,
      data_sources: ["sina", "tencent"],
    };
    const researchSnapshot = {
      schemaVersion: "newma-desk.equity-research.v1",
      frameworkVersion: "1.0",
      methodology: [
        "cross-market-normalization",
        "evidence-ledger",
        "source-provenance",
        "explicit-data-gaps",
      ],
      identity: {
        symbol: "AAPL",
        name: "Apple Inc.",
        market: "US",
        currency: "USD",
      },
      coverage: { coveredDimensions: 4, totalDimensions: 6, ratio: 2 / 3 },
      sections: [
        { id: "valuation", title: "估值与预期", status: "covered", evidenceIds: ["valuation.price"] },
        { id: "growth", title: "增长质量", status: "covered", evidenceIds: ["growth.revenue_yoy"] },
        { id: "profitability", title: "盈利与资本效率", status: "covered", evidenceIds: ["profitability.roe"] },
        { id: "cash_flow", title: "现金流质量", status: "gap", evidenceIds: [] },
        { id: "balance_sheet", title: "资产负债与韧性", status: "covered", evidenceIds: ["balance_sheet.debt_ratio"] },
        { id: "disclosure", title: "披露与可追溯证据", status: "gap", evidenceIds: [] },
      ],
      evidenceLedger: [
        {
          id: "valuation.price",
          dimension: "valuation",
          label: "现价",
          value: 231.42,
          source: "sina",
          sourceType: "structured",
          field: "price",
          asOf: "2026-07-27T08:00:00Z",
          unit: "USD/share",
          currency: "USD",
          confidence: "high",
        },
        {
          id: "growth.revenue_yoy",
          dimension: "growth",
          label: "营业收入同比",
          value: 6.4,
          source: "SEC companyfacts",
          sourceType: "filing",
          field: "Revenues",
          asOf: "2026-06-30",
          unit: "%",
          currency: null,
          confidence: "high",
        },
      ],
      sources: ["sina", "SEC companyfacts"],
      gaps: ["统一经营现金流证据尚未接入", "最新 10-Q 原文尚未配置 SEC User-Agent"],
      generatedAt: "2026-07-27T08:00:01Z",
    };

    await page.route("**/api/research/global/stock**", async (route) => {
      if (new URL(route.request().url()).searchParams.get("symbol") === "AAPL") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: globalStock }),
        });
        return;
      }
      await route.continue();
    });
    await page.route("**/api/research/equity-research/snapshot**", async (route) => {
      if (new URL(route.request().url()).searchParams.get("symbol") === "AAPL") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: researchSnapshot }),
        });
        return;
      }
      await route.continue();
    });
    await page.route("**/api/agent/tasks**", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (route.request().method() === "POST" && requestUrl.pathname === "/api/agent/tasks") {
        agentPayload = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({ id: "equity-research-e2e-task", status: "queued" }),
        });
        return;
      }
      if (
        route.request().method() === "GET" &&
        requestUrl.pathname === "/api/agent/tasks/equity-research-e2e-task"
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "equity-research-e2e-task",
            status: "completed",
            result: { answer: "EVIDENCE_LEDGER_CONTEXT_OK" },
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto(`${shellOrigin}/?mod=stock-research`, {
      waitUntil: "domcontentloaded",
    });
    const frame = page.frameLocator('iframe[title="个股研究"]');
    const input = frame.getByPlaceholder(/A 股 6 位代码/);
    await input.fill("AAPL");
    await frame.getByRole("button", { name: "查询" }).click();
    await expect(frame.getByRole("heading", { name: "Apple Inc." })).toBeVisible();
    await expect(frame.getByText("跨市场研究框架")).toBeVisible();
    await frame.locator("summary").filter({ hasText: "Evidence Ledger" }).click();
    await expect(frame.getByText("valuation.price", { exact: true })).toBeVisible();
    await expect(frame.getByText("SEC companyfacts", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "问当前 Mod" }).click();
    const drawer = page.getByRole("complementary", { name: "个股研究 Agent" });
    await drawer.getByPlaceholder("就当前页面提问…").fill("引用证据说明当前研究覆盖");
    await drawer.getByRole("button", { name: "发送" }).click();
    await expect(drawer).toContainText("EVIDENCE_LEDGER_CONTEXT_OK");

    expect(agentPayload).toMatchObject({
      moduleId: "stock-research",
      capability: "module.explain",
      context: {
        vibedesk: {
          source: "mod-bridge",
          page: {
            selection: { symbol: "AAPL", name: "Apple Inc.", market: "US" },
            visibleBlocks: expect.arrayContaining([
              expect.objectContaining({ id: "equity-research-framework", type: "evidence-ledger" }),
            ]),
            data: {
              summary: {
                researchFramework: {
                  frameworkVersion: "1.0",
                  evidenceLedger: expect.arrayContaining([
                    expect.objectContaining({
                      id: "growth.revenue_yoy",
                      source: "SEC companyfacts",
                      asOf: "2026-06-30",
                    }),
                  ]),
                  gaps: expect.arrayContaining(["统一经营现金流证据尚未接入"]),
                },
              },
            },
          },
        },
      },
    });
  });
});
