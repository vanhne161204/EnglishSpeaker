# EnglishTalker

A mobile app for practicing spoken English — find a partner, talk on a topic, get
real-time AI help, and save useful sentences. See [`docs/`](./docs) for the full
product and engineering documentation (PRD, architecture, database, etc.).

## Repository layout

```
EnglishTalker/
├── backend/    FastAPI service (Python) — REST API, async SQLAlchemy, Alembic
├── frontend/   React Native app (Expo + TypeScript) — iOS + Android
└── docs/       Product & engineering documentation
```

## Tech stack

| Area | Choice |
|------|--------|
| Mobile app | React Native + TypeScript (Expo) |
| Backend | FastAPI (async Python) |
| Database | PostgreSQL + pgvector (SQLite for the zero-setup demo) |
| Cache / queues / realtime fan-out | Redis |
| AI | Claude API (task-routed models) |

See [`docs/06_Architecture.md`](./docs/06_Architecture.md) and
[`docs/07_Database.md`](./docs/07_Database.md) for the design.

## Run the demo (2 terminals)

**1. Backend** (runs on SQLite, no infra needed):

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows (use source .venv/bin/activate on macOS/Linux)
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
# API docs at http://localhost:8000/docs
```

**2. Frontend:**

```bash
cd frontend
npm install
npm start
# press i / a, or scan the QR code with Expo Go
```

The app loads the seeded topic list from the backend — your end-to-end demo.

## Going beyond the demo

- Swap SQLite for Postgres + pgvector + Redis: `cd backend && docker compose up --build`.
- Use migrations instead of auto-create: set `AUTO_CREATE_TABLES=false`, run `alembic upgrade head`.
- Build out the remaining domains (auth, rooms, matching, sessions, notes, AI, subscriptions)
  following the same `route → service → repository → model` layering and the schema in `docs/07_Database.md`.
