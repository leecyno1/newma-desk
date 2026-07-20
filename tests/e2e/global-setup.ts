import { rm } from "node:fs/promises";
import { resolve } from "node:path";

import {
  request,
  type APIRequestContext,
  type APIResponse,
} from "@playwright/test";

const apiOrigin = "http://127.0.0.1:8901";
const e2eDatabase = resolve("runtime/e2e-foundation.db");
const defaultDatabase = resolve("runtime/vibe-visualization.db");
const databaseSidecars = ["", "-journal", "-shm", "-wal"];

const demoManifest = {
  schemaVersion: "1.0",
  id: "demo",
  name: "Demo Module",
  version: "0.1.0",
  category: "demo",
  entry: { type: "static", url: "/modules/demo/" },
  permissions: [],
  dataServices: [],
  agentCapabilities: [],
  events: { emits: [], accepts: [] },
};

async function responseSummary(response: APIResponse): Promise<string> {
  const text = (await response.text()).replace(/\s+/g, " ").trim();
  return text ? `: ${text.slice(0, 300)}` : "";
}

async function expectStatus(
  response: APIResponse,
  expected: number,
  operation: string,
): Promise<void> {
  if (response.status() !== expected) {
    throw new Error(
      `${operation} failed with HTTP ${response.status()}${await responseSummary(response)}`,
    );
  }
}

async function waitForApi(api: APIRequestContext): Promise<void> {
  const deadline = Date.now() + 15_000;
  let lastFailure = "API did not respond";

  while (Date.now() < deadline) {
    try {
      const response = await api.get("/api/health", { timeout: 1_000 });
      if (response.ok()) {
        const health = (await response.json()) as { ok?: unknown };
        if (health.ok === true) return;
        lastFailure = "API health response did not report ok=true";
      } else {
        lastFailure = `API health returned HTTP ${response.status()}`;
      }
    } catch (error) {
      lastFailure =
        error instanceof Error ? error.message : "API request failed";
    }

    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }

  throw new Error(`E2E setup could not reach the isolated API: ${lastFailure}`);
}

async function resetE2eDatabase(): Promise<void> {
  if (e2eDatabase === defaultDatabase) {
    throw new Error("Refusing to reset the default application database");
  }

  for (const suffix of databaseSidecars) {
    await rm(`${e2eDatabase}${suffix}`, { force: true });
  }
}

export default async function globalSetup(): Promise<void> {
  const api = await request.newContext({ baseURL: apiOrigin });

  try {
    await waitForApi(api);
    await resetE2eDatabase();

    const draftResponse = await api.post("/api/modules/drafts", {
      data: demoManifest,
    });
    await expectStatus(draftResponse, 201, "Creating the demo module draft");

    const draft = (await draftResponse.json()) as {
      moduleId?: unknown;
      revision?: unknown;
    };
    if (draft.moduleId !== "demo" || !Number.isInteger(draft.revision)) {
      throw new Error(
        "Creating the demo module draft returned an invalid revision",
      );
    }

    const publishResponse = await api.post(
      `/api/modules/demo/revisions/${draft.revision}/publish`,
    );
    await expectStatus(publishResponse, 200, "Publishing the demo module draft");
  } finally {
    await api.dispose();
  }
}
