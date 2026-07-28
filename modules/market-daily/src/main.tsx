import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@newma-desk/desk-ui/tokens.css";

import { MarketPulseApp } from "./App";
import { marketWorkspaceFromSearch } from "./workspaces/config";
import { MarketWorkspaceApp } from "./workspaces/WorkspaceApp";
import "./styles.css";
import "./workspaces/workspaces.css";

const workspace = marketWorkspaceFromSearch(window.location.search);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {workspace ? <MarketWorkspaceApp config={workspace} /> : <MarketPulseApp />}
  </StrictMode>,
);
