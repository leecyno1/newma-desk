import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "/mod-runtime/portfolio-center/",
  plugins: [react()],
  build: {
    target: "esnext",
    modulePreload: { polyfill: false },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8911",
    },
  },
  test: {
    environment: "jsdom",
  },
});
