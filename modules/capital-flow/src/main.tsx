import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@newma-desk/desk-ui/mod-theme.css";
import { CapitalFlowApp } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><CapitalFlowApp /></StrictMode>,
);
