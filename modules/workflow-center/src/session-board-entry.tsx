import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@newma-desk/desk-ui/mod-theme.css";
import { SessionBoard } from "./SessionBoard";

createRoot(document.getElementById("root")!).render(<StrictMode><SessionBoard /></StrictMode>);
