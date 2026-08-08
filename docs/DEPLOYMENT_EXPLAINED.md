# EnglishTalker — Deployment Explained (the "why" behind every step)

This document explains **what each part does and why**, for both the **code
changes** and the **infrastructure setup** that took EnglishTalker from "runs on
my laptop" to "live on the internet at englishspeaker.me."

It's written to be read top to bottom. Plain language, one idea at a time.

- Companion runbook (the commands): `docs/DEPLOYMENT.md`
- This file (the reasons): you're reading it

---

## 1. The big picture — three companies, three jobs

Your app is served by three different services. Each has one clear job.


| Service        | Its job                                           | Think of it as                                     |
| -------------- | ------------------------------------------------- | -------------------------------------------------- |
| **Namecheap**  | You **own** the name `englishspeaker.me`          | The office where you registered your business name |
| **Cloudflare** | The **phone book** (DNS) + **hosts the frontend** | Google Maps + the dining room                      |
| **AWS EC2**    | Runs the **backend** (API + database)             | The kitchen in the back                            |


**Why three?** No single one does everything cheaply. You *buy the name* at
Namecheap, *point traffic* with Cloudflare, and *run the server* on AWS. Each is
the cheapest/best at its one job.

### How a visitor reaches your app

```
Visitor types  englishspeaker.me
      │
      ▼
Namecheap: "I own this name → its phone book is at Cloudflare"
      │
      ▼
Cloudflare DNS (phone book) answers:
   englishspeaker.me      → Cloudflare Worker  (your frontend)
   api.englishspeaker.me  → AWS EC2 13.213.87.223  (your backend)
      │
      ▼
Frontend (Cloudflare) draws the pages,
and calls the backend (EC2) for data (login, rooms, messages).
```

---



## 2. PART A — Code changes for production, and why

Your app worked on your laptop, but "works on my laptop" is not "safe on the
public internet." These code changes made it production-ready.

### 2.1 Real login tokens (JWT) — *security*

