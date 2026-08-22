import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";

import "@newma-desk/desk-ui/mod-theme.css";

import { StrategicAllocationApp } from "./StrategicAllocationApp";
import "./styles.css";

const workspace = new URLSearchParams(window.location.search).get("workspace");
const useLedgerWorkspace = workspace === "portfolio-activities" || workspace === "portfolio-risk";
const PortfolioCenterApp = lazy(() => import("./App").then(({ PortfolioCenterApp: app }) => ({ default: app })));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {useLedgerWorkspace ? (
      <Suspense fallback={<main className="saa-root saa-loading"><span>正在加载组合账本</span></main>}>
        <PortfolioCenterApp />
      </Suspense>
    ) : <StrategicAllocationApp />}
  </StrictMode>,
);
