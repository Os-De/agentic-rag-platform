from app.core.config import Settings, get_settings


def test_defaults_are_sane():
    s = Settings(_env_file=None)
    assert s.llm_provider in ("ollama", "openai", "anthropic")
    assert s.chunk_overlap < s.chunk_size
    assert s.retrieval_top_k >= 1


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CHUNK_SIZE", "512")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.llm_provider == "anthropic"
        assert s.chunk_size == 512
    finally:
        get_settings.cache_clear()  # don't leak into other tests
