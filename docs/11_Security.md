<!-- Purpose: Documents authentication, authorization, session handling, and the security controls that protect user data. Defines the two-role model (Admin, User), the anonymous browse-only state, and the rules every endpoint must follow. -->

# 11 Security — Authentication & Authorization

## 11.1 The one rule

> **The server decides who you are. The client never tells it.**

Every gap in §11.4 is a variation of breaking that rule. Read it before writing
any endpoint that touches user data.

---

## 11.2 Roles

Two roles. Anyone not signed in can look, but cannot practise.

| Role | How you get it | Can do |
|---|---|---|
| **Anonymous** | Not signed in | Browse the marketing pages and the topic library. Nothing else. |
| **User** | Registered with username + password | Rooms, warm-up, matching, transcripts, Coach Reports, notes, profile |
| **Admin** | Username is in `ADMIN_USERNAMES` | Everything a User can, plus manage topics, categories, docs and questions |

### Practice requires an account

**Rooms and warm-up are behind login.** So is anything that produces or reads
per-learner data: matching, notes, profile, transcripts, reports.

This reverses PRD §9.1, which made login optional. Update the PRD to match — two
documents disagreeing about who may enter a room is how the gap in §11.4 got
written in the first place.

The reasons it is the right call here:

- **Practice produces durable data.** A room writes transcript segments, which
  feed sentence feedback and band reports. Those are worthless without an owner
  — a guest speaks, generates cost, and can never read the result.
- **AI costs money per call.** Anonymous access to `/assist` is an open tap on
  your OpenAI bill with no user to attribute or cap it against
  (`app/ai/metering.py` caps *per user*).
- **Moderation needs a stable identity.** Kicking a guest means nothing when the
  next visit produces a new id.
- **It removes an entire security mechanism.** Every actor now arrives with a
  real JWT, so there is no second, weaker identity path to secure — see §11.9.

What stays open: the home page, pricing, about, how-it-works, safety, contact,
and **browsing topics**. Someone should be able to see what they would be
learning before signing up. They just cannot start talking.

**There is no role hierarchy beyond this.** Admin is a boolean, not a permission
set. If a third role ever appears (moderator, teacher, school), replace the
boolean with a `role` column before adding a second boolean — two booleans is
how permission systems rot.

---

## 11.3 What exists today

Genuinely solid, and worth keeping:

| Control | Implementation |
|---|---|
| Password storage | **bcrypt**, salted, 72-byte truncation applied consistently to hash *and* verify (`app/core/security.py`) |
| Session token | **JWT, HS256**, signed with `SECRET_KEY`, carries `sub` / `adm` / `iat` / `exp` |
| Token lifetime | 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES`) |
| Transport | `Authorization: Bearer <jwt>`, attached automatically by `app/lib/api/client.ts` |
| Admin re-check | `require_admin` re-reads `is_admin` **from the database**, so revoking admin takes effect on the next request rather than when the token expires |
| Username enumeration | Login returns one generic error for both "no such user" and "wrong password" |
| Brute force | Rate limited per IP — register 5/10min, login 10/min |
| Startup guard | The app **refuses to start** in production with the default `SECRET_KEY` |

Two decisions here are better than they look and should not be undone:

- **`adm` in the token is a hint, not authority.** Authorization re-reads the
  database. A stolen or stale token cannot grant admin.
- **The JWT replaced a raw user id as the session token.** That was a critical
  impersonation hole; the code comments record it so nobody reintroduces it.

---

## 11.4 What is broken

Ranked by what an attacker can actually do. **All four are the same bug**: the
server trusts an identity supplied by the caller.

### 🔴 1. Anyone can kick anyone from any room

`ModerateRequest` takes `owner_id` **in the request body**:

```python
class ModerateRequest(BaseModel):
    owner_id: uuid.UUID        # ← supplied by the caller
    target_user_id: uuid.UUID
    action: ModerationAction
