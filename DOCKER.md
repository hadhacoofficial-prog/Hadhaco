# Docker Development Environment

Full-stack Docker setup for the Hadha.co project.

## Services

| Service         | URL                        | Description                             |
|-----------------|----------------------------|-----------------------------------------|
| backend         | http://localhost:8000      | FastAPI (uvicorn --reload)              |
| frontend        | http://localhost:8080      | React + TanStack Start (Vite / Nitro)   |
| hadha-redis     | localhost:6379             | Redis 7 (AOF persistence)               |
| redis-commander | http://localhost:8082      | Browser-based Redis key browser         |
| dozzle          | http://localhost:8081      | Real-time container log viewer          |

## Prerequisites

- Docker Desktop (with Compose v2)
- `Backend/.env` populated from `Backend/.env.example`
- `Frontend/.env` populated from `Frontend/.env.example`

## Quick start

```bash
# First run — builds images and starts all services
docker compose up --build

# Subsequent runs
docker compose up

# Background mode
docker compose up --build -d
```

## Per-service commands

```bash
# Rebuild a single service after dependency changes
docker compose build backend
docker compose build frontend

# Tail logs for one service
docker compose logs -f backend
docker compose logs -f frontend

# Open a shell in the backend container
docker compose exec backend bash

# Run Alembic migrations
docker compose exec backend alembic upgrade head

# Run pytest
docker compose exec backend pytest
```

## Redis

The `hadha-redis` service uses `redis:7-alpine` with AOF persistence (`--appendonly yes`)
and a 256 MB memory cap. Data survives container restarts via the `redis_data` named volume.

```bash
# Open a Redis CLI session
docker compose exec hadha-redis redis-cli

# Ping Redis from the backend container (verifies service-name DNS)
docker compose exec backend python -c \
  "import asyncio, redis.asyncio as r; asyncio.run(r.from_url('redis://hadha-redis:6379/0').ping())"

# Flush the cache (dev only)
docker compose exec hadha-redis redis-cli FLUSHALL

# Inspect memory usage
docker compose exec hadha-redis redis-cli INFO memory
```

## Redis Commander

Open http://localhost:8082 to browse and manage Redis keys in the browser.
It connects automatically to `hadha-redis` with no extra configuration.

Capabilities:
- Browse and search all keys
- Inspect, edit, and delete values
- Monitor TTLs and memory usage
- Verify cache invalidation during development

## View container logs (Dozzle)

Open http://localhost:8081 — Dozzle auto-discovers all running containers and
streams their stdout/stderr in real time. No extra configuration needed.

## Hot reload

| Service  | Trigger                       | Mechanism                              |
|----------|-------------------------------|----------------------------------------|
| backend  | Edit any `.py` file           | Uvicorn `--reload` watches `/app`      |
| frontend | Edit any `src/` file          | Vite HMR over WebSocket                |

Both rely on the bind-mount volumes defined in `docker-compose.yml`.

## Environment variables

### Backend (`Backend/.env`)

The Docker Compose file overrides these variables automatically:

```
REDIS_URL=redis://hadha-redis:6379/0     # Docker service name, not localhost
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:5173,http://frontend:8080
ALLOWED_HOSTS=localhost,127.0.0.1,backend
```

Everything else is loaded from `Backend/.env`. No changes needed for Docker dev.

### Frontend (`Frontend/.env`)

`VITE_API_BASE_URL` stays at `http://localhost:8000/api/v1` — this URL is
embedded in the client-side bundle and must be reachable from the **browser**,
which accesses the backend via the host-mapped port 8000.

## Frontend port — why 8080?

`@lovable.dev/vite-tanstack-config` starts the Nitro SSR dev server on port **8080**
(visible in the Vite startup log: `Local: http://localhost:8080/`). This is the
authoritative source — the compose port mapping, Dockerfile EXPOSE, and CORS
allowed origins all align on 8080.

## Database connectivity — IPv4 preference fix

The backend Dockerfile appends one line to `/etc/gai.conf`:

```
precedence ::ffff:0:0/96  100
```

**Why this is needed:**
Python's `socket.getaddrinfo()` uses glibc, which sorts results according to
RFC 6724 address-selection rules. By default, IPv6 (AAAA) addresses are ranked
*above* IPv4 (A) addresses. asyncpg iterates results in that order, tries IPv6
first, and fails with `OSError: [Errno 99] Cannot assign requested address`
(`EADDRNOTAVAIL`) because Docker's bridge network on WSL2/Windows has no local
IPv6 address to use as the connection source. The IPv4 fallback may not be
reached if the DNS response shape causes all addresses to be IPv6.

Setting `precedence ::ffff:0:0/96 100` promotes the IPv4-mapped address range
to priority 100 (vs. the default 10), so `getaddrinfo()` returns IPv4 addresses
first. asyncpg connects on its first try without touching IPv6.

The compose file also carries `sysctls: {net.ipv6.conf.all.disable_ipv6: "1"}`
as a belt-and-suspenders guard: if any code path somehow still reaches an IPv6
address, the kernel refuses the socket immediately rather than hanging on a
connection timeout.

## node_modules isolation

The frontend service uses a named Docker volume (`frontend_node_modules`) for
`node_modules`. This prevents Windows/Linux filesystem ABI mismatches and keeps
the container's installed packages separate from any local `node_modules`.

If `package.json` changes, rebuild to refresh the volume:

```bash
docker compose build frontend
docker volume rm hadha_frontend_node_modules
docker compose up frontend
```

## Startup order

```
hadha-redis (healthy)
    └── backend (healthy)
            └── frontend
redis-commander (after hadha-redis healthy)
dozzle (no dependency)
```

## Stopping and cleaning up

```bash
# Stop without removing volumes
docker compose down

# Stop and remove all volumes (wipes Redis data and node_modules cache)
docker compose down -v
```

## Validation checklist

After `docker compose up --build`:

- [ ] `http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] `http://localhost:8080` loads the frontend
- [ ] `http://localhost:8082` opens Redis Commander
- [ ] `http://localhost:8081` opens Dozzle with all container logs
- [ ] `docker compose exec hadha-redis redis-cli ping` → `PONG`
- [ ] Backend logs show `Connected to Supabase` (no ENETUNREACH)
- [ ] Backend logs show Redis connected (no connection errors)
- [ ] Editing a `.py` file triggers uvicorn reload in backend logs
- [ ] Editing a `src/` file triggers HMR in browser console

## Production

Production deployment uses the existing `Backend/docker/docker-compose.yml`
(with nginx reverse proxy) and a Vercel deployment for the frontend.
The `Dockerfile` and `docker-compose.yml` at the project root are for
**development only**.
