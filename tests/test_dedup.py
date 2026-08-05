"""Tests for graphify/dedup.py entity deduplication pipeline."""
from __future__ import annotations
import pytest
from graphify.dedup import deduplicate_entities, _defines_id, _entropy, _shingles


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


def test_build_dedup_preserves_semantic_attributes():
    """The default build path must not discard semantic enrichment (#2091)."""
    from graphify.build import build
    ast = {
        "nodes": [{"id": "src_auth_login", "label": "login", "file_type": "code",
                   "source_file": "src/auth.py", "_origin": "ast",
                   "source_location": "L42"}],
        "edges": [],
    }
    semantic = {
        "nodes": [{"id": "src_auth_login", "label": "User login handler",
                   "file_type": "code", "source_file": "src/auth.py",
                   "summary": "Authenticates a user.", "confidence_score": 0.9}],
        "edges": [],
    }

    node = dict(build([ast, semantic], directed=True, dedup=True).nodes["src_auth_login"])

    assert node["label"] == "login"
    assert node["source_location"] == "L42"
    assert node["summary"] == "Authenticates a user."
    assert node["confidence_score"] == 0.9


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


# ── #1504: cross-chunk node ID collision warning ──────────────────────────────

def test_cross_chunk_id_collision_emits_warning(capsys):
    """When two nodes share the same ID but come from different source files
    (a cross-chunk LLM ID collision), a WARNING must be printed to stderr
    and only the first node survives (#1504)."""
    nodes = [
        {"id": "readme_booking_service", "label": "Booking Service",
         "file_type": "concept", "source_file": "module-a/README.md"},
        {"id": "readme_booking_service", "label": "Booking Service",
         "file_type": "concept", "source_file": "module-b/README.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})

    assert len(result_nodes) == 1
    assert result_nodes[0]["source_file"] == "module-a/README.md"

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "readme_booking_service" in captured.err
    assert "module-b/README.md" in captured.err
    assert "module-a/README.md" in captured.err


def test_same_id_same_source_file_no_warning(capsys):
    """When two nodes share both ID and source_file (same-file dedup),
    no collision warning should be emitted."""
    nodes = [
        {"id": "readme_booking_service", "label": "Booking Service",
         "file_type": "concept", "source_file": "module-a/README.md"},
        {"id": "readme_booking_service", "label": "Booking Service (dupe)",
         "file_type": "concept", "source_file": "module-a/README.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})

    assert len(result_nodes) == 1
    captured = capsys.readouterr()
    assert "WARNING" not in captured.err


# ── #1857: dedup summary log breakdown ────────────────────────────────────────

def test_dedup_summary_prints_fuzzy_count_when_no_exact_merges(capsys):
    """A fuzzy-only run must still report the fuzzy count (#1857).

    Two long, high-entropy, non-code labels on different files. Pass 1 (exact,
    same-file) finds nothing; Pass 2 (Jaro-Winkler cross-file) merges them.
    Previously the fuzzy count was nested inside `if exact_merges`, so this
    line printed as `Deduplicated 1 node(s).` with no breakdown.
    """
    nodes = [
        {"id": "g1", "label": "GraphExtractor", "file_type": "concept", "source_file": "a.md"},
        {"id": "g2", "label": "Graph Extractor", "file_type": "concept", "source_file": "b.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1
    captured = capsys.readouterr()
    assert "Deduplicated" in captured.out
    assert "fuzzy" in captured.out
    assert "exact" not in captured.out


def test_dedup_summary_still_reports_exact_only(capsys):
    """Non-regression: an exact-only run still prints `(N exact)` and no fuzzy."""
    # Same file + same normalized label → Pass 1 exact merge.
    nodes = [
        {"id": "u1", "label": "User Service", "file_type": "concept", "source_file": "svc.md"},
        {"id": "u2", "label": "user service", "file_type": "concept", "source_file": "svc.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1
    captured = capsys.readouterr()
    assert "exact" in captured.out
    assert "fuzzy" not in captured.out


# ── ID collisions: definition vs cross-reference ──────────────────────────────

# The defining node and a doc that merely mentions the entity. Both mint the ID
# encoded from the *defining* file's path, so they collide by construction.
_DEFINING = {"id": "agents_make_batch_fixtures_make_batch_fixtures",
             "label": "make-batch-fixtures agent", "file_type": "concept",
             "source_file": "agents/make-batch-fixtures.md"}
_REFERENCING = {"id": "agents_make_batch_fixtures_make_batch_fixtures",
                "label": "make-batch-fixtures", "file_type": "concept",
                "source_file": "available/diagnose-issue/SKILL.md"}


@pytest.mark.parametrize("nodes", [
    [_DEFINING, _REFERENCING],
    [_REFERENCING, _DEFINING],
], ids=["definition-first", "reference-first"])
def test_defining_file_wins_over_referencing_file(nodes, capsys):
    """The node whose source_file is the file its ID encodes survives, whichever
    chunk order the nodes arrive in — the survivor must not depend on it."""
    result_nodes, _ = deduplicate_entities(list(nodes), [], communities={})

    assert len(result_nodes) == 1
    assert result_nodes[0]["source_file"] == "agents/make-batch-fixtures.md"
    assert result_nodes[0]["label"] == "make-batch-fixtures agent"


def test_reference_collision_is_silent(capsys):
    """A cross-reference rewires silently without importing foreign-file metadata."""
    edges = _make_edges("agents_make_batch_fixtures_make_batch_fixtures", "other")
    referencing = dict(_REFERENCING, summary="Reference-local description.")
    result_nodes, result_edges = deduplicate_entities(
        [_DEFINING, referencing], edges, communities={})

    assert len(result_nodes) == 1
    assert len(result_edges) == 1
    assert "summary" not in result_nodes[0]
    captured = capsys.readouterr()
    assert "WARNING" not in captured.err
    assert "note:" not in captured.err


def test_absolute_source_path_still_defines_id(capsys):
    """source_file is absolute in some pipelines and repo-relative in others; the
    defining file is recognised either way."""
    absolute = dict(_DEFINING, source_file="/home/u/proj/agents/make-batch-fixtures.md")
    result_nodes, _ = deduplicate_entities([_REFERENCING, absolute], [], communities={})

    assert len(result_nodes) == 1
    assert result_nodes[0]["label"] == "make-batch-fixtures agent"
    assert "WARNING" not in capsys.readouterr().err


def test_same_file_relabel_is_noted(capsys):
    """Two labels for one ID from one file: the loser's label is discarded, which is
    the one drop that used to be silent. It is a note, not a collision warning."""
    nodes = [
        {"id": "agents_make_batch_fixtures_make_batch_fixtures",
         "label": "make-batch-fixtures agent", "file_type": "concept",
         "source_file": "agents/make-batch-fixtures.md"},
        {"id": "agents_make_batch_fixtures_make_batch_fixtures",
         "label": "make-batch-fixtures helper agent", "file_type": "concept",
         "source_file": "agents/make-batch-fixtures.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})

    assert len(result_nodes) == 1
    captured = capsys.readouterr()
    assert "note:" in captured.err
    assert "make-batch-fixtures helper agent" in captured.err
    assert "WARNING" not in captured.err


@pytest.mark.parametrize("nodes", [
    [
        {"id": "src_auth_login", "label": "login", "file_type": "code",
         "source_file": "src/auth.py", "_origin": "ast", "source_location": "L42"},
        {"id": "src_auth_login", "label": "User login handler", "file_type": "code",
         "source_file": "src/auth.py", "summary": "Authenticates a user.",
         "confidence_score": 0.9},
    ],
    [
        {"id": "src_auth_login", "label": "User login handler", "file_type": "code",
         "source_file": "src/auth.py", "summary": "Authenticates a user.",
         "confidence_score": 0.9},
        {"id": "src_auth_login", "label": "login", "file_type": "code",
         "source_file": "src/auth.py", "_origin": "ast", "source_location": "L42"},
    ],
], ids=["ast-first", "semantic-first"])
def test_same_id_same_entity_retains_complementary_attributes(nodes):
    """Exact-ID dedup combines AST precision with semantic enrichment (#2091)."""
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})

    assert len(result_nodes) == 1
    assert result_nodes[0] == {
        "id": "src_auth_login",
        "label": "login",
        "file_type": "code",
        "source_file": "src/auth.py",
        "_origin": "ast",
        "source_location": "L42",
        "summary": "Authenticates a user.",
        "confidence_score": 0.9,
    }


def test_cross_file_id_collision_does_not_mix_attributes(capsys):
    """Two files that both mint one ID remain isolated despite exact-ID dedup."""
    nodes = [
        {"id": "pkg_service_run", "label": "run", "file_type": "code",
         "source_file": "pkg/service.py", "source_location": "L10"},
        {"id": "pkg_service_run", "label": "run helper", "file_type": "code",
         "source_file": "pkg_service.py", "summary": "Different function."},
    ]

    result_nodes, _ = deduplicate_entities(nodes, [], communities={})

    assert len(result_nodes) == 1
    assert result_nodes[0]["source_file"] == "pkg/service.py"
    assert "summary" not in result_nodes[0]
    assert "WARNING" in capsys.readouterr().err


def test_collision_survivor_is_order_independent():
    """#1851: definer + same-file relabel + cross-file reference. Across every
    insertion order the SAME node (source_file AND label) must survive — the
    definer heuristic alone left the label order-dependent among co-definers."""
    import itertools
    nid = "agents_make_batch_fixtures_make_batch_fixtures"
    definer = {"id": nid, "label": "make-batch-fixtures agent",
               "file_type": "concept", "source_file": "agents/make-batch-fixtures.md"}
    relabel = {"id": nid, "label": "make-batch-fixtures helper agent",
               "file_type": "concept", "source_file": "agents/make-batch-fixtures.md"}
    xref = {"id": nid, "label": "make-batch-fixtures", "file_type": "concept",
            "source_file": "available/diagnose-issue/SKILL.md"}
    survivors = set()
    for perm in itertools.permutations([definer, relabel, xref]):
        out, _ = deduplicate_entities([dict(n) for n in perm], [], communities={})
        assert len(out) == 1
        survivors.add((out[0]["source_file"], out[0]["label"]))
    assert survivors == {("agents/make-batch-fixtures.md", "make-batch-fixtures agent")}, (
        f"non-deterministic collision survivor: {survivors}"
    )


def test_bare_file_node_defines_its_own_id():
    """A file-level semantic node whose id is exactly the slugified path (no
    `_entity` suffix) must be recognised as defining its id (#1851 tweak)."""
    assert _defines_id({"id": "agents_make_batch_fixtures",
                        "source_file": "agents/make-batch-fixtures.md"})


def test_defines_id_helper():
    assert _defines_id(_DEFINING)
    assert not _defines_id(_REFERENCING)
    # Pre-#1504 IDs keyed off the bare filename stem.
    assert _defines_id({"id": "readme_booking_service",
                        "source_file": "module-a/README.md"})
    # A path that is merely a string-prefix of the ID's path does not define it.
    assert not _defines_id({"id": "agents_foo", "source_file": "agent/foo.md"})
    assert not _defines_id({"id": "docs_intro_foo", "source_file": ""})


# ── #2091 review: attribute-merge correctness (fixes A-D) ─────────────────────

def test_dedup_gapfill_is_order_independent_with_multiple_losers():
    """(fix A) With 3+ same-ID same-source records, the merged attributes must not
    depend on arrival order — the best loser by collision rank supplies each
    missing key deterministically, preserving the #1851 order-independence."""
    import itertools
    base = [
        {"id": "f", "label": "f", "file_type": "code", "source_file": "m.py",
         "source_location": "L1"},                                  # shortest label -> survivor
        {"id": "f", "label": "f helper beta", "file_type": "code",
         "source_file": "m.py", "summary": "BETA"},
        {"id": "f", "label": "f helper alpha", "file_type": "code",
         "source_file": "m.py", "summary": "ALPHA"},
    ]
    seen = set()
    for perm in itertools.permutations(base):
        nodes, _ = deduplicate_entities([dict(n) for n in perm], [], communities={})
        assert len(nodes) == 1
        seen.add(nodes[0].get("summary"))
    assert len(seen) == 1, f"merged summary depends on arrival order: {seen}"


def test_dedup_no_attribute_merge_when_source_file_missing():
    """(fix B) Two provenance-less records sharing an ID must NOT cross-pollinate
    attributes — '' == '' is not proof of the same symbol (#1178)."""
    nodes = [
        {"id": "c", "label": "c", "file_type": "concept", "summary": "A"},
        {"id": "c", "label": "c", "file_type": "concept", "notes": "B"},
    ]
    result, _ = deduplicate_entities([dict(n) for n in nodes], [], communities={})
    assert len(result) == 1
    surv = result[0]
    assert not ("summary" in surv and "notes" in surv), (
        "provenance-less same-id records must not merge attributes"
    )


def test_dedup_survivor_does_not_inherit_false_origin_ast():
    """(fix C) An LLM survivor must not inherit _origin='ast' from a dropped
    same-source AST record — a false authority tag is read by ghost-merge/watch."""
    nodes = [
        {"id": "x", "label": "run", "file_type": "code", "source_file": "m.py",
         "source_location": "L9"},                                   # shorter label -> survivor (LLM)
        {"id": "x", "label": "run() [ast]", "file_type": "code", "source_file": "m.py",
         "source_location": "L2", "_origin": "ast"},                 # loser carries _origin=ast
    ]
    result, _ = deduplicate_entities([dict(n) for n in nodes], [], communities={})
    assert len(result) == 1
    assert result[0].get("_origin") != "ast", "survivor must not inherit a false _origin=ast"


def test_dedup_fills_explicit_none_attribute():
    """(fix D) An explicit source_location=None on the survivor is treated as
    absent and filled from a same-source record that has a real line (#2091)."""
    nodes = [
        {"id": "y", "label": "y", "file_type": "code", "source_file": "m.py",
         "source_location": None},                                   # survivor, explicit None
        {"id": "y", "label": "y helper", "file_type": "code", "source_file": "m.py",
         "source_location": "L7"},
    ]
    result, _ = deduplicate_entities([dict(n) for n in nodes], [], communities={})
    assert len(result) == 1
    assert result[0].get("source_location") == "L7", "explicit-None must be filled from the loser"


# ── #2182: cross-file exact-duplicate concepts must merge ─────────────────────

def test_crossfile_identical_concepts_merge_and_rewire():
    """Two `concept` nodes whose labels are byte-identical after _norm() but
    live in different files must merge (#2182). Pass 1 used to defer them to
    Pass 2, whose norm-unique candidate filter (`seen_norms`) structurally
    cannot form an equal-norm pair — so exact cross-file duplicates were the
    one class of duplicate that never merged, while a one-char-different
    fuzzy pair did."""
    nodes = [
        {"id": "sz_intl", "label": "SHENZHEN INTERNATIONAL",
         "file_type": "concept", "source_file": "doc1.md"},
        {"id": "shenzhen_international_holdings", "label": "Shenzhen international",
         "file_type": "concept", "source_file": "doc2.md"},
        {"id": "port_ops", "label": "Port Operations",
         "file_type": "concept", "source_file": "doc2.md"},
    ]
    edges = [{"source": "shenzhen_international_holdings", "target": "port_ops",
              "relation": "operates"}]
    result_nodes, result_edges = deduplicate_entities(nodes, edges, communities={})
    ids = {n["id"] for n in result_nodes}
    assert len(result_nodes) == 2
    # _pick_winner prefers the shorter, non-chunk-suffixed id.
    assert "sz_intl" in ids
    assert "shenzhen_international_holdings" not in ids
    # The loser's edge is rewired to the winner.
    assert result_edges == [
        {"source": "sz_intl", "target": "port_ops", "relation": "operates"}]


def test_crossfile_one_char_typo_concepts_still_merge():
    """Non-regression: the near-identical (one-char-different) cross-file pair
    that already merged via Pass 2 fuzzy matching must keep merging (#2182)."""
    nodes = [
        {"id": "g1", "label": "Authentication Manager",
         "file_type": "concept", "source_file": "a.md"},
        {"id": "g2", "label": "Authentication Managr",
         "file_type": "concept", "source_file": "b.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1


_RATIONALE_BOILER = ("Django app config for apps.platform.cards. No business "
                     "logic here. Domain services live in services.py.")


@pytest.mark.parametrize("a,b", [
    ({"id": "d1", "label": "Getting Started Installation Guide",
      "file_type": "document", "source_file": "docs/a.md"},
     {"id": "d2", "label": "Getting Started Installation Guide",
      "file_type": "document", "source_file": "docs/b.md"}),
    ({"id": "r1", "label": _RATIONALE_BOILER,
      "file_type": "rationale", "source_file": "apps/platform/cards/apps.py"},
     {"id": "r2", "label": _RATIONALE_BOILER,
      "file_type": "rationale", "source_file": "apps/platform/cores/apps.py"}),
    ({"id": "backend_a_render_frame", "label": "render_frame",
      "file_type": "code", "source_file": "backend_a.py"},
     {"id": "backend_b_render_frame", "label": "render_frame",
      "file_type": "code", "source_file": "backend_b.py"}),
    ({"id": "web_logo", "label": "logo.png",
      "file_type": "image", "source_file": "web/assets/logo.png"},
     {"id": "docs_logo", "label": "logo.png",
      "file_type": "image", "source_file": "docs/img/logo.png"}),
    ({"id": "logo_concept", "label": "logo.png",
      "file_type": "concept", "source_file": "doc1.md"},
     {"id": "logo_image", "label": "logo.png",
      "file_type": "image", "source_file": "assets/logo.png"}),
    ({"id": "shenzhen_a", "label": "Shenzhen International",
      "file_type": "concept", "source_file": ""},
     {"id": "shenzhen_b", "label": "Shenzhen International",
      "file_type": "concept", "source_file": ""}),
    ({"id": "api_a", "label": "API",
      "file_type": "concept", "source_file": "doc1.md"},
     {"id": "api_b", "label": "API",
      "file_type": "concept", "source_file": "doc2.md"}),
], ids=["document", "rationale", "code", "image-basename", "concept-image-mixed",
        "empty-source-file", "low-entropy-concept"])
def test_crossfile_identical_labels_stay_distinct_for_guarded_types(a, b):
    """The #2182 fix is gated to high-entropy `concept` nodes with provenance
    on BOTH sides. Identical labels must NOT merge for: file-anchored types
    (document/rationale, #1284), code (#1205), images sharing a basename in
    different dirs, mixed concept+image pairs, provenance-less nodes (#1178),
    and low-entropy generic labels."""
    result_nodes, _ = deduplicate_entities([dict(a), dict(b)], [], communities={})
    assert len(result_nodes) == 2, (
        f"guarded pair ({a['id']}, {b['id']}) was merged — #2182 fix leaked "
        f"past its concept-only gate"
    )


def test_cross_repo_guard_still_raises():
    """The cross-repo guard is untouched by #2182: identical concepts from
    different repos must still raise, never merge."""
    nodes = [
        {"id": "c1", "label": "Shenzhen International", "file_type": "concept",
         "source_file": "doc1.md", "repo": "repo-a"},
        {"id": "c2", "label": "Shenzhen International", "file_type": "concept",
         "source_file": "doc2.md", "repo": "repo-b"},
    ]
    with pytest.raises(ValueError, match="multiple repos"):
        deduplicate_entities(nodes, [], communities={})


def test_crossfile_concept_merge_is_order_independent():
    """Three identical-norm concepts across three files: every input order must
    yield the same single survivor (#2182). Winner ids differ in length so
    _pick_winner has a unique minimum."""
    import itertools
    base = [
        {"id": "shenzhen", "label": "SHENZHEN INTERNATIONAL",
         "file_type": "concept", "source_file": "doc1.md"},
        {"id": "shenzhen_intl", "label": "Shenzhen international",
         "file_type": "concept", "source_file": "doc2.md"},
        {"id": "shenzhen_international", "label": "shenzhen-international",
         "file_type": "concept", "source_file": "doc3.md"},
    ]
    survivors = set()
    for perm in itertools.permutations(base):
        out, _ = deduplicate_entities([dict(n) for n in perm], [], communities={})
        assert len(out) == 1
        survivors.add(out[0]["id"])
    assert survivors == {"shenzhen"}, f"non-deterministic survivor: {survivors}"


def test_crossfile_concept_merge_deterministic_across_hash_seeds():
    """#2182 determinism, #1753/#2074 precedent: the survivor must not depend on
    PYTHONHASHSEED. pytest fixes the seed per process, so run out-of-process
    with shuffled input."""
    import os
    import subprocess
    import sys
    script = (
        "import random, sys\n"
        "from graphify.dedup import deduplicate_entities\n"
        "nodes = [\n"
        "    {'id': 'shenzhen', 'label': 'SHENZHEN INTERNATIONAL',\n"
        "     'file_type': 'concept', 'source_file': 'doc1.md'},\n"
        "    {'id': 'shenzhen_intl', 'label': 'Shenzhen international',\n"
        "     'file_type': 'concept', 'source_file': 'doc2.md'},\n"
        "    {'id': 'shenzhen_international', 'label': 'shenzhen-international',\n"
        "     'file_type': 'concept', 'source_file': 'doc3.md'},\n"
        "]\n"
        "random.Random(int(sys.argv[1])).shuffle(nodes)\n"
        "out, _ = deduplicate_entities(nodes, [], communities={})\n"
        "print(len(out), sorted(n['id'] for n in out)[0])\n"
    )
    results = set()
    for seed in ("0", "1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run(
            [sys.executable, "-c", script, seed],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0, r.stderr
        results.add(r.stdout.strip().splitlines()[-1])
    assert results == {"1 shenzhen"}, (
        f"non-deterministic dedup across hash seeds: {results}"
    )


def test_crossfile_concept_merge_is_transitive():
    """Exact cross-file matches and a punctuation variant collapse to one
    survivor: {'Acme Corp' doc1, 'Acme Corp' doc2, 'Acme Corp.' doc3} all
    normalize to 'acme corp' and must transitively union (#2182)."""
    nodes = [
        {"id": "acme_corp_one", "label": "Acme Corp",
         "file_type": "concept", "source_file": "doc1.md"},
        {"id": "acme_corp_two", "label": "Acme Corp",
         "file_type": "concept", "source_file": "doc2.md"},
        {"id": "acme_corp_three", "label": "Acme Corp.",
         "file_type": "concept", "source_file": "doc3.md"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1
