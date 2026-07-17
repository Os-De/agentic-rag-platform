"""Rate limiting (Phase 4) via slowapi — per-client-IP token buckets.

Limits are env-tunable (RATE_LIMIT_LOGIN / RATE_LIMIT_CHAT). Note: the default
in-memory storage is per-process; with multiple uvicorn workers each worker has
its own bucket. For strict global limits point slowapi at Redis (documented in
architecture §6).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
