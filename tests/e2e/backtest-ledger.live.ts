import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

const shellOrigin = process.env.NEWMA_DESK_E2E_ORIGIN ?? "http://127.0.0.1:5888";

test("paper backtest materializes Strategy Ledger and shares it with Desk Agent", async ({
  page,
}) => {
  test.slow();
  await page.goto(`${shellOrigin}/?mod=backtest-lab`, { waitUntil: "domcontentloaded" });
  const frame = page.frameLocator('iframe[title="回测实验室"]');
  await expect(frame.getByText(/策略实验账本|Strategy Experiment Ledger/, { exact: true })).toBeVisible();
  const tradingFrame = page.frames().find((candidate) => candidate.url().includes("/mod-runtime/trading/reports"));
  expect(tradingFrame).toBeDefined();
  const quickForm = frame.getByRole("heading", { name: /快速回测|Quick Backtest/, exact: true })
    .locator("xpath=ancestor::section[1]");
  await quickForm.locator("select").first().selectOption("sma_crossover");
  await quickForm.getByPlaceholder(/AAPL/).fill("AAPL");
  const dateInputs = quickForm.locator('input[type="date"]');
  await dateInputs.nth(0).fill("2025-01-02");
  await dateInputs.nth(1).fill("2025-03-31");
  const numberInputs = quickForm.locator('input[type="number"]');
  await numberInputs.nth(0).fill("100000");
  await numberInputs.nth(1).fill("0.001");
  await numberInputs.nth(2).fill("10");
  await numberInputs.nth(3).fill("30");
  const createResponsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().endsWith("/api/trading/runs/quick"),
  );
  await quickForm.getByRole("button", { name: /开始回测|Start backtest/ }).click();
  const create = await createResponsePromise;
  expect(create.status()).toBe(202);
  const created = await create.json() as { run_id: string };
  const createHeaders = create.request().headers();
  const sessionHeaders = Object.fromEntries(
    Object.entries(createHeaders).filter(([name]) => name.startsWith("x-newma-desk-")),
  );

  await expect.poll(async () => {
    return tradingFrame!.evaluate(async ({ runId, headers }) => {
      const response = await fetch(`/api/trading/runs/${encodeURIComponent(runId)}/status`, { headers });
      if (!response.ok) throw new Error(`status request failed: ${response.status}`);
      return (await response.json() as { status: string }).status;
    }, { runId: created.run_id, headers: sessionHeaders });
  }, {
    timeout: 120_000,
    intervals: [500, 1_000, 2_000, 5_000],
  }).toBe("success");

  const result = await tradingFrame!.evaluate(async ({ runId, headers }) => {
    const response = await fetch(
      `/api/trading/runs/${encodeURIComponent(runId)}?chart_payload=summary`,
      { headers },
    );
    if (!response.ok) throw new Error(`run detail request failed: ${response.status}`);
    return response.json();
  }, { runId: created.run_id, headers: sessionHeaders }) as {
    run_directory: string;
    strategy_ledger: {
      schema_version: string;
      ledger_id: string;
      mode: string;
      execution_mode: string;
      strategy: { id: string; version: string };
      metrics: { total_return: number; max_drawdown: number; trade_count: number };
    };
  };
  expect(result.strategy_ledger).toMatchObject({
    schema_version: "newma-desk.strategy-ledger.v1",
    mode: "paper-only",
    execution_mode: "paper",
    strategy: { id: "vibe-trading.sma-crossover" },
  });
  expect(Number.isFinite(result.strategy_ledger.metrics.total_return)).toBe(true);
  expect(Number.isFinite(result.strategy_ledger.metrics.max_drawdown)).toBe(true);
  expect(result.strategy_ledger.metrics.trade_count).toBeGreaterThanOrEqual(0);

  const persisted = JSON.parse(
    readFileSync(`${result.run_directory}/strategy_ledger.json`, "utf-8"),
  ) as { ledger_id: string; status: string };
  expect(persisted).toMatchObject({
    ledger_id: result.strategy_ledger.ledger_id,
    status: "completed",
  });

  let agentPayload: Record<string, unknown> | undefined;
  await page.route("**/api/agent/tasks**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "POST" && url.pathname === "/api/agent/tasks") {
      agentPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ id: "strategy-ledger-e2e", status: "queued" }),
      });
      return;
    }
    if (route.request().method() === "GET" && url.pathname === "/api/agent/tasks/strategy-ledger-e2e") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "strategy-ledger-e2e",
          status: "completed",
          result: { answer: "STRATEGY_LEDGER_CONTEXT_OK" },
        }),
      });
      return;
    }
    await route.continue();
  });

  await frame.getByRole("button", { name: /刷新|Refresh/ }).click();
  await frame.getByPlaceholder(/搜索运行 ID|Search run id/i).fill(created.run_id);
  const report = frame.getByRole("article").filter({ hasText: created.run_id });
  await expect(report.getByText(created.run_id, { exact: true })).toBeVisible();
  await expect(report.getByText("SMA Crossover", { exact: true })).toBeVisible();
  await expect(report.getByText(/仅纸面回测|Paper only/, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "问当前 Mod" }).click();
  const drawer = page.getByRole("complementary", { name: "回测实验室 Agent" });
  await drawer.getByPlaceholder("就当前页面提问…").fill("比较当前筛选到的策略实验");
  await drawer.getByRole("button", { name: "发送" }).click();
  await expect(drawer).toContainText("STRATEGY_LEDGER_CONTEXT_OK");
  expect(agentPayload).toMatchObject({
    moduleId: "backtest-lab",
    context: {
      vibedesk: {
        source: "mod-bridge",
        page: {
          data: {
            source: "vibe-trading-rendered-page",
            summary: {
              strategyLedger: {
                schemaVersion: "newma-desk.strategy-ledger.v1",
                executionPolicy: "paper-only",
                experimentCount: 1,
                experiments: [
                  {
                    runId: created.run_id,
                    strategy: { id: "vibe-trading.sma-crossover" },
                  },
                ],
              },
            },
          },
        },
      },
    },
  });
});
