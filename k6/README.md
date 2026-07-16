# Hadha.co — k6 Performance Testing Suite

Production-grade performance testing framework for the Hadha.co storefront and backend API.

## Architecture

```
k6/
├── config/               # Environment configs (development.js, production.js)
├── helpers/              # HTTP client, auth, setup utilities
│   ├── http.js           # Envelope-aware HTTP helpers with custom metrics
│   ├── auth.js           # Dev auth login, session management
│   └── setup.js          # Reusable test lifecycle setup
├── shared/               # Shared data loaders, thresholds
│   ├── data-loader.js    # Dynamic fixture loading from live API
│   └── thresholds.js     # Threshold definitions per test profile
├── thresholds/           # Threshold configurations
│   └── default.js        # Smoke/load/stress/spike/checkout/inventory thresholds
├── catalog/              # Product browsing tests
│   ├── products.js       # Product listing + detail (10 VUs)
│   ├── categories-collections.js  # Category tree + collections browsing
│   └── homepage.js       # CMS homepage + component data loading
├── search/               # Search functionality tests
│   └── search.js         # Full-text search + autocomplete + trending
├── cart/                 # Cart operations tests
│   └── cart.js           # Guest cart CRUD flow
├── checkout/             # Checkout flow tests
│   ├── checkout.js       # Pre-payment checkout journey
│   └── coupons.js        # Coupon validation performance
├── orders/               # Order & account tests
│   ├── profile-orders.js # Profile, orders, addresses
│   ├── reviews.js        # Product review browsing
│   └── wishlist.js       # Wishlist operations
├── inventory/            # Inventory concurrency tests
│   ├── concurrency.js    # 100 concurrent buyers (same product)
│   └── concurrency-stress.js  # 200→500→1000 VU ramp
├── auth/                 # Authentication tests
│   └── auth-flow.js      # Dev login, token verification, profile
├── smoke/                # Smoke test scenarios
│   ├── health.js         # Health/readiness/liveness probes
│   └── full-suite.js     # Quick validation of all critical endpoints
├── load/                 # Load test scenarios
│   └── full-journey.js   # Realistic mixed traffic (10→50 VUs)
├── stress/               # Stress test scenarios
│   └── full-suite.js     # Beyond-capacity (50→200 VUs)
├── spike/                # Spike test scenarios
│   └── flash-sale.js     # Sudden traffic surge (5→200 VUs)
├── soak/                 # Soak test scenarios
│   └── endurance.js      # 30-min sustained load (30 VUs)
├── scenarios/            # Comprehensive scenario runner
│   └── full-storefront.js  # Unified runner with --env SCENARIO=X
├── reports/              # Performance reports & analysis
│   ├── api-rankings.js   # API endpoint rankings by criticality
│   └── performance-report.js  # Scores, bottlenecks, optimizations
└── run-tests.bat         # Windows runner script
```

## Quick Start

### Prerequisites

1. **Install k6**: https://grafana.com/docs/k6/latest/set-up/install-k6/
   ```bash
   # Windows (winget)
   winget install k6

   # macOS
   brew install k6

   # Docker
   docker pull grafana/k6
   ```

2. **Start the backend**:
   ```bash
   docker compose up backend redis
   # or
   cd Backend && python -m uvicorn app.main:app --reload
   ```

3. **Set environment variables** (for authenticated tests):
   ```bash
   set DEV_EMAIL=admin@hadha.co
   set DEV_PASSWORD=your-password
   set CUSTOMER_EMAIL=customer@hadha.co
   set CUSTOMER_PASSWORD=your-password
   ```

### Run Tests

```bash
# Smoke tests (2 minutes — recommended first run)
k6 run smoke/full-suite.js

# Using the unified runner
k6 run scenarios/full-storefront.js --env SCENARIO=smoke
k6 run scenarios/full-storefront.js --env SCENARIO=load
k6 run scenarios/full-storefront.js --env SCENARIO=stress

# Or use the batch script
run-tests.bat smoke
run-tests.bat load
run-tests.bat all
```

### Individual Test Suites

```bash
# Catalog browsing
k6 run catalog/products.js
k6 run catalog/categories-collections.js
k6 run catalog/homepage.js

# Search
k6 run search/search.js

# Cart operations
k6 run cart/cart.js

# Checkout flow
k6 run checkout/checkout.js
k6 run checkout/coupons.js

# Orders & Account
k6 run orders/profile-orders.js
k6 run orders/reviews.js
k6 run orders/wishlist.js

# Authentication
k6 run auth/auth-flow.js

# Inventory concurrency (critical)
k6 run inventory/concurrency.js
k6 run inventory/concurrency-stress.js

# Health checks
k6 run smoke/health.js
```

