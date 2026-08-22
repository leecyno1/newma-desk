export interface ModelProviderDescription {
  id: string;
  name?: string;
  available?: boolean;
  capabilities: string[];
  default: boolean;
}

export interface ModelResponse {
  answer: string;
  adapter: string;
  model: string;
}

interface ModelResponseInput {
  moduleId: string;
  capability: string;
  prompt: string;
  context: Record<string, unknown>;
  adapter?: string;
}

async function responseJson<T>(response: Response): Promise<T> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (!response.ok) {
    const detail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : `Model Gateway 返回 ${response.status}`;
    throw new Error(detail);
  }
  return body as T;
}

export async function loadModelProviders(): Promise<ModelProviderDescription[]> {
  const response = await fetch("/api/model/providers", {
    credentials: "omit",
    headers: { Accept: "application/json" },
  });
  const body = await responseJson<{ providers: ModelProviderDescription[] }>(response);
  return body.providers;
}

export async function createModelResponse(
  input: ModelResponseInput,
  identity?: { userId: string },
): Promise<ModelResponse> {
  const headers = new Headers({
    Accept: "application/json",
    "Content-Type": "application/json",
  });
  if (identity?.userId) headers.set("X-User-Id", identity.userId);
  const response = await fetch("/api/model/responses", {
    method: "POST",
    credentials: "omit",
    headers,
    body: JSON.stringify(input),
  });
  return responseJson<ModelResponse>(response);
}
