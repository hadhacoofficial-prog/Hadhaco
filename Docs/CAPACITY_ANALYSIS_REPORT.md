You are now entering Phase 2 of the Hadha.co Performance Engineering project.

The Redis caching layer, HTTP caching, profiling infrastructure, and initial k6 suite have already been implemented.

DO NOT regenerate them.

Continue from the existing implementation.

Your goal is NOT to write more code.

Your goal is to prove (or disprove) that Hadha.co is production-ready using real measurements.

Think like a Principal Performance Engineer responsible for certifying an ecommerce platform before launch.

=====================================================================
CURRENT ENVIRONMENT
=====================================================================

Storefront
http://localhost:8080

Backend
http://localhost:8000

Admin
Auto detect

Database
Supabase PostgreSQL (Free Tier)

Redis
Enabled

FastAPI

SQLAlchemy Async

Docker

Existing Redis cache layer

Existing HTTP cache layer

Existing profiling endpoint (/health/metrics)

Existing k6 suite

Use the current implementation.

Do NOT recreate it.

=====================================================================
PHASE 1
VERIFY THE CURRENT IMPLEMENTATION
=====================================================================

Do NOT trust previous reports.

Re-read the codebase.

Verify

Redis cache

HTTP cache

Invalidation

ETags

Cache-Control

SQLAlchemy profiling

Redis profiling

Pool profiling

k6 scenarios

Determine whether every optimization is actually active.

If something is incomplete,
fix it before testing.

=====================================================================
PHASE 2
VERIFY REDIS
=====================================================================

Do NOT assume Redis is helping.

Measure it.

For every cached endpoint collect

Redis Hit Count

Redis Miss Count

Hit Ratio

Miss Ratio

Lookup Time

Memory Usage

Key Count

TTL Remaining

Evictions

Expired Keys

Largest Keys

Slow Commands

Generate a report

Endpoint

Cache Hit %

Cache Miss %

Lookup Time

TTL

DB Queries Avoided

Latency Saved

=====================================================================
PHASE 3
VERIFY CACHE INVALIDATION
=====================================================================

Actually verify invalidation.

For

Products

Categories

Collections

CMS

SEO

Reviews

Feature Flags

Test

GET

↓

Redis HIT

↓

Update Resource

↓

Redis Key Deleted

↓

GET

↓

DB Read

↓

Redis Rebuilt

Produce proof.

=====================================================================
PHASE 4
VERIFY DATABASE
=====================================================================

Enable SQL profiling.

Collect

Total Queries

Duplicate Queries

Repeated Queries

N+1 Queries

Slow Queries

Sequential Scans

Index Usage

Query Duration

Top 50 Slow Queries

Use

pg_stat_statements

EXPLAIN ANALYZE

SQLAlchemy Events

Do NOT estimate.

Measure.

=====================================================================
PHASE 5
VERIFY CONNECTION POOL
=====================================================================

Do NOT assume the connection pool is the bottleneck.

Measure

Pool Size

Checked Out

Idle

Overflow

Checkout Wait

Acquire Time

Timeout Count

Peak Utilization

Queue Length

Determine

Is the bottleneck

Database

Pool

Redis

Application

Network

Workers

Support every conclusion with metrics.

=====================================================================
PHASE 6
VERIFY FRONTEND PERFORMANCE
=====================================================================

Backend APIs are not enough.

Measure

Lighthouse

LCP

CLS

FCP

TTFB

JS Bundle Size

Hydration Time

Network Waterfall

Image Loading

Font Loading

Verify

Cloudflare compatibility

Compression

Caching

=====================================================================
PHASE 7
REALISTIC USER TRAFFIC
=====================================================================

Do NOT simulate identical users.

Generate realistic ecommerce traffic.

Example

70%
Browsing

15%
Search

8%
Product Detail

4%
Add To Cart

2%
Checkout

1%
Payment

Automatically discover the correct API sequence from the codebase.

=====================================================================
PHASE 8
AUTHENTICATED FLOWS
=====================================================================

Reuse my logged-in account.

Do NOT create fake users.

Test

Login

Profile

Wishlist

Cart

Checkout

Order

Reservation

Payment

Notifications

Account

=====================================================================
PHASE 9
FLASH SALE
=====================================================================

Use one product.

Generate

100

200

300

500

1000

buyers

trying to purchase simultaneously.

Verify

Reservation

Stock

Overselling

Deadlocks

Race Conditions

Rollback

Inventory Release

=====================================================================
PHASE 10
PAYMENT TESTS
=====================================================================

Simulate

Payment Success

Payment Failure

Duplicate Callback

Webhook Retry

Late Payment

Reservation Expiry

Payment Timeout

Verify

Order State

Inventory

Notifications

=====================================================================
PHASE 11
BACKGROUND SYSTEMS
=====================================================================

Stress

Notification Workers

Reservation Workers

CMS Workers

Media Workers

Retry Workers

Verify

Queue Delays

Execution Time

Failures

Retries

=====================================================================
PHASE 12
FAILURE TESTING
=====================================================================

Verify graceful degradation.

Restart Redis

↓

Verify backend still works.

Restart PostgreSQL

↓

Verify graceful errors.

Kill Notification Worker

↓

Orders continue.

Kill Scheduler

↓

Reservations recover.

=====================================================================
PHASE 13
PRODUCTION LOAD TESTS
=====================================================================

Run staged tests.

25 Users

↓

50 Users

↓

75 Users

↓

100 Users

↓

150 Users

↓

200 Users

↓

300 Users

↓

500 Users

Only continue when previous stage passes.

For every stage report

Requests/sec

Orders/min

Checkout/min

Payments/min

P50

P95

P99

CPU

Memory

Redis

Pool Usage

DB Queries

Success Rate

=====================================================================
PHASE 14
OPTIMIZE
=====================================================================

If bottlenecks exist

Fix them.

Possible improvements

Indexes

Redis

Caching

Pagination

Compression

Serialization

Workers

Connection Pool

SQL

HTTP

Then rerun every affected benchmark.

=====================================================================
PHASE 15
PRODUCTION CERTIFICATION
=====================================================================

Generate a final engineering report.

Include

1. Redis effectiveness

2. Cache hit ratios

3. DB query reduction

4. HTTP cache effectiveness

5. SQL profiling

6. Pool profiling

7. Redis profiling

8. Lighthouse scores

9. Browser performance

10. API performance

11. Slow APIs

12. Slow SQL

13. Missing indexes

14. Remaining N+1 queries

15. Pool bottlenecks

16. Infrastructure bottlenecks

17. Security observations

18. Capacity planning

19. Maximum Requests/sec

20. Maximum Orders/min

21. Maximum Checkouts/min

22. Maximum Payments/min

23. Maximum Concurrent Users

24. Breaking Point

25. Recovery Time

26. Recommended VPS

27. Recommended Supabase Plan

28. Recommended Redis Size

29. Production Readiness Score (/100)

30. Go / No-Go Recommendation

=====================================================================
IMPORTANT
=====================================================================

Do NOT trust previous reports.

Every conclusion must be backed by measurements.

Do NOT estimate.

Do NOT guess.

If a claim cannot be proven, explicitly state that it is unverified.

Reuse the existing k6 suite and profiling infrastructure.

Do not generate generic examples.

Everything must be based on the actual Hadha.co codebase.

Keep iterating until no major bottlenecks remain or improvements plateau.

The final deliverable should be a production certification report that can confidently answer:

- How many concurrent users can Hadha.co support?
- How many requests per second can it sustain?
- How many orders per minute can it process?
- What fails first under heavy load?
- What infrastructure upgrades are required to safely support 500+ concurrent users?