## Test Coverage Matrix

| Feature Area | Test File | Endpoints Covered | VUs |
|---|---|---|---|
| Health | `smoke/health.js` | `/health`, `/health/ready`, `/health/live` | 1 |
| Product Listing | `catalog/products.js` | `/products` (8 filter combos) | 10 |
| Product Detail | `catalog/products.js` | `/products/:slug` | 10 |
| Categories | `catalog/categories-collections.js` | `/categories`, `/categories/navbar`, `/categories/navigation` | 10 |
| Collections | `catalog/categories-collections.js` | `/collections`, `/collections/:slug` | 10 |
| Homepage | `catalog/homepage.js` | `/cms/homepage`, `/seo/page`, component data | 20 |
| Search | `search/search.js` | `/search`, `/search/autocomplete`, `/search/trending` | 15 |
| Cart | `cart/cart.js` | `/cart`, `/cart/items`, update, remove, clear | 10 |
| Checkout | `checkout/checkout.js` | `/cart/items`, `/orders/create-payment`, `/coupons/validate` | 5 |
| Coupons | `checkout/coupons.js` | `/coupons/validate` | 10 |
| Profile | `orders/profile-orders.js` | `/me`, `/me/addresses`, `/orders` | 5 |
| Reviews | `orders/reviews.js` | `/reviews/products/:id`, `/reviews/products/:id/summary` | 10 |
| Wishlist | `orders/wishlist.js` | `/me/wishlist`, toggle, add, remove | 5 |
| Auth | `auth/auth-flow.js` | `/dev/login`, `/dev/me`, `/auth/verify-token` | 5 |
| Inventory | `inventory/concurrency.js` | `/cart/items`, `/orders/create-payment` (100 VUs) | 100 |
| Inventory Stress | `inventory/concurrency-stress.js` | Same (200→500→1000 VUs) | 1000 |

## Performance Targets

| Metric | Target | Critical Threshold |
|---|---|---|
| Homepage p95 | < 300ms | > 500ms |
| Product List p95 | < 400ms | > 800ms |
| Product Detail p95 | < 300ms | > 600ms |
| Search p95 | < 500ms | > 1000ms |
| Autocomplete p95 | < 200ms | > 400ms |
| Cart Operations p95 | < 300ms | > 600ms |
| Checkout p95 | < 1000ms | > 2000ms |
| Error Rate | < 0.1% | > 1% |
| Throughput | > 25 req/s | < 10 req/s |

## Key Findings from Codebase Analysis

### Architecture
- **Backend**: FastAPI async + SQLAlchemy 2.0 async + PostgreSQL + Redis
- **Auth**: Supabase Auth (JWT ES256 verification, JWKS caching)
- **Payments**: Razorpay (2-phase: create intent → verify)
- **Inventory**: SELECT FOR UPDATE with deadlock prevention (sorted locking)
- **Cache**: Redis with SHA256-hashed param keys for product listings

### Top 5 Bottlenecks
1. **DB Connection Pool**: pool_size=3, max_overflow=1 (4 max connections)
2. **Inventory Lock Contention**: SELECT FOR UPDATE serializes same-SKU checkouts
3. **No Product Detail Cache**: Every product view hits the database
4. **Razorpay Thread Pool**: Sync HTTP in thread pool adds latency
5. **Redis SCAN Invalidation**: Pattern-based scan on checkout can stall

### Top 5 Quick Wins
1. Increase pool_size to 10, max_overflow to 5
2. Add Redis caching for product detail pages
3. Cache slug→ID mappings for category/collection filters
4. Add Redis caching for search results (1min TTL)
5. Replace sync Razorpay calls with async httpx

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Backend API base URL |
| `STOREFRONT_URL` | `http://localhost:8080` | Frontend URL |
| `DEV_EMAIL` | (empty) | Dev auth email for k6 |
| `DEV_PASSWORD` | (empty) | Dev auth password for k6 |
| `CUSTOMER_EMAIL` | (empty) | Customer auth email |
| `CUSTOMER_PASSWORD` | (empty) | Customer auth password |
| `SCENARIO` | `smoke` | Scenario for unified runner |

## Output

Results are written to `k6/reports/output/` in JSON format, compatible with:
- **Grafana**: Import JSON for dashboards
- **k6 Cloud**: Upload results for analysis
- **Custom scripts**: Parse JSON for reports
