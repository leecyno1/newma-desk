import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@newma-desk/desk-ui/mod-theme.css";

import { GlobalIntelligenceApp } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <GlobalIntelligenceApp />
  </StrictMode>,
);
