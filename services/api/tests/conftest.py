"""Test env: force SQLite so unit tests never need Postgres.

Must run before any `app.*` import (pytest imports conftest first).
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./.pytest.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
