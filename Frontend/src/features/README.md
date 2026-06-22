# Feature modules

Reserved for future feature-bounded code: when a single feature (e.g. checkout,
admin-orders) starts spanning multiple components, hooks, and services, move it
into `src/features/<feature>/` with its own `components/`, `hooks/`, and
`services.ts`. Today the app is small enough that flat folders are fine — no
code lives here yet, intentionally.

Planned module map (matches SOW):

- home/         shop/         products/      categories/
- cart/         wishlist/     checkout/      orders/
- account/      auth/         reviews/       cms/
- admin/        search/