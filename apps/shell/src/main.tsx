import { createRoot } from "react-dom/client";

import "@newma-desk/desk-ui/tokens.css";

import { App } from "./App";
import { WebsiteAuthGate } from "./components/WebsiteAuthGate";
import "./styles.css";

const root = document.getElementById("root");

if (!root) throw new Error("Shell root element is missing");

// Opt in with the matching API switch; existing local development stays independent.
createRoot(root).render(import.meta.env.VITE_NEWMA_WEBSITE_AUTH_ENABLED === "1"
  ? <WebsiteAuthGate>{(identity) => <App authoritativeIdentity={identity} />}</WebsiteAuthGate>
  : <App />);
