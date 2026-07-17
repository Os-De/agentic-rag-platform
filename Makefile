# Convenience targets (use Git Bash / WSL on Windows, or copy the commands)

.PHONY: up up-all down logs ps dev test lint fmt ingest clean

up:            ## Start core stack (api, qdrant, postgres)
	docker compose up -d --build

up-all:        ## Start everything (all profiles)
	docker compose --profile monitoring --profile mlops --profile ui --profile tracing up -d --build

down:          ## Stop all services
	docker compose --profile monitoring --profile mlops --profile ui --profile tracing down

logs:          ## Tail API logs
	docker compose logs -f api

ps:            ## Show running services
	docker compose ps

dev:           ## Run API locally with reload (needs: docker compose up -d qdrant postgres)
	cd services/api && uvicorn app.main:app --reload --port 8000

test:          ## Run unit tests
	cd services/api && pytest tests -q

lint:          ## Lint all Python
	ruff check .

fmt:           ## Auto-format
	ruff format .

ingest:        ## Ingest sample documents via the API
	python scripts/ingest_samples.py

clean:         ## Remove containers AND volumes (destroys data!)
	docker compose --profile monitoring --profile mlops --profile ui --profile tracing down -v
