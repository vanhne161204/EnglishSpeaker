#!/usr/bin/env bash
# Nightly database backup (see docs/DEPLOYMENT.md §14).
# Dumps the Postgres container, gzips it, and (optionally) copies it off-box to S3.
# Runs before every deploy and on a cron schedule.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# `--env-file` is required so Compose can substitute the ${VAR} placeholders
# (Postgres creds, coturn settings) in the compose file.
COMPOSE="docker compose --env-file ${DEPLOY_DIR}/.env.prod -f ${DEPLOY_DIR}/docker-compose.prod.yml"
BACKUP_DIR="${HOME}/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/englishtalker-${STAMP}.sql.gz"

# Optional: set to your bucket to copy backups off the instance.
# The EC2 needs an IAM role allowing s3:PutObject to this bucket (no keys on the box).
S3_BUCKET="${BACKUP_S3_BUCKET:-}"

mkdir -p "${BACKUP_DIR}"

echo "[backup] dumping database → ${OUT}"
${COMPOSE} exec -T db pg_dump -U englishtalker englishtalker | gzip > "${OUT}"

if [[ -n "${S3_BUCKET}" ]]; then
  echo "[backup] copying to s3://${S3_BUCKET}/db/"
  aws s3 cp "${OUT}" "s3://${S3_BUCKET}/db/" --storage-class STANDARD_IA
fi

# Keep 14 days of local backups.
find "${BACKUP_DIR}" -name '*.sql.gz' -mtime +14 -delete

echo "[backup] done"
