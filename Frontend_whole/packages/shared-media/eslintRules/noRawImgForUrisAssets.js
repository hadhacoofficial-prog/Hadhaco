/**
 * no-raw-img-for-uris-assets
 *
 * Flags raw `<img>` JSX elements whose `src` looks like it points at a
 * Universal Image System asset (our unified R2 key convention,
 * `images/{module}/{owner_type}/{owner_id}/{image_id}/...` — see
 * docs/architecture/Universal_Responsive_Image_System_Design.md §12) and
 * suggests `<ResponsiveImage>` from `@hadha/shared-media` instead, since
 * that's the only component that builds `srcSet`/`sizes` from an
 * ImageBundle (closes Audit G1/G16 — no raw `<img>` should ever again
 * regress to serving one fixed size to every viewport for these assets).
 *
 * STATUS: authored per the architecture doc's Phase 2 scope, NOT YET wired
 * into any eslint.config.js. Enforcing it repo-wide is a Phase 3 activity,
 * once `<ResponsiveImage>` has actually replaced the call sites it would
 * flag — turning it on today would fail the build on legitimate
 * still-in-migration code.
 *
 * To enable later: add this file's directory to an app's eslint.config.js
 * via a local plugin, e.g.:
 *   import noRawImg from "@hadha/shared-media/eslintRules/noRawImgForUrisAssets";
 *   { plugins: { "uris": { rules: { "no-raw-img-for-uris-assets": noRawImg } } },
 *     rules: { "uris/no-raw-img-for-uris-assets": "error" } }
 */

const URIS_PATH_PATTERN = /\/images\/[a-z0-9_-]+\/[a-z0-9_-]+\//i;

/** @type {import("eslint").Rule.RuleModule} */
module.exports = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Disallow raw <img> for Universal Image System assets — use <ResponsiveImage> from @hadha/shared-media",
    },
    schema: [],
    messages: {
      useResponsiveImage:
        "This <img> appears to render a Universal Image System asset (URL matches the images/{module}/{owner_type}/{owner_id}/... convention). Use <ResponsiveImage bundle={...} /> from @hadha/shared-media instead, so srcSet/sizes are generated automatically.",
    },
  },
  create(context) {
    return {
      JSXOpeningElement(node) {
        if (node.name.type !== "JSXIdentifier" || node.name.name !== "img") return;

        const srcAttr = node.attributes.find(
          (attr) => attr.type === "JSXAttribute" && attr.name.name === "src",
        );
        if (!srcAttr || !srcAttr.value) return;

        let srcText = null;
        if (srcAttr.value.type === "Literal" && typeof srcAttr.value.value === "string") {
          srcText = srcAttr.value.value;
        } else if (
          srcAttr.value.type === "JSXExpressionContainer" &&
          srcAttr.value.expression.type === "Literal" &&
          typeof srcAttr.value.expression.value === "string"
        ) {
          srcText = srcAttr.value.expression.value;
        }

        if (srcText && URIS_PATH_PATTERN.test(srcText)) {
          context.report({ node, messageId: "useResponsiveImage" });
        }
      },
    };
  },
};
