# Hadha.co Monitoring & Observability

Complete monitoring stack for production observability.

## Architecture

```
Internet
  │
  ▼
Cloudflare (CDN, WAF, DNS)
  │
  ▼
Nginx (reverse proxy, TLS termination)
  │
  ├── hadha.co ──────────► storefront:3000
  ├── api.hadha.co ──────► backend:8000
  ├── admin.hadha.co ────► admin:3000
  ├── grafana.hadha.co ──► grafana:3000
  ├── uptime.hadha.co ───► uptime-kuma:3001
  ├── errors.hadha.co ───► glitchtip:8000
  ├── redis.hadha.co ────► redis-commander:8081
  └── dozzle.hadha.co ───► dozzle:8080

Internal Only (no public access):
  ├── prometheus:9090 ◄── scrape all services + recording/alert rules
  ├── loki:3100 ◄── receive logs from promtail (embedded cache enabled)
  ├── promtail:9080 ──► ship logs to loki (universal Docker SD)
  ├── redis-exporter:9121 ──► Redis metrics for Prometheus
  ├── node-exporter:9100 ──► host metrics
  └── cadvisor:8080 ──► container metrics
```

## Services

### Public (via Nginx)

| Service | Domain | Port | Auth |
|---------|--------|------|------|
| Grafana | grafana.hadha.co | 3000 | Username/password |
| Uptime Kuma | uptime.hadha.co | 3001 | Username/password (first-run setup) |
| GlitchTip | errors.hadha.co | 8000 | Username/password |
| Redis Commander | redis.hadha.co | 8081 | HTTP Basic Auth |
| Dozzle | dozzle.hadha.co | 8080 | Simple auth (users.yml) |

### Internal (no public access)

| Service | Port | Purpose |
|---------|------|---------|
| Prometheus | 9090 | Metrics collection, recording rules, alerting |
| Loki | 3100 | Log aggregation with embedded cache |
| Promtail | 9080 | Log collection agent (universal Docker SD) |
| Redis Exporter | 9121 | Redis metrics for Prometheus |
| Node Exporter | 9100 | Host system metrics |
| cAdvisor | 8080 | Container resource metrics |

## Dashboards

### Grafana (grafana.hadha.co)

Auto-provisioned dashboards in the "Hadha.co" folder:

1. **Hadha - Application** — Request rate by handler/status, response time (p50/p95/p99), error rate, active requests, duration histogram. Service filter variable.
2. **Hadha - Docker** — Container CPU vs limit, memory vs limit, network I/O, disk I/O. Per-container filter variable.
3. **Hadha - Redis** — Up status, clients, memory vs max, hit rate, ops/sec, fragmentation ratio, commands breakdown, keyspace, evictions.
4. **Hadha - System** — CPU, memory breakdown (piechart), disk usage + I/O, network traffic, load average with CPU count reference line, uptime.
5. **Hadha - Logs** — Log ingestion rate, live log stream with service/level filters, error rate by service, recent error viewer.

### Prometheus (localhost:9090 internal)

Scrape targets:
- `hadha-backend:8000/metrics` — FastAPI HTTP metrics (prometheus-fastapi-instrumentator)
- `hadha-redis-exporter:9121` — Redis metrics (memory, clients, keyspace, commands)
- `hadha-node-exporter:9100` — Host CPU, memory, disk, network
- `hadha-cadvisor:8080` — Container resource usage (filtered: no fs, blkio, tasks)
- `hadha-loki:3100` — Loki self-monitoring

### Recording Rules (`prometheus/rules/recording.yml`)

Pre-computed metrics for faster dashboard loading:
- `job:http_requests:rate5m` — Request rate by handler
- `job:http_request_duration_seconds:p95/p50/p99` — Latency percentiles
- `job:http_errors:error_ratio5m` — Error ratio
- `redis:hit_ratio:ratio` — Cache hit ratio
- `redis:commands:rate5m` — Command rate
- `container:cpu_usage:percent`, `container:memory_usage:bytes` — Container metrics
- `host:cpu_usage:percent`, `host:memory_usage:percent`, `host:disk_usage:percent` — Host metrics

### Alert Rules (`prometheus/rules/alerts.yml`)

