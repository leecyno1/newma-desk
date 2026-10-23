import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Static-only delivery for older Desk servers; no workflow backend is mounted.
export default defineConfig({
  root: fileURLToPath(new URL("./session-board", import.meta.url)),
  base: "/mod-runtime/workflow-center/",
  plugins: [react()],
  build: { outDir: "../dist-sessions", emptyOutDir: true },
});
