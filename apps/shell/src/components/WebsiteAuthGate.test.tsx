import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WebsiteAuthGate } from "./WebsiteAuthGate";

const session = () => ({ mode: "website", userId: "member-one", workspaceId: "newma-member-one-c10375", expiresAt: new Date(Date.now() + 600000).toISOString() });
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function mount() {
  const child = vi.fn((identity) => <div data-testid="business">{identity?.workspaceId ?? "local"}</div>);
  render(<WebsiteAuthGate>{child}</WebsiteAuthGate>);
  return child;
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("WebsiteAuthGate", () => {
  it("waits for server identity and ignores URL and localStorage identities", async () => {
    window.history.replaceState(null, "", "/?workspace=forged");
    window.localStorage.setItem("vibedesk.userId.v1", "forged");
    let resolve!: (value: Response) => void;
    const fetcher = vi.fn(() => new Promise<Response>((done) => { resolve = done; }));
    vi.stubGlobal("fetch", fetcher);
    const child = mount();
    expect(child).not.toHaveBeenCalled();
    await act(async () => resolve(response(session())));
    expect(screen.getByTestId("business")).toHaveTextContent("newma-member-one-c10375");
    expect(fetcher).toHaveBeenCalledWith("/api/auth/session", expect.objectContaining({ credentials: "same-origin", cache: "no-store" }));
    expect(window.localStorage.getItem("vibedesk.userId.v1")).toBe("forged");
  });

  it("only uses local mode when the API explicitly selects it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ mode: "local" })));
    mount();
    expect(await screen.findByTestId("business")).toHaveTextContent("local");
  });

  it.each([401, 403])("offers Newma login for %s without loading business components", async (status) => {
    window.history.replaceState(null, "", "/?mod=industry-map");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, status)));
    const child = mount();
    const link = await screen.findByRole("link", { name: "前往 Newma 登录" });
    expect(link.getAttribute("href")).toBe("/api/auth/website/start?returnTo=%2F%3Fmod%3Dindustry-map");
    expect(child).not.toHaveBeenCalled();
  });

  it.each([{}, { ...session(), workspaceId: "other-workspace" }, { ...session(), expiresAt: "invalid" }, { ...session(), expiresAt: "2000-01-01T00:00:00Z" }])("fails closed for malformed or expired sessions", async (value) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(value)));
    const child = mount();
    await screen.findByText("暂时无法确认登录状态");
    expect(child).not.toHaveBeenCalled();
  });

  it.each([404, 500])("never falls back to local identity for HTTP %s", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, status)));
    const child = mount();
    await screen.findByText("暂时无法确认登录状态");
    expect(child).not.toHaveBeenCalled();
  });

  it("can retry after a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(response(session())));
    mount();
    await screen.findByText("暂时无法确认登录状态");
    fireEvent.click(screen.getByRole("button", { name: "重新检查" }));
    await screen.findByTestId("business");
  });

  it("unmounts the old workspace when a focus check detects revocation", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response(session())).mockResolvedValue(response({}, 401)));
    mount();
    await screen.findByTestId("business");
    fireEvent(window, new Event("focus"));
    await screen.findByText("请连接 Newma");
    expect(screen.queryByTestId("business")).toBeNull();
  });

  it("stops the business UI during logout and clears the server session", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response(session())).mockResolvedValue(response({ ok: true }));
    vi.stubGlobal("fetch", fetcher);
    mount();
    await screen.findByTestId("business");
    fireEvent.click(screen.getByRole("button", { name: "退出 Desk" }));
    expect(screen.queryByTestId("business")).toBeNull();
    await screen.findByText("请连接 Newma");
    expect(fetcher).toHaveBeenLastCalledWith("/api/auth/logout", expect.objectContaining({ method: "POST", credentials: "same-origin" }));
  });

  it("removes the workspace at the token expiry without waiting for focus", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ ...session(), expiresAt: new Date(Date.now() + 1000).toISOString() })));
    mount();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByTestId("business")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(1001); });
    expect(screen.queryByTestId("business")).toBeNull();
    expect(screen.getByText("请连接 Newma")).toBeInTheDocument();
  });

  it("does not let an in-flight identity check restore the workspace after logout", async () => {
    let resolve!: (value: Response) => void;
    const fetcher = vi.fn().mockResolvedValueOnce(response(session()))
      .mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }))
      .mockResolvedValueOnce(response({ ok: true }));
    vi.stubGlobal("fetch", fetcher);
    mount();
    await screen.findByTestId("business");
    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "退出 Desk" }));
    await screen.findByText("请连接 Newma");
    await act(async () => resolve(response(session())));
    expect(screen.queryByTestId("business")).toBeNull();
  });
});
