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

### `GET /topics/{id}/questions` · `PUT /topics/{id}/questions`

**The simple way to author questions.** Writing one question through the doc tree
takes four calls (create doc → add `questions` section → add question → add answer
template). Admins think in plain question/answer pairs, so these two endpoints do
the same job in one call. Same storage underneath — just a flatter door.

`GET` returns the topic's questions as flat pairs. Unlike `GET /questions` it
**includes a draft doc**, so the admin editor loads what is really stored rather
than silently overwriting it on the next save. A topic with no doc returns `[]`,
not `404`.

```json
[{ "id": "…", "text": "What is your favourite food?", "answer": "My favourite food is pizza.", "sort_order": 0 }]
```

`PUT` replaces the whole list (admin). It creates the doc and the `questions`
section if they don't exist, and sets the doc to `published` — saving questions is
the admin saying they're ready, so they reach learners immediately. Questions
missing from the body are deleted, along with their answer templates. Other
sections (vocabulary, tips) are left untouched. `404` if the topic is unknown.

```json
{ "items": [{ "text": "What is your favourite food?", "answer": "My favourite food is pizza." }] }
```

`answer` is optional — a blank one saves the question with no answer template.
Max 50 items. Blank `text` is rejected with `422`.

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

## AI Voice Coach (Warm-up)

Voice-to-voice practice with Gemini Live (PRD §8.12). All three endpoints need
sign-in. The browser opens the Gemini session itself; the server only issues the
token, keeps the daily allowance, and closes the books.

### `GET /voice-coach/usage`
Today's allowance. `enabled: false` means the server has no `GEMINI_API_KEY`.

```json
{ "enabled": true, "daily_limit_seconds": 900, "used_seconds": 120,
  "remaining_seconds": 780, "session_max_seconds": 600,
  "resets_at": "2026-09-11T00:00:00Z" }
```

### `POST /voice-coach/sessions`
Start a session. Body: `{ "topic_id": "<uuid>" | null }` (`null` = general warm-up).
Returns `201`:

```json
{ "id": "…", "token": "auth_tokens/…", "model": "gemini-3.1-flash-live-preview",
  "expires_at": "…", "max_seconds": 600, "remaining_seconds": 300,
  "topic_title": "Travel", "questions": ["Where did you go last summer?"] }
```

- `token` is a Gemini **ephemeral token**: one use, it must open a session within
  60 seconds, and Gemini rejects audio after `expires_at`. The model, the coach
  instructions and the output settings are locked inside it.
- Connect with `new GoogleGenAI({ apiKey: token, apiVersion: "v1beta" })`, then
  `ai.live.connect({ model })`.
- `remaining_seconds` is what is left today **after** this session's full limit is held.
- Errors: `401` not signed in · `404` unknown topic · `429 voice_coach_limit` no
  minutes left, or another session is still open · `503 voice_coach_unavailable`
  no key, or the monthly AI budget is spent · `502 voice_coach_failed` Gemini
  refused the token. Rate limit: 10 starts per minute.

### `POST /voice-coach/sessions/{id}/end`
End a session and give back the unused time. Time is measured by the server
clock. Calling it twice is safe. `404` if the session is not yours.

```json
{ "id": "…", "used_seconds": 184, "remaining_seconds": 716 }
```

## Shadowing

Listen-and-repeat drill (PRD §8.14). All endpoints need sign-in.

### `GET /shadowing/topics/{topic_id}/items`
The sentences to shadow in one topic, taken from its published doc, with my best
score for each.

```json
{ "topic_id": "…", "topic_title": "Travel", "level": "A2", "voice_enabled": true,
  "items": [ { "key": "question-…", "kind": "question", "text": "Where did you go last summer?",
               "translation": "…", "audio_url": null, "best_score": 83, "attempts": 2 } ] }
```

