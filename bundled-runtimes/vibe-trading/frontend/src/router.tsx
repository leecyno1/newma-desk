import { Suspense, lazy, type ComponentType } from "react";
import { createBrowserRouter } from "react-router-dom";

const integrated = import.meta.env.VITE_NEWMA_DESK_INTEGRATED === "1";
const Layout = integrated
  ? lazy(() => import("@/components/layout/IntegratedLayout").then((m) => ({ default: m.IntegratedLayout })))
  : lazy(() => import("@/components/layout/Layout").then((m) => ({ default: m.Layout })));

const Home = lazy(() => import("@/pages/Home").then((m) => ({ default: m.Home })));
const Agent = integrated
  ? lazy(() => import("@/pages/DeskAgent").then((m) => ({ default: m.DeskAgent })))
  : lazy(() => import("@/pages/Agent").then((m) => ({ default: m.Agent })));
const RunDetail = lazy(() =>
  import("@/pages/RunDetail").then((m) => ({ default: m.RunDetail })),
);
const Compare = lazy(() =>
  import("@/pages/Compare").then((m) => ({ default: m.Compare })),
);
const Settings = integrated
  ? lazy(() => import("@/pages/IntegratedSettings").then((m) => ({ default: m.IntegratedSettings })))
  : lazy(() => import("@/pages/Settings").then((m) => ({ default: m.Settings })));
const Runtime = lazy(() =>
  import("@/pages/Runtime").then((m) => ({ default: m.Runtime })),
);
const Reports = lazy(() =>
  import("@/pages/Reports").then((m) => ({ default: m.Reports })),
);
const Correlation = lazy(() =>
  import("@/pages/Correlation").then((m) => ({ default: m.Correlation })),
);
const AlphaZoo = lazy(() =>
  import("@/pages/AlphaZoo").then((m) => ({ default: m.AlphaZoo })),
);

function PageLoader() {
  return (
    <div className="flex h-[60vh] items-center justify-center text-muted-foreground">
      Loading…
    </div>
  );
}

function wrap(Component: ComponentType) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

const basename = import.meta.env.BASE_URL.replace(/\/$/, "") || "/";

export const router = createBrowserRouter([
  {
    element: wrap(Layout),
    children: [
      { path: "/", element: wrap(Home) },
      { path: "/agent", element: wrap(Agent) },
      { path: "/runtime", element: wrap(Runtime) },
      { path: "/reports", element: wrap(Reports) },
      { path: "/settings", element: wrap(Settings) },
      { path: "/runs/:runId", element: wrap(RunDetail) },
      { path: "/compare", element: wrap(Compare) },
      { path: "/correlation", element: wrap(Correlation) },
      { path: "/alpha-zoo", element: wrap(AlphaZoo) },
      { path: "/alpha-zoo/bench", element: wrap(AlphaZoo) },
      { path: "/alpha-zoo/compare", element: wrap(AlphaZoo) },
      { path: "/alpha-zoo/:alphaId", element: wrap(AlphaZoo) },
    ],
  },
], { basename });
