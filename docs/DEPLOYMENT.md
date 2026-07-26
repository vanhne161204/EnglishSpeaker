# EnglishTalker — Production Deployment Runbook (AWS EC2 + Namecheap)

> Goal: take the app from local Docker to a professional, HTTPS-secured public
> deployment on **one AWS EC2 instance**, using a **Namecheap** domain (GitHub
> Student Pack) and **PostgreSQL running in Docker on the same box**. Sized for
> **~50 users/hour**.

**Status of the app:** all features tested and passing (auth+JWT, admin gate,
rooms, chat/WebSocket presence, translate, matchmaking, speech-to-text, rate
limiting). The only thing left before going live is this infrastructure.

> **Important trade-off:** self-hosting the database in Docker is the cheapest
> option, but **you own the backups and uptime**. There is no managed safety net —
> if the EC2's disk is lost and you have no backup, your users are gone. §14 sets
> up a mandatory backup routine that makes this safe. Do not skip it.

---

## 1. Decisions (what this runbook assumes)

| Area                    | Choice                                                                                        | Why                                                                                              |
| ----------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Compute                 | **1 EC2 instance** (`t3.medium`) running Docker Compose                                        | Simple, cheap, enough for 50/hr; in-memory WebSocket state needs a single backend process anyway |
| Database                | **PostgreSQL 16 + pgvector in Docker** on the same EC2                                         | Cheapest; but you own backups (see §14) — the backup routine is **mandatory**, not optional      |
| Cache/Redis             | **Redis in Docker** on the EC2                                                                 | Low traffic; fine to co-locate. Move to ElastiCache only when scaling out                         |
| Domain + DNS            | **Namecheap** (Student Pack free `.me`, free BasicDNS)                                         | Free; no Route 53 needed                                                                          |
| TLS / HTTPS             | **Caddy** on the EC2 (auto Let's Encrypt)                                                      | Free, auto-renewing certs; no ALB/ACM needed                                                      |
| Frontend hosting        | **Option A: Cloudflare Pages (free)** *(recommended)* or **Option B: node-server on the EC2**  | The frontend already builds for Cloudflare; see §8                                                |
| Voice (WebRTC)          | **coturn** (TURN) on the EC2                                                                    | Voice fails behind strict/corporate NAT without TURN                                              |
| Secrets                 | **Locked-down `.env.prod`** on the box (or AWS SSM Parameter Store)                            | Keep `SECRET_KEY`/DB creds out of the repo                                                        |
| Backups                 | **`pg_dump` → EBS snapshots + off-box copy to S3** (§14)                                       | Replaces RDS's automated backups — the price of self-hosting the DB                               |
| No NAT / no RDS         | Single **public** EC2 with an Elastic IP; DB is a local container                              | A public instance has direct internet; nothing needs a NAT or a managed DB                        |

**Architecture (recommended: frontend on Cloudflare Pages):**

```
                Namecheap DNS (free)
        ┌───────────────┴────────────────┐
        ▼                                 ▼
   yourname.me                       api.yourname.me
   Cloudflare Pages (free CDN+TLS)   A record → EC2 Elastic IP
   (TanStack SSR)                          │
                                           ▼
                        ┌──────────────────────────────────┐
                        │  EC2  t3.medium (public)          │
                        │  Docker Compose:                  │
                        │   • Caddy (TLS :443/:80)          │
                        │   • api (FastAPI :8000)           │
                        │   • postgres (+pgvector)  ──┐     │
                        │   • redis                   │     │
                        │   • coturn (TURN)           │     │
                        └─────────────────────────────┼─────┘
                                                       ▼
                                   DB data on a Docker volume (EBS disk)
                                   → nightly pg_dump + EBS snapshot (§14)
```

**All-on-EC2 variant (Option B):** `yourname.me` A-record → EC2; Caddy path-routes
`/` → frontend container, `/api` + `/ws` → api container. One domain, one box.

---

## 2. Cost estimate (per month)

| Item                                  | Cost                                  | Notes                                   |
| ------------------------------------- | ------------------------------------- | --------------------------------------- |
| EC2 `t3.medium` (2 vCPU / 4 GB)       | ~$30 on-demand (~$17 reserved 1-yr)   | Runs api + postgres + redis + Caddy     |
| EBS storage (40 GB gp3)               | ~$3.20                                | App + Docker + **database data**        |
| EBS snapshots (backups)               | ~$1–2                                 | Incremental; only changed blocks        |
| S3 (off-box `pg_dump` copies)         | ~$0.20–0.50                           | A few GB of dumps                        |
| Elastic IP (attached)                 | $0                                    | Charged only if unattached              |
| Domain + DNS (Namecheap Student Pack) | **$0** (year 1)                       | `.me` renews ~$20/yr after              |
| Cloudflare Pages (frontend)           | **$0**                                | Free tier is plenty                     |
| Data transfer                         | ~$1–5                                 | Low at this scale                       |
| **Total**                             | **~$35–42 / month**                   | ~$22–28 with a reserved instance        |

Self-hosting the DB saves ~$13–15/mo vs RDS — the cost is that **backups and
uptime are now your job** (§14). If you later want the managed safety net back,
switch `DATABASE_URL` to an RDS endpoint and drop the `postgres` service.

---

## 3. Prerequisites (do these first)

- [ ] AWS account with billing set up; pick a region close to your users (e.g. `ap-southeast-1` Singapore for Vietnam).
- [ ] Claim the **Namecheap** domain from the GitHub Student Pack.
- [ ] (Recommended) A free **Cloudflare** account for frontend hosting.
- [ ] An **SSH key pair** created in the EC2 console (download the `.pem`).
- [ ] Locally: the repo builds and all tests pass (already verified).
- [ ] Generate a strong secret now: `openssl rand -hex 32` → save it for `SECRET_KEY`.
- [ ] Choose a strong **Postgres password** for the DB container.
- [ ] (For off-box backups) An **S3 bucket** (private, versioned) for DB dumps.

---

## 4. Phase 1 — Domain & DNS (Namecheap)

1. In Namecheap, register/activate your Student Pack domain (e.g. `yourname.me`).
2. Keep **BasicDNS** (Namecheap's free DNS). Do **not** switch nameservers to Route 53.
3. You'll add A records **after** the EC2 has its Elastic IP (Phase 4). Records needed:

| Type  | Host        | Value                   | Purpose                  |
| ----- | ----------- | ----------------------- | ------------------------ |
| A     | `api`       | EC2 Elastic IP          | Backend API + WebSockets |
| A     | `turn`      | EC2 Elastic IP          | TURN server (voice)      |
| CNAME | `@` / `www` | Cloudflare Pages target | Frontend (Option A)      |

> All-on-EC2 (Option B) instead: `A @ → EIP` and `A www → EIP`, no Cloudflare.

**Renewal warning:** the free `.me` lasts **1 year**. Set a reminder; check the
renewal price now so the site doesn't lapse.

---

## 5. Phase 2 — AWS Networking & Security Groups

Use the **default VPC** (simplest) with a public subnet, or create a VPC with one
public subnet. No private subnets / NAT needed for this single-instance design.

**Security Group for the EC2** (inbound):

| Port        | Protocol | Source           | Why                                               |
| ----------- | -------- | ---------------- | ------------------------------------------------- |
| 22          | TCP      | **your IP only** | SSH admin                                         |
| 80          | TCP      | 0.0.0.0/0        | HTTP (Caddy → Let's Encrypt challenge + redirect) |
| 443         | TCP      | 0.0.0.0/0        | HTTPS + `wss://`                                  |
| 3478        | TCP+UDP  | 0.0.0.0/0        | TURN/STUN                                         |
| 5349        | TCP+UDP  | 0.0.0.0/0        | TURN over TLS                                     |
| 49152–65535 | UDP      | 0.0.0.0/0        | TURN media relay range                            |

> **Do NOT open port 5432 (Postgres).** The database is a Docker container reached
> only over the internal compose network — it must never be exposed to the
> internet. Leave 5432 closed in the security group and do not publish it in
> Docker (`expose`, not `ports`).

---

## 6. Phase 3 — PostgreSQL in Docker (+ pgvector)

The database runs as a container on the EC2, using the official **pgvector** image
(same as local dev), with its data on a **named Docker volume** so it survives
container restarts and redeploys.

Key points (the container is defined in the compose file in §9):

- Image: `pgvector/pgvector:pg16` (Postgres 16 with the `vector` extension available).
- Data volume: `pgdata:/var/lib/postgresql/data` (this is what you back up in §14).
- Credentials come from `.env.prod` (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`).
- Reached by the API at host **`db`** (the compose service name), port 5432 — never
  exposed to the host/internet.
- Enable the vector extension once (the app's document embeddings need it):
  ```bash
  docker compose -f docker-compose.prod.yml exec db \
    psql -U englishtalker -d englishtalker -c "CREATE EXTENSION IF NOT EXISTS vector;"
  ```
- Final `DATABASE_URL` (note the **async** driver and the internal `db` host):
  ```
  postgresql+asyncpg://englishtalker:<password>@db:5432/englishtalker
  ```

> Because the DB lives on the instance's EBS volume, **losing the volume = losing
> your data**. §14 is not optional.

---

## 7. Phase 4 — EC2 Instance

1. Launch **EC2**: Amazon Linux 2023 (or Ubuntu 22.04), `t3.medium`, **40 GB gp3**
   (extra room for the database + Docker), your key pair, the EC2 security group,
   in a public subnet with **auto-assign public IP on**.
2. **Allocate an Elastic IP** and associate it with the instance (stable IP).
3. Point the Namecheap **A records** (`api`, `turn`) at the Elastic IP (Phase 1).
4. SSH in and install Docker + Compose:
   ```bash
   # Amazon Linux 2023
   sudo dnf update -y
   sudo dnf install -y docker git
   sudo systemctl enable --now docker
   sudo usermod -aG docker ec2-user
   # Docker Compose v2 plugin
   sudo mkdir -p /usr/local/lib/docker/cli-plugins
   sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
     -o /usr/local/lib/docker/cli-plugins/docker-compose
   sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
   # log out/in so the docker group applies
   ```
5. Get the code: `git clone <your repo>` (or pull built images from a registry).

---

## 8. Phase 5 — Frontend hosting (choose one)

The frontend (TanStack Start) currently **builds for Cloudflare** (`vite.config.ts`).

### Option A — Cloudflare Pages *(recommended: free, matches the build)*

1. Push the repo to GitHub; in Cloudflare Pages, **Create project → connect the
   repo**, set the build:
   - Build command: `npm run build`
   - Output: the Cloudflare Pages / TanStack Start output directory (Pages
     auto-detects; confirm against the built `dist/`).
   - Build env var: `VITE_API_BASE_URL=https://api.yourname.me/api/v1`
2. Add your custom domain `yourname.me` in Pages → it gives you a CNAME target;
   add that CNAME in Namecheap. Cloudflare handles TLS automatically.
3. Backend `CORS_ORIGINS=["https://yourname.me"]`.

### Option B — Run the frontend on the EC2 (single domain)

The Cloudflare bundle won't run under Node. Switch the Nitro preset to a Node
server, then containerize it:

1. Set the server preset to `node-server` (Nitro) in the app/vite config and
   rebuild; confirm you get a runnable Node entry (e.g. `.output/server/index.mjs`).
2. Add a `web` service to `docker-compose.prod.yml` running that Node server on
   `:3000`, and have **Caddy** route `/` → `web:3000`, `/api` + `/ws` → `api:8000`.
3. Build with `VITE_API_BASE_URL=https://yourname.me/api/v1`; set
   `CORS_ORIGINS=["https://yourname.me"]`.

> Recommendation: **Option A**. It's free, globally fast, auto-TLS, and needs no
> preset change. Use Option B only if you want everything on one box/domain.

---

## 9. Phase 6 — App deploy on EC2 (Caddy + api + postgres + redis)

Create these files on the EC2 (e.g. in `~/englishtalker/deploy/`).

`Caddyfile` (auto-HTTPS for the API; add the `web` block for Option B):

```
api.yourname.me {
    reverse_proxy api:8000
}

# Option B only — single-domain path routing:
# yourname.me {
#     handle /api/* { reverse_proxy api:8000 }
#     handle /ws/*  { reverse_proxy api:8000 }
#     handle        { reverse_proxy web:3000 }
# }
```

`docker-compose.prod.yml` (API + Postgres + Redis + Caddy; add `web` for Option B):

```yaml
services:
  api:
    image: <your-ecr-or-registry>/englishtalker-api:latest   # or build: ../backend
    env_file: .env.prod
    expose: ["8000"]
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    # NOTE: no `ports:` — the DB is reachable only inside the compose network.
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped

  caddy:
    image: caddy:2-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on: [api]
    restart: unless-stopped

volumes:
  pgdata:
  caddy_data:
  caddy_config:
```

`.env.prod` (chmod 600; never commit — see §11 for values).

Launch:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Caddy fetches a Let's Encrypt cert for `api.yourname.me` on first start (ports
80/443 must be open and DNS must already point at the EIP).

---

## 10. Phase 7 — TURN server (coturn) for voice

Voice (WebRTC) needs TURN to work behind strict/corporate NAT. Run coturn on the
same EC2.

1. **App change required:** the frontend currently uses STUN only. Add your TURN
   server to the `RTCPeerConnection` `iceServers` config (in the voice hook),
   e.g. `{ urls: "turn:turn.yourname.me:3478", username, credential }`.
2. Run coturn (Docker) with a config like:
   ```
   listening-port=3478
   tls-listening-port=5349
   min-port=49152
   max-port=65535
   realm=yourname.me
   # Prefer time-limited REST credentials; simplest is a static user:
   user=etturn:<strong-password>
   external-ip=<EIP>
   fingerprint
   lt-cred-mech
   ```
3. Open the ports from Phase 2. Test with `trickle-ice` (Google's WebRTC ICE test
   page) that a `relay` candidate appears.

> Deferrable for a soft launch: without TURN, voice still works for many users on
> home wifi (STUN only), just not everyone. Chat, warm-up, and STT don't need it.

---

## 11. Phase 8 — Production configuration (`.env.prod`)

```env
ENVIRONMENT=production          # enables the secret check; disables auto-create & seeding
DEBUG=false                     # turns off SQL echo (huge logs)
SECRET_KEY=<openssl rand -hex 32>     # app REFUSES to start with the default in prod
AUTO_CREATE_TABLES=false        # use Alembic migrations, never create_all
SEED_DEMO_DATA=false
CORS_ORIGINS=["https://yourname.me"]

# Database (Docker container on this box)
POSTGRES_USER=englishtalker
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=englishtalker
DATABASE_URL=postgresql+asyncpg://englishtalker:<strong-password>@db:5432/englishtalker

REDIS_URL=redis://redis:6379/0
ADMIN_USERNAMES=["<your-admin-username>"]
ANTHROPIC_API_KEY=<key>         # only if using the AI coach (costs $ per call)
```

**Secrets handling:** keep `.env.prod` on the box with `chmod 600` (or store the
values in **AWS SSM Parameter Store** and render the file on deploy). Never commit
secrets.

**Single worker:** keep the default `uvicorn` (one worker). Presence, kick-bans,
and rate-limits are in-memory — multiple workers would break them until moved to
Redis.

---

## 12. Phase 9 — Database migrations

Never use `create_all` in production. On every deploy, run Alembic:

```bash
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

Do this **once after** the DB container + `.env.prod` are ready (and after
`CREATE EXTENSION vector;`), and on every release that changes the schema.
**Take a DB backup before running migrations** (see §14).

---

## 13. Phase 10 — Verify HTTPS & core flows

- [ ] `https://api.yourname.me/api/v1/health` → `200`
- [ ] Cert is valid (padlock, no warning)
- [ ] `https://yourname.me` loads the app
- [ ] Register an account; the `ADMIN_USERNAMES` user gets the Admin link
- [ ] Mic works (needs HTTPS): warm-up STT + live-chat mic
- [ ] Two browsers in a room see each other (roster) and can chat
- [ ] Voice: test between two networks (wifi + mobile) — needs TURN
- [ ] Old admin-impersonation attack fails (a raw UUID as bearer → 401)

---

## 14. Phase 11 — Backups & monitoring (MANDATORY for a self-hosted DB)

With no RDS, **you** are responsible for the database. Do all three layers:

**A. Nightly logical backup (`pg_dump`) + off-box copy to S3**
Create `~/englishtalker/deploy/backup.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="/home/ec2-user/backups/englishtalker-$STAMP.sql.gz"
mkdir -p /home/ec2-user/backups
docker compose -f /home/ec2-user/englishtalker/deploy/docker-compose.prod.yml \
  exec -T db pg_dump -U englishtalker englishtalker | gzip > "$OUT"
# Copy off the box so an instance/volume loss can't take the backup with it:
aws s3 cp "$OUT" "s3://<your-backup-bucket>/db/" --storage-class STANDARD_IA
# Keep 14 days locally:
find /home/ec2-user/backups -name '*.sql.gz' -mtime +14 -delete
```
Schedule it: `crontab -e` → `0 3 * * * /home/ec2-user/englishtalker/deploy/backup.sh >> /home/ec2-user/backup.log 2>&1`
Give the EC2 an **IAM role** allowing `s3:PutObject` to that bucket (no keys on the box).

**B. EBS snapshots (whole-disk safety net)**
Enable **Amazon Data Lifecycle Manager** to snapshot the instance's EBS volume
daily and retain ~7. This captures the `pgdata` volume even if a `pg_dump` fails.

**C. Test a restore (do this before launch — an untested backup is not a backup):**
```bash
gunzip -c englishtalker-<stamp>.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U englishtalker englishtalker
```

**Monitoring:**
- **CloudWatch agent** on EC2: CPU/mem/**disk** alarms (disk > 80% is dangerous —
  the DB shares the volume).
- **Container logs**: `docker compose logs -f`; optionally ship to CloudWatch Logs.
- **App errors**: add Sentry (optional).
- **Uptime**: a free external monitor (e.g. UptimeRobot) hitting `/api/v1/health`.
- **Backup monitor**: alert if a new object hasn't landed in the S3 backup prefix
  in 24h (a silent backup failure is the classic way to lose data).

---

## 15. Phase 12 — CI/CD (GitHub Actions + Cloudflare Pages)

For a first version you'll ship daily, this pipeline is essential: it tests every
change, builds the image, and deploys safely (with a DB backup, migration, and
health check) so a bad push can't silently break production.

### Pipeline overview

```
push / PR ─▶ CI (test & lint)            push to main ─▶ CD (deploy backend)
             backend.yml   (pytest, ruff, mypy)          deploy.yml:
             frontend-web.yml (tsc, eslint, build)          verify → build → deploy
                                                             (backup → pull → migrate
                                                              → restart → health check)

frontend  ─▶ Cloudflare Pages auto-builds & deploys frontend-web/ on push to main
```

### Workflow files (in `.github/workflows/`)

| File | Trigger | Does |
|---|---|---|
| `backend.yml` | changes under `backend/**` | `ruff check`, `mypy`, `pytest` |
| `frontend-web.yml` | changes under `frontend-web/**` | `typecheck`, `lint`, `build` |
| `deploy.yml` | push to `main` (backend/deploy paths) + manual | test → build image → push to GHCR → SSH deploy to EC2 |
| `frontend.yml` | changes under `frontend/**` | legacy **Expo mobile app** — not the website |

> The website's frontend is `frontend-web/` (deployed via Cloudflare Pages). The
> old `frontend.yml` covers the separate Expo app in `frontend/`.

### What `deploy.yml` does on every push to `main`
1. **verify** — runs `ruff check` + `pytest` (never deploys a red build).
2. **build** — builds the API image and pushes it to **GHCR**
   (`ghcr.io/<owner>/englishtalker-api:latest` + `:<sha>`), layer-cached so daily
   pushes only upload the changed code layer.
3. **deploy** — SSHes to the EC2 and runs, in order:
   `backup.sh` → `docker compose pull api` → `alembic upgrade head` →
   `docker compose up -d` → **health check** (fails the run if the API isn't serving).

### One-time setup (you do this once)

**1. Create a GHCR read token** so the EC2 can pull the private image:
GitHub → Settings → Developer settings → **Personal access token (classic)** with
the `read:packages` scope. Save the value for the `GHCR_PAT` secret.

**2. Add repository secrets** (repo → Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `EC2_HOST` | Elastic IP or `api.yourname.me` |
| `EC2_USER` | `ec2-user` |
| `EC2_SSH_KEY` | the **private** key (PEM) for that user |
| `GHCR_PAT` | the `read:packages` token from step 1 |
| `HEALTHCHECK_URL` | `https://api.yourname.me/api/v1/health` |

**3. Prepare the EC2 deploy folder** `~/englishtalker/deploy/` containing
`docker-compose.prod.yml`, `Caddyfile`, `.env.prod` (chmod 600), and `backup.sh`
(chmod +x). The compose file's `api` service must reference the GHCR image
(`image: ghcr.io/<owner>/englishtalker-api:latest`).

**4. Connect Cloudflare Pages** to the repo (see §8, Option A) with build env
`VITE_API_BASE_URL=https://api.yourname.me/api/v1`. It then auto-deploys the
frontend on every push to `main` — no Action needed.

**5. (Recommended) Protect `main`** — require the `backend` and `frontend-web`
checks to pass before merging, so only green code reaches production.

### Daily workflow after setup
- Work on a branch → open a PR → CI runs automatically.
- Merge to `main` → `deploy.yml` ships the backend, Cloudflare Pages ships the
  frontend. Watch the **Actions** tab; a red run means it did **not** deploy.
- **Manual deploy / re-deploy:** Actions tab → `deploy` → **Run workflow**.

### Rollback via CI/CD
- **Backend:** re-run `deploy` from an earlier green commit, or on the EC2 pin the
  image to a previous tag (`ghcr.io/<owner>/englishtalker-api:<old-sha>`) and
  `docker compose up -d`.
- **Bad migration:** restore from the `pg_dump` that `backup.sh` took at the start
  of that same deploy (see §14 / §17).

### Hardening later (optional)
Swap the SSH deploy for **GitHub OIDC → AWS role → SSM Run Command** (no SSH key
in secrets, no inbound SSH port). Add a **manual approval** environment gate
before the deploy job.

---

## 16. Go-live checklist

- [ ] `ENVIRONMENT=production`, strong `SECRET_KEY`, `DEBUG=false`, `AUTO_CREATE_TABLES=false`, `SEED_DEMO_DATA=false`
- [ ] `CREATE EXTENSION vector;` done; `alembic upgrade head` clean
- [ ] `CORS_ORIGINS` = your real domain only
- [ ] Postgres port 5432 is **not** exposed (no `ports:`, closed in the SG)
- [ ] HTTPS valid on both frontend and API; mic/voice/STT tested over HTTPS
- [ ] TURN reachable; voice tested across two networks
- [ ] Admin user registered; admin gate + impersonation test verified
- [ ] **Nightly backup runs, lands in S3, and a restore was tested**
- [ ] EBS daily snapshots enabled; CloudWatch disk/CPU alarms armed; uptime monitor on
- [ ] Domain renewal reminder set (free `.me` = 1 year)
- [ ] SSH restricted to your IP; `.env.prod` is `chmod 600`; no secrets in the repo

---

## 17. Rollback & recovery

- **App rollback:** redeploy the previous image tag (`docker compose up -d` with
  the old tag). Keep the last known-good tag.
- **Bad migration:** stop the app, restore the DB from the pre-migration `pg_dump`
  (§14C), redeploy the matching old image. **Always back up before migrating.**
- **Volume/data corruption:** restore the latest `pg_dump` into a fresh `db`
  container (§14C), or roll the EBS volume back to the last snapshot.
- **Instance dies:** launch a new EC2, reattach the Elastic IP, `git pull`,
  restore the DB from the **S3** backup into a fresh `db` container, then
  `docker compose up -d`. (This is why the off-box S3 copy matters — a dead
  instance takes its local disk with it.)

---

## 18. Scaling beyond ~50/hour (later)

Two limits appear as you grow:

1. **In-memory state** (WebSocket presence, kick-bans, rate-limits) ties you to a
   single backend process. To run 2+ instances: move presence/pub-sub and
   rate-limit counters to **Redis**, then put the API behind an **ALB**.
2. **DB on the app box** competes for CPU/RAM/disk and can't scale independently.
   The clean upgrade is to move the database to **RDS** (managed, backups, bigger
   instances) — just point `DATABASE_URL` at the RDS endpoint and remove the
   `postgres` service. Do this before serious growth.

Whisper STT is CPU-heavy; if transcription load grows, cap concurrent
transcriptions or offload STT to the browser (Web Speech API) where possible.

---

## 19. Quick troubleshooting

| Symptom                                    | Likely cause                             | Fix                                                     |
| ------------------------------------------ | ---------------------------------------- | ------------------------------------------------------- |
| `api-1` won't start, `SECRET_KEY` error    | Default secret in production             | Set a real `SECRET_KEY`                                 |
| `UndefinedColumnError` on a query          | Migrations not run / `create_all` used   | `alembic upgrade head`; `AUTO_CREATE_TABLES=false`      |
| API can't resolve/connect to `db`          | DB container not healthy yet             | `docker compose ps`; wait for `db` healthy; check creds |
| `type "vector" does not exist`             | pgvector extension not enabled           | `CREATE EXTENSION vector;` in the app DB (§6)           |
| Mic / voice / STT silently fail            | Site not on HTTPS                        | Fix TLS; browsers block mic on http://                  |
| Voice connects but no audio for some users | No TURN / NAT                            | Deploy coturn; add it to `iceServers`                   |
| CORS errors in the browser                 | `CORS_ORIGINS` wrong                     | Set it to the exact frontend origin                     |
| Caddy can't get a cert                     | 80/443 closed or DNS not pointing at EIP | Open ports; verify the A record                         |
| Disk full / DB won't write                 | EBS volume filled (DB shares it)         | Grow the gp3 volume; check backup retention/log sizes   |

---

*Generated as the deployment plan for EnglishTalker. Companion files
(`docker-compose.prod.yml`, `Caddyfile`, `.env.prod` template, `backup.sh`, coturn
config) can be generated next on request.*