- `kind` is `question`, `answer` (an answer template's example), `term` (a phrase)
  or `example` (a vocabulary or phrase example).
- `audio_url` is set only when an admin attached a recording. Otherwise fetch the
  model voice with the endpoint below.
- `voice_enabled: false` means the server cannot make model voices: use the browser's voice.
- `404` for an unknown or unpublished topic. A topic whose doc is not published returns no items.

### `GET /shadowing/topics/{topic_id}/items/{key}/audio`
The model voice for one sentence, as `audio/wav`. Made with Gemini TTS the first
time anyone asks, then served from the database. Sends an `ETag` and answers `304`
to a matching `If-None-Match`.

- `503 shadowing_voice_unavailable`: no TTS key, the TTS call failed, or the
  monthly AI budget is spent. Fall back to the browser voice.
- `404` if `key` is not a sentence of that topic. Rate limit: 120 per minute.

### `POST /shadowing/attempts`
Score one try and keep it. Returns `201`:

```json
// request
{ "topic_id": "…", "item_key": "question-…", "heard_text": "where you go last summer",
  "duration_ms": 2100, "reference_ms": 1900, "engine": "browser" }
// response
{ "score": 83,
  "words": [ { "word": "Where", "heard": "where", "status": "ok" },
             { "word": "did", "heard": null, "status": "missed" } ],
  "extra": [], "tempo_ratio": 1.11, "tempo": "good", "best_score": 83, "attempts": 1 }
```

- `score` is a **word match** from 0 to 100, **not** a pronunciation score:
  `ok` = 1, `close` (nearly the same spelling, e.g. "colour"/"color") = ½,
  `wrong` or `missed` = 0. Contractions and small numbers are normalised first
  ("I'm" = "I am", "5" = "five").
- `tempo` compares the learner's speech time with the model voice: `slow` above
  1.35×, `fast` below 0.75×, otherwise `good`. Null without both durations.
- `engine`: `browser` (Web Speech API) or `server` (`POST /transcribe`).

### `POST /shadowing/assess`
Deep pronunciation check of one try, by Azure (PRD §8.14 Phase 2). Multipart form:
`topic_id`, `item_key`, and `audio`. The audio must be a WAV file with 16-bit PCM,
16 kHz, mono, 0.3–30 seconds long; the browser converts the recording. Returns `200`:

```json
{ "accuracy": 93.3, "fluency": 95.0, "completeness": 100.0, "prosody": 86.1,
  "words": [ { "word": "went", "accuracy": 100.0, "error": "None", "is_name": false },
             { "word": "da", "accuracy": 61.0, "error": "None", "is_name": true } ],
  "heard": "I went to Da Nang with my family.", "seconds": 4.4, "remaining_today": 2 }
```

- `accuracy` is the mean word accuracy **without names**. A name is a capitalised
  word that does not start a sentence. `prosody` is null when the add-on is off.
- `error` uses Azure's terms: `None`, `Mispronunciation`, `Omission`, `Insertion`.
- Errors:
  - `503 pronunciation_unavailable`: no Azure key, or the AI budget is spent.
  - `429 pronunciation_limit`: today's checks are used up.
  - `400`: wrong audio format or length.
  - `422 nothing_heard`: no speech in the recording.
  - `502 pronunciation_failed`: Azure error. It does not use up a check.
  - `404`: unknown sentence.
- Rate limit: 20 per minute.
- The item list (`GET /shadowing/topics/{id}/items`) also returns
  `assess_enabled` and `assess_remaining`.

## Sentence Notes

### `GET /notes` / `POST /notes`
List and save sentence notes (PRD §8.7). The chat screen saves here when a user
keeps an AI suggestion or long-presses a message.

One shape covers both kinds of note. At least one of `original_text`,
`improved_text`, or `translated_text` is required — otherwise `422`.

**Correction** — what the user said plus the better version:

```json
{ "original_text": "I very like travel.", "improved_text": "I really enjoy travelling.", "source": "ai", "topic": "Travel" }
```

**Translation pair** — the same phrase in two languages, saved from the in-room
translator (PRD §8.10). The language codes let the UI label each side rather than
showing the user's own language as a mistake:

```json
{ "original_text": "tôi thích du lịch", "translated_text": "I like traveling", "source_lang": "vi", "target_lang": "en", "source": "translation", "topic": "Travel" }
```

`source_lang` / `target_lang` are short codes (max 10 chars) matching the
translator's list: `en` · `vi` · `es` · `fr` · `ja` · `ko`.

### `PATCH /notes/{id}` · `DELETE /notes/{id}`
Edit (partial: any of the fields above) or delete a note. `404` if unknown;
`DELETE` → `204`.

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
