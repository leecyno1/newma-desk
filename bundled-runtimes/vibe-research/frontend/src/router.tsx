import { Suspense, lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

const integrated = import.meta.env.VITE_NEWMA_DESK_INTEGRATED === "1";
const RootLayout = integrated
  ? lazy(() =>
      import("@/components/layout/IntegratedLayout").then((module) => ({
        default: module.IntegratedLayout,
      })),
    )
  : lazy(() =>
      import("@/components/layout/Layout").then((module) => ({
        default: module.Layout,
      })),
    );
const Settings = integrated
  ? lazy(() =>
      import("@/pages/IntegratedSettings").then((module) => ({
        default: module.IntegratedSettings,
      })),
    )
  : lazy(() =>
      import("@/pages/Settings").then((module) => ({
        default: module.Settings,
      })),
    );

function LayoutLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center text-muted-foreground">
      Loading…
    </div>
  );
}

const basename = import.meta.env.BASE_URL.replace(/\/$/, "") || "/";

export const router = createBrowserRouter([
  {
    element: (
      <Suspense fallback={<LayoutLoader />}>
        <RootLayout />
      </Suspense>
    ),
    children: [
      { path: "/", element: <Navigate to="/daily-review" replace /> },
      {
        path: "/daily-review",
        lazy: async () => ({ Component: (await import("@/pages/DailyReview")).DailyReview }),
      },
      {
        path: "/intel",
        lazy: async () => ({ Component: (await import("@/pages/Intel")).Intel }),
      },
      {
        path: "/sectors",
        lazy: async () => ({ Component: (await import("@/pages/Sectors")).Sectors }),
      },
      {
        path: "/sectors/:key",
        lazy: async () => ({ Component: (await import("@/pages/SectorDetail")).SectorDetail }),
      },
      {
        path: "/portfolio",
        lazy: async () => ({ Component: (await import("@/pages/Portfolio")).Portfolio }),
      },
      {
        path: "/stock-data",
        lazy: async () => ({ Component: (await import("@/pages/StockData")).StockData }),
      },
      {
        path: "/etf-research",
        lazy: async () => ({ Component: (await import("@/pages/EtfResearch")).EtfResearch }),
      },
      {
        path: "/catalyst-calendar",
        lazy: async () => ({ Component: (await import("@/pages/CatalystCalendar")).CatalystCalendar }),
      },
      {
        path: "/earnings-workbench",
        lazy: async () => ({ Component: (await import("@/pages/EarningsWorkbench")).EarningsWorkbench }),
      },
      {
        path: "/peer-comparison",
        lazy: async () => ({ Component: (await import("@/pages/PeerComparison")).PeerComparison }),
      },
      {
        path: "/valuation-workbench",
        lazy: async () => ({ Component: (await import("@/pages/ValuationWorkbench")).ValuationWorkbench }),
      },
      {
        path: "/research-memo",
        lazy: async () => ({ Component: (await import("@/pages/ResearchMemo")).ResearchMemo }),
      },
      {
        path: "/thesis-tracker",
        lazy: async () => ({ Component: (await import("@/pages/ThesisTracker")).ThesisTracker }),
      },
      {
        path: "/macro-monitor",
        lazy: async () => ({ Component: (await import("@/pages/MacroMonitor")).MacroMonitor }),
      },
      {
        path: "/watchlist",
        lazy: async () => ({ Component: (await import("@/pages/Watchlist")).Watchlist }),
      },
      {
        path: "/idea-funnel",
        lazy: async () => ({ Component: (await import("@/pages/IdeaFunnel")).IdeaFunnel }),
      },
      {
        path: "/my-reports",
        lazy: async () => ({ Component: (await import("@/pages/MyReports")).MyReports }),
      },
      {
        path: "/notes",
        lazy: async () => ({ Component: (await import("@/pages/Notes")).Notes }),
      },
      {
        path: "/settings",
        element: (
          <Suspense fallback={<LayoutLoader />}>
            <Settings />
          </Suspense>
        ),
      },
    ],
  },
], { basename });