| Alert | Condition | Severity |
|-------|-----------|----------|
| ServiceDown | target unreachable > 1m | critical |
| HighCPUUsage | host CPU > 90% for 5m | warning |
| HighMemoryUsage | host RAM > 85% for 5m | warning |
| DiskSpaceLow | disk > 85% for 10m | critical |
| DiskSpaceCritical | disk > 95% for 5m | critical |
| HighErrorRate | 5xx > 5% for 5m | warning |
| HighLatencyP95 | P95 > 2s for 5m | warning |
| HighLatencyP99 | P99 > 5s for 5m | critical |
| RedisDown | redis unreachable > 1m | critical |
| RedisHighMemory | memory > 90% maxmemory | warning |
| RedisHighEviction | evictions > 10/s | warning |
| RedisLowHitRate | hit rate < 80% | warning |
| ContainerHighCPU | container CPU > 80% | warning |
| ContainerHighMemory | container RAM > 90% limit | warning |
| ContainerRestarted | > 3 restarts/hour | warning |
| LokiDown | Loki unreachable > 1m | critical |

### Grafana Alerting

Provisioned contact points and notification policies:
- Contact point: `hadha-admin-email` → `admin@hadha.co`
- Policy: critical alerts → 10s wait, 2m interval, 1h repeat
- Policy: warning alerts → 30s wait, 5m interval, 4h repeat

## Environment Variables

Add to `.env.production`:

```bash
# ── Grafana ──
GRAFANA_USERNAME=admin
GRAFANA_PASSWORD=<secure-password>

# ── Uptime Kuma ──
UPTIME_USERNAME=admin
UPTIME_PASSWORD=<secure-password>

# ── GlitchTip ──
GLITCHTIP_DB_PASSWORD=<secure-password>
GLITCHTIP_SECRET_KEY=<64-char-random>
GLITCHTIP_DSN=https://<key>@errors.hadha.co/<project_id>
GLITCHTIP_FRONTEND_DSN=https://<key>@errors.hadha.co/<project_id>

# ── Backend (error tracking) ──
SENTRY_DSN=<glitchtip-backend-dsn>

# ── Frontend (error tracking) ──
VITE_SENTRY_DSN=<glitchtip-frontend-dsn>
```

## Data Retention

| Service | Retention | Storage | Max Size |
|---------|-----------|---------|----------|
| Prometheus | 15 days | `prometheus_data` | 512MB (WAL 32MB segments) |
| Loki | 7 days | `loki_data` | ~2GB (chunks by compactor) |
| Grafana | Indefinite | `grafana_data` | Dashboard JSON only |
| Uptime Kuma | Indefinite | `uptime_kuma_data` | Monitor history |
| GlitchTip | Indefinite | `glitchtip_db_data` | Error events |

## Resource Limits (Production)

| Service | Memory | CPU |
|---------|--------|-----|
| Prometheus | 256M | 0.5 |
| Grafana | 256M | 0.5 |
| Loki | 256M | 0.5 |
| Promtail | 64M | 0.1 |
| Redis Exporter | 32M | 0.1 |
| Node Exporter | 32M | 0.1 |
| cAdvisor | 128M | 0.25 |
| Uptime Kuma | 128M | 0.25 |
| GlitchTip | 256M | 0.5 |
| GlitchTip DB | 128M | 0.25 |
| **Total** | **~1.9GB** | **~2.85** |

## Optimization Applied

### Prometheus
- `--storage.tsdb.wal-segment-size=32MB` — Reduces WAL disk usage
- `metric_relabel_configs` on cAdvisor — Drops fs, blkio, tasks, container_scrape_error metrics
- `metric_relabel_configs` on Node Exporter — Drops conntrack, netstat, unused filesystem types
- Recording rules pre-compute expensive dashboard queries

### Loki
- Embedded cache enabled (50MB) — Reduces query latency
- `max_entries_limit_per_query: 5000` — Prevents memory spikes
- `max_query_parallelism: 4` — Limits concurrent queries
- `per_stream_rate_limit: 2MB` — Prevents one noisy container from consuming all ingestion

### Promtail
- Universal Docker SD — No project name filter, works for both local and production
- Drops healthcheck noise from all services (nginx, backend, grafana, prometheus, etc.)
- Drops DEBUG-level logs after 2h
- Drops own logs to prevent feedback loops

