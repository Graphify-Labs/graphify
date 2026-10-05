"""Behavioral contracts for advisory and partition corpus thresholds."""

from graphify.corpus_policy import assess_corpus


def test_file_limit_requires_partition_even_for_small_sources():
    assessment = assess_corpus(total_files=501, total_words=10_000)

    assert assessment.partition_required is True
    assert assessment.reasons == ("file_count",)
    assert "501 files" in assessment.message


def test_word_limit_is_a_partition_gate_not_a_token_claim():
    assessment = assess_corpus(total_files=10, total_words=2_000_001)

    assert assessment.partition_required is True
    assert assessment.reasons == ("word_count",)
    assert "words" in assessment.message
    assert "tokens" not in assessment.message.lower()


def test_large_advisory_does_not_force_partition_below_hard_gate():
    assessment = assess_corpus(total_files=400, total_words=500_000)

    assert assessment.advisory is True
    assert assessment.partition_required is False
    assert "can be processed as one graph" in assessment.message


def test_existing_graph_queries_bypass_fresh_extraction_partition_policy():
    assessment = assess_corpus(
        total_files=2_000,
        total_words=4_000_000,
        existing_graph=True,
    )

    assert assessment.partition_required is False
    assert assessment.existing_graph is True
    assert "existing graph" in assessment.message.lower()
