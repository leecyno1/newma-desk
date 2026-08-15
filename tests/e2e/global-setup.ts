import { readFile, rm } from "node:fs/promises";
import { resolve } from "node:path";

import {
  request,
  type APIRequestContext,
  type APIResponse,
} from "@playwright/test";

import {
  apiHealthPath,
  apiOrigin,
  databaseFiles,
  demoModulePath,
} from "./runtime-config";

const demoManifest = {
  schemaVersion: "1.0",
  id: "demo",
  name: "Demo Mod",
  version: "0.1.0",
  category: "demo",
  entry: { type: "static", url: demoModulePath },
  permissions: [],
  dataServices: [],
  agentCapabilities: [],
  events: { emits: [], accepts: [] },
};

async function publishManifest(
  api: APIRequestContext,
  manifest: Record<string, unknown>,
  operation: string,
): Promise<void> {
  const draftResponse = await api.post("/api/mods/drafts", {
    data: manifest,
  });
  await expectStatus(draftResponse, 201, `Creating ${operation} draft`);

  const draft = (await draftResponse.json()) as {
    moduleId?: unknown;
    revision?: unknown;
  };
  if (
    draft.moduleId !== manifest.id ||
    !Number.isInteger(draft.revision)
  ) {
    throw new Error(`Creating ${operation} draft returned an invalid revision`);
  }

  const publishResponse = await api.post(
    `/api/mods/${draft.moduleId}/revisions/${draft.revision}/publish`,
  );
  await expectStatus(publishResponse, 200, `Publishing ${operation} draft`);
}

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
      const response = await api.get(apiHealthPath, { timeout: 1_000 });
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
  for (const databaseFile of databaseFiles) {
    await rm(databaseFile, { force: true });
  }
}

export default async function globalSetup(): Promise<void> {
  const api = await request.newContext({ baseURL: apiOrigin });

  try {
    await waitForApi(api);
    await resetE2eDatabase();

    await publishManifest(api, demoManifest, "the demo module");
    const marketManifest = JSON.parse(
      await readFile(resolve("modules/market-daily/module.json"), "utf8"),
    ) as Record<string, unknown>;
    await publishManifest(
      api,
      marketManifest,
      "the market module",
    );
  } finally {
    await api.dispose();
  }
}
