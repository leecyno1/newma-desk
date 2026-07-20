import { createRoot } from "react-dom/client";

import "@vibe-visualization/ui-foundation/tokens.css";

import { App } from "./App";
import "./styles.css";

const root = document.getElementById("root");

if (!root) throw new Error("Shell root element is missing");

createRoot(root).render(<App />);
