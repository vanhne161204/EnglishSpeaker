<!-- Purpose: Documents API contracts, endpoints, request and response schemas, authentication, authorization, errors, and versioning. -->

# 08 API

## Overview

The backend is a FastAPI service. All REST endpoints are versioned under a common
prefix and return JSON. Interactive docs are served at `/docs` (Swagger UI) and the
OpenAPI schema at `/api/v1/openapi.json`.

- **Base URL (REST):** `http://<host>:8000/api/v1`
- **Base URL (WebSocket):** `ws://<host>:8000/api/v1`
- **Content type:** `application/json`
- **Auth:** none yet. Identity is a lightweight profile (`user_id`) created via
  `POST /users` and passed by the client. A full auth slice (JWT) can layer on later.

### Error format

Handled domain errors return a consistent envelope:

```json
{ "error": { "code": "not_found", "message": "Room not found" } }
```

| Status | When |
| ------ | ---- |
| 422 | Request body/query fails validation |
| 404 | `not_found` — room or user does not exist |
| 409 | `conflict` — e.g. `room_full` when joining a room at capacity |

## System

### `GET /health`
Liveness probe. Returns `{ "status": "ok", "service": ..., "environment": ... }`.

## Categories

Themes that group topics (PRD §8.1). Reads are open; writes require an admin.

### `GET /categories`
List categories, ordered by `sort_order` then `name`.

### `POST /categories`
Create a category (admin). → `201`. `409` if the slug already exists.

```json
{ "slug": "daily-life", "name": "Daily Life", "description": "…", "icon_url": null, "sort_order": 0 }
```

### `GET /categories/{id}` · `PATCH /categories/{id}` · `DELETE /categories/{id}`
Get, edit (partial: `name`/`description`/`icon_url`/`sort_order`), or delete a
category (admin). Deleting one keeps its topics — their `category_id` is cleared,
so they fall back to the UI's "Other" group. `DELETE` → `204`.

## Topics

### `GET /topics?category_id=`
List conversation topics, ordered by `sort_order` then `title`. Pass `category_id`
to list one category's topics.

### `POST /topics`
Create a topic (admin). `409` if the slug already exists; `404` if `category_id`
is unknown.

```json
{ "slug": "travel", "title": "Travel", "level": "intermediate", "category_id": "…", "cover_image_url": null, "sort_order": 0 }
```

### `GET /topics/{id}` · `PATCH /topics/{id}` · `DELETE /topics/{id}`
Get, edit (partial: `title`/`description`/`level`/`status`/`category_id`/
`cover_image_url`/`sort_order`), or delete a topic (admin). Deleting a topic
deletes its documentation too. `PATCH`/`DELETE` return `404` if unknown;
`DELETE` → `204`.

### `GET /topics/{id}/doc`
The topic's documentation with its **full tree** — sections, items, questions, and
answer templates in one response. `404` if the topic is unknown *or* has no doc
yet (which is a normal state, not an error).

## Docs (Documentation Content)

A topic's learning page (PRD §8.2). One topic has at most one doc. A doc is an
ordered list of sections, and a section's `type` decides where its content lives:

| `type` | Holds | Field |
|---|---|---|
| `vocabulary` · `phrases` | words and phrases | `items` |
| `questions` | conversation questions | `questions` |
| `tips` · `text` | free-form prose | `body` |

Reads return the whole tree; writes are per-node. Reads are open; writes require
an admin. In every path below the fixed segment comes **before** the id, so
`/docs/sections/{id}` never collides with `/docs/{doc_id}`.

### `GET /docs?topic_id=`
List doc summaries (no tree), optionally filtered to one topic.

### `POST /docs`
Start a topic's documentation (admin). → `201`. `404` if the topic is unknown;
`409` if it already has a doc.

```json
{ "topic_id": "…", "title": "Travel", "intro": "Read this before you speak.", "level": null, "status": "draft" }
```

`status` ∈ `draft` · `published` · `archived`. Only `published` docs feed
`GET /questions`.

### `GET /docs/{id}`
Fetch one doc with its full tree. `404` if unknown.

### `PATCH /docs/{id}` · `DELETE /docs/{id}`
Edit (partial: `title`/`intro`/`level`/`status`) or delete a doc (admin).
Deleting cascades to every section, item, question, and answer template.
`DELETE` → `204`.

### `POST /docs/{doc_id}/sections`
Add a section (admin). → `201`.

```json
{ "type": "vocabulary", "title": "Useful travel words", "body": null, "sort_order": 0 }
```

