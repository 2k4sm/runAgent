# runAgent — Backend

Multi-agent chatbot platform for SMEs. FastAPI + LiteLLM + Supabase (Postgres + Storage).

## Setup

```bash
uv sync --extra dev
cp .env.example .env   # fill in real values
```

Run the database migrations in `supabase/migrations/` (in order) via the
Supabase SQL editor or `supabase db push`.

## Run

```bash
uv run uvicorn run_agent.main:app --reload
```

Health check: `GET http://localhost:8000/api/v1/health`

## Quality

```bash
uv run ruff check src/
uv run ty check
```

## Deploy

The repo ships a `Dockerfile` and `docker-compose.yml`.

Local / any Docker host:

```bash
docker compose up --build   # serves on :8000, reads .env
```

Dokploy:

1. Create a **Compose** application pointing at this repository.
2. Set the environment variables (see `.env.example`) in the Dokploy UI.
3. Attach a domain to the `backend` service on port `8000`.

Run the migrations in `supabase/migrations/` once against your Supabase
project before the first deploy.
