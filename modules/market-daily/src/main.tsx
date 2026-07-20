import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@vibe-visualization/ui-foundation/tokens.css";

import { MarketDailyApp } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MarketDailyApp />
  </StrictMode>,
);
