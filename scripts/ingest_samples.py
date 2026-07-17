"""Ingest every file in data/samples/ through the API (login → upload).

Usage:  python scripts/ingest_samples.py  [--api http://localhost:8000]
Requires: pip install httpx   (already in services/api/requirements-dev.txt)
"""

import argparse
import os
from pathlib import Path

import httpx

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", "admin@example.com"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "admin123"))
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=120) as client:
        resp = client.post(
            "/api/v1/auth/token", data={"username": args.email, "password": args.password}
        )
        resp.raise_for_status()
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        for path in sorted(SAMPLES_DIR.glob("*")):
            if path.suffix.lower() not in {".txt", ".md", ".markdown", ".pdf"}:
                continue
            r = client.post(
                "/api/v1/ingest",
                headers=headers,
                files={"file": (path.name, path.read_bytes())},
            )
            if r.status_code == 201:
                print(f"✔ {path.name}: {r.json()['num_chunks']} chunks")
            else:
                print(f"✘ {path.name}: {r.status_code} {r.text}")

        docs = client.get("/api/v1/documents", headers=headers).json()
        print(f"\nKnowledge base now holds {len(docs)} document(s).")


if __name__ == "__main__":
    main()
