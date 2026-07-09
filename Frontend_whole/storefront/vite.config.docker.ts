import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  nitro: {
    preset: "node",
  },
  tanstackStart: {
    server: {
      entry: "server",
    },
  },
  vite: {
    build: {
      rollupOptions: {
        // @hadha/shared-media's entry point re-exports the crop editor
        // (CropCanvas -> react-easy-crop) alongside ResponsiveImage, which
        // is all storefront actually uses. Locally that resolves fine
        // because react-easy-crop is hoisted into the monorepo root
        // node_modules (it's a real dependency of `admin`), but the
        // Docker build installs storefront's dependency tree in isolation,
        // where it's genuinely absent — failing Rollup's module-graph
        // resolution before tree-shaking ever gets a chance to drop the
        // unused code. Marking it external skips that resolution; the
        // import is unreachable at runtime here anyway, so nothing is
        // ever emitted.
        external: ["react-easy-crop"],
      },
    },
  },
});
