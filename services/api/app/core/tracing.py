"""OpenTelemetry LLM tracing (ADR-011) — vendor-neutral alternative to LangSmith.

TRACING_BACKEND selects one:
  none       no OTel (LangSmith still works independently via LANGSMITH_* env vars)
  phoenix    OpenInference (TraceAI) instrumentation → Arize Phoenix UI (:6006)
  traceloop  OpenLLMetry auto-instrumentation → any OTLP backend (Jaeger UI :16686)

Both run under `docker compose --profile tracing up -d`. Traces never leave your
infrastructure — the data-sovereignty answer for enterprise deployments.
"""

import structlog

from app.core.config import get_settings

log = structlog.get_logger()


def configure_tracing() -> None:
    """Called once at startup. Failures are logged, never fatal."""
    s = get_settings()
    backend = s.tracing_backend.lower().strip()

    if backend in ("", "none"):
        return

    if backend == "phoenix":
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "rag-api"}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=s.phoenix_collector_endpoint))
        )
        trace.set_tracer_provider(provider)
        LangChainInstrumentor().instrument(tracer_provider=provider)
        log.info("tracing enabled", backend="phoenix (OpenInference)",
                 endpoint=s.phoenix_collector_endpoint)
        return

    if backend == "traceloop":
        from traceloop.sdk import Traceloop

        # Points at any OTLP collector (Jaeger in the tracing profile);
        # instruments LangChain, OpenAI, Anthropic, and Qdrant automatically.
        Traceloop.init(app_name="rag-api", api_endpoint=s.otlp_endpoint)
        log.info("tracing enabled", backend="traceloop (OpenLLMetry)",
                 endpoint=s.otlp_endpoint)
        return

    log.warning("unknown TRACING_BACKEND — tracing disabled", value=backend)
