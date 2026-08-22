import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    build: {
      target: "es2022",
      modulePreload: { polyfill: false },
    },
    optimizeDeps: {
      // MapLibre owns a dedicated module worker. Keeping it out of Vite's
      // dependency pre-bundle prevents a stale optimized worker URL from
      // making the first map paint fail after a dependency or build refresh.
      exclude: ["maplibre-gl"],
    },
    server: {
      proxy: {
        "/api": env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8911",
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
