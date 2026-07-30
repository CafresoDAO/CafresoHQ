# CafresoHQ search-network worker (standalone)

A minimal, stdlib-only Python service that joins the CafresoHQ decentralized
search network: it polls the `cafresohq_state` Internet Computer canister for
queued search jobs, answers them via Brave Search + an LLM, and writes
results back over HMAC-signed HTTPS. It also runs the network's self-curation
crons (gap-filling, breaking news, topic clustering) when enabled.

## Relationship to `serve.py`

This is the same worker code that used to run inside `serve.py` (the full
CafresoHQ "HQ" agentic-workspace monolith) behind `SEARCH_WORKER=1`. It has
been extracted into its own file and image so that:

- A search worker can run independently of the HQ product (no terminal/PTY,
  no Hermes gateway, no vault, no UI) — smaller image, smaller trust/audit
  surface for anyone running someone else's code with their own Brave key.
- Fixing or updating the search path no longer requires rebuilding and
  restarting the entire HQ monolith.
- The worker can run somewhere more reliable than a single always-on
  developer machine.

See `worker.py`'s module docstring for exactly what changed in the
extraction (model/backend resolution, dropped Hermes-gateway fallback, the
status endpoint) versus what ported over unchanged.

`serve.py`'s own `SEARCH_WORKER=1` code path still exists and still works —
this is an additive extraction, not a replacement, until a validated cutover
retires the in-monolith path (see the extraction plan this came from).

## Running it

```
docker build -t cafreso-search-worker:local -f search_worker_service/Dockerfile .
docker run -d --name cafreso-search-worker \
  --env-file worker.env \
  -p 8788:8788 \
  -v cafreso-search-worker-data:/data \
  cafreso-search-worker:local
```

Or via `docker-compose.worker.yml` at the repo root:

```
docker compose -f docker-compose.worker.yml up -d --build
```

Required env (in `worker.env`, gitignored — same file convention as
`docker-compose.local.yml`):

```
SEARCH_WORKER=1
WORKER_PRINCIPAL=<principal registered via ai.cafreso.com settings>
WORKER_SECRET=<64-hex secret shown once at registration>
BRAVE_API_KEY=<your Brave key>
```

Optional model config — see `worker.py`'s module docstring for the full
precedence rules (local env always wins over the operator's published
default):

```
WORKER_MODEL=<model name>
WORKER_BACKEND_URL=<OpenAI-compatible endpoint>
WORKER_BACKEND_KEY=<its API key — never published anywhere, local only>
```

Crons (only ONE instance across your whole deployment should have these on
at a time — see the operational-rule note in `worker.py`'s module docstring):

```
GAP_CRON=1      # default on
NEWS_CRON=1     # default off
TOPICS_CRON=1   # default on
```

## Status endpoint

`GET :8788/health`, `:8788/gap/status`, `:8788/news/status` — same JSON
shape as the routes that used to live on serve.py's main HTTP handler.
