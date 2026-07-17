# Deploy to GCP (Phase 9)

Managed topology: **Cloud Run** (API + UI) · **Qdrant Cloud** (free tier) ·
**Cloud SQL for PostgreSQL** · **Secret Manager** · GitHub Actions CD.

## One-time setup (gcloud CLI)

```bash
gcloud auth login
gcloud projects create rag-platform-<unique> --set-as-default
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com

# 1. PostgreSQL (db-f1-micro = cheapest)
gcloud sql instances create rag-pg --database-version=POSTGRES_16 \
  --tier=db-f1-micro --region=europe-west1
gcloud sql users set-password postgres --instance=rag-pg --password="<STRONG-PASSWORD>"
gcloud sql databases create rag --instance=rag-pg

# 2. Qdrant Cloud: free cluster at https://cloud.qdrant.io → QDRANT_URL + API key

# 3. Secrets
echo -n "$(openssl rand -hex 32)" | gcloud secrets create jwt-secret --data-file=-
echo -n "<OPENAI_API_KEY>" | gcloud secrets create openai-key --data-file=-

# 4. Deploy API from the GHCR image (or mirror to Artifact Registry)
gcloud run deploy rag-api \
  --image ghcr.io/<you>/<repo>/rag-api:latest \
  --region europe-west1 --allow-unauthenticated \
  --port 8000 --min-instances 0 --max-instances 3 \
  --add-cloudsql-instances <project>:europe-west1:rag-pg \
  --set-secrets JWT_SECRET_KEY=jwt-secret:latest,OPENAI_API_KEY=openai-key:latest \
  --set-env-vars ENVIRONMENT=prod,LLM_PROVIDER=openai,\
DATABASE_URL="postgresql+psycopg://postgres:<pw>@/rag?host=/cloudsql/<project>:europe-west1:rag-pg",\
QDRANT_URL="<qdrant-cloud-url>",CORS_ORIGINS="https://<ui-url>"

# 5. UI: gcloud run deploy rag-ui --image ghcr.io/<you>/<repo>/rag-ui:latest \
#        --port 8501 --set-env-vars API_BASE_URL=https://<rag-api-url>
```

Notes: Cloud Run scales to zero (cold starts include FastEmbed model load — mount
min-instances 1 if that hurts); first request after deploy warms the cache.

## Checklist before going live

- [ ] Secrets only in Secret Manager
- [ ] `ADMIN_PASSWORD` rotated after first login
- [ ] CORS restricted to the UI origin
- [ ] Cloud SQL: private IP or authorized networks only
- [ ] Billing budget alert configured
