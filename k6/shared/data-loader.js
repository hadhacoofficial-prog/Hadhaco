// k6 shared — Dynamic test data loader
// Fetches real products, categories, collections from the live API
// Used during setup phase to seed test data

import { apiGet, apiPost, apiUrl } from "../helpers/http.js";

/**
 * Fetch real product data from the API.
 * Returns an array of { id, slug, name, base_price, variants[] }.
 */
export function loadProducts(count) {
  const { body } = apiGet("/products", {
    query: { page: 1, page_size: count || 50, include_collections: false },
  }, { name: "setup_load_products" });

  if (!body || !body.data || !body.data.items) return [];

  return body.data.items.map((p) => ({
    id: p.id,
    slug: p.slug,
    name: p.name,
    base_price: p.base_price,
    stock_quantity: p.stock_quantity,
    // Pick first variant if available
    variant_id: p.variants && p.variants.length > 0 ? p.variants[0].id : null,
    variant_name: p.variants && p.variants.length > 0 ? p.variants[0].name : null,
  }));
}

/**
 * Fetch real categories from the API.
 * Returns an array of { id, slug, name }.
 */
export function loadCategories() {
  const { body } = apiGet("/categories", {}, { name: "setup_load_categories" });
  if (!body || !body.data) return [];

  // Categories come as a tree; flatten them
  const flat = [];
  function walk(nodes) {
    if (!nodes) return;
    for (const n of nodes) {
      flat.push({ id: n.id, slug: n.slug, name: n.name });
      if (n.children) walk(n.children);
    }
  }
  walk(body.data);
  return flat;
}

/**
 * Fetch real collections from the API.
 * Returns an array of { id, slug, name, product_count }.
 */
export function loadCollections() {
  const { body } = apiGet("/collections", {}, { name: "setup_load_collections" });
  if (!body || !body.data) return [];

  return body.data.map((c) => ({
    id: c.id,
    slug: c.slug,
    name: c.name,
    product_count: c.product_count || 0,
  }));
}

/**
 * Fetch homepage data from the CMS.
 */
export function loadHomepage() {
  const { body } = apiGet("/cms/homepage", {}, { name: "setup_load_homepage" });
  if (!body || !body.data) return null;
  return body.data;
}

/**
 * Build the complete test fixture set.
 * Called once during setup, shared across all VUs via __ITER sharing.
 */
export function buildFixtures() {
  const products = loadProducts(50);
  const categories = loadCategories();
  const collections = loadCollections();
  const homepage = loadHomepage();

  // Separate products by stock status for different test scenarios
  const inStockProducts = products.filter((p) => p.stock_quantity > 0);
  const outOfStockProducts = products.filter((p) => p.stock_quantity === 0);
  const variantProducts = products.filter((p) => p.variant_id !== null);

  return {
    products,
    productsById: Object.fromEntries(products.map((p) => [p.id, p])),
    productsBySlug: Object.fromEntries(products.map((p) => [p.slug, p])),
    inStockProducts,
    outOfStockProducts,
    variantProducts,
    categories,
    collections,
    homepage,
    timestamp: Date.now(),
  };
}
