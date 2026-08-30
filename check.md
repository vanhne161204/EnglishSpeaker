Step 2 — On the EC2 box

2a. Open the firewall ports

AWS Console → EC2 → Instances → click your instance → Security tab → click the security group name → Edit inbound rules → Add rule three times:

┌────────────┬──────────┬─────────────┬───────────┬──────────────────┐
│    Type    │ Protocol │ Port range  │  Source   │   Description    │
├────────────┼──────────┼─────────────┼───────────┼──────────────────┤
│ Custom TCP │ TCP      │ 3478        │ 0.0.0.0/0 │ TURN control TCP │
├────────────┼──────────┼─────────────┼───────────┼──────────────────┤
│ Custom UDP │ UDP      │ 3478        │ 0.0.0.0/0 │ TURN control UDP │
├────────────┼──────────┼─────────────┼───────────┼──────────────────┤
│ Custom UDP │ UDP      │ 49160-49200 │ 0.0.0.0/0 │ TURN media relay │
└────────────┴──────────┴─────────────┴───────────┴──────────────────┘

Click Save rules.

Both 3478 rules are needed. UDP is the fast path; TCP is the fallback for networks that block UDP.

2b. SSH in

ssh -i "D:\personal\EnlishTalker\local-key-access-english-talker-ec2-instance.pem" ec2-user@13.213.87.223

2c. Get the new compose file onto the box

The deploy workflow does not pull git — it only runs docker compose in that folder. So the new coturn service is not there yet.

cd ~/englishtalker/deploy
git rev-parse --is-inside-work-tree 2>/dev/null && echo "IS A GIT CLONE" || echo "NOT A CLONE"

- If it says IS A GIT CLONE → run git pull (from the repo root if needed).
- If it says NOT A CLONE → the file was hand-copied. Open it and paste the coturn service in yourself:
nano docker-compose.prod.yml
- Copy the coturn: block from deploy/docker-compose.prod.yml in your local repo. Put it above the caddy: service, at the same indent level (2 spaces).

Confirm it landed:

grep -c coturn docker-compose.prod.yml     # must be more than 0

2d. Add the TURN settings to .env.prod

This generates a random password and appends everything in one go. Note >> (append), not > — a single > would wipe your file.

cd ~/englishtalker/deploy
cp .env.prod .env.prod.bak          # safety copy first

TURN_PW=$(openssl rand -hex 24)
cat >> .env.prod <<EOF

# TURN relay for room voice (docs/DEPLOYMENT.md §10)
TURN_REALM=englishspeaker.me
TURN_USER=etturn
TURN_PASSWORD=$TURN_PW
TURN_EXTERNAL_IP=13.213.87.223
EOF

chmod 600 .env.prod
echo "=== COPY THIS PASSWORD, you need it in Step 3 ==="
echo "$TURN_PW"

Save that password somewhere now. Step 3 needs the exact same value.

2e. Start coturn

cd ~/englishtalker/deploy
docker compose --env-file .env.prod -f docker-compose.prod.yml config | grep -A 12 "coturn:"

Check the output: --realm=englishspeaker.me, --user=etturn:<your password>, --external-ip=13.213.87.223. If any is blank, .env.prod is wrong — fix it before starting.

Then:

docker compose --env-file .env.prod -f docker-compose.prod.yml up -d coturn
docker compose --env-file .env.prod -f docker-compose.prod.yml logs coturn | tail -30

Healthy logs mention Listener opened on : 3478 and Relay ... 49160. If you see CONFIG ERROR or the container keeps restarting, a variable is empty.

Verify from your PowerShell (back on Windows):

Test-NetConnection turn.englishspeaker.me -Port 3478

TcpTestSucceeded : True means DNS and the security group are both right. (This only tests TCP — UDP is checked properly in step 3.)

---
Step 3 — Cloudflare Pages

This is the step people skip, and then nothing changes.

1. Cloudflare dashboard → Workers & Pages → click your frontend-web Pages project.
2. Settings → Environment variables (newer UI calls this Variables and Secrets).
3. Under Production, add these three:

┌───────────────────┬────────────────────────────────────────────────────────────────────────┐
│       Name        │                                 Value                                  │
├───────────────────┼────────────────────────────────────────────────────────────────────────┤
│ VITE_TURN_URL     │ turn:turn.englishspeaker.me:3478,turn:turn.englishspeaker.me:3478?tran │
│                   │ sport=tcp                                                              │
├───────────────────┼────────────────────────────────────────────────────────────────────────┤
│ VITE_TURN_USERNAM │ etturn                                                                 │
│ E                 │                                                                        │
├───────────────────┼────────────────────────────────────────────────────────────────────────┤
│ VITE_TURN_CREDENT │ the password you saved in step 2d                                      │
│ IAL               │                                                                        │
└───────────────────┴────────────────────────────────────────────────────────────────────────┘

Add the same three under Preview too, if you test preview deploys.

4. Save.
5. Rebuild — this is mandatory. Go to Deployments, find the newest one, click the ⋯ menu → Retry deployment. Or push an empty commit:
git commit --allow-empty -m "chore: rebuild with TURN env vars"; git push

Vite replaces import.meta.env.VITE_* with literal text when it builds. The variable is not read at runtime. So a saved variable with no rebuild does absolutely nothing.

---
Verify the whole thing

A. Check the relay works — open Google's Trickle ICE page (https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/):

1. Remove the default STUN server row.
2. Add: TURN URI turn:turn.englishspeaker.me:3478, username etturn, password = yours.
3. Click Gather candidates.

You need at least one row with Component Type = relay. If you only get host and srflx, the relay is unreachable — recheck the UDP rules and TURN_EXTERNAL_IP.

B. Check the real call — join the same room from your laptop on wifi and your phone on mobile data. Do not use the same wifi for both; that can succeed for the wrong reason and hide the problem.

If it still fails, the app now tells you which side is wrong: it says "none is configured" if step 3 didn't take effect, and "the TURN relay did not answer" if step 2 is the problem.

---
One thing to know

The TURN password ships inside your JavaScript bundle. Anyone viewing your site can read it. That is normal for static TURN credentials, but it means a stranger could use your relay's bandwidth. It's fine for now. If traffic grows, switch to coturn's time-limited REST credentials, where the backend hands out a short-lived token instead.


cat >> .env.prod <<'EOF'

# --- AI provider layer (docs/18_AI_Provider_Architecture.md) ---
OPENAI_API_KEY=<your-openai-key-here>
AI_MONTHLY_BUDGET_USD=10
AI_ENABLED=true

# MUST be "tiny" — the Dockerfile pre-downloads only tiny under HF_HOME.
# Unset, the code default "base" downloads ~150MB on the FIRST transcribe
# request, blocking it. It looks exactly like a broken microphone.
STT_MODEL=tiny
EOF