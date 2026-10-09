# Sorting & Filtering — Site-wide Audit and Plan (2026-10-09)

## 1. Audit — every list/grid/table in the app

### Storefront (hadha.co)

| Page | Today | Sort? | Filter? | Decision |
|---|---|---|---|---|
| `/products` (shop, gender/category nav, deals, new arrivals) | Server paging; `sort` param only partly honoured (`popular` silently = newest); no filter UI at all | Yes | Yes | Full discovery toolbar + filter sidebar/drawer, URL state |
| `/search` | Server paging; no sort, no filters beyond nav presets | Yes (+Relevance) | Yes | Same discovery toolbar, Relevance default when `q` is present |
| `/collections/$slug` | Has a sidebar, but state is local (lost on refresh/back), "In stock" checkbox sends nothing, price slider hard-coded 500–10 000 | Yes | Yes | Move to shared discovery toolbar, URL state, real stock filter, data-driven price range |
| Category pages | Served by `/products?category=` — only exact category matched, sub-categories excluded | — | — | Category filter includes descendants |
| `/collections` (index) | ~10 cards, curated order | No | No | Leave: editorial ordering, tiny list |
| `/wishlist` | Client list, typically < 20 items | No | No | Leave: personal, small |
| Product detail → Reviews tab | Fetches 50, fixed order | Yes | Yes (stars) | Sort (newest / highest / lowest / most helpful) + star filter, server-side |
| Account → Orders | Fetches first 20, no paging (orders 21+ invisible) | No (date desc is right) | Yes (status) | Status filter + pagination |
| Home rails, cart, checkout, PDP related, CMS pages | Curated / transactional | No | No | Leave |

### Admin (admin.hadha.co)

| Page | Today | Decision |
|---|---|---|
| Products | Search + collection; no sort, no status/category/stock filter | Sortable headers (name, price, stock, status, created, updated, rating, sold), filters: status, category, collection, gender, stock status, flags |
| Orders | Status tabs only; backend search unused | Sortable headers (number, date, total, status, payment), search (order #, name, phone, email), payment / fulfilment status, date range presets, order-total range |
| Customers | Search only | Sortable headers (name, email, joined, last updated), role + active filters, joined date range |
| Reviews | Status tabs only | Sort (date, rating, helpful), rating filter, verified-purchase toggle, search, date range |
| Coupons | Plain list | Search by code, status (active / inactive / expired), type filter, sortable headers |
| Enquiries | Status tabs + search | Sort (date, name, status), date range |
| Inventory | Already complete (search, sort, status chips, category/collection) | Reuse as reference; switch to shared sort header |
| Collections | Search + active/featured; sort fixed to `sort_order` | Sortable headers (name, product count, created, order) |
| Categories | Tree view | Leave tree ordering (hierarchy + `sort_order` is the meaning); search already present |
| Collection / Category detail product lists | Paging only | Leave: curated membership lists, short |
| Notification logs | Status, channel, search; backend date range unused | Add date range presets |
| Dashboard / Reports / Analytics | Aggregates; dashboard already has date range | Leave |
| CMS sections / media / templates / settings | Config screens | Leave |

## 2. Architecture

### Backend (server-side, allowlisted)
* Every sort is a `Literal`/regex-allowlisted key mapped to a column in a dict — never `getattr(Model, user_input)`.
* Every ordered query gets a deterministic tie-breaker (`id`) so offset pages never duplicate/skip rows.
* Filters applied before `OFFSET/LIMIT`; counts via `COUNT(*) OVER()`.
* `/products` additions: sorts `relevance`, `average_rating`, `sold_quantity`, `discount`, `updated_at`, `featured`; filters `in_stock`, `on_sale`, `min_rating`, multi-value `category_slug`, `metal_type`, `purity`, `gender`; category filter includes sub-categories.
* New `GET /products/facets` — disjunctive facet counts (categories, gender, metal, purity, price bounds, rating buckets, stock / sale / new / bestseller counts) under the current filter set; Redis SWR cached like the list.
* Admin list endpoints gain `sort_by`/`sort_dir` + the filters in the table above. Existing params and defaults unchanged → backward compatible.
* Migration `0066`: indexes supporting the new sorts/filters.

### Frontend shared primitives (`@hadha/shared-ui/data/*`)
`SortableHeader`, `DateRangeFilter` (+ `resolveDatePreset`), `ActiveFilterChips`, `ResultCount`, `TablePagination`, `FilterSelect`.

### Storefront discovery (`storefront/src/components/discovery/*`)
`discoverySearchSchema` + `buildProductApiParams` (one URL contract for `/products`, `/search`, `/collections/$slug`), `DiscoveryToolbar`, `SortDropdown`, `ProductFilterPanel`, `FilterDrawer` (mobile sheet), `PriceRangeFilter`, `useProductFacets`.

URL contract: `?q=&category=a,b&gender=&metal=&purity=&minPrice=&maxPrice=&rating=4&inStock=true&onSale=true&new=true&bestseller=true&sort=price_asc&page=2`.
Legacy params (`deals=true`, `sort=newest`, `/search?cat=`, `/search?filter=`) keep working.

## 3. Order of work
1. Backend: products (list + facets) → admin lists → reviews → migration.
2. Shared primitives.
3. Storefront: search, products, collections, PDP reviews, account orders.
4. Admin: products, orders, customers, reviews, coupons, enquiries, collections, notification logs, inventory header reuse.
5. QA: black/ruff/mypy/pytest, tsc/eslint, live browser pass on both apps.
