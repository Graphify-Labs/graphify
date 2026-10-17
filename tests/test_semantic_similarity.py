"""Tests for cross-file semantic similarity reconciliation (#3948)."""
from __future__ import annotations

import pytest

from graphify.semantic_similarity import (
    _node_text,
    _tokenize,
    reconcile_semantic_similarity,
)


def test_tokenize_filters_stop_words_and_short_tokens():
    text = "The quick brown fox jumps over the lazy dog and 123 rules"
    tokens = _tokenize(text)
    assert "the" not in tokens
    assert "and" not in tokens
    assert "123" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens
    assert "rules" in tokens


def test_node_text_aggregates_rationale_and_label():
    node = {
        "id": "concept_a",
        "label": "Authentication Invariant",
        "rationale": "Always verify cryptographic signatures before state mutation",
        "file_type": "rationale",
    }
    text = _node_text(node)
    assert "Always verify cryptographic signatures" in text
    assert "Authentication Invariant" in text


def test_reconcile_emits_semantically_similar_to_for_high_cosine():
    nodes = [
        {
            "id": "doc_a_rule",
            "label": "Tenant Isolation Policy",
            "rationale": "Enforce tenant boundary isolation across multi-tenant database transactions and storage shards",
            "file_type": "rationale",
            "source_file": "docs/arch/isolation.md",
        },
        {
            "id": "doc_b_rule",
            "label": "Tenant Isolation Requirement",
            "rationale": "Enforce tenant boundary isolation across multi-tenant database transactions and storage shards",
            "file_type": "concept",
            "source_file": "policies/security.md",
        },
    ]
    edges = []
    updated = reconcile_semantic_similarity(nodes, edges, report=False)
    assert len(updated) == 1
    edge = updated[0]
    assert edge["source"] == "doc_a_rule"
    assert edge["target"] == "doc_b_rule"
    assert edge["relation"] == "semantically_similar_to"
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] >= 0.85


def test_reconcile_catches_paraphrased_rule_with_rare_term_overlap():
    """Concrete case from #3948:
    Two documents state the same core design rule in different words and
    surrounded by lengthy document-specific material, diluting global TF-IDF
    cosine to ~0.37. The shared low-frequency terms allow the second
    acceptance path to identify the pair.
    """
    shared_core = (
        "asynchronous idempotent retry backoff with jitter and deadletter queue"
    )
    long_doc_1 = (
        f"Billing pipeline settlement batch processing architecture. {shared_core}. "
        "Contains extensive background regarding invoice lifecycle, chargeback limits, "
        "reconciliation schedules, and compliance requirements for PCI auditing."
    )
    long_doc_2 = (
        f"Notification dispatch cluster operations manual. {shared_core}. "
        "Covers gateway failover thresholds, SMS rate-limiting headers, APNs TLS certificates, "
        "and subscriber webhook circuit breakers."
    )

    nodes = [
        {
            "id": "billing_retry",
            "label": "Settlement Retry Strategy",
            "rationale": long_doc_1,
            "file_type": "rationale",
            "source_file": "services/billing/SPEC.md",
        },
        {
            "id": "notification_retry",
            "label": "Dispatch Failure Handling",
            "rationale": long_doc_2,
            "file_type": "concept",
            "source_file": "services/notifications/README.md",
        },
    ]

    edges = []
    # Moderate cosine path with shared rare terms
    updated = reconcile_semantic_similarity(
        nodes,
        edges,
        cosine_threshold=0.65,
        moderate_cosine_threshold=0.25,
        min_rare_terms=4,
        report=False,
    )
    assert len(updated) == 1
    edge = updated[0]
    assert edge["relation"] == "semantically_similar_to"
    assert edge["confidence"] == "INFERRED"
    assert 0.65 <= edge["confidence_score"] <= 0.95


