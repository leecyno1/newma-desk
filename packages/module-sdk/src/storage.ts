import type { DeskInit } from "@newma-desk/contracts";

import {
  normalizeGatewayBaseUrl,
  requestGatewayJson,
  type GatewayFetch,
} from "./agent";


export interface ModStorageDocument<T = unknown> {
  moduleId: string;
  namespace: string;
  key: string;
  schemaVersion: number;
  revision: number;
  value: T;
  sizeBytes: number;
  createdAt: string;
  updatedAt: string;
}

export interface ModStorageDocumentList<T = unknown> {
  items: Array<ModStorageDocument<T>>;
  nextCursor?: string;
}

export interface ModStorageClientConfig {
  baseUrl: string;
  modId: string;
  accessToken: string;
  instanceId: string;
  fetch?: GatewayFetch;
}

export interface ModStorageListOptions {
  cursor?: string;
  limit?: number;
}

export interface ModStorageClient {
  get<T = unknown>(namespace: string, key: string): Promise<ModStorageDocument<T>>;
  list<T = unknown>(
    namespace: string,
    options?: ModStorageListOptions,
  ): Promise<ModStorageDocumentList<T>>;
  put<T = unknown>(
    namespace: string,
    key: string,
    value: T,
    expectedRevision: number,
  ): Promise<ModStorageDocument<T>>;
  delete(namespace: string, key: string, expectedRevision: number): Promise<void>;
}

function pathSegment(value: string, label: string): string {
  if (!value) throw new Error(`${label} cannot be empty`);
  return encodeURIComponent(value);
}

function validateRevision(value: number, allowZero: boolean): number {
  const minimum = allowZero ? 0 : 1;
  if (!Number.isInteger(value) || value < minimum) {
    throw new Error(`expectedRevision must be an integer greater than or equal to ${minimum}`);
  }
  return value;
}

function sessionHeaders(config: ModStorageClientConfig): HeadersInit {
  if (!config.accessToken) throw new Error("Mod storage accessToken cannot be empty");
  if (!config.instanceId) throw new Error("Mod storage instanceId cannot be empty");
  return {
    Authorization: `Bearer ${config.accessToken}`,
    "X-Newma-Desk-Instance-Id": config.instanceId,
  };
}

export function createModStorageClient(
  config: ModStorageClientConfig,
): ModStorageClient {
  const baseUrl = normalizeGatewayBaseUrl(config.baseUrl);
  const fetcher = config.fetch ?? globalThis.fetch.bind(globalThis);
  const modId = pathSegment(config.modId, "Mod ID");
  const headers = sessionHeaders(config);
  const namespaceUrl = (namespace: string) =>
    `${baseUrl}/api/mods/${modId}/storage/${pathSegment(namespace, "Storage namespace")}`;
  const documentUrl = (namespace: string, key: string) =>
    `${namespaceUrl(namespace)}/${pathSegment(key, "Storage key")}`;

  return {
    get<T = unknown>(namespace: string, key: string) {
      return requestGatewayJson<ModStorageDocument<T>>(
        fetcher,
        documentUrl(namespace, key),
        { headers },
      );
    },
    list<T = unknown>(
      namespace: string,
      options: ModStorageListOptions = {},
    ) {
      const url = new URL(namespaceUrl(namespace));
      if (options.cursor !== undefined) {
        url.searchParams.set("cursor", options.cursor);
      }
      if (options.limit !== undefined) {
        if (!Number.isInteger(options.limit) || options.limit < 1 || options.limit > 100) {
          return Promise.reject(new Error("limit must be an integer between 1 and 100"));
        }
        url.searchParams.set("limit", String(options.limit));
      }
      return requestGatewayJson<ModStorageDocumentList<T>>(
        fetcher,
        url.toString(),
        { headers },
      );
    },
    put<T = unknown>(
      namespace: string,
      key: string,
      value: T,
      expectedRevision: number,
    ) {
      return requestGatewayJson<ModStorageDocument<T>>(
        fetcher,
        documentUrl(namespace, key),
        {
          method: "PUT",
          headers,
          body: JSON.stringify({
            expectedRevision: validateRevision(expectedRevision, true),
            value,
          }),
        },
      );
    },
    delete(namespace: string, key: string, expectedRevision: number) {
      const url = new URL(documentUrl(namespace, key));
      url.searchParams.set(
        "expectedRevision",
        String(validateRevision(expectedRevision, false)),
      );
      return requestGatewayJson<void>(fetcher, url.toString(), {
        method: "DELETE",
        headers,
      });
    },
  };
}

export function createModStorageClientFromDesk(
  config: DeskInit,
  fetch?: GatewayFetch,
): ModStorageClient {
  if (!config.gateways.storage) {
    throw new Error("Desk does not expose the Mod Storage gateway");
  }
  if (!config.session) {
    throw new Error("Desk Mod session is required for storage access");
  }
  return createModStorageClient({
    baseUrl: new URL(config.gateways.storage).origin,
    modId: config.modId,
    accessToken: config.session.accessToken,
    instanceId: config.instanceId,
    fetch,
  });
}
