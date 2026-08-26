import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import i18n from "@/i18n";
import { AUTH_REQUIRED_MESSAGE } from "@/lib/apiClient";
import { Correlation } from "../Correlation";

const requestAuthHeadersMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/apiAuth", () => ({
  requestAuthHeaders: requestAuthHeadersMock,
}));

vi.mock("@/components/charts/CorrelationMatrix", () => ({
  CorrelationMatrix: ({ labels }: { labels: string[] }) => (
    <div data-testid="correlation-matrix">{labels.join(",")}</div>
  ),
}));

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("Correlation request adapter", () => {
  beforeEach(async () => {
    localStorage.clear();
    await i18n.changeLanguage("en");
    requestAuthHeadersMock.mockReset();
    requestAuthHeadersMock.mockResolvedValue({
      "X-Newma-Desk-Mod-Session": "mod-session-token",
      "X-Newma-Desk-Instance-Id": "instance-1",
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses the shared request adapter and forwards Mod session headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        labels: ["000001.SZ", "600519.SH"],
        matrix: [[1, 0.4], [0.4, 1]],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<Correlation />);
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      "/correlation?codes=000001.SZ%2C600519.SH%2C000858.SZ%2C601318.SH&days=90&method=pearson",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-Newma-Desk-Mod-Session": "mod-session-token",
          "X-Newma-Desk-Instance-Id": "instance-1",
        }),
      }),
    );
    expect(await screen.findByTestId("correlation-matrix")).toHaveTextContent(
      "000001.SZ,600519.SH",
    );
  });

  it.each([401, 403])(
    "maps HTTP %s authorization failures through the shared API error contract",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(jsonResponse({ detail: "backend detail" }, status)),
      );

      render(<Correlation />);
      fireEvent.click(screen.getByRole("button", { name: "Compute" }));

      expect(await screen.findByText(AUTH_REQUIRED_MESSAGE)).toBeInTheDocument();
      expect(screen.queryByTestId("correlation-matrix")).not.toBeInTheDocument();
    },
  );

  it("keeps the last successful matrix visible when refresh fails", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        labels: ["000001.SZ", "600519.SH"],
        matrix: [[1, 0.4], [0.4, 1]],
      }))
      .mockResolvedValueOnce(jsonResponse({ detail: "temporary failure" }, 500));
    vi.stubGlobal("fetch", fetchMock);

    render(<Correlation />);
    const compute = screen.getByRole("button", { name: "Compute" });
    fireEvent.click(compute);
    expect(await screen.findByTestId("correlation-matrix")).toHaveTextContent("000001.SZ,600519.SH");

    fireEvent.click(compute);
    expect(await screen.findByText("temporary failure")).toBeInTheDocument();
    expect(screen.getByTestId("correlation-matrix")).toHaveTextContent("000001.SZ,600519.SH");
  });
});
