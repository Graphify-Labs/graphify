"""Tests for graphify/dedup.py entity deduplication pipeline."""
from __future__ import annotations
import pytest
from graphify.dedup import deduplicate_entities, _entropy, _shingles


# ── entropy gate ─────────────────────────────────────────────────────────────

def test_entropy_short_label_low():
    assert _entropy("AI") < 2.5

def test_entropy_normal_label_high():
    assert _entropy("AuthenticationManager") >= 2.5

def test_entropy_empty_string():
    assert _entropy("") == 0.0


# ── shingles ─────────────────────────────────────────────────────────────────

def test_shingles_produces_trigrams():
    s = _shingles("hello")
    assert "hel" in s
    assert "ell" in s
    assert "llo" in s

def test_shingles_short_string():
    # strings shorter than 3 chars return single shingle of the string itself
    assert _shingles("ab") == {"ab"}


# ── full pipeline ─────────────────────────────────────────────────────────────

def _make_nodes(*labels):
    return [{"id": label.lower().replace(" ", "_"), "label": label, "source_file": "test.md"} for label in labels]

def _make_edges(src, tgt, relation="relates_to"):
    return [{"source": src, "target": tgt, "relation": relation}]


def test_exact_duplicates_merged():
    nodes = _make_nodes("UserService", "userservice", "User Service")
    edges = []
    result_nodes, result_edges = deduplicate_entities(nodes, edges, communities={})
    # All three are the same concept — only one survives
    assert len(result_nodes) == 1


def test_typo_merged():
    # "GraphExtractor" vs "Graph Extractor" — Jaro-Winkler >= 0.92
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 1


def test_unrelated_not_merged():
    nodes = _make_nodes("UserService", "OrderService")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2


def test_short_low_entropy_not_merged():
    # "AI" and "ML" are low-entropy — entropy gate skips them
    nodes = _make_nodes("AI", "ML")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2


def test_edges_rewired_after_merge():
    nodes = _make_nodes("GraphExtractor", "Graph Extractor", "Parser")
    # edge from loser to Parser should be rewired to winner
    edges = [{"source": "graph_extractor", "target": "parser", "relation": "uses"}]
    result_nodes, result_edges = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2  # merged + Parser
    # edge should still exist (rewired to winner)
    assert len(result_edges) == 1


def test_self_loops_dropped_after_merge():
    # If both endpoints of an edge get merged into same node, drop the edge
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = [{"source": "graphextractor", "target": "graph_extractor", "relation": "same"}]
    _, result_edges = deduplicate_entities(nodes, edges, communities={})
    assert result_edges == []


def test_community_boost_aids_merge():
    # Two nodes in same community with score in 0.75-0.85 zone get boosted
    nodes = _make_nodes("AuthManager", "Auth Manager")
    edges = []
    # Same community → boost → merge
    communities = {"authmanager": 1, "auth_manager": 1}
    result_with, _ = deduplicate_entities(nodes, edges, communities=communities)
    # Different community → no boost
    communities_diff = {"authmanager": 1, "auth_manager": 2}
    result_without, _ = deduplicate_entities(nodes, edges, communities=communities_diff)
    assert len(result_with) <= len(result_without)


def test_empty_inputs():
    result_nodes, result_edges = deduplicate_entities([], [], communities={})
    assert result_nodes == []
    assert result_edges == []


def test_single_node_no_crash():
    nodes = _make_nodes("UserService")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1


def test_dedup_llm_flag_accepted():
    """deduplicate_entities accepts dedup_llm_backend without crashing when no ambiguous pairs exist."""
    nodes = _make_nodes("UserService", "OrderService")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={}, dedup_llm_backend=None)
    assert len(result_nodes) == 2


# ── build integration ─────────────────────────────────────────────────────────

def test_build_calls_dedup():
    """build() should deduplicate near-identical nodes across extractions."""
    from graphify.build import build
    chunk1 = {
        "nodes": [{"id": "graphextractor", "label": "GraphExtractor", "source_file": "a.py"}],
        "edges": [],
    }
    chunk2 = {
        "nodes": [{"id": "graph_extractor", "label": "Graph Extractor", "source_file": "b.py"}],
        "edges": [],
    }
    G = build([chunk1, chunk2])
    assert G.number_of_nodes() == 1


# --- #878: fuzzy dedup false merges on short/variant labels ---

def test_dedup_does_not_merge_numeric_variants(tmp_path):
    """Chip SKU variants (ASR1603 vs ASR1605) must not be merged (#878)."""
    nodes = _make_nodes("ASR1603", "ASR1605")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2, "ASR1603 and ASR1605 are distinct chip models, not duplicates"


