import './i18n';
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { useDarkMode } from "./hooks/useDarkMode";
import { router } from "./router";
import "./lib/vibedesk";
import "./index.css";

function NewmaToaster() {
  const { dark } = useDarkMode();
  return (
    <Toaster
      position="bottom-right"
      theme={dark ? "dark" : "light"}
      richColors
      closeButton
      duration={3500}
      toastOptions={{
        classNames: {
          toast: "!border-border !bg-popover !text-popover-foreground !shadow-lg",
          description: "!text-muted-foreground",
          closeButton: "!border-border !bg-muted !text-muted-foreground",
          actionButton: "!bg-primary !text-primary-foreground",
          cancelButton: "!bg-muted !text-muted-foreground",
        },
      }}
    />
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <RouterProvider router={router} />
      <NewmaToaster />
    </ErrorBoundary>
  </StrictMode>
);
