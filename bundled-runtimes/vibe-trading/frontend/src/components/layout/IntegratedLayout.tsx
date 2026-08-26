import { Outlet } from "react-router-dom";

/** Minimal shell for Desk-hosted Trading pages; Desk owns navigation and Agent UI. */
export function IntegratedLayout() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="min-h-screen overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
