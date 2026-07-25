import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// TEMPORARY debugging config — not for commit. Proxies /api to the local
// backend so this scratch dev server (running on a non-whitelisted CORS
// port) can hit it without touching Backend ALLOWED_ORIGINS.
export default defineConfig({
  nitro: {
    preset: "vercel",
  },
  tanstackStart: {
    server: {
      entry: "server",
    },
  },
  vite: {
    server: {
      port: 8090,
      strictPort: true,
      allowedHosts: true,
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  },
});