def test_dedup_does_not_merge_short_insertion_variants(tmp_path):
    """Short labels differing by an insertion (cranel vs cranelr) must not merge (#878)."""
    nodes = _make_nodes("cranel", "cranelr")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2, "cranel and cranelr are distinct, not a typo"


def test_dedup_does_not_merge_model_with_suffix(tmp_path):
    """M1 vs M1 Pro must not merge (#878)."""
    nodes = _make_nodes("M1", "M1 Pro")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2, "M1 and M1 Pro are distinct Apple chip variants"


def test_dedup_still_merges_real_typos():
    """Genuine same-length single-char typos should still merge (#878 non-regression)."""
    from graphify.dedup import _is_variant_pair, _short_label_blocked
    from rapidfuzz.distance import JaroWinkler
    a, b = "graphextractor", "graphextractar"
    score = JaroWinkler.normalized_similarity(a, b) * 100
    assert not _is_variant_pair(a, b), "not a variant pair"
    assert not _short_label_blocked(a, b, score), "long-enough label, should not be blocked"


def test_variant_pair_helper():
    """_is_variant_pair correctly identifies chip-model variant pairs (#878)."""
    from graphify.dedup import _is_variant_pair
    assert _is_variant_pair("asr1603", "asr1605")
    assert _is_variant_pair("cortex a55", "cortex a55x")
    assert not _is_variant_pair("graphextractor", "graphextracter")
    assert not _is_variant_pair("foo", "foo")


def test_prefix_extension_symbols_not_merged():
    """Distinct symbols whose name is a strict prefix-extension of another must not
    be merged (#1201). getActiveSession / getActiveSessions score ~98.82 JW but are
    different functions; parseConfig / parseConfigFile likewise."""
    import networkx as nx
    from graphify.dedup import deduplicate_entities

    pairs = [
        ("getActiveSession", "getActiveSessions"),
        ("parseConfig", "parseConfigFile"),
        ("load", "loadAll"),
        ("handleRequest", "handleRequestTimeout"),
    ]
    for a, b in pairs:
        nodes = [
            {"id": f"{a}_id", "label": a, "type": "CODE", "src_file": "api.py"},
            {"id": f"{b}_id", "label": b, "type": "CODE", "src_file": "api.py"},
        ]
        edges = [{"src": f"{a}_id", "tgt": f"{b}_id", "relation": "calls",
                  "c": 1.0, "weight": 1.0}]
        out_nodes, _ = deduplicate_entities(
            nodes, edges, communities={f"{a}_id": 0, f"{b}_id": 0}
        )
        labels = {n["label"] for n in out_nodes}
        assert a in labels and b in labels, (
            f"#1201 regression: '{a}' and '{b}' were merged — they are distinct symbols"
        )


