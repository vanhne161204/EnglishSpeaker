# EnglishTalker — Web Frontend

The marketing + demo website for EnglishTalker. Built with **TanStack Start**
(React 19, SSR) and **Tailwind CSS v4**, with shadcn/ui-style primitives.

It sits beside the other apps in the monorepo:

| Folder         | App                              |
| -------------- | -------------------------------- |
| `frontend-web` | This web app (TanStack Start)    |
| `frontend`     | Mobile app (React Native / Expo) |
| `backend`      | API (FastAPI)                    |

## Getting started

```bash
npm install
cp .env.example .env.local   # then edit VITE_API_BASE_URL if needed
npm run dev                  # http://localhost:8080 (falls back to 8081 if busy)
```

To run against a local backend, start it first (from `backend/`):

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

> Use `127.0.0.1`, not `localhost` — uvicorn binds the IPv4 loopback by default.

### Scripts

| Command           | Purpose                         |
| ----------------- | ------------------------------- |
| `npm run dev`     | Vite dev server (HMR)           |
| `npm run build`   | Production build (client + SSR) |
| `npm run preview` | Preview the production build    |
| `npm run lint`    | ESLint                          |

## Configuration

Environment is read from `.env.local` (gitignored). See `.env.example`.

| Variable            | Default                        | Description                          |
| ------------------- | ------------------------------ | ------------------------------------ |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api/v1` | Backend REST base (WS base derived). |

## Backend API integration

A typed client wraps the FastAPI backend under `src/lib/api/`:

- **`client.ts`** — `apiRequest<T>()` fetch wrapper. Resolves base URLs from env,
  serializes JSON + query params, and turns the backend error envelope
  (`{ "error": { code, message } }`) into a typed `ApiError` (`.status`, `.code`).
- **`types.ts`** — wire types mirroring `backend/app/schemas` (Topic, Room, User,
  Message, TranslateResult, AssistResult, Note, Subscription, …).
- **`index.ts`** — one function per endpoint, grouped by resource
  (`listTopics`, `listRooms`, `joinRoom`, `translate`, `assist`, `createUser`,
  `matchOne`, `roomSocketUrl`, `transcribe`, …).

```ts
import { listRooms, translate } from "@/lib/api";

const rooms = await listRooms({ mode: "normal" });
const { translated_text } = await translate({ text: "Good morning", target_lang: "vi" });
```

### Current state

The data-driven screens run on the **live backend** — there is no mock data:

- **Topics** (`/topics`, `/topics/$id`) — real topics + their documents (learning notes).
- **Rooms** (`/rooms`) — real open rooms with live filters (format/level/mode/topic).
- **Room** (`/rooms/$id`) — joins via `POST /rooms/{id}/join`, loads message history,
  and runs **live chat over the room WebSocket**; the in-room **translator** and **AI
  coach** call `/translate` and `/assist`.
- **Match** (`/match`) — `POST /match/one` · `/match/random`, then navigates to the room.

A browser identity (`user_id`) is created on first need via `POST /users` and kept in
`localStorage` (`src/lib/identity.ts`). Cosmetic-only mappings (topic emoji, level
labels) live in `src/lib/presentation.ts`. The marketing pages (Home, Features,
Pricing, etc.) remain static copy.

Not yet wired (no backend endpoint / out of scope): in-browser voice (WebRTC is
mobile-only for now), room creation from the web (rooms are born from matching),
and Speech-to-Text capture UI.

This project is connected to [Lovable](https://lovable.dev) — see `AGENTS.md`.
Avoid rewriting published git history so the Lovable sync stays intact.

<!-- deploy check: verifying Cloudflare is connected to vanhne161204/EnglishSpeaker (2026-08-10) -->
