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
