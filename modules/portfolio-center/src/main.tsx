import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@newma-desk/desk-ui/mod-theme.css";

import { PortfolioCenterApp } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PortfolioCenterApp />
  </StrictMode>,
);