### `PATCH /docs/sections/{id}` · `DELETE /docs/sections/{id}`
Edit (partial: `title`/`body`/`sort_order`) or delete a section (admin). `type` is
**not** editable — changing it would orphan the section's children, so delete and
recreate instead. `DELETE` → `204`.

### `POST /docs/sections/{section_id}/items`
Add a word or phrase (admin). → `201`. `400` (`bad_request`) if the section is not
a `vocabulary` or `phrases` section.

```json
{ "term": "layover", "phonetic": "/ˈleɪoʊvər/", "meaning": "a wait between two flights", "translation": null, "example": "We have a two-hour layover.", "audio_url": null, "sort_order": 0 }
```

### `PATCH /docs/items/{id}` · `DELETE /docs/items/{id}`
Edit or delete an item (admin). `DELETE` → `204`.

## Questions and answer templates

Questions live in a doc's `questions` section, but get their own resource because
Warm-up Practice (PRD §8.12) reads them flat, across many topics, without walking
each doc tree.

### `GET /questions?topic_id=`
Questions from **published** docs, each flattened with its `topic_id` and
`topic_title`, and carrying its `answer_templates`. Ordered by topic, then by the
admin's section and question order. Draft and archived docs are skipped.

### `POST /questions`
Add a question (admin). → `201`. `400` (`bad_request`) if `section_id` is not a
`questions` section.

```json
{ "section_id": "…", "text": "What is your favourite food?", "translation": null, "audio_url": null, "sort_order": 0 }
```

### `PATCH /questions/{id}` · `DELETE /questions/{id}`
Edit (partial: `text`/`translation`/`audio_url`/`sort_order`) or delete a question
(admin). Deleting takes its answer templates with it. `DELETE` → `204`.

### `POST /questions/{question_id}/answers`
Add a fill-in-the-blank answer template (admin). → `201`. `404` if the question is
unknown.

```json
{ "template": "My favourite food is ___.", "example": "My favourite food is pizza.", "translation": null, "audio_url": null, "sort_order": 0 }
```

### `PATCH /questions/answers/{id}` · `DELETE /questions/answers/{id}`
Edit or delete an answer template (admin). `DELETE` → `204`.

## Users (lightweight profiles)

A profile is a display name plus learning preferences. No password.

### `POST /users`
Create a profile. → `201`

```json
// request
{ "display_name": "Maya", "level": "intermediate", "interests": "travel,music" }
```

`display_name` is required (1–80 chars). Returns the created `User` (with `id`).

### `GET /users/{user_id}`
Fetch a profile (includes `plan`). `404` if unknown.

### `GET /users/{user_id}/subscription`
The user's plan and limits (PRD §8.11).

```json
{ "plan": "free", "limits": { "ai_suggestions_per_day": 10, "max_saved_notes": 50, "max_topics": 5 } }
```

### `PUT /users/{user_id}/subscription`
Upgrade or cancel — set `{ "plan": "free" | "premium" }`. Premium limits are `null`
(unlimited). Limit *enforcement* (usage counting) is a planned follow-up.

## Rooms

A room hosts a conversation. A **1-on-1 is just a room with `kind = "one_on_one"`
and `capacity = 2`** — group and 1-on-1 share one model (see PRD §8.3).

### `GET /rooms?mode=&kind=`
List open rooms. Optional filters: `mode` (`normal` | `incognito`),
`kind` (`group` | `one_on_one`).

### `GET /rooms/{room_id}`
Fetch a single room. `404` if unknown.

### `POST /rooms/{room_id}/join`
Join a room. Idempotent (re-joining does not double-count). `409 room_full` when at
capacity; `404` if the room or user is unknown. Returns the updated `Room`.

```json
// request — display_name overrides the shown name (used for incognito aliases)
{ "user_id": "…", "display_name": "Anon-4f2a" }
```

If `display_name` is omitted, the user's profile name is used.

### `POST /rooms/{room_id}/leave`
Leave a room (frees the seat). Returns the updated `Room`.

```json
{ "user_id": "…" }
```

### `GET /rooms/{room_id}/messages`
Message history for a room, oldest-first (most recent 100).

### `POST /rooms/{room_id}/messages`
Send a message over REST (a fallback; live chat uses the WebSocket). → `201`. The
stored `sender_name` is the user's in-room alias when present, otherwise their
profile name — so incognito rooms never leak the real name.

```json
{ "user_id": "…", "text": "Hello there!" }
```

## Matching

A match resolves to a room to join, so both endpoints return a `Room`. Strategy is
synchronous "find-or-create": return a suitable open room, or create one to wait in.

### `POST /match/one`
Find (or create) a 1-on-1 room in the same mode, preferring the requested topic.

```json
{ "mode": "normal", "topic": "Travel", "level": "intermediate" }
```

