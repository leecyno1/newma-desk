import { describe, expect, it } from "vitest";
import { loadWorkspaceIdentity } from "./workspaceIdentity";

describe("workspace identity", () => {
  it("uses the host project workspace without replacing the standalone workspace", () => {
    window.localStorage.setItem("vibedesk.workspaceId.v1", "standalone-workspace");
    window.history.replaceState(
      null,
      "",
      "/?host=newma&workspace=newma-mod-market-123",
    );

    expect(loadWorkspaceIdentity().workspaceId).toBe("newma-mod-market-123");
    expect(window.localStorage.getItem("vibedesk.workspaceId.v1")).toBe(
      "standalone-workspace",
    );
  });
});
