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

test.describe("Newma-Dock integrated Research and Trading runtimes", () => {
  test.skip(
    !shellOrigin || !apiOrigin,
    "Run with playwright.domain-suites.config.ts against the unified Newma-Dock stack",
  );

  test("serves both domain APIs from the Newma-Dock API process", async ({
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
    const userId = "e2e-watchlist-user";
    const workspaceId = "e2e-watchlist-workspace";
    const groupName = `E2E 半导体组合 ${Date.now()}`;
    let agentPayload: Record<string, unknown> | undefined;

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

    await page.getByRole("button", { name: "我的持仓", exact: true }).click();
    const portfolioFrame = page.frameLocator('iframe[title="我的持仓"]');
    await expect(portfolioFrame.getByPlaceholder("6 位代码").first()).toHaveValue("600519");
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
      await expect(page).toHaveTitle(/Newma-Dock/);
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
});