def test_pass2_winner_union_does_not_pull_in_uncompared_same_label_nodes():
    """Pass 2's winner selection must consider only the verified pair (#1247).

    Picking the winner from the union of both normalized-label groups pulls
    never-compared nodes into the merge: here A ("Session Manager", auth.md)
    and B ("Session Manager", billing.md) are deliberately kept distinct by
    the cross-file identical-label guards (#1046, #1178), yet when the
    A-C fuzzy match ("Session Managr" typo) fires, _pick_winner over
    [A, B, C] selects B (shortest id) and unions B with both A and C —
    merging B although it was never compared against anything.
    """
    nodes = [
        {"id": "session_manager_auth", "label": "Session Manager",
         "source_file": "auth.md"},
        {"id": "sm", "label": "Session Manager",
         "source_file": "billing.md"},
        {"id": "session_managr_notes", "label": "Session Managr",
         "source_file": "notes.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    ids = {n["id"] for n in result_nodes}
    # B must survive as a distinct node: identical label across different
    # source files is exactly what the #1046/#1178 guards keep separate.
    assert "sm" in ids, (
        "uncompared cross-file node 'sm' was absorbed via pass-2 winner-union"
    )
    # The verified fuzzy pair (A, C) still merges — only one of them survives.
    assert len(result_nodes) == 2


def test_prefix_guard_does_not_block_same_length_typos():
    """The prefix-extension guard must not fire for same-length pairs — only strict
    prefix-extensions (one is a substring of the other) should be blocked (#1201).
    graphextractor / graphextractar have the same length, so neither starts-with the
    other, and the guard must not fire."""
    from graphify.dedup import _norm
    a = _norm("GraphExtractor")   # "graphextractor" — 14 chars
    b = _norm("GraphExtractar")   # "graphextractar" — 14 chars
    lo, hi = sorted((a, b), key=len)
    # Same-length pair: startswith only holds when strings are identical
    assert not (hi.startswith(lo) and hi != lo), (
        f"Prefix guard fires on same-length pair ({a!r}, {b!r}) — should not"
    )


def test_prefix_guard_fires_for_extension_pairs():
    """The prefix-extension guard must fire for pairs where one is a strict prefix
    of the other, preventing false merges (#1201)."""
    from graphify.dedup import _norm
    pairs = [
        ("getActiveSession", "getActiveSessions"),
        ("parseConfig", "parseConfigFile"),
        ("load", "loadAll"),
    ]
    for a_raw, b_raw in pairs:
        a, b = _norm(a_raw), _norm(b_raw)
        lo, hi = sorted((a, b), key=len)
        assert hi.startswith(lo) and hi != lo, (
            f"Prefix guard should fire for ({a!r}, {b!r}) but did not"
        )


# ── #1284: numbered siblings + cross-file file-anchored boilerplate ──────────

def test_numeric_tokens_differ_helper():
    """_numeric_tokens_differ compares digit runs as zero-padding-insensitive
    multisets (#1284)."""
    from graphify.dedup import _numeric_tokens_differ
    assert _numeric_tokens_differ("adr 0011 d5 pipeline placement", "adr 0013 d4 pipeline placement")
    assert _numeric_tokens_differ("3 1 product goals", "1 1 product goals")
    assert _numeric_tokens_differ("code block3", "code block13")
    assert not _numeric_tokens_differ("phase 09 overview", "phase 9 overview")  # zero-padding
    assert not _numeric_tokens_differ("module layout wave 3", "module layouts wave 3")
    assert not _numeric_tokens_differ("graph extractor", "graph extractar")  # digitless


def test_dedup_does_not_merge_numbered_siblings():
    """Long labels differing only in embedded numbers (ADR/section/issue ids)
    must not merge — numbered siblings, not duplicates (#1284)."""
    nodes = [
        {"id": "n1", "label": "Pipeline placement — 4 call sites (ADR 0013 D4)",
         "file_type": "document", "source_file": "docs/index-activity.md"},
        {"id": "n2", "label": "Pipeline placement — 4 call sites (ADR 0011 §D5)",
         "file_type": "document", "source_file": "docs/schema-matcher.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


def test_dedup_does_not_merge_crossfile_rationale_boilerplate():
    """Rationale nodes are file-anchored like code (#1205): parallel modules'
    boilerplate docstrings differing by one word must not merge (#1284)."""
    boiler = ("Django app config for {}. No business logic here. "
              "Domain services live in services.py and adapters in providers.")
    nodes = [
        {"id": "r1", "label": boiler.format("apps.platform.cards"),
         "file_type": "rationale", "source_file": "apps/platform/cards/apps.py"},
        {"id": "r2", "label": boiler.format("apps.platform.cores"),
         "file_type": "rationale", "source_file": "apps/platform/cores/apps.py"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


def test_dedup_does_not_merge_crossfile_document_headings():
    """Document nodes are file-anchored too: near-identical headings in different
    files are distinct sections, not duplicates (#1284, extends the rationale guard)."""
    nodes = [
        {"id": "d1", "label": "Getting Started Installation Guide",
         "file_type": "document", "source_file": "docs/a.md"},
        {"id": "d2", "label": "Getting Started Installation Setup",
         "file_type": "document", "source_file": "docs/b.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


def test_dedup_still_merges_samefile_rationale_duplicates():
    """The file-anchored guard only blocks cross-file pairs — near-identical
    rationale duplicates within one file still merge (#1284 non-regression)."""
    nodes = [
        {"id": "r1", "label": "Counts-only metrics export, a read-only aggregation service.",
         "file_type": "rationale", "source_file": "apps/schemas/metrics.py"},
        {"id": "r2", "label": "Counts-only metrics export, the read-only aggregation service.",
         "file_type": "rationale", "source_file": "apps/schemas/metrics.py"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1


# ── #1243: JaroWinkler prefix-bonus over-merge (cross-file) ──────────────────

def test_dedup_does_not_merge_crossfile_shared_prefix_divergence():
    """Cross-file labels sharing a long prefix but diverging in a distinguishing
    token ("…jest native" vs "…react native") get JaroWinkler's prefix bonus past
    threshold but are distinct entities; scoring them on plain Jaro blocks the
    merge (#1243)."""
    nodes = [
        {"id": "p1", "label": "testing library jest native",
         "file_type": "concept", "source_file": "pkg-a/package.json"},
        {"id": "p2", "label": "testing library react native",
         "file_type": "concept", "source_file": "pkg-b/package.json"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


def test_dedup_still_merges_crossfile_true_duplicates():
    """The #1243 guard only drops the prefix bonus — a genuine cross-file
    duplicate (high similarity on Jaro alone) must still merge."""
    nodes = [
        {"id": "g1", "label": "GraphExtractor", "file_type": "concept", "source_file": "a.md"},
        {"id": "g2", "label": "Graph Extractor", "file_type": "concept", "source_file": "b.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1
