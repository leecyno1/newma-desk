import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    base: "/mods/global-intelligence/",
    build: {
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks: {
            "geo-deck": ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/mapbox"],
            "geo-map": ["maplibre-gl"],
            "react-runtime": ["react", "react-dom"],
          },
        },
      },
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
