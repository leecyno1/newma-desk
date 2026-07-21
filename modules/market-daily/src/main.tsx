import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@vibedesk/desk-ui/tokens.css";

import { MarketPulseApp } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MarketPulseApp />
  </StrictMode>,
);
