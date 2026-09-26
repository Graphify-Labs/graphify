"""Exact-versus-estimated query telemetry contracts."""

from graphify.token_usage import QueryUsage, measure_text


def test_measurement_uses_injected_model_tokenizer_exactly():
    measurement = measure_text("alpha beta", tokenizer=lambda text: [1, 2, 3])

    assert measurement.tokens == 3
    assert measurement.exact is True
    assert measurement.method == "model_tokenizer"


def test_missing_tokenizer_is_labeled_estimated_not_billable():
    measurement = measure_text("abcdefgh", tokenizer=None)

    assert measurement.tokens == 2
    assert measurement.exact is False
    assert measurement.method == "character_estimate"


def test_deterministic_graph_retrieval_records_zero_model_usage():
    usage = QueryUsage.for_retrieval(
        query="where is cache lookup",
        evidence="{}",
        tokenizer=lambda text: list(text),
        follow_up_count=1,
    )

    assert usage.llm_invoked is False
    assert usage.model_input_tokens == 0
    assert usage.model_output_tokens == 0
    assert usage.follow_up_count == 1
    assert usage.evidence_tokens == 2
