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
