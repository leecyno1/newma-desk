import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/mod-runtime/workflow-center/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8911",
    },
  },
});
