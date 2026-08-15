export type StoreInstallState = "available" | "installed" | "update-available";

export interface StoreMod {
  id: string;
  suiteId: string;
  name: string;
  description: string;
  version: string;
  publisher: string;
  upstream: string;
  category: string;
  tags: string[];
  defaultInstall: boolean;
  installState: StoreInstallState;
  installedRevision?: number;
  installedVersion?: string;
  installedStatus?: "published" | "disabled";
  sourceUrl: string;
}

export interface ModStoreCatalog {
  id: string;
  name: string;
  repository: string;
  ref: string;
  catalogSource: "bundled" | "github";
  commit?: string;
  syncedAt?: string;
  mods: StoreMod[];
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function parseStoreMod(value: unknown): StoreMod {
  if (typeof value !== "object" || value === null) {
    throw new Error("Mod 商店返回了无效数据");
  }
  const row = value as Record<string, unknown>;
  if (
    !nonEmptyString(row.id) ||
    !nonEmptyString(row.name) ||
    !nonEmptyString(row.description) ||
    !nonEmptyString(row.version) ||
    !nonEmptyString(row.publisher) ||
    !nonEmptyString(row.upstream) ||
    !nonEmptyString(row.category) ||
    !Array.isArray(row.tags) ||
    row.tags.some((tag) => !nonEmptyString(tag)) ||
    typeof row.defaultInstall !== "boolean" ||
    !["available", "installed", "update-available"].includes(
      String(row.installState),
    ) ||
    !nonEmptyString(row.sourceUrl)
  ) {
    throw new Error("Mod 商店返回了无效数据");
  }
  if (
    row.installedRevision !== undefined &&
    !Number.isInteger(row.installedRevision)
  ) {
    throw new Error("Mod 商店返回了无效数据");
  }
  return {
    id: row.id,
    suiteId: nonEmptyString(row.suiteId) ? row.suiteId : row.id,
    name: row.name,
    description: row.description,
    version: row.version,
    publisher: row.publisher,
    upstream: row.upstream,
    category: row.category,
    tags: row.tags as string[],
    defaultInstall: row.defaultInstall,
    installState: row.installState as StoreInstallState,
    ...(row.installedRevision === undefined
      ? {}
      : { installedRevision: row.installedRevision as number }),
    ...(nonEmptyString(row.installedVersion)
      ? { installedVersion: row.installedVersion }
      : {}),
    ...(row.installedStatus === "published" ||
    row.installedStatus === "disabled"
      ? { installedStatus: row.installedStatus }
      : {}),
    sourceUrl: row.sourceUrl,
  };
}

async function readStoreCatalog(response: Response): Promise<ModStoreCatalog> {
  if (!response.ok) throw new Error(`Mod 商店连接失败（${response.status}）`);
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new Error("Mod 商店返回了无效数据");
  }
  if (typeof value !== "object" || value === null) {
    throw new Error("Mod 商店返回了无效数据");
  }
  const row = value as Record<string, unknown>;
  if (
    !nonEmptyString(row.id) ||
    !nonEmptyString(row.name) ||
    !nonEmptyString(row.repository) ||
    !nonEmptyString(row.ref) ||
    !Array.isArray(row.mods)
  ) {
    throw new Error("Mod 商店返回了无效数据");
  }
  return {
    id: row.id,
    name: row.name,
    repository: row.repository,
    ref: row.ref,
    catalogSource: row.catalogSource === "github" ? "github" : "bundled",
    ...(nonEmptyString(row.commit) ? { commit: row.commit } : {}),
    ...(nonEmptyString(row.syncedAt) ? { syncedAt: row.syncedAt } : {}),
    mods: row.mods.map(parseStoreMod),
  };
}

export async function listStoreMods(): Promise<ModStoreCatalog> {
  return readStoreCatalog(await fetch("/api/store/mods"));
}

export async function syncStoreMods(): Promise<ModStoreCatalog> {
  return readStoreCatalog(await fetch("/api/store/sync", { method: "POST" }));
}

export async function installStoreMod(
  modId: string,
): Promise<"installed" | "updated" | "unchanged"> {
  const response = await fetch(
    `/api/store/mods/${encodeURIComponent(modId)}/install`,
    { method: "POST" },
  );
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (!response.ok) {
    const detail =
      body &&
      typeof body === "object" &&
      typeof (body as Record<string, unknown>).detail === "string"
        ? String((body as Record<string, unknown>).detail)
        : `Git 安装失败（${response.status}）`;
    throw new Error(detail);
  }
  const action =
    body && typeof body === "object"
      ? (body as Record<string, unknown>).action
      : undefined;
  if (
    action !== "installed" &&
    action !== "updated" &&
    action !== "unchanged"
  ) {
    throw new Error("Mod 商店返回了无效安装结果");
  }
  return action;
}
