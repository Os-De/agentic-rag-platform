# Platform Overview (sample document)

The Enterprise-Grade Agentic RAG Platform lets authenticated users upload documents
and ask questions answered strictly from those documents, with citations.

## Components

The ingestion pipeline extracts text from uploaded files (.txt, .md, .pdf, .docx,
.html), splits it into overlapping chunks with a recursive character splitter,
extracts structural metadata such as phase numbers, embeds each chunk, and upserts
the vectors into a Qdrant collection. Identical content is deduplicated by hash, so
re-uploading the same file never creates duplicates. Every upload is registered in
PostgreSQL with a content hash and chunk count.

The agentic RAG pipeline is a LangGraph state machine. A query analyzer runs first:
it fixes spelling errors, clarifies vague terms, routes small talk away from
retrieval, and detects when the user asks about the last or final phase — in that
case retrieval ranks chunks by their phase number metadata instead of text
similarity alone. The agent then retrieves top-k chunks from Qdrant, grades each
chunk for relevance, rewrites the query once if nothing relevant was found, and
generates a grounded, cited answer. If the context still lacks the answer, the
agent says it does not know instead of guessing. Conversations have memory: passing
the conversation identifier back continues the thread.

The security layer uses OAuth2 password login that issues JWT tokens, with rate
limiting on login and chat. Role-based access control defines three roles: viewer
(chat and read), engineer (also ingest documents), and admin (also manage users and
read the audit log). Every privileged action is written to an audit trail, and
accounts can be disabled without deleting their history.

The LLM layer is provider-agnostic: requests can target local models served by
Ollama or API models from OpenAI and Anthropic, chosen per request.

## Operations

Observability combines LangSmith traces for agent behavior with Prometheus metrics
and a provisioned Grafana dashboard covering request rates, error ratio, agent
latency per provider, query corrections, and retrieval score coverage. Alert rules
fire on API downtime, high error rate, slow responses, and low retrieval scores.
MLflow tracks fine-tuning experiments, RAGAS evaluates answer quality with CI
thresholds, and a scheduled drift job compares production queries against a
reference distribution. Production deployment uses Docker Compose behind a Caddy
TLS proxy or managed containers on Azure and GCP, shipped by a tag-triggered CD
pipeline.
