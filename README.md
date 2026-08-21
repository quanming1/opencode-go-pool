# OpenCode Go Pool

A proxy service that merges multiple OpenCode Go subscription accounts into a single logical upstream, with a visual monitoring dashboard.

[中文说明](README.zh-CN.md)

## Why

A single OpenCode Go account is limited by a 5-hour rolling call window. When one account is not enough, merge several subscriptions into a pool: when an account hits its quota (429 / rate-limited) it is automatically cooled down and the next healthy account takes over, while clients only see one unified API endpoint. A web dashboard shows account status, usage trends, quota status and the unified event timeline in real time.

## Features

- **Account pool with state machine** — `healthy` / `cooldown` / `disabled`; automatic cooldown on quota/auth failures, auto-disable after consecutive failures, lazy + scheduled recovery.
- **Transparent forwarding** — pass-through of both `OpenAI Responses` and `Chat Completions` protocols, non-streaming JSON and streaming SSE.
- **Failover rotation** — on quota / network / server errors, mark down the failed account and retry the next healthy one; every request returns an `X-Pool-Account` header.
- **SQLite persistence** — account states and usage statistics survive restarts (WAL mode).
- **Gateway API keys** — optional bearer-auth for the forwarding and management endpoints (off by default for local single-user setups).
- **Quota display** — real per-account rolling/weekly/monthly usage from the official OpenCode Go `/usage` endpoint, with server-side TTL cache and per-account degradation.
- **Monitoring dashboard** — account status cards, usage & rotation trend charts (ECharts), quota overview, and a unified event timeline (requests / cooldown / switches / key failures / gateway key lifecycle).
- **One-click startup** — `python start.py` kills stale processes on ports 48700/48701 (including orphaned uvicorn `--reload` workers) and quietly starts backend + frontend with health checks.
- **Automatic CI/CD packaging** — every push/PR builds the backend wheel and the frontend `dist`, assembles a complete release package, verifies it (fresh-venv install + asset integrity), and uploads it as a downloadable artifact; `v*` tags publish it to the GitHub Release automatically.
- **i18n + theming with color tokens** — built-in zh/en switching and light/dark themes; every color is a CSS variable mirrored by `src/theme/tokens.ts` (a single source for ECharts and other JS consumers; consistency between the CSS variables and the TS tokens is enforced by a unit test).

## Architecture

```
Clients (ftre / any OpenAI Responses or Chat Completions caller)
        ↓  OpenAI-friendly protocol (Responses / Chat Completions)
  OpenCode Go Pool proxy (FastAPI :48700)
   ├─ Account pool (state machine: healthy / cooldown / disabled)
   ├─ Transparent forwarding (JSON / streaming SSE)
   ├─ Failover rotation (quota → cooldown & switch; repeated failures → auto-disable)
   ├─ SQLite persistence (survives restarts)
        ↓  dispatch by account API key
   OpenCode Go accounts A / B / C ...
        ↑
  Web dashboard (React + ECharts :48701)
```

## Quick Start

### One-click startup (recommended)

After the first-time manual install steps below (backend `.venv` + frontend `pnpm install`), day-to-day development is just:

```bash
python start.py
```

It kills stale processes on ports 48700/48701 (including orphaned uvicorn `--reload` children), silently starts backend + frontend, then runs health checks. Logs go to `logs/backend.log` and `logs/web.log` (git-ignored). Running it again restarts the services.

### 1. Backend (Python 3.12)

```bash
cd apps/backend
python -m venv .venv
.venv\Scripts\activate          # Windows (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"

# Configure accounts (keys are referenced via env vars, never committed)
copy config\accounts.example.yaml config\accounts.yaml   # Windows
set OPENCODE_GO_KEY_1=sk-xxxx   # matches ${OPENCODE_GO_KEY_1} in accounts.yaml

.venv\Scripts\python -m uvicorn opencode_pool.app:app --host 127.0.0.1 --port 48700
```

### 2. Frontend (Node 24 + pnpm 11)

```bash
cd apps/web
pnpm install
pnpm dev          # http://localhost:48701
```

### 3. Verify

```bash
curl http://127.0.0.1:48700/health
curl http://127.0.0.1:48700/api/accounts
```

Open http://localhost:48701 in a browser to view the account status dashboard, usage trends and the unified event timeline.

A detailed manual is available at [docs/usage.md](docs/usage.md) (Chinese).