**Before:** the login "token" was just the user's ID number. Anyone who saw an
ID (they're visible in API responses) could pretend to be that user — including
the admin. That's a total break.
**Change:** login now returns a **JWT** — a token that is *cryptographically
signed* with a secret key only your server knows, and it *expires*. A faked token
won't match the signature, so it's rejected.
**Why it matters:** without this, anyone could take over any account. This was the
single most important fix.
*(Files:* `app/core/security.py`*,* `app/api/deps.py`*,* `app/api/v1/routes/auth.py`*.)*

### 2.2 CORS lockdown — *security*

**CORS** = the browser rule for "which websites are allowed to call this API."
**Before:** it allowed **any** website. **Change:** it now allows **only your
frontend** (`CORS_ORIGINS`). **Why:** stops a random malicious site from making
calls to your API using a logged-in user's browser.

### 2.3 Rate limiting — *abuse protection*

**Change:** login/register now allow only a few tries per minute per visitor
(returns `429 Too Many Requests` after that). **Why:** stops bots from guessing
passwords thousands of times, and stops spam sign-ups.
*(File:* `app/core/rate_limit.py`*.)*

### 2.4 Admin flag + admin gate — *authorization*

**Change:** added an `is_admin` flag on users and a `require_admin` check on the
content-management endpoints (create/edit/delete topics and documents). A username
in `ADMIN_USERNAMES` becomes admin automatically.
**Why:** only you should be able to manage the app's learning content, not every
user. *(Files:* `app/models/user.py`*,* `app/api/deps.py`*.)*

### 2.5 Production settings — *safety switches*

Set in `.env.prod`:

- `ENVIRONMENT=production` — turns on the "refuse to start with the default secret"
check, and turns **off** the dev shortcuts below.
- `DEBUG=false` — stops printing every database query (huge, slow logs).
- `AUTO_CREATE_TABLES=false` — **very important.** In dev, the app auto-built the
database tables from the code (`create_all`). In production that's dangerous
(it can't safely change existing tables), so we turn it off and use **migrations**
instead (see 2.7).
- `SEED_DEMO_DATA=false` — don't insert fake demo rooms/users.



### 2.6 Smaller Docker image — *fit the server + faster deploys*

**Problem:** the backend image was **~9.5 GB** because one translation library
(`argostranslate`) pulled in **PyTorch** (a giant machine-learning library).
**Change:** removed it (your default translator is Google, and the code falls back
gracefully), and switched the speech model from `base` to `tiny`.
**Result:** image dropped to **~1.23 GB**. **Why it matters:** it now fits your
2 GB server, builds faster, and uploads/downloads in a minute instead of an hour.
*(Files:* `backend/requirements.txt`*,* `backend/Dockerfile`*.)*

### 2.7 Migrations, and the drift fix (0010) — *correct database schema*

**Migrations** = an ordered list of scripts that build/change the database, one
step at a time (`0001`, `0002`, …). Production runs these instead of `create_all`
so schema changes are safe and repeatable.
**The bug we hit:** two columns (`rooms.owner_id`, `users.phone`) existed in the
code but **no migration created them**. In dev, `create_all` hid this. In
production, login and rooms crashed (500) because those columns were missing.
**Fix:** migration `0010_sync_owner_and_phone` adds them. **Lesson:** every column
you add to a model needs a matching migration.

### 2.8 `wrangler.jsonc` — *let Cloudflare deploy the frontend*

Cloudflare's build tool tried to re-build the frontend and choked on the custom
Lovable config. Adding `frontend-web/wrangler.jsonc` (pointing at the already-built
output) told Cloudflare "just upload these files" — no re-build, no error.

---



## 3. PART B — Infrastructure setup, step by step, and why



### 3.1 The domain (Namecheap) — *own the name*

You registered `englishspeaker.me`. This just proves the name is **yours**.
Namecheap hosts nothing; it only owns the name and says where its "phone book" is.

### 3.2 Security group (AWS firewall) — *only open the doors you need*

A **security group** is a firewall: a list of which network "doors" (ports) are
open. We opened:


| Port                                                                           | For   | Why                                                        |
| ------------------------------------------------------------------------------ | ----- | ---------------------------------------------------------- |
| 22                                                                             | SSH   | So *you* (your IP only) can log into the server            |
| 80                                                                             | HTTP  | So Caddy can get its HTTPS certificate + redirect to HTTPS |
| 443                                                                            | HTTPS | The real, secure web traffic                               |
| 3478, 5349, 49152–65535                                                        | TURN  | For voice calls (later)                                    |
| We **did NOT** open 5432 (the database). **Why:** the database should never be |       |                                                            |
| reachable from the internet — only the app talks to it, privately.             |       |                                                            |




### 3.3 EC2 instance — *the actual computer*

**EC2** = a rented computer in Amazon's data center (yours is in Singapore).
You picked `t3.small` (2 GB RAM) to balance cost (~$19/mo, fits your $100
credit for months) against needing enough memory to run the speech model + database.

### 3.4 Elastic IP — *a permanent address*

A normal server IP changes if you stop/start it. An **Elastic IP** is a **fixed**
address (`13.213.87.223`) that stays yours. **Why:** your DNS points at this IP —
it must not change.

### 3.5 DNS records (`api`, `turn`) — *the phone book entries*

You added:

- `api.englishspeaker.me → 13.213.87.223` — so the frontend can find your backend.
- `turn.englishspeaker.me → 13.213.87.223` — for the future voice server. These are set to **"DN S only" (grey cloud)** in Cloudflare. **Why grey:** so the
traffic goes **straight to your EC2** and Caddy can handle HTTPS itself. If it were
"proxied" (orange), Cloudflare would intercept it and Caddy couldn't get a cert.



### 3.6 Moving DNS to Cloudflare — *required for the frontend*

You started with Namecheap's phone book, then switched to Cloudflare's (the
nameserver change). **Why:** Cloudflare Workers (your frontend host) can only
attach your custom domain if Cloudflare also runs the DNS. Bonus: Cloudflare DNS
is free and fast.

### 3.7 Install Docker + Compose on the EC2 — *run the containers*

**Docker** runs your app inside "containers" (isolated boxes with everything the
app needs). **Docker Compose** runs *several* containers together from one file.
**Why:** the same setup runs identically everywhere — no "works on my machine."

### 3.8 The deploy files — *the recipe for your server*

In `~/englishtalker/deploy/` on the EC2:

`docker-compose.prod.yml` — the recipe. It defines 4 containers:


| Container                                                                         | Job                                                   |
| --------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `api`                                                                             | Your FastAPI backend (pulled from GHCR)               |
| `db`                                                                              | PostgreSQL database (+ pgvector) — stores everything  |
| `redis`                                                                           | Fast in-memory store (cache/queues)                   |
| `caddy`                                                                           | Web server that gives you HTTPS and forwards to `api` |
| It also creates a private network (containers find each other by name like `db`), |                                                       |
| and a **volume** (`pgdata`) so the database survives restarts.                    |                                                       |


`Caddyfile` — tells Caddy: "for `api.englishspeaker.me`, get an HTTPS cert
automatically and forward to the `api` container on port 8000."

`.env.prod` — your secret settings (passwords, keys). Never committed to Git.
`chmod 600` = only your user can read it.

**The** `.env` **vs** `.env.prod` **gotcha:** Docker Compose reads `${VARIABLES}` (like the
DB password) only from a file named exactly `.env` — not `.env.prod`. That's
why we copied it (`cp .env.prod .env`). Without it, the DB got a blank password and
crash-looped.

### 3.9 GHCR — build the image, ship it to the server

**GHCR** = GitHub Container Registry, a place to store Docker images.
**The flow:** build the image on your **PC** (lots of RAM, fast) → **push** to GHCR
→ the **EC2 pulls** it. **Why not build on the EC2?** The 2 GB server would be slow
or run out of memory building it. Building on your PC and having the small server
just *download* the result is much more reliable.

### 3.10 The deploy sequence, and why the order matters

```
1. up -d db redis      → start the database + redis first
2. CREATE EXTENSION vector  → turn on pgvector (needed before migrations that use it)
3. alembic upgrade head → build all the tables (migrations 0001…0010)
4. up -d               → start api + caddy
5. ps                  → check everything is running
```

**Why this order:** the database must exist and have the `vector` feature enabled
*before* migrations run; migrations must build the tables *before* the API serves
requests.

### 3.11 Caddy + automatic HTTPS — *the secure padlock*

The moment Caddy starts, it contacts **Let's Encrypt** (a free certificate
authority), proves it controls `api.englishspeaker.me` (via port 80), and gets a
real HTTPS certificate — then renews it automatically forever. **Why HTTPS
matters:** browsers block the microphone, camera, and voice on non-HTTPS sites, and
it encrypts all traffic. Without HTTPS, half your app wouldn't work.

### 3.12 Frontend on Cloudflare Workers — *the website itself*

Your frontend (built with TanStack Start) runs on Cloudflare's global network. It's
served fast from data centers near each visitor, with free HTTPS. It's currently at
`englishspeaker.caovietanhhd.workers.dev`, and will move to `englishspeaker.me` once
you attach the custom domain.

---



## 4. Every environment variable, explained

These live in `.env.prod` on the EC2:


| Variable                    | What it does                                                         |
| --------------------------- | -------------------------------------------------------------------- |
| `ENVIRONMENT=production`    | Turns on prod safety checks; turns off dev shortcuts                 |
| `DEBUG=false`               | Stops verbose SQL logging                                            |
| `SECRET_KEY`                | The secret used to sign login tokens (JWT). Must be random + private |
| `AUTO_CREATE_TABLES=false`  | Use migrations, not auto-build, for the DB schema                    |
| `SEED_DEMO_DATA=false`      | Don't insert fake demo content                                       |
| `CORS_ORIGINS`              | Which websites may call the API (your frontend URLs)                 |
| `STT_MODEL=tiny`            | The small speech-to-text model, so it fits 2 GB RAM                  |
| `POSTGRES_USER/PASSWORD/DB` | The database login                                                   |
| `DATABASE_URL`              | How the app connects to the database (`@db` = the container name)    |
| `REDIS_URL`                 | How the app connects to Redis                                        |
| `ADMIN_USERNAMES`           | Usernames that automatically become admins                           |


---



## 5. Problems we hit (and what they taught us)

Real deployments hit snags. Here are the ones you actually solved, so they make
sense next time:

1. **Docker DNS glitch** — the app couldn't find `db`. Fix: `down` then `up` (it
  rebuilds the network). Lesson: `down` recreates the container network.
