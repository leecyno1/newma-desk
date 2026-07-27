import {
  normalizeGatewayBaseUrl,
  requestGatewayJson,
  type GatewayClientConfig,
} from "./agent";

export interface DataServiceClient {
  invoke<T = unknown>(
    serviceId: string,
    capabilityId: string,
    input: Record<string, unknown>,
  ): Promise<T>;
}

export interface UnifiedDataClient {
  query<T = unknown>(
    capabilityId: string,
    input?: Record<string, unknown>,
  ): Promise<T>;
}

export interface UnifiedDataClientConfig {
  invokeAction<T = unknown>(
    actionId: string,
    input?: Record<string, unknown>,
  ): Promise<T>;
  actionByCapability?: Record<string, string>;
}

function pathSegment(value: string): string {
  if (!value) throw new Error("Data service ID cannot be empty");
  return encodeURIComponent(value);
}

export function createDataServiceClient(
  config: GatewayClientConfig,
): DataServiceClient {
  const baseUrl = normalizeGatewayBaseUrl(config.baseUrl);
  const fetcher = config.fetch ?? globalThis.fetch.bind(globalThis);

  return {
    invoke<T = unknown>(
      serviceId: string,
      capabilityId: string,
      input: Record<string, unknown>,
    ) {
      return requestGatewayJson<T>(
        fetcher,
        `${baseUrl}/api/data-services/${pathSegment(serviceId)}/invoke/${pathSegment(capabilityId)}`,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
  };
}

/**
 * Creates the provider-agnostic data client used by embedded Mods. The Mod
 * declares a Data Action, while Newma-Dock selects the concrete provider and
 * keeps service URLs and credentials in the Desk backend.
 */
export function createUnifiedDataClient(
  config: UnifiedDataClientConfig,
): UnifiedDataClient {
  return {
    query<T = unknown>(
      capabilityId: string,
      input: Record<string, unknown> = {},
    ) {
      if (!capabilityId) {
        return Promise.reject(new Error("Data capability ID cannot be empty"));
      }
      const actionId = config.actionByCapability?.[capabilityId] ?? capabilityId;
      return config.invokeAction<T>(actionId, input);
    },
  };
}
