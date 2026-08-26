import { requestAuthHeaders } from "@/lib/apiAuth";
import { isVibeDeskEmbedded } from "@/lib/vibedesk";

export const API_BASE = (
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ||
  ""
);

export function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const AUTH_REQUIRED_MESSAGE = isVibeDeskEmbedded
  ? "The Newma-Desk Mod session is unavailable or expired. Reopen this Mod from Newma-Desk."
  : "Remote API access requires an API key. Add it in Settings, or run the backend on localhost for local-only use.";

export function isAuthRequiredError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

export async function errorFromResponse(res: Response): Promise<ApiError> {
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    detail = body.detail || body.message || detail;
  } catch {
    // Preserve the status-only fallback when the server did not return JSON.
  }
  if (res.status === 401 || res.status === 403) {
    detail = AUTH_REQUIRED_MESSAGE;
  }
  return new ApiError(detail, res.status);
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const { headers, ...rest } = options ?? {};
  const mergedHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await requestAuthHeaders()),
  };
  if (headers) {
    new Headers(headers).forEach((value, key) => {
      mergedHeaders[key] = value;
    });
  }
  const res = await fetch(apiUrl(path), { ...rest, headers: mergedHeaders });
  if (!res.ok) throw await errorFromResponse(res);

  const text = await res.text();
  if (!text) return {} as T;
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const preview = text.slice(0, 80).replace(/\s+/g, " ");
    throw new ApiError(
      `Expected JSON from ${path}, got ${contentType || "unknown content type"}: ${preview}`,
      res.status,
    );
  }
  return JSON.parse(text) as T;
}
