import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/mod-runtime/capital-flow/",
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8911" } },
});
