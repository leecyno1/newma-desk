import { act, render, screen } from "@testing-library/react";
import i18n from "@/i18n";
import { Settings } from "../Settings";

const apiMock = vi.hoisted(() => ({
  getLLMSettings: vi.fn(),
  getDataSourceSettings: vi.fn(),
  getChannelStatus: vi.fn(),
  startChannels: vi.fn(),
  stopChannels: vi.fn(),
  updateLLMSettings: vi.fn(),
  updateDataSourceSettings: vi.fn(),
}));
const qverisLifecycle = vi.hoisted(() => ({
  mounted: vi.fn(),
  unmounted: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
  isAuthRequiredError: vi.fn(() => false),
}));

vi.mock("@/lib/apiAuth", () => ({
  getApiAuthKey: vi.fn(() => ""),
  setApiAuthKey: vi.fn(),
}));

vi.mock("@/components/settings/QVerisSettings", async () => {
  const { useEffect } = await vi.importActual<typeof import("react")>("react");
  return {
    QVerisSettings: () => {
      useEffect(() => {
        qverisLifecycle.mounted();
        return () => qverisLifecycle.unmounted();
      }, []);
      return <section data-testid="qveris-settings">QVeris settings</section>;
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

function llmSettings() {
  return {
    provider: "openrouter",
    model_name: "deepseek/deepseek-v3.2",
    base_url: "https://openrouter.ai/api/v1",
    api_key_env: "OPENROUTER_API_KEY",
    api_key_configured: false,
    api_key_required: true,
    temperature: 0.1,
    timeout_seconds: 120,
    max_retries: 2,
    reasoning_effort: "",
    sse_timeout_seconds: 300,
    env_path: "agent/.env",
    providers: [],
  };
}

function dataSourceSettings() {
  return {
    tushare_token_configured: false,
    baostock_supported: true,
    baostock_installed: true,
    baostock_message: "BaoStock available",
    env_path: "agent/.env",
  };
}

function channelStatus() {
  return {
    running: false,
    inbound_queue: 0,
    outbound_queue: 0,
    session_count: 0,
    channels: {},
  };
}

describe("Settings lifecycle", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    vi.clearAllMocks();
  });

  it("keeps one QVeris settings instance while the page finishes loading", async () => {
    const llm = deferred<ReturnType<typeof llmSettings>>();
    const dataSource = deferred<ReturnType<typeof dataSourceSettings>>();
    const channels = deferred<ReturnType<typeof channelStatus>>();
    apiMock.getLLMSettings.mockReturnValue(llm.promise);
    apiMock.getDataSourceSettings.mockReturnValue(dataSource.promise);
    apiMock.getChannelStatus.mockReturnValue(channels.promise);

    render(<Settings />);

    expect(screen.getAllByTestId("qveris-settings")).toHaveLength(1);
    expect(qverisLifecycle.mounted).toHaveBeenCalledTimes(1);

    await act(async () => {
      llm.resolve(llmSettings());
      dataSource.resolve(dataSourceSettings());
      channels.resolve(channelStatus());
      await Promise.all([llm.promise, dataSource.promise, channels.promise]);
    });

    expect(await screen.findByText("LLM Settings")).toBeInTheDocument();
    expect(screen.getAllByTestId("qveris-settings")).toHaveLength(1);
    expect(qverisLifecycle.mounted).toHaveBeenCalledTimes(1);
    expect(qverisLifecycle.unmounted).not.toHaveBeenCalled();
  });
});
