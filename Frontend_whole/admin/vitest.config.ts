import { defineConfig } from "vitest/config";
import { resolve } from "path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", "dist", ".output", "e2e"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov", "json"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/routeTree.gen.ts", "src/**/*.d.ts", "src/test/**"],
    },
  },
  resolve: {
    alias: [
      { find: "@", replacement: resolve(__dirname, "./src") },
      // Mirrors the tsconfig path: the package `exports` map common/* to
      // *.tsx, but hooks there (use-debounce) are .ts — the app build
      // resolves via tsconfig paths, so tests must too.
      {
        find: /^@hadha\/shared-ui\/common\/(.*)$/,
        replacement: resolve(__dirname, "../packages/shared-ui/src/common/$1"),
      },
    ],
  },
});
