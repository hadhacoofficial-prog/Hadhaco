import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// Production Docker build config — uses Nitro's standalone Node.js preset
// instead of the default "vercel" preset. Used in the production Dockerfile:
//   NITRO_PRESET=node npm run build
// This file is a fallback if the env var is not respected by the plugin.
export default defineConfig({
  nitro: {
    preset: "node",
  },
  tanstackStart: {
    server: {
      entry: "server",
    },
  },
});
