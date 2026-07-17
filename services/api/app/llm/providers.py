"""Multi-provider LLM + embeddings factory (see ADR-003 / ADR-004).

One seam for the whole platform: local (Ollama) and API models (OpenAI, Anthropic)
behind the LangChain chat-model interface, selectable per request or via env.
Imports are lazy so unused providers cost nothing.
"""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings

SUPPORTED_PROVIDERS = ("ollama", "openai", "anthropic")


def get_chat_model(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    s = get_settings()
    provider = (provider or s.llm_provider).lower()
    temperature = s.llm_temperature if temperature is None else temperature

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model or s.ollama_model,
            base_url=s.ollama_base_url,
            temperature=temperature,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI  # needs OPENAI_API_KEY

        return ChatOpenAI(model=model or s.openai_model, temperature=temperature)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic  # needs ANTHROPIC_API_KEY

        return ChatAnthropic(model=model or s.anthropic_model, temperature=temperature)

    raise ValueError(f"Unknown LLM provider '{provider}'. Supported: {SUPPORTED_PROVIDERS}")


def get_embeddings(provider: str | None = None) -> Embeddings:
    """NOTE: embedding model defines the vector space — switching providers/models
    requires re-ingesting into a fresh collection (dimension is probed at startup)."""
    s = get_settings()
    provider = (provider or s.embedding_provider).lower()

    if provider == "fastembed":
        # Local, CPU, no API key. First use downloads the model (~100 MB, cached).
        from langchain_community.embeddings import FastEmbedEmbeddings

        return FastEmbedEmbeddings(model_name=s.fastembed_model)
    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(model=s.ollama_embedding_model, base_url=s.ollama_base_url)
    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=s.openai_embedding_model)

    raise ValueError(f"Unknown embedding provider '{provider}'")
