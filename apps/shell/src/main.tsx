import { createRoot } from "react-dom/client";

import "@newma-dock/desk-ui/tokens.css";

import { App } from "./App";
import "./styles.css";

const root = document.getElementById("root");

if (!root) throw new Error("Shell root element is missing");

createRoot(root).render(<App />);
