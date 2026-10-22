import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
export default defineConfig(({ mode }) => ({ base: "/mod-runtime/industry-research/", plugins: [react()],
  build: {rollupOptions: {output: {manualChunks(id) {
    if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return "react-vendor";
  }}}},
  server: { proxy: { "/api": loadEnv(mode, ".", "").VITE_API_PROXY_TARGET
    || (mode === "standalone" ? "http://127.0.0.1:18950" : "http://127.0.0.1:8911") } } }));
