import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { router } from "./router";
import "./lib/vibedesk";
import "./index.css";

function currentTheme(): "light" | "dark" {
  return document.documentElement.classList.contains("dark") ||
    document.documentElement.dataset.theme === "dark"
    ? "dark"
    : "light";
}

function ThemeAwareToaster() {
  const [theme, setTheme] = useState<"light" | "dark">(currentTheme);

  useEffect(() => {
    const sync = () => setTheme(currentTheme());
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "data-vibedesk-theme"],
    });
    window.addEventListener("vibedesk:theme", sync);
    sync();
    return () => {
      observer.disconnect();
      window.removeEventListener("vibedesk:theme", sync);
    };
  }, []);

  return <Toaster position="bottom-right" theme={theme} richColors closeButton duration={3500} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <RouterProvider router={router} />
      <ThemeAwareToaster />
    </ErrorBoundary>
  </StrictMode>
);
