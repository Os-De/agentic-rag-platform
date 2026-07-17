#!/usr/bin/env bash
# Production entrypoint: WEB_CONCURRENCY workers (default 1 for dev).
# Note: MemorySaver conversation memory and slowapi buckets are per-worker;
# for shared state use the Postgres checkpointer / Redis storage (docs §6).
set -euo pipefail
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-1}"