def test_reconcile_skips_same_source_file():
    nodes = [
        {
            "id": "concept_1",
            "label": "Memory Pool",
            "rationale": "Fixed size buffer chunk allocator to eliminate heap fragmentation",
            "file_type": "concept",
            "source_file": "src/allocator.c",
        },
        {
            "id": "concept_2",
            "label": "Buffer Pool",
            "rationale": "Fixed size buffer chunk allocator to eliminate heap fragmentation",
            "file_type": "rationale",
            "source_file": "src/allocator.c",
        },
    ]
    edges = []
    updated = reconcile_semantic_similarity(nodes, edges, report=False)
    assert len(updated) == 0


def test_reconcile_preserves_existing_edge_without_duplicate():
    nodes = [
        {
            "id": "rule_a",
            "label": "Data Encryption",
            "rationale": "AES-GCM encryption for all sensitive payloads at rest and in transit",
            "file_type": "rationale",
            "source_file": "security/spec.md",
        },
        {
            "id": "rule_b",
            "label": "Payload Protection",
            "rationale": "AES-GCM encryption for all sensitive payloads at rest and in transit",
            "file_type": "concept",
            "source_file": "storage/spec.md",
        },
    ]
    existing = [
        {
            "source": "rule_a",
            "target": "rule_b",
            "relation": "references",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
        }
    ]
    updated = reconcile_semantic_similarity(nodes, existing, report=False)
    # Does not duplicate or overwrite the existing edge
    assert len(updated) == 1
    assert updated[0]["relation"] == "references"


def test_reconcile_idempotence():
    nodes = [
        {
            "id": "rule_a",
            "label": "Data Encryption",
            "rationale": "AES-GCM encryption for all sensitive payloads at rest and in transit",
            "file_type": "rationale",
            "source_file": "security/spec.md",
        },
        {
            "id": "rule_b",
            "label": "Payload Protection",
            "rationale": "AES-GCM encryption for all sensitive payloads at rest and in transit",
            "file_type": "concept",
            "source_file": "storage/spec.md",
        },
    ]
    edges = []
    first_pass = reconcile_semantic_similarity(nodes, edges, report=False)
    assert len(first_pass) == 1

    second_pass = reconcile_semantic_similarity(nodes, first_pass, report=False)
    assert len(second_pass) == 1


def test_reconcile_ignores_code_nodes_without_rationale():
    nodes = [
        {
            "id": "func_a",
            "label": "validate_user",
            "file_type": "code",
            "source_file": "auth/user.py",
        },
        {
            "id": "func_b",
            "label": "validate_user",
            "file_type": "code",
            "source_file": "api/user.py",
        },
    ]
    edges = []
    updated = reconcile_semantic_similarity(nodes, edges, report=False)
    assert len(updated) == 0


def test_reconcile_handles_empty_or_trivial():
    assert reconcile_semantic_similarity([], []) == []
    assert reconcile_semantic_similarity([{"id": "a"}], []) == []
    assert reconcile_semantic_similarity([{"id": "a", "label": ""}], []) == []


def test_reconcile_with_reporting_output(capsys):
    nodes = [
        {
            "id": "rule_a",
            "label": "Tenant Isolation Policy",
            "rationale": "Enforce tenant boundary isolation across multi-tenant database transactions and storage shards",
            "file_type": "rationale",
            "source_file": "docs/arch/isolation.md",
        },
        {
            "id": "rule_b",
            "label": "Tenant Isolation Requirement",
            "rationale": "Enforce tenant boundary isolation across multi-tenant database transactions and storage shards",
            "file_type": "concept",
            "source_file": "policies/security.md",
        },
    ]
    edges = []
    updated = reconcile_semantic_similarity(nodes, edges, report=True)
    assert len(updated) == 1
    captured = capsys.readouterr()
    assert "[graphify] Reconciled 1 cross-file semantically_similar_to edge(s):" in captured.err
    assert "rule_a ~ rule_b" in captured.err