### Grafana
- `GF_LOG_LEVEL: warn` — Minimal logging
- `GF_AUTH_ANONYMOUS_ENABLED: false` in production
- `GF_USERS_ALLOW_SIGN_UP: false`
- `GF_INSTALL_PLUGINS: ""` — No extra plugins
- Dashboards are editable for customization

## Logs

### Collection Flow

```
Container stdout/stderr
  → Docker JSON log driver
  → Promtail (Docker SD, no filter)
  → Loki (stores & indexes)
  → Grafana (queries & visualizes)
```

### What Gets Collected

- **Backend** — structlog JSON output (request_id, user_id, method, path, status, duration_ms)
- **Nginx** — Access logs (request timing, upstream response time)
- **All containers** — stdout/stderr via Docker log driver

### What Gets Dropped

- Healthcheck probes from all services (nginx-health, /health, /health/live, /metrics, /_health/)
- DEBUG-level logs older than 2h
- Promtail's own logs (feedback loop prevention)
- wget/cron noise from monitoring containers

### Log Queries (Grafana Explore → Loki)

```logql
# All backend errors
{service="backend"} | json | level="error"

# Slow requests (>500ms)
{service="backend"} | json | duration_ms > 500

# Nginx 5xx errors
{container="hadha-nginx"} |= " 5"

# All container logs (universal — works for local and production)
{project=~"hadha.*"}
```

## Error Tracking (GlitchTip)

### Backend Integration

- Sentry SDK (`sentry-sdk[fastapi]`) initialized at app startup
- Captures: unhandled exceptions, HTTP 5xx errors, SQLAlchemy failures, Redis failures
- Attaches: environment, release version, request context
- 10% transaction sampling for performance tracing

### Frontend Integration

- `@sentry/react` initialized in both storefront and admin `__root.tsx`
- Captures: React error boundary catches, unhandled promise rejections, API failures
- Attaches: route, environment, browser context
- Session replay on errors (50% sample rate)

### First-Time Setup

1. Navigate to `errors.hadha.co`
2. Create admin account
3. Create a project (e.g., "Hadha Backend", "Hadha Storefront")
4. Copy the DSN to `.env.production`
5. Redeploy

## Uptime Monitoring

### First-Time Setup

1. Navigate to `uptime.hadha.co`
2. Create admin account
3. Add monitors:

| Monitor | URL | Interval |
|---------|-----|----------|
| Storefront | https://hadha.co | 60s |
| API Health | https://api.hadha.co/health | 60s |
| API Readiness | https://api.hadha.co/health/ready | 60s |
| Admin Panel | https://admin.hadha.co | 60s |
| Grafana | https://grafana.hadha.co/api/health | 300s |
| GlitchTip | https://errors.hadha.co/_health/ | 300s |
| Redis (TCP) | hadha-redis:6379 | 60s |

## Nginx Configuration

New server blocks added:

- `grafana.hadha.co.conf` — Proxies to Grafana:3000 with WebSocket support
- `uptime.hadha.co.conf` — Proxies to Uptime Kuma:3001 with SSE/WebSocket support
- `errors.hadha.co.conf` — Proxies to GlitchTip:8000 with 50MB upload limit
- `00-health.conf` — Added `/nginx_status` for Prometheus scraping (internal IPs only)

## Troubleshooting

### Prometheus not scraping targets

```bash
docker exec hadha-prometheus wget -qO- http://localhost:9090/api/v1/targets
```

### Prometheus rules not loading

```bash
docker exec hadha-prometheus wget -qO- http://localhost:9090/api/v1/rules
```

### Loki not receiving logs

```bash
docker exec hadha-promtail wget -qO- http://localhost:9080/ready
docker logs hadha-promtail --tail 50
```

### Grafana showing "No data"

1. Check Prometheus datasource: Settings → Data Sources → Prometheus → Test
2. Check Loki datasource: Settings → Data Sources → Loki → Test
3. Verify targets in Prometheus → Status → Targets
4. Check recording rules in Prometheus → Status → Rules

### GlitchTip not receiving events

1. Check DSN matches in backend `.env` and frontend `.env`
2. Verify GlitchTip is healthy: `docker logs hadha-glitchtip --tail 50`
3. Check `errors.hadha.co` for incoming events
