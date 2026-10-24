import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The browser only ever talks to its own origin (auth-and-threat-model.md A2.14). In development
// this dev server proxies /api and /ws to the API on port 8000; in Docker, nginx does the same.
// ICD_API_TARGET points both proxies elsewhere, for example at the countdown test server
// (npm run dev:countdown).
const apiTarget = process.env.ICD_API_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // /api/health -> http://localhost:8000/health
      "/api": {
        target: apiTarget,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      // Countdown channel (T1-11). The path is kept: /ws/response-windows -> /ws/response-windows
      "/ws": {
        target: apiTarget,
        ws: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
