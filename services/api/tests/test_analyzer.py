"""The analyzer must NEVER break the pipeline — malformed LLM output falls back."""

from app.agents.analyzer import parse_analysis


def test_clean_json():
    raw = (
        '{"corrected_query": "What is the best phase to run the final step?", '
        '"was_corrected": true, "wants_latest_phase": true, "route": "retrieve"}'
    )
    a = parse_analysis(raw, original_question="What is the best fase to run the final?")
    assert a.was_corrected
    assert a.wants_latest_phase
    assert a.route == "retrieve"
    assert "phase" in a.corrected_query


def test_json_wrapped_in_chatter_and_fences():
    raw = 'Sure! Here you go:\n```json\n{"corrected_query": "hello", '
    raw += '"was_corrected": false, "wants_latest_phase": false, "route": "direct"}\n```'
    a = parse_analysis(raw, original_question="hello")
    assert a.route == "direct"
    assert not a.was_corrected


def test_garbage_falls_back_to_original():
    a = parse_analysis("I cannot help with that.", original_question="my query")
    assert a.corrected_query == "my query"
    assert not a.was_corrected
    assert a.route == "retrieve"


def test_invalid_route_defaults_to_retrieve():
    raw = '{"corrected_query": "q", "was_corrected": false, "route": "banana"}'
    assert parse_analysis(raw, "q").route == "retrieve"


def test_was_corrected_requires_actual_change():
    raw = '{"corrected_query": "same", "was_corrected": true, "route": "retrieve"}'
    assert parse_analysis(raw, "same").was_corrected is False


def test_empty_corrected_query_falls_back():
    raw = '{"corrected_query": "", "was_corrected": true, "route": "retrieve"}'
    assert parse_analysis(raw, "original").corrected_query == "original"