## API Summary

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check (returns status + version) |
| `/api/accounts` | GET | Pool accounts overview with masked keys |
| `/api/stats?hours=24` | GET | Usage aggregation (hourly buckets + per-account totals) |
| `/api/quota?refresh=0\|1` | GET | Per-account rolling/weekly/monthly quota + pool summary (server-side TTL cache) |
| `/api/events?limit=100&type=request,key_switch` | GET | Unified event log (`type`/`data`/`meta`/`time`; comma-separated type filter) |
| `/api/keys` | GET/POST | List / create gateway API keys (plaintext shown once) |
| `/api/v1/responses` | POST | OpenAI Responses transparent forwarding (streaming SSE supported) |
| `/api/v1/chat/completions` | POST | OpenAI Chat Completions transparent forwarding (streaming SSE supported) |
| `/api/v1/models` | GET | Merged model list of the account pool |
| `/v1/*` | - | Standard OpenAI SDK path aliases for the forwarding endpoints above |

Forwarding example:

```bash
curl http://127.0.0.1:48700/api/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.6-luna","input":"hi","stream":false}'
```

## Configuration (.env / environment variables)

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | opencode-go-pool | Application name |
| `LOG_LEVEL` | INFO | Log level |
| `HOST` | 127.0.0.1 | Listen address |
| `PORT` | 48700 | Listen port |
| `UPSTREAM_BASE_URL` | https://api.opencode.ai/v1 | Default upstream (overridable per account) |
| `UPSTREAM_TIMEOUT` | 60 | Upstream request timeout (seconds) |
| `POOL_SCAN_INTERVAL_SECONDS` | 60 | Cooldown scan interval (seconds) |
| `MAX_CONSECUTIVE_FAILURES` | 3 | Consecutive failures before auto-disable |
| `DB_PATH` | data/opencode_pool.db | SQLite database path |
| `QUOTA_CACHE_TTL_SECONDS` | 60 | Quota query cache TTL (seconds) |
| `QUOTA_TIMEOUT_SECONDS` | 10 | Per-account quota query timeout (seconds) |
| `FAST_MODE` | false | Performance-first mode: successful requests are aggregated in memory only (bounded, 168h window) and never written to SQLite — no per-request usage rows or request events. Failures / key switches / cooldown / disable events are still persisted. Per-request success history is not retained across restarts. `/api/stats` returns `mode: "fast"` and the dashboard shows a FAST badge. |

Account configuration: `apps/backend/config/accounts.example.yaml` — `api_key` references environment variables via `${ENV_VAR}` (e.g. `${OPENCODE_GO_KEY_1}`). Secrets live only in your local `.env` / environment, never in the repository.

Optional gateway authentication: in `.env.keys` (git-ignored), set `GATEWAY_AUTH=on` to enable bearer validation and `GATEWAY_MASTER_KEY` to register a master key. Gateway keys are stored hashed (SHA-256) in the database; the plaintext is shown only once at creation.

## Directory Layout

```
opencode-go-pool/
├─ apps/
│  ├─ backend/     FastAPI proxy core (accounts / proxy / usage / quota / store / scheduler)
│  └─ web/         React + Vite + ECharts dashboard (status / quota / usage / events)
├─ docs/           TODO.yaml / PROCESS.md / prd/ / usage.md / security-audit.md
└─ start.py        One-click startup script (Windows)
```

## Development Workflow (Rondo Method)

- Behavior rules: `AGENTS.md`
- Task list: `docs/TODO.yaml` (single source of truth)
- Process: `docs/PROCESS.md` (six-step loop)
- Per-stage PRD: `docs/prd/`
- CI/CD: on every push/PR — backend (`pytest` + `ruff` + build the wheel) and web (`eslint` + `vitest` + `build`); then a `pack` job assembles and verifies a complete release package and uploads it as an artifact (see [CI/CD Packaging](#cicd-packaging))
- Branching: Git Flow with a full pull-request flow (main/develop never receive direct commits; feature branches are merged via PR with mandatory stage-ID scoped commit messages)

## CI/CD Packaging

Every push/PR runs three jobs (`.github/workflows/ci.yml`):

1. **backend** — lint, test, and `python -m build` produce the `opencode_pool` wheel (uploaded as the `backend-dist` artifact);
2. **web** — lint, test, and build `dist/` (uploaded as the `web-dist` artifact);
3. **pack** — downloads both artifacts and runs `scripts/package_release.py` (pure standard library, also runnable locally) to assemble `opencode-go-pool-<version>.zip` (back-end wheel + frontend `dist` + `start.py` + docs + sample configs). The script verifies the package: the wheel installs in a fresh `venv` and imports with the matching version, and every asset referenced by `dist/index.html` exists inside the package. The resulting zip is uploaded as the `release-package` artifact.

Pushing a `v*` tag additionally uploads the package to the GitHub Release of the same tag (auto-created if missing), so every release ships a ready-to-use archive.

## Compliance Boundary

This project only supports legitimate access with official API keys and failure failover. It does not implement cookie scraping, session reuse, credential forging, or reselling quotas. Whether aggregating multiple subscriptions behind an internal gateway complies with OpenCode's terms is up to the official answer from OpenCode.

## License

[MIT](LICENSE)
