import { modManifestSchema, type ModManifest } from "@newma-desk/contracts";
import {
  normalizeModCopilotPrompts,
  type ModCopilotPrompts,
} from "../lib/modCopilotPrompts";

export interface StoredMod {
  moduleId: string;
  revision: number;
  status: "draft" | "published" | "disabled";
  manifest: ModManifest;
  createdAt: string;
  copilotPrompts?: ModCopilotPrompts;
}

function parseStoredMod(value: unknown): StoredMod {
  if (typeof value !== "object" || value === null) {
    throw new Error("mod registry returned malformed data");
  }

  const row = value as Record<string, unknown>;
  if (
    typeof row.moduleId !== "string" ||
    !Number.isInteger(row.revision) ||
    (row.status !== "draft" &&
      row.status !== "published" &&
      row.status !== "disabled") ||
    typeof row.createdAt !== "string"
  ) {
    throw new Error("mod registry returned malformed data");
  }

  const manifest = modManifestSchema.safeParse(row.manifest);
  if (!manifest.success) {
    throw new Error("mod registry returned malformed data");
  }

  return {
    moduleId: row.moduleId,
    revision: row.revision as number,
    status: row.status,
    manifest: manifest.data,
    createdAt: row.createdAt,
    copilotPrompts: normalizeModCopilotPrompts(row.copilotPrompts),
  };
}

async function readStoredMod(response: Response): Promise<StoredMod> {
  try {
    return parseStoredMod(await response.json());
  } catch (error) {
    if (
      error instanceof Error &&
      error.message === "mod registry returned malformed data"
    ) {
      throw error;
    }
    throw new Error("mod registry returned malformed data");
  }
}

export async function listMods(): Promise<StoredMod[]> {
  const response = await fetch("/api/mods");
  if (!response.ok) {
    throw new Error(`mod registry returned ${response.status}`);
  }

  let rows: unknown;
  try {
    rows = await response.json();
  } catch {
    throw new Error("mod registry returned malformed data");
  }
  if (!Array.isArray(rows)) {
    throw new Error("mod registry returned malformed data");
  }

  return rows.map(parseStoredMod);
}

export async function getModRevision(
  modId: string,
  revision: string,
  signal?: AbortSignal,
): Promise<StoredMod> {
  const response = await fetch(
    `/api/mods/${encodeURIComponent(modId)}/revisions/${encodeURIComponent(revision)}`,
    { signal },
  );
  if (!response.ok) {
    throw new Error(`mod registry returned ${response.status}`);
  }

  return readStoredMod(response);
}

// Compatibility exports for older integrations and tests that import the
// former Module terminology.
export type StoredModule = StoredMod;
export const listModules = listMods;
export const getModuleRevision = getModRevision;
