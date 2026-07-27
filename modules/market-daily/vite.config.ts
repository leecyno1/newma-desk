import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    base: "/mods/market-daily/",
    build: {
      chunkSizeWarningLimit: 1100,
    },
    plugins: [react()],
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
