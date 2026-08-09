import { describe, expect, it } from "vitest";

import { normalizeModCopilotPrompts } from "./modCopilotPrompts";

describe("buildModCopilotPromptGroups", () => {
  it("accepts bounded Desk-owned ask and edit prompt groups", () => {
    const prompts = normalizeModCopilotPrompts({
      ask: [
        {
          id: "understand",
          label: "提炼与核验",
          suggestions: [
            {
              id: "summary",
              intent: "summary",
              label: "总结",
              prompt: "总结当前 Mod",
            },
          ],
        },
      ],
      edit: [
        {
          id: "modify",
          label: "修改与优化",
          suggestions: [
            {
              id: "fix",
              intent: "modification",
              label: "修复",
              prompt: "修复当前 Mod",
            },
          ],
        },
      ],
    });

    expect(prompts.ask[0]?.suggestions[0]?.prompt).toBe("总结当前 Mod");
    expect(prompts.edit[0]?.suggestions[0]?.intent).toBe("modification");
  });

  it("drops malformed or unsupported suggestions", () => {
    const prompts = normalizeModCopilotPrompts({
      ask: [
        {
          id: "unsafe",
          label: "无效",
          suggestions: [
            { id: "x", intent: "unknown", label: "X", prompt: "X" },
          ],
        },
      ],
    });

    expect(prompts).toEqual({ ask: [], edit: [] });
  });
});
