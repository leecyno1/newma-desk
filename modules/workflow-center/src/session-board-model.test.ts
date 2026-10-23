import { describe, expect, it } from "vitest";
import { selectSessions, SESSION_LANES, type SessionCard } from "./session-board-model";
const card = (id: string, fields: Partial<SessionCard> = {}): SessionCard => ({ id, title: id, projectId: "p1", projectName: "投研", model: "sol", status: "idle", attention: "", pinned: false, readOnly: false, updatedAt: null, url: `https://newma.example/?session=${id}`, ...fields });
describe("session board filters", () => {
  it("combines project, text and pinned filters", () => {
    const rows = [card("a", { pinned: true }), card("b", { projectId: "p2", pinned: true }), card("c")];
    expect(selectSessions(rows, " SOL ", "p1", true).map((row) => row.id)).toEqual(["a"]);
    expect(rows).toHaveLength(3);
  });
  it("places pinned first, then recent updates; missing dates remain last", () => {
    expect(selectSessions([card("old"), card("new", { updatedAt: "2026-10-23T09:00:00Z" }), card("pinned", { pinned: true })], "", "", false).map((row) => row.id)).toEqual(["pinned", "new", "old"]);
  });
  it("keeps unknown separate and does not call idle completed", () => {
    expect(SESSION_LANES.map((row) => row.id)).toContain("unknown");
    expect(SESSION_LANES.map((row) => row.id)).not.toContain("completed");
    expect(selectSessions([card("unknown", { status: "unknown" })], "", "", false)[0]?.status).toBe("unknown");
  });
});
