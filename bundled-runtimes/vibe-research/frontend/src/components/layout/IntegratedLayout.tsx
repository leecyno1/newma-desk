import { Outlet } from "react-router-dom";

/** Minimal Research shell for Desk-hosted pages; Desk owns navigation and Agent UI. */
export function IntegratedLayout() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="min-h-screen overflow-auto">
        <div className="mx-auto w-full max-w-[1880px] px-4 py-4 sm:px-5 sm:py-5 2xl:px-7">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