### `POST /match/random`
Find (or create) any open room in the same mode.

```json
{ "mode": "incognito" }
```

## Translation

### `POST /translate`
Translate a short phrase (in-room translator). The default engine is **Google
Translate** (best Vietnamese quality, no LLM). With no key it uses Google's free
public endpoint; set `GOOGLE_TRANSLATE_API_KEY` to use the official Cloud
Translation API (reliable, no rate limits). Any failure degrades to a
clearly-labelled demo stub (`provider: "stub"`), never an error.

```json
{ "text": "Good morning", "source_lang": "en", "target_lang": "vi" }
// → { "translated_text": "Chào buổi sáng", "target_lang": "vi", "provider": "google" }
```

`source_lang` is optional for Google (it auto-detects). The engine is configurable
via `TRANSLATION_PROVIDER`:

- `google` (default) — Google Translate; best Vietnamese quality.
- `argos` — offline open-source neural MT, no network at translate time (weaker quality).
- `claude` — Claude API (needs `ANTHROPIC_API_KEY`); most natural.
- `stub` — labelled demo echo.
- `auto` — try google → argos → claude → stub.

## AI Conversation Help

### `POST /assist`
In-room AI coach (PRD §8.8). Claude-powered when `ANTHROPIC_API_KEY` is set,
otherwise a clearly-labelled demo stub (`provider: "stub"`).

```json
// improve a sentence the user is about to send
{ "kind": "improve", "text": "i very like travel" }

// suggest a reply, given the last thing the other person said
{ "kind": "reply", "context": "What did you do this weekend?" }
```

`kind` is `improve` (requires `text`; `422` if blank) or `reply` (uses `context`).
Pass an optional `topic_id` to **ground** the suggestion in that topic's
documentation — each section is flattened into a short prompt line (RAG, §8.2/§8.8). Returns `{ "suggestion": "...", "kind": "...", "provider": "claude" | "stub" }`.

## Speech-to-Text

### `POST /transcribe`
Transcribe recorded audio to text (PRD §8.9). Multipart upload: `audio` (file) and
optional `language`. Powered by offline **faster-whisper** (open-source, no LLM)
when installed; otherwise a labelled stub. Returns
`{ "text": "...", "language": "en", "provider": "whisper" | "stub" }`.

## Sentence Notes

### `GET /notes` / `POST /notes`
List and save sentence notes (PRD §8.7). The chat screen saves here when a user
keeps an AI suggestion or long-presses a message.

### `PATCH /notes/{id}` · `DELETE /notes/{id}`
Edit (partial) or delete a note. `404` if unknown; `DELETE` → `204`.

## Realtime — WebSocket

### `WS /ws/rooms/{room_id}?user_id=&name=`
Live conversation channel for a room. The client should `POST /rooms/{id}/join`
first (so an in-room alias exists), then open this socket.

**Client → server** frames:

```json
{ "text": "Hello everyone" }
```

**Server → client** frames:

```json
{ "type": "message", "message": { "id": "…", "sender_name": "Maya", "text": "Hi", "created_at": "…" } }
{ "type": "presence", "event": "join", "name": "Maya" }
{ "type": "presence", "event": "leave", "name": "Maya" }
{ "type": "error", "message": "Could not send message" }
```

Each inbound message is persisted (same path as the REST send) and broadcast to all
sockets in the room. Fan-out is in-memory (single process); Redis pub/sub is the
documented scale-out path (see docs/06_Architecture.md).

### `WS /ws/voice/{room_id}?user_id=&name=`
WebRTC **voice call** signaling for a room. The server relays signaling only —
audio flows peer-to-peer in a **mesh** (no media touches the server). Requires a
custom dev build on the client (native `react-native-webrtc`; not Expo Go).

On connect the server sends the newcomer the peers already present and notifies the
others. Peers then exchange SDP/ICE through targeted relay frames.

**Server → client:**

```json
{ "type": "peers", "peers": [{ "id": "...", "name": "Maya" }] }   // you: offer to each
{ "type": "peer-joined", "peer": { "id": "...", "name": "Leo" } }  // wait for their offer
{ "type": "peer-left", "peer": { "id": "..." } }
{ "type": "offer" | "answer" | "ice-candidate", "from": "<peerId>", "data": { ... } }
```

**Client → server** (always targeted at one peer):

```json
{ "type": "offer" | "answer" | "ice-candidate", "to": "<peerId>", "data": { ... } }
```

ICE uses public STUN by default; configure a TURN server (app.json `extra`) for
restrictive networks. A full mesh suits 1-on-1 and small rooms; an SFU is the path
for large rooms.
