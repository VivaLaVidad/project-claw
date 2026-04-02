#!/bin/sh
set -e

PORT="${PORT:-8765}"
WORKERS="${WORKERS:-4}"

exec gunicorn cloud_server.api_server_pro:app \
  -k uvicorn.workers.UvicornWorker \
  --workers "${WORKERS}" \
  --bind "0.0.0.0:${PORT}" \
  --timeout 120 \
  --graceful-timeout 30 \
  --keep-alive 20 \
  --access-logfile - \
  --error-logfile -
