export type GatewayFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export interface GatewayClientConfig {
  baseUrl: string;
  fetch?: GatewayFetch;
  accessToken?: string;
  instanceId?: string;
}

export class GatewayError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "GatewayError";
    this.status = status;
    this.detail = detail;
  }
}

export function normalizeGatewayBaseUrl(baseUrl: string): string {
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    throw new Error("Gateway baseUrl must be an HTTP(S) origin");
  }
  if (
    (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    (parsed.pathname !== "/" && parsed.pathname !== "")
  ) {
    throw new Error("Gateway baseUrl must be an HTTP(S) origin");
  }
  return parsed.origin;
}

async function responseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  try {
    return await response.json();
  } catch {
    if (response.ok) {
      throw new GatewayError(
        response.status,
        "Gateway returned an invalid response",
      );
    }
    return undefined;
  }
}

export async function requestGatewayJson<T>(
  fetcher: GatewayFetch,
  url: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetcher(url, {
    ...init,
    credentials: "omit",
    redirect: "error",
    headers,
  });
  const body = await responseBody(response);
  if (!response.ok) {
    const detail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : typeof body === "object" &&
            body !== null &&
            "error" in body &&
            typeof body.error === "object" &&
            body.error !== null &&
            "message" in body.error &&
            typeof body.error.message === "string"
          ? body.error.message
          : "Gateway request failed";
    throw new GatewayError(response.status, detail);
  }
  return body as T;
}
