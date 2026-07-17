# Deploy to Azure (Phase 9)

Managed topology: **Container Apps** (API + UI) · **Qdrant Cloud** (free tier) ·
**Azure Database for PostgreSQL Flexible Server** · **Key Vault** for secrets ·
GitHub Actions CD (already in `.github/workflows/cd.yml`).

LLMs in the cloud: use API providers (OpenAI/Anthropic/Azure OpenAI). Self-hosted
Ollama needs a GPU VM — start with API providers, optimize cost later.

## One-time setup (Azure CLI)

```bash
az login
az group create -n rag-platform -l westeurope

# 1. PostgreSQL (adjust sku for budget; B1ms is the cheapest burstable)
az postgres flexible-server create -g rag-platform -n rag-pg \
  --admin-user ragadmin --admin-password "<STRONG-PASSWORD>" \
  --sku-name Standard_B1ms --tier Burstable --storage-size 32 --version 16
az postgres flexible-server db create -g rag-platform -s rag-pg -d rag

# 2. Qdrant Cloud: create a free cluster at https://cloud.qdrant.io
#    → note QDRANT_URL (https://xyz.cloud.qdrant.io:6333) and API key.
#    (Set env QDRANT_URL; add api_key support in vectorstore.py — 3 lines.)

# 3. Key Vault for secrets
az keyvault create -g rag-platform -n rag-kv
az keyvault secret set --vault-name rag-kv -n jwt-secret --value "$(openssl rand -hex 32)"
az keyvault secret set --vault-name rag-kv -n openai-key --value "<OPENAI_API_KEY>"

# 4. Container Apps environment
az containerapp env create -g rag-platform -n rag-env -l westeurope

# 5. API app (image pushed by the CD workflow on git tag)
az containerapp create -g rag-platform -n rag-api \
  --environment rag-env \
  --image ghcr.io/<you>/<repo>/rag-api:latest \
  --target-port 8000 --ingress external \
  --min-replicas 1 --max-replicas 3 \
  --secrets jwt-secret=keyvaultref:<kv-uri>/secrets/jwt-secret,identityref:system \
  --env-vars ENVIRONMENT=prod LLM_PROVIDER=openai \
    JWT_SECRET_KEY=secretref:jwt-secret \
    DATABASE_URL="postgresql+psycopg://ragadmin:<pw>@rag-pg.postgres.database.azure.com:5432/rag" \
    QDRANT_URL="<qdrant-cloud-url>" CORS_ORIGINS="https://<your-ui-domain>"

# 6. UI app (optional — same pattern with rag-ui image, target-port 8501,
#    env API_BASE_URL=https://<rag-api-fqdn>)
```

## CD wiring

1. Repo variable `DEPLOY_TARGET=azure`.
2. Secret `AZURE_CREDENTIALS`: `az ad sp create-for-rbac --role contributor --scopes /subscriptions/<sub>/resourceGroups/rag-platform --sdk-auth`
3. `git tag v1.0.0 && git push --tags` → build → push → deploy → smoke test.

## Checklist before going live

- [ ] `JWT_SECRET_KEY` from Key Vault, never in env files
- [ ] `ADMIN_PASSWORD` rotated after first login
- [ ] CORS restricted to the UI origin
- [ ] Postgres firewall: allow only Container Apps outbound IPs
- [ ] Budget alert on the resource group (Cost Management)
