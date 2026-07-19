import { defineConfig } from "@lovable.dev/vite-tanstack-config";

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
      port: 8081,
      strictPort: true,
      allowedHosts: true,
    },
  },
});
