import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { searchForWorkspaceRoot } from "vite";
import { defineConfig } from "vitest/config";

const proxyTarget = process.env.VITE_DEV_PROXY_TARGET ?? "http://localhost:8000";
const samplesDir = fileURLToPath(new URL("../samples", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@samples": samplesDir
    }
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    fs: {
      allow: [searchForWorkspaceRoot(process.cwd()), samplesDir]
    },
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true
      }
    }
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: "./vitest.setup.ts",
    globals: true
  }
});
