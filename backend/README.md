# EnglishTalker — Backend (FastAPI)

Async FastAPI service following a layered architecture:

```
app/
  api/            HTTP layer (versioned routers + dependencies)
    v1/routes/    endpoint modules (health, topics, ...)
  services/       business logic
  repositories/   data access (SQLAlchemy queries)
  models/         ORM models (+ reusable mixins)
  schemas/        Pydantic request/response contracts
  core/           config, logging, exception handling
  db/             engine, session, declarative base
  seeds/          demo data
alembic/          database migrations
tests/            pytest suite
```

Request flow: **route → service → repository → model**. Schemas isolate the API
contract from the ORM; the service layer keeps business rules out of HTTP code.

## Quick start (zero infrastructure)

Defaults to SQLite, so it runs with nothing else installed.

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
# source .venv/bin/activate                         # macOS/Linux
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Topics (seeded): http://localhost:8000/api/v1/topics

## Full stack (Postgres + pgvector + Redis)

```bash
cd backend
docker compose up --build
```

## Migrations (production path)

```bash
alembic upgrade head                       # apply
alembic revision --autogenerate -m "msg"   # create
```

> `AUTO_CREATE_TABLES=true` bootstraps tables + demo data in development only.
> In staging/production set it `false` and rely on Alembic.

## Tests & quality

```bash
pytest           # tests
ruff check .     # lint
mypy app         # type-check
```

## Configuration

All settings come from environment variables — see `.env.example`.