2. **GitHub Actions disabled** — new-account anti-abuse. Workaround: deploy
  manually (build → push → pull) while support enables it.
3. **9.5 GB image** — an unused ML library. Fix: removed it → 1.23 GB.
4. **Cloudflare Vite error** — the Lovable config confused Cloudflare's builder.
  Fix: `wrangler.jsonc` to deploy the pre-built output.
5. **Blank DB password / crash loop** — Compose reads `${VARS}` from `.env`, not
  `.env.prod`. Fix: `cp .env.prod .env`.
6. **500 on login/rooms** — migrations were missing two columns. Fix: migration
  `0010`. Lesson: models and migrations must stay in sync.

---



## 6. What's live now, and what's left

**Live and working:**

- Backend API: `https://api.englishspeaker.me` (HTTPS, database, auth, rooms)
- Frontend: `https://englishspeaker.caovietanhhd.workers.dev`
- Admin: register the username `admin` → automatic admin rights

**Still to do (not blocking):**

- **Attach the Worker to** `englishspeaker.me` once Cloudflare DNS is active →
final URL becomes `https://englishspeaker.me`.
- **Backups** — `deploy/backup.sh` + a nightly cron. Do this before real users;
self-hosting the DB means backups are your responsibility.
- **Voice (TURN server)** — run coturn when you want reliable voice calls.
- **Automatic deploys** — once GitHub Actions is enabled, pushing to `main` will
build + deploy for you (the `.github/workflows/deploy.yml` pipeline).

---



## 7. Cheat sheet — daily operations

On the EC2, in `~/englishtalker/deploy/`:

```bash
# See what's running
docker compose -f docker-compose.prod.yml ps

# View the API logs
docker compose -f docker-compose.prod.yml logs api --tail 50

# Deploy a new backend version (after pushing a new image to GHCR)
docker compose -f docker-compose.prod.yml pull api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d

# Back up the database by hand
docker compose -f docker-compose.prod.yml exec db pg_dump -U englishtalker englishtalker | gzip > backup.sql.gz

# Restart everything
docker compose -f docker-compose.prod.yml restart
```

To ship a new **backend** version end to end: change code → build image on your PC
→ push to GHCR → run the "Deploy a new backend version" block above on the EC2.

To ship a new **frontend** version: push to GitHub → Cloudflare rebuilds it
automatically.