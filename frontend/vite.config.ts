import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development, `npm run dev` proxies API calls to a locally running backend
// (python -m famtree with FAMTREE_LISTEN_PORT=8080).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8080" },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    include: ["test/**/*.test.{ts,tsx}"],
  },
});