```

`RoomService.moderate` then checks `room.owner_id == owner_id` — comparing a
database value against a number the attacker chose. Room ids and owner ids are
both returned by public endpoints, so:

```
POST /api/v1/rooms/{room_id}/moderate
{"owner_id": "<the real owner's id>", "target_user_id": "<anyone>", "action": "kick"}
```

kicks any member of any room, and **bans them permanently** (§11.7).

**Fix:** delete `owner_id` from the schema. Take the caller from
`Depends(get_current_user)` and compare `room.owner_id == user.id`.

### 🔴 2. The WebSocket accepts any claimed identity

```
/ws/rooms/{room_id}?user_id=...&name=...
```

There is **no token check**. `user_id` and `name` are query parameters, so
anyone who knows a room id can connect as any user — posting chat messages and
transcript lines under someone else's name, which then get graded as that
person's English.

**Fix:** require the JWT (query parameter `?token=` — browsers cannot set headers
on a WebSocket handshake), decode it, and derive `user_id` from `sub`. Reject
with close code `1008` when it is missing or invalid.

### 🟠 3. Notes are global

`SentenceNote` has **no `user_id` column** — the model docstring says so
outright: *"no user_id yet — that arrives with the auth slice. For the first
demo notes are global."* Every learner sees and can delete every other
learner's saved sentences.

**Fix:** add `user_id`, scope every query to the authenticated user, and require
auth on all four `/notes` endpoints. Existing rows have no owner — decide
whether to delete them or assign them to an admin.

### 🟠 4. Join, leave and profile take a caller-supplied `user_id`

`JoinRequest.user_id`, `leaveRoom`, and the `/users` endpoints all identify the
actor from the body or path rather than the token. Effects are smaller —
occupying a seat as someone else, editing another profile — but it is the same
defect and should be fixed in the same pass.

---

## 11.5 The authorization matrix

What each endpoint must require **after** the fixes. This is the spec: an
endpoint not on this list is a bug.

### API

| Endpoint group | Anon | User | Admin | Rule |
|---|:---:|:---:|:---:|---|
| `POST /auth/register`, `/auth/login` | ✅ | ✅ | ✅ | Rate limited |
| `GET /health` | ✅ | ✅ | ✅ | Public |
| `GET /topics`, `/categories`, `/docs` | ✅ | ✅ | ✅ | The shop window — browsable before signing up |
| `POST|PATCH|DELETE /topics`, `/categories`, `/docs`, `/questions` | ❌ | ❌ | ✅ | `require_admin` |
| `GET /rooms`, `GET /rooms/{id}` | ✅ | ✅ | ✅ | Listing only — shows what exists, not its contents |
| `POST /rooms` (create) | ❌ | ✅ | ✅ | Owner = **token**, never the body |
| `POST /rooms/{id}/join`, `/leave` | ❌ | ✅ | ✅ | Actor = token |
| `POST /rooms/{id}/moderate` | ❌ | 🔒 | 🔒 | **Owner of that room only**, from token |
| `WS /ws/rooms/{id}`, `/ws/voice/{id}` | ❌ | ✅ | ✅ | Identity from the token, never a query param |
| `POST /assist`, `/translate`, `/transcribe` | ❌ | ✅ | ✅ | Every AI call is attributable and capped |
| `GET /transcripts/rooms/{id}` | ❌ | ✅ | ✅ | Members of that room |
| `GET|DELETE /transcripts/me` | ❌ | 🔒 | 🔒 | **Own rows only** |
| `POST|GET /feedback/*`, `/reports/*` | ❌ | 🔒 | 🔒 | **Own rows only** |
| `GET|POST|PATCH|DELETE /notes` | ❌ | 🔒 | 🔒 | **Own rows only** |
| `GET|PATCH /users/me` | ❌ | 🔒 | 🔒 | Own profile only |

🔒 = authenticated **and** scoped to the caller's own data.

### Frontend routes

The API is the real boundary; route guards only save a wasted round trip and a
confusing empty screen.

| Route | Anon |
|---|:---:|
| `/`, `/about`, `/contact`, `/features`, `/how-it-works`, `/pricing`, `/safety`, `/login` | ✅ |
| `/topics`, `/topics/{id}` | ✅ |
| `/rooms`, `/rooms/{id}`, `/warmup`, `/match` | ❌ → `/login?next=…` |
| `/notes`, `/profile` | ❌ → `/login?next=…` |
| `/admin` | Admin only |

Send them to login with a `next` parameter, then return them where they were
going. A learner who clicks a shared room link and is bounced to an unexplained
home page usually does not come back.

Guarding takes **two** pieces, and one alone is not enough:

| Piece | Where | Covers |
|---|---|---|
| `requireAuth()` in `beforeLoad` | each guarded route | client-side navigation (clicking a link) |
| `<AuthWatcher>` | `__root.tsx` | hard page loads, and logging out while on a guarded page |

`beforeLoad` cannot do the job by itself. On a hard load it runs on the
**server**, where `localStorage` does not exist, so it has to let the render
through — and it is not re-run once the client hydrates. Without the watcher,
opening `/rooms` in a fresh tab shows the page to a signed-out visitor until the
first API call 401s.

The same asymmetry runs the other way. `/login` redirects an **already** signed-in
visitor to `next ?? /rooms`, so no one is shown a login form for a session they
already have.

### Signed-in state in the UI

Identity lives in `localStorage`, which the server cannot read, so the first
paint of any auth-dependent element is unavoidably ignorant. Rendering the
signed-out version and swapping it a frame later makes a live session look
logged out — the header flashes "Log in" at someone who is already in a room.

The rule: **render a neutral placeholder until hydration, never a guess.**
`useHydrated()` in `lib/identity.ts` is that flag, and the header, the account
menu and the footer's Admin link all gate on it.

Two more consequences of "an account is required":

- **The header has two navs.** A visitor sees the marketing pages; a signed-in
  learner sees Rooms / Warm-up / Match / Notes. Showing a visitor links that only
  bounce them to `/login` is worse than not showing them.
- **A dead token signs itself out.** `apiRequest` calls the handler registered by
  `identity.ts` on a **401 that carried a token** — expired or revoked — which
  clears the session and lets `<AuthWatcher>` move the user to `/login`. A 401
  with no token is just an anonymous call and clears nothing; a **403** never
  logs anyone out, because it means "signed in, but not allowed here".

### The scoping rule

For any endpoint marked 🔒:

> **Filter on the authenticated user. Never on an id from the URL or body.**

```python
# WRONG — anyone can read anyone
async def my_notes(user_id: uuid.UUID): ...

# RIGHT — the token decides
async def my_notes(user: User = Depends(get_current_user)):
    return await repo.list_for_user(user.id)
```

`/transcripts/me`, `/feedback/me` and `/reports/me` already follow this. `/notes`
and `/users` do not.

---

## 11.6 Sessions

**Current:** a 7-day JWT, stateless, no refresh, no revocation.

That is a reasonable trade for a practice app — but be explicit about what it
means, because "log out" currently does nothing server-side:

| Property | Today | Acceptable? |
|---|---|---|
| Expiry | 7 days | Yes — a learner shouldn't be logged out mid-session |
| Refresh | None; re-login after 7 days | Yes for now |
| Revocation | **None.** A stolen token is valid until it expires | **No, once you have paying users** |
| Logout | Client clears local storage; the token stays valid | Misleading — say so in the UI, or fix it |
| Storage | `localStorage` under `et_user` | Acceptable; XSS-readable, see §11.8 |

**When to add revocation:** the first time a user can lose money or be
impersonated meaningfully — realistically, when payments land. The cheapest
implementation is a `token_version` integer on `User`, included as a claim and
compared on every request; bumping it invalidates every existing token for that
user. That costs one column and one comparison, and gives you working logout,
"sign out everywhere", and a response to a leaked token.

---

## 11.7 Moderation and bans

Kick currently bans **permanently**, in a **process-local in-memory dict**
(`app/services/moderation.py`). Two problems:

- **No undo.** `clear_room()` exists but nothing calls it. A host who kicks by
  mistake has locked that person out of that room forever.
- **Silently inconsistent.** The ban evaporates on every deploy or restart, and
  would not be shared across replicas.

**Fix:** give bans a duration (24 hours is generous for a practice app), store
them in Redis with a TTL, and add `DELETE /rooms/{id}/bans/{user_id}` for the
owner. Until then, the frontend at least tells a banned learner plainly what
happened and sends them to another room rather than offering a Retry that cannot
work.

---

## 11.8 Other controls

**Already right:**

- **CORS** is an explicit origin allowlist, not `*` — required, since the app
  sends credentials.
- **HTTPS everywhere** via Caddy with automatic Let's Encrypt. Also a functional
  requirement: the Web Speech API refuses to start outside a secure context.
- **Secrets** live in `.env.prod` (chmod 600), never the repo. `.gitignore`
  excludes `.env*` but allows `.env.example`.
- **Prompt injection** is handled where user speech reaches a model: content is
  wrapped in `<conversation>` tags, never placed in the system prompt, and
  evidence quotes are verified against the speaker's own text
  (`docs/10_AI_Design.md` §10.3.0, §10.7).
- **Spend abuse** is capped per user per day and per org per month
  (`app/ai/metering.py`).

**Gaps worth knowing:**

- **`localStorage` is readable by any XSS.** An httpOnly cookie is stronger, but
  needs CSRF protection in exchange. Not worth switching until there is money in
  the account; do switch before there is.
- **The rate limiter is in-memory and per-process** — it resets on restart and
  does not span replicas. Move it to Redis alongside the ban list.
- **No audit log.** Nothing records who kicked whom, or who edited a topic.
  Add one when a second admin exists.
- **No password reset**, and no email on file to send one to. A learner who
  forgets their password loses their account, transcripts and reports. This is
  the biggest *product* risk in this document.

---

## 11.9 Implementation plan

Ordered by risk. Steps 1–3 are the security fix and belong in one PR.

**Step 1 — Take identity from the token (~half a day). 🔴**

1. Delete `owner_id` from `ModerateRequest`; derive it from `get_current_user`.
2. Same for `JoinRequest.user_id`, `/leave`, and `/users`.
3. Add a regression test per endpoint: *a non-owner calling moderate gets 403*.

**Step 2 — Authenticate the WebSockets (~half a day). 🔴**

1. Accept `?token=` on `/ws/rooms/{id}` and `/ws/voice/{id}`.
2. Decode it, take `user_id` from `sub`, ignore any supplied `user_id`.
3. Close with `1008` when missing or invalid.
4. Update `roomSocketUrl` / `voiceSocketUrl` to append the token.

   No guest-token mechanism is needed: rooms require an account, so every socket
   arrives with a real JWT. That is one whole security surface this decision
   deletes rather than adds.

**Step 3 — Scope notes to their owner (~half a day). 🟠**

1. Migration: add `user_id` to `sentence_notes` (nullable, then backfill or
   delete, then make it non-null).
2. Require auth on all `/notes` endpoints and filter on the caller.

**Step 4 — Bans that expire (~half a day). 🟠**

Redis with a TTL, plus an unban endpoint for the owner.

**Step 5 — Real logout (~half a day).**

`token_version` on `User`, checked on every request.

**Step 6 — Password reset.**

Needs an email address and a mail provider. Design it before you have users who
can lose something.

---

## 11.10 What NOT to build

- **Roles beyond Admin and User.** Two is right for the product today. Add a
  `role` column when a third genuinely appears — not a second boolean.
- **OAuth / social login.** More surface area, and it does not solve the actual
  gaps in §11.4. Username and password is the correct choice at this size.
- **A permissions framework.** With two roles, `require_admin` and "scope to the
  caller" cover everything. A policy engine here would be more code than rules.
- **A guest tier that can still practise.** That was the old design and it is
  what §11.2 replaces. Half-authenticated actors are how the gaps in §11.4 got
  written; do not reintroduce them under another name.
- **Blocking the topic library behind login.** Someone must be able to see what
  they would be learning before they hand over a password. The wall goes around
  *practising*, not around *looking*.
