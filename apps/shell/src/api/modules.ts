import {
  moduleManifestSchema,
  type ModuleManifest,
} from "@vibe-visualization/contracts";

export interface StoredModule {
  moduleId: string;
  revision: number;
  status: "draft" | "published" | "disabled";
  manifest: ModuleManifest;
  createdAt: string;
}

function parseStoredModule(value: unknown): StoredModule {
  if (typeof value !== "object" || value === null) {
    throw new Error("module registry returned malformed data");
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
    throw new Error("module registry returned malformed data");
  }

  const manifest = moduleManifestSchema.safeParse(row.manifest);
  if (!manifest.success) {
    throw new Error("module registry returned malformed data");
  }

  return {
    moduleId: row.moduleId,
    revision: row.revision as number,
    status: row.status,
    manifest: manifest.data,
    createdAt: row.createdAt,
  };
}

async function readStoredModule(response: Response): Promise<StoredModule> {
  try {
    return parseStoredModule(await response.json());
  } catch (error) {
    if (
      error instanceof Error &&
      error.message === "module registry returned malformed data"
    ) {
      throw error;
    }
    throw new Error("module registry returned malformed data");
  }
}

export async function listModules(): Promise<StoredModule[]> {
  const response = await fetch("/api/modules");
  if (!response.ok) {
    throw new Error(`module registry returned ${response.status}`);
  }

  let rows: unknown;
  try {
    rows = await response.json();
  } catch {
    throw new Error("module registry returned malformed data");
  }
  if (!Array.isArray(rows)) {
    throw new Error("module registry returned malformed data");
  }

  return rows.map(parseStoredModule);
}

export async function getModuleRevision(
  moduleId: string,
  revision: string,
): Promise<StoredModule> {
  const response = await fetch(
    `/api/modules/${encodeURIComponent(moduleId)}/revisions/${encodeURIComponent(revision)}`,
  );
  if (!response.ok) {
    throw new Error(`module registry returned ${response.status}`);
  }

  return readStoredModule(response);
}
