import { createArtifactClient, type ArtifactClient, type ReplayArtifactRecord } from "@newma-desk/mod-sdk";
import { createStorageRequest, StorageAccessError, type StorageClientOptions } from "./storageAccess";

export type ReplayClient = Pick<ArtifactClient, "createReplay" | "listReplays" | "viewUrl"> & {
  readView?: (record: ReplayArtifactRecord) => Promise<string>;
};

export function createReplayStorage(input: StorageClientOptions): ReplayClient {
  if (!input.session) return createArtifactClient({ baseUrl: input.baseUrl, fetch: input.fetch });
  const request = createStorageRequest(input);
  const assertModule = (id: string) => {
    if (id !== "trading-replay" || input.session!.config.modId !== id) throw new StorageAccessError(403, "当前页面不能访问回放归档");
  };
  return {
    createReplay(spec) {
      assertModule(spec.moduleId);
      return request("POST", "/api/artifacts/replays", spec);
    },
    listReplays(moduleId) {
      assertModule(moduleId);
      return request("GET", "/api/artifacts/replays?module_id=trading-replay");
    },
    async readView(record) {
      assertModule(record.moduleId);
      if (!/^[0-9a-f]{32}$/.test(record.id)) throw new Error("归档标识无效");
      return request("GET", `/api/artifacts/replays/${record.id}/view`, undefined, "html");
    },
    // Signed archives are fetched into a sandbox, never opened with credentials in a URL.
    viewUrl: () => "",
  };
}

export interface LayoutRecord { id: string; name: string; savedAt: string; state: Record<string, unknown> }

export function createLayoutSaver(input: StorageClientOptions, modId: string) {
  const request = createStorageRequest({ ...input, validateResponse(payload) {
    const doc = payload as { moduleId?: string; namespace?: string; key?: string; value?: LayoutRecord };
    if (doc.moduleId !== modId || doc.namespace !== "layouts" || doc.key !== doc.value?.id) {
      throw new StorageAccessError(403, "布局响应与当前页面不匹配");
    }
  } });
  return async (record: LayoutRecord) => {
    if (input.session) {
      if (input.session.config.modId !== modId) throw new StorageAccessError(403, "布局页面不匹配");
      const doc = await request<{ value: LayoutRecord }>("PUT", `/api/mods/${encodeURIComponent(modId)}/storage/layouts/${encodeURIComponent(record.id)}`,
        { expectedRevision: 0, value: record });
      return doc.value;
    }
    const key = `vibedesk.${modId}.layouts.v1`;
    let records: unknown[] = [];
    try { const parsed: unknown = JSON.parse(window.localStorage.getItem(key) || "[]"); if (Array.isArray(parsed)) records = parsed; } catch { /* Local legacy data only. */ }
    window.localStorage.setItem(key, JSON.stringify([record, ...records].slice(0, 20)));
    return record;
  };
}
