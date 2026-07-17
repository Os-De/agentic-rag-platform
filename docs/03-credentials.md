# Credentials Guide — add/change username & password per service

## 1. Platform API + Streamlit UI (same accounts)

The Streamlit UI logs in through the API, so there is only ONE user system.

**First admin** comes from `.env` (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) — seeded only once, on first startup with an empty database. Editing `.env` later does NOT change an existing user.

- **Change your password:** login at http://localhost:8000/docs → `POST /api/v1/auth/change-password` with `{"current_password": "...", "new_password": "..."}`.
- **Add a user:** as admin → `POST /api/v1/auth/register` with email, password, role (`viewer` / `engineer` / `admin`).
- **Change role / disable a user:** `GET /api/v1/admin/users` (copy the id) → `PATCH /api/v1/admin/users/{id}` with `{"role": "engineer"}` or `{"is_active": false}`.
- **Forgot the admin password?** Reset the database: `docker compose down && docker volume rm enterprise-gradeagenticragplatform_pgdata`, set new values in `.env`, start again (⚠ deletes users/registry/audit, not vectors).

## 2. Grafana — http://localhost:3000

- **First-time default:** `admin / admin` (from `GF_SECURITY_ADMIN_*` in `docker-compose.yml` — applies only on first start of the volume).
- **Change password:** log in → click the profile icon (bottom-left) → *Change password*.
- **Reset from terminal (if locked out):** `docker exec rag-grafana grafana cli admin reset-admin-password NewPass123`
- **Add users:** ☰ menu → *Administration → Users and access → Users → New user*.
- Production: password comes from the `GRAFANA_PASSWORD` shell variable (`docker-compose.prod.yml`).

## 3. Prometheus — http://localhost:9090

No authentication by default (and in prod it is bound to localhost only — reached via SSH tunnel, which is the recommended protection). To force basic auth anyway:

1. Generate a bcrypt hash: `docker run --rm httpd:2.4-alpine htpasswd -nbB admin 'YourPass'` (copy the part after `admin:`).
2. Create `monitoring/prometheus/web.yml`:
   ```yaml
   basic_auth_users:
     admin: "$2y$10$...paste-hash-here..."
   ```
3. In `docker-compose.yml` under `prometheus:` add the mount and flag:
   ```yaml
   volumes:
     - ./monitoring/prometheus/web.yml:/etc/prometheus/web.yml:ro
   command: ["--config.file=/etc/prometheus/prometheus.yml", "--web.config.file=/etc/prometheus/web.yml"]
   ```
4. `docker compose up -d prometheus`. Note: Grafana's datasource and any scrapers must then send the same credentials.

## 4. Qdrant — http://localhost:6333/dashboard

No auth by default. To protect it with an API key:

1. In `docker-compose.yml` under `qdrant:` add:
   ```yaml
   environment:
     QDRANT__SERVICE__API_KEY: your-secret-key
   ```
2. Give the API the same key — in `services/api/app/rag/vectorstore.py`, change one line:
   ```python
   return QdrantClient(url=get_settings().qdrant_url, api_key="your-secret-key")
   ```
   (better: add `qdrant_api_key: str = ""` to `core/config.py` and read it from `.env`).
3. `docker compose up -d --build`. The dashboard will now ask for the key.

## 5. MLflow — http://localhost:5000

No auth by default. To enable the built-in basic auth:

1. In `docker-compose.yml`, append `--app-name basic-auth` to the mlflow `command:`.
2. Restart: `docker compose --profile mlops up -d mlflow`. Default login: `admin / password1234`.
3. Change it immediately:
   ```bash
   curl -u admin:password1234 -X PATCH http://localhost:5000/api/2.0/mlflow/users/update-password \
     -H "Content-Type: application/json" -d '{"username": "admin", "password": "NewPass123"}'
   ```
4. Add users: `POST /api/2.0/mlflow/users/create` with the same `-u admin:...` header.

## 6. Phoenix (:6006) & Jaeger (:16686) — tracing profile

No authentication by default on either; both are dev tools bound to localhost use.
Do not expose them publicly — in production keep them off the proxy (the prod
compose doesn't include them) or bind to `127.0.0.1` like Prometheus/Grafana and
reach them via SSH tunnel.

## 7. PostgreSQL (internal, no dashboard)

Dev credentials `rag / rag` live in `docker-compose.yml` (`POSTGRES_*`) and must match `DATABASE_URL`. The password is baked into the volume on first start — to change it later: `docker exec -it rag-postgres psql -U rag -c "ALTER USER rag WITH PASSWORD 'NewPass';"` then update `DATABASE_URL` everywhere and restart the API. Production reads `POSTGRES_PASSWORD` from the shell environment.

---

**Rule of thumb:** dev defaults are fine on your laptop; before anything is reachable from the internet, every service above must have a changed password or be unexposed (the prod compose already unexposes Prometheus/Grafana/Qdrant/Postgres — only Caddy's 80/443 are public).
