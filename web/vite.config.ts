import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxied rather than cross-origin so the SSE endpoint is same-origin in
      // dev. EventSource is stricter about CORS than fetch, and a live view
      // that works in tests but not in the browser would be a poor discovery.
      "/api": {
        target: "http://127.0.0.1:8077",
        changeOrigin: true,
      },
    },
  },
});
