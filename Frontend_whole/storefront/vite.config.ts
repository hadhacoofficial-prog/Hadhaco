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
      port: 8080,
      strictPort: true,
    },
    build: {
      rollupOptions: {
        // See vite.config.docker.ts for why: @hadha/shared-media's entry
        // point re-exports the crop editor (react-easy-crop), which
        // storefront never actually uses (only ResponsiveImage), and
        // which storefront doesn't declare as its own dependency — this
        // resolves locally today only because it's hoisted from admin's
        // install. Externalizing it here keeps this build correct in any
        // environment that installs storefront's tree in isolation.
        external: ["react-easy-crop"],
      },
    },
  },
});
