# How to Deploy an Update (manual release checklist)

Use this **every time you change the code and want it live**. It's the manual
process (works even while GitHub Actions is disabled — Cloudflare and GHCR don't
need Actions).

**Your values (already filled in):**
- Image: `ghcr.io/vanhhhh04/englishtalker-api:latest`
- Server: `ec2-user@13.213.87.223` (`api.englishspeaker.me`)
- Deploy folder on the server: `~/englishtalker/deploy`
- Frontend: pushed to GitHub → Cloudflare rebuilds automatically
- Health check: `https://api.englishspeaker.me/api/v1/health`

---

## TL;DR — which part changed?

| You changed… | Do this |
|---|---|
| **`frontend-web/…`** (UI) | `git push` → Cloudflare auto-deploys. Done. |
| **`backend/…`** (API/DB) | Build image → push to GHCR → on server: pull → migrate → restart. |
| **Both** | Do both. |

---

## A) Frontend update (UI changes)

On your **PC**:
```powershell
git add -A
git commit -m "describe your change"
git push
```
Cloudflare detects the push, rebuilds `frontend-web/`, and deploys it to
`https://englishspeaker.me`. Watch progress in the Cloudflare dashboard →
Workers & Pages → your project. **No other step needed.**

> Reminder: the frontend calls the backend at `https://api.englishspeaker.me`.
> If you add a NEW frontend origin, add it to `CORS_ORIGINS` in the backend
> `.env.prod` (see section B) or the browser will block the calls.

---

## B) Backend update (API or database changes)

### Prerequisites (once per work session)
- **Docker Desktop is running** on your PC.
- You're **logged in to GHCR** on your PC (only needed if it forgot):
  ```powershell
  docker login ghcr.io -u vanhhhh04
  # paste your ghp_… token at the Password prompt
  ```

### Step 1 — Commit first (recommended)
`docker build` reads files from disk, not Git, so a commit isn't *required* for the
image to include your changes — but commit anyway so the running image matches a
known commit (for rollback + backup), and so any frontend changes deploy too.
```powershell
git add -A
git commit -m "describe your change"
git push
```

### Step 2 — Build + push the image (on your PC)
```powershell
docker build -t ghcr.io/vanhhhh04/englishtalker-api:latest ./backend
docker push ghcr.io/vanhhhh04/englishtalker-api:latest
```
Only the changed layer uploads, so after the first time this is quick.

### Step 3 — Deploy on the server
SSH in:
```powershell
ssh -i "local-key-access-english-talker-ec2-instance.pem" ec2-user@13.213.87.223
```
Then:
```bash
cd ~/englishtalker/deploy

# (recommended) back up the database first — see docs/DEPLOYMENT.md §14
# ./backup.sh

# get the new image
docker compose -f docker-compose.prod.yml pull api

# run migrations — only needed if you added/changed a DB column (see below).
# Safe to run anyway; it does nothing if there's nothing new.
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# restart with the new image
docker compose -f docker-compose.prod.yml up -d
```

### Step 4 — Verify
```bash
docker compose -f docker-compose.prod.yml ps          # all Up, db healthy
docker compose -f docker-compose.prod.yml logs api --tail 20   # "Application startup complete"
```
From anywhere:
```
https://api.englishspeaker.me/api/v1/health  →  {"status":"ok",...}
```

---

## Do I need to run the migration?

**Run `alembic upgrade head` only if you added or changed a database column** —
i.e. you edited a model in `backend/app/models/` AND added a new migration file
in `backend/alembic/versions/`.

- **Changed a model?** You MUST also add a matching migration, or production will
  500 (this is the "drift" bug we hit). Create one, commit it, rebuild the image,
  then run `alembic upgrade head` on the server.
- **No model change** (e.g. fixed logic, changed a message, added an endpoint that
  uses existing tables)? No migration needed — just pull + `up -d`.

Running `alembic upgrade head` when there's nothing new is harmless.

---

## Changing settings only (no code change)

If you only need to change an environment value (e.g. add a key, change
`CORS_ORIGINS`, switch `STT_PROVIDER`), you don't rebuild the image:
```bash
cd ~/englishtalker/deploy
nano .env.prod          # edit the value(s)
cp .env.prod .env       # keep the compose-substitution copy in sync (IMPORTANT)
docker compose -f docker-compose.prod.yml up -d   # recreates with new env
```
> ⚠️ Always `cp .env.prod .env` after editing — Docker Compose reads `${VARS}`
> from `.env`, not `.env.prod`. Skipping this gives blank values and a crash loop.

---

## Rollback (if a release breaks things)

**Backend:** each image push is tagged `:latest`. To roll back, on your PC push the
previous good commit's image, or on the server pin a known-good digest and
`up -d`. Simplest safe habit: keep the last working image around.
```bash
# stop the bad version fast:
docker compose -f docker-compose.prod.yml down
# ...fix, rebuild/pull a good image, then:
docker compose -f docker-compose.prod.yml up -d
```
**Bad migration:** restore the database from the `pg_dump` you took before
deploying (see docs/DEPLOYMENT.md §14/§17), then redeploy the matching old image.
**Always back up before a migration.**

---

## Common gotchas

| Symptom | Fix |
|---|---|
| `docker: cannot connect to the Docker daemon` | Start **Docker Desktop** on your PC |
| `denied` on `docker push` | Re-run `docker login ghcr.io -u vanhhhh04` with your token |
| `POSTGRES_* variable is not set` / DB crash loop | Run `cp .env.prod .env` in the deploy folder |
| `UndefinedColumnError` (500 after deploy) | You changed a model without a migration — add one, rebuild, `alembic upgrade head` |
| Frontend didn't update | Check Cloudflare → your project → latest deployment; confirm the push landed on `main` |
| `SECRET_KEY` startup error | `SECRET_KEY` missing/default in `.env.prod` |

---

## Quick reference — the whole thing in one block

**Frontend only:**
```powershell
git add -A && git commit -m "change" && git push
```

**Backend (PC):**
```powershell
docker build -t ghcr.io/vanhhhh04/englishtalker-api:latest ./backend
docker push ghcr.io/vanhhhh04/englishtalker-api:latest
```
**Backend (server):**
```bash
cd ~/englishtalker/deploy
docker compose -f docker-compose.prod.yml pull api
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
```

When GitHub Actions is re-enabled, all of the backend steps happen automatically
on `git push` (via `.github/workflows/deploy.yml`) — until then, this is your flow.
