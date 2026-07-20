import {
  normalizeGatewayBaseUrl,
  requestGatewayJson,
  type GatewayClientConfig,
  type GatewayFetch,
} from "./agent";

export interface ModelResponseCreateInput {
  moduleId?: string;
  capability?: string;
  prompt?: string;
  context?: Record<string, unknown>;
  input?: Record<string, unknown>;
  adapter?: string;
  model?: string;
}

export interface ModelResponse {
  answer: string;
  adapter: string;
  model: string;
}

export interface ModelProviderDescription {
  id: string;
  capabilities: string[];
  default: boolean;
}

export interface ModelGatewayClient {
  createResponse(input: ModelResponseCreateInput): Promise<ModelResponse>;
  listProviders(): Promise<ModelProviderDescription[]>;
}

export function createModelClient(
  config: GatewayClientConfig,
): ModelGatewayClient {
  const baseUrl = normalizeGatewayBaseUrl(config.baseUrl);
  const fetcher: GatewayFetch =
    config.fetch ?? globalThis.fetch.bind(globalThis);

  return {
    createResponse(input) {
      return requestGatewayJson<ModelResponse>(
        fetcher,
        `${baseUrl}/api/model/responses`,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    async listProviders() {
      const response = await requestGatewayJson<{
        providers: ModelProviderDescription[];
      }>(fetcher, `${baseUrl}/api/model/providers`);
      return response.providers;
    },
  };
}
