export interface ModCacheStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface ModSnapshot<T> {
  schemaVersion: number;
  updatedAt: string;
  value: T;
}

export interface ModSnapshotCacheConfig {
  modId: string;
  userId?: string;
  workspaceId: string;
  resourceKey: string;
  schemaVersion?: number;
  maxBytes?: number;
  storage?: ModCacheStorage;
}

export interface ModSnapshotCache<T> {
  readonly key: string;
  read(): ModSnapshot<T> | undefined;
  write(value: T, updatedAt?: string): ModSnapshot<T> | undefined;
  clear(): void;
}

export interface RefreshWithModSnapshotOptions<T> {
  cache: ModSnapshotCache<T>;
  load(): Promise<T>;
  current?: T;
}

export interface ModSnapshotRefreshResult<T> {
  value?: T;
  updatedAt?: string;
  source: "network" | "current" | "cache" | "empty";
  error?: unknown;
}

const CACHE_PREFIX = "newma-desk.mod-cache.v1";
const DEFAULT_MAX_BYTES = 512 * 1024;

function requiredPart(value: string, label: string): string {
  const clean = value.trim();
  if (!clean) throw new Error(`${label} cannot be empty`);
  return encodeURIComponent(clean);
}

function byteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function defaultStorage(): ModCacheStorage | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

/**
 * Stores only the last successful display snapshot for one Mod resource.
 * The cache is isolated by user, workspace, Mod and resource key.
 */
export function createModSnapshotCache<T>(
  config: ModSnapshotCacheConfig,
): ModSnapshotCache<T> {
  const schemaVersion = config.schemaVersion ?? 1;
  const maxBytes = config.maxBytes ?? DEFAULT_MAX_BYTES;
  if (!Number.isInteger(schemaVersion) || schemaVersion < 1) {
    throw new Error("schemaVersion must be a positive integer");
  }
  if (!Number.isFinite(maxBytes) || maxBytes < 1) {
    throw new Error("maxBytes must be greater than zero");
  }
  const storage = config.storage ?? defaultStorage();
  const key = [
    CACHE_PREFIX,
    requiredPart(config.userId ?? "local-user", "User ID"),
    requiredPart(config.workspaceId, "Workspace ID"),
    requiredPart(config.modId, "Mod ID"),
    requiredPart(config.resourceKey, "Resource key"),
  ].join(".");

  const clear = () => {
    try {
      storage?.removeItem(key);
    } catch {
      // Cache failure must never block the Mod.
    }
  };

  return {
    key,
    read() {
      try {
        const raw = storage?.getItem(key);
        if (!raw) return undefined;
        const parsed = JSON.parse(raw) as Partial<ModSnapshot<T>>;
        if (
          parsed.schemaVersion !== schemaVersion ||
          typeof parsed.updatedAt !== "string" ||
          !("value" in parsed)
        ) {
          clear();
          return undefined;
        }
        return parsed as ModSnapshot<T>;
      } catch {
        clear();
        return undefined;
      }
    },
    write(value, updatedAt = new Date().toISOString()) {
      const snapshot: ModSnapshot<T> = { schemaVersion, updatedAt, value };
      try {
        const serialized = JSON.stringify(snapshot);
        if (byteLength(serialized) > maxBytes) return undefined;
        storage?.setItem(key, serialized);
        return snapshot;
      } catch {
        return undefined;
      }
    },
    clear,
  };
}

/**
 * Refreshes data without discarding the current or cached last-good value.
 */
export async function refreshWithModSnapshot<T>(
  options: RefreshWithModSnapshotOptions<T>,
): Promise<ModSnapshotRefreshResult<T>> {
  const cached = options.cache.read();
  try {
    const value = await options.load();
    const snapshot = options.cache.write(value);
    return {
      value,
      updatedAt: snapshot?.updatedAt ?? new Date().toISOString(),
      source: "network",
    };
  } catch (error) {
    if (options.current !== undefined) {
      return { value: options.current, source: "current", error };
    }
    if (cached) {
      return {
        value: cached.value,
        updatedAt: cached.updatedAt,
        source: "cache",
        error,
      };
    }
    return { source: "empty", error };
  }
}
