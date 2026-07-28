import type { PlaywrightTestConfig } from "@playwright/test";

type BrowserProject = NonNullable<PlaywrightTestConfig["projects"]>[number];

export function chromiumProject(name = "chromium"): BrowserProject {
  const configuredChannel = (
    process.env.NEWMA_DESK_PLAYWRIGHT_CHANNEL ||
    process.env.NEWMA_DOCK_PLAYWRIGHT_CHANNEL ||
    process.env.VIBEDESK_PLAYWRIGHT_CHANNEL
  )?.trim();
  const channel = configuredChannel || (process.env.CI ? undefined : "chrome");
  return {
    name,
    use: {
      browserName: "chromium",
      ...(channel ? { channel } : {}),
    },
  };
}
