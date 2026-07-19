"""Tests for serve.py - MCP graph query helpers (no mcp package required)."""
import json
from typing import Any

import pytest
from tests.native_helpers import triangle, make_loaded
from graphify.helix.model import node_attributes

from graphify.serve import (
    _communities_from_graph,
    _score_nodes as _native_score_nodes,
    _score_query as _native_score_query,
    _compute_idf as _native_compute_idf,
    _EXACT_MATCH_BONUS,
    _SOURCE_MATCH_BONUS,
    _pick_seeds as _native_pick_seeds,
    _bfs as _native_bfs,
    _dfs as _native_dfs,
    _find_node as _native_find_node,
    _filter_graph_by_context as _native_filter_graph_by_context,
    _infer_context_filters,
    _query_terms,
    _query_graph_text as _native_query_graph_text,
    _resolve_context_filters,
    _cut_lines_to_budget,
    _subgraph_to_text as _native_subgraph_to_text,
    _load_graph,
    _community_header,
    _search_tokens,
)


def _graph(loaded):
    return getattr(loaded, "graph", loaded)


def _query(loaded):
    query = getattr(loaded, "query", None)
    assert query is not None, "query helpers must be tested through a real LoadedGraph"
    return query


def _score_nodes(loaded, terms):
    return _native_score_nodes(_graph(loaded), terms, native_query=_query(loaded))


def _score_query(loaded, terms, *, collect_per_term_seeds):
    return _native_score_query(
        _graph(loaded),
        terms,
        collect_per_term_seeds=collect_per_term_seeds,
        native_query=_query(loaded),
    )


def _compute_idf(loaded, terms):
    return _native_compute_idf(_graph(loaded), terms, _query(loaded))


def _find_node(loaded, label):
    return _native_find_node(_graph(loaded), label, native_query=_query(loaded))


def _bfs(loaded, start_nodes, depth, context_filters=None):
    return _native_bfs(
        _graph(loaded),
        start_nodes,
        depth,
        context_filters,
        native_query=_query(loaded),
    )


def _dfs(loaded, start_nodes, depth, context_filters=None):
    return _native_dfs(
        _graph(loaded),
        start_nodes,
        depth,
        context_filters,
        native_query=_query(loaded),
    )


def _query_graph_text(loaded, question, **kwargs):
    return _native_query_graph_text(
        _graph(loaded), question, native_query=_query(loaded), **kwargs
    )


def _pick_seeds(scored, *args, G=None, **kwargs):
    return _native_pick_seeds(
        scored, *args, G=_graph(G) if G is not None else None, **kwargs
    )


def _filter_graph_by_context(loaded, context_filters):
    _native_graph, filters = _native_filter_graph_by_context(
        _graph(loaded), context_filters
    )
    return loaded, filters


def _subgraph_to_text(loaded, nodes, edges, *args, **kwargs):
    return _native_subgraph_to_text(
        _graph(loaded), nodes, edges, *args, **kwargs
    )


def _edge_records(loaded, *pairs):
    G = _graph(loaded)
    records = []
    for source, target in pairs:
        edge_ids = G.edges_between(source, target) or G.edges_between(target, source)
        records.append(G.edge(edge_ids[0]))
    return records


def _make_graph() -> Any:
    return make_loaded(
        nodes=[
            {"id": "n1", "label": "extract", "source_file": "extract.py", "source_location": "L10", "community": 0},
            {"id": "n2", "label": "cluster", "source_file": "cluster.py", "source_location": "L5", "community": 0},
            {"id": "n3", "label": "build", "source_file": "build.py", "source_location": "L1", "community": 1},
            {"id": "n4", "label": "report", "source_file": "report.py", "source_location": "L1", "community": 1},
            {"id": "n5", "label": "isolated", "source_file": "other.py", "source_location": "L1", "community": 2},
        ],
        edges=[
            {"source": "n1", "target": "n2", "relation": "calls", "confidence": "INFERRED", "context": "call"},
            {"source": "n2", "target": "n3", "relation": "imports", "confidence": "EXTRACTED", "context": "import"},
            {"source": "n3", "target": "n4", "relation": "uses", "confidence": "EXTRACTED"},
        ],
    )


def test_native_dfs_respects_depth(tmp_path):
    graph = triangle(tmp_path)
    nodes, _ = _dfs(graph, ["a"], 0)
    assert nodes == {"a"}


def test_loaded_snapshot_has_no_python_runtime_cache():
    loaded = make_loaded(nodes=[{"id": "snapshot", "label": "Snapshot"}])
    assert not hasattr(loaded.graph, "_graphify_cache")


# --- _score_nodes ---

def test_score_nodes_exact_label_match():
    G = _make_graph()
    scored = _score_nodes(G, ["extract"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids
    assert scored[0][1] == "n1"  # highest score first

def test_score_nodes_no_match():
    G = _make_graph()
    scored = _score_nodes(G, ["xyzzy"])
    assert scored == []

def test_score_nodes_source_file_partial():
    G = _make_graph()
    # "cluster.py" contains "cluster" - should score 0.5 for source match
    scored = _score_nodes(G, ["cluster"])
    nids = [nid for _, nid in scored]
    assert "n2" in nids


def test_score_nodes_ignores_trailing_punctuation():
    G = _make_graph()
    scored = _score_nodes(G, ["extract?"])
    assert scored[0][1] == "n1"


def test_score_nodes_multiword_exact_label_outranks_superset():
    """A multi-word query equal to a whole label must resolve uniquely.

    Regression for the `graphify path` "No path found" bug: every node sharing
    the query's token set scored identically (no single token equals a
    multi-word label, so the per-token exact tier never fired), the tie broke by
    arbitrary node-id sort, and a wrong/disconnected endpoint was chosen. The
    full-query tier in _score_nodes must make the exact label win strictly.
    """
    # Reproduce the real graph: norm_label keeps punctuation (strip_diacritics +
    # lower, NOT tokenized), so the ':' survives. A tokenized query can never
    # equal that, which is exactly why the first-cut fix was a no-op for
    # punctuated labels. The exact node must still win via the label's tokenized
    # form.
    nodes = [
        {
            "id": nid,
            "label": label,
            "norm_label": label.lower(),
            "source_file": "uoce_dehumidifier.yaml",
            "community": 0,
        }
        for nid, label in (
            ("exact", "UOCE: Dehumidifier Driver"),
            ("super", "UOCE: Dehumidifier Driver State Machine"),
            ("decoy", "Dehumidifier Driver Helper"),
        )
    ]
    G = make_loaded(nodes=nodes)

    # CLI resolves endpoints as [t.lower() for t in label.split()].
    scored = _score_nodes(G, [t.lower() for t in "UOCE: Dehumidifier Driver".split()])

    # Resolves uniquely to the exact label, strictly ahead of the superset.
    assert scored[0][1] == "exact"
    assert scored[0][0] > scored[1][0], "exact label must strictly outrank superset/token-bag matches"


def test_score_nodes_coverage_lone_generic_exact_hit_loses_to_multi_term_match():
    """A lone generic-word exact match must not bury a multi-term match.

    Reproduces #1602: in a multi-term query, a single generic term that
    exactly equals a short leaf label (query term "list" vs a list() function
    node) received the full exact-tier bonus and outranked every node matching
    several of the query's terms, even when the query contained the target's
    literal identifier. The per-term exact/prefix tiers are now scaled by
    squared term coverage, so a 1-of-5-terms collision drops below a
    multi-term match. The leaves live in the same directory as the target
    (the realistic case) to pin that source-path hits do not count as
    coverage and hand the collision its exact tier back.
    """
    nodes = [
        {"id": "target", "label": "ClientLive.Index", "norm_label": "clientlive.index", "source_file": "lib/clients_live/index.ex", "community": 0},
        {"id": "form", "label": "ClientLive.Form", "norm_label": "clientlive.form", "source_file": "lib/clients_live/form.ex", "community": 0},
        {"id": "show", "label": "ClientLive.Show", "norm_label": "clientlive.show", "source_file": "lib/clients_live/show.ex", "community": 0},
    ]
    # Same-named tiny leaf functions: "list" == bare label fires the exact
    # tier. Placed in the target's own directory so their source paths also
    # substring-match the query term "clients": a path hit must not inflate
    # the coverage that multiplies the exact tier.
    for i in range(3):
        nodes.append({"id": f"leaf{i}", "label": "list()", "norm_label": "list()", "source_file": f"lib/clients_live/helpers{i}.ex", "community": 0})
    # Filler making "list" a common (low-IDF) token, as in a real graph where
    # list()/get()/new() style names are ubiquitous.
    for i in range(24):
        label = f"shopping list {i}"
        nodes.append({"id": f"filler{i}", "label": label, "norm_label": label, "source_file": f"lib/filler{i}.ex", "community": 0})
    G = make_loaded(nodes=nodes)

    # The user pastes the real identifier plus context words; tokenization
    # yields 5 terms: clientlive, index, clients, list, columns.
    scored = _score_nodes(G, [t.lower() for t in "ClientLive.Index clients list columns".split()])
    by_id = {nid: s for s, nid in scored}

    assert scored[0][1] == "target"
    assert by_id["target"] > by_id["leaf0"], (
        "a 1-of-5-terms exact collision must not outrank the node matching 3 of 5 terms"
    )


def test_score_nodes_coverage_full_coverage_query_is_unchanged():
    """Coverage scaling must not touch full-coverage queries (coverage == 1).

    A single-term identifier lookup keeps the exact tier's full magnitude, so
    `query "FooBarService"` behavior is byte-identical to before #1602.
    """
    G = _make_graph()
    scored = _score_nodes(G, ["extract"])
    w = _compute_idf(G, ["extract"])["extract"]
    assert scored[0][1] == "n1"
    # Full-query exact tier (10x) + per-term exact tier + source hit
    # ("extract" in "extract.py"), all undampened.
    expected = (_EXACT_MATCH_BONUS * 10 + _EXACT_MATCH_BONUS + _SOURCE_MATCH_BONUS) * w
    assert scored[0][0] == pytest.approx(expected)


def test_find_node_ignores_trailing_punctuation():
    G = _make_graph()
    assert _find_node(G, "extract?") == ["n1"]


def test_find_node_matches_full_punctuated_unicode_label():
    G = make_loaded(nodes=[{"id": "n1", "label": "Skill /auditar — Auditoría inquisitiva de enlaces"}])

    assert _find_node(G, "Skill /auditar — Auditoría inquisitiva de enlaces") == ["n1"]


def test_find_node_matches_punctuated_file_label_exactly():
    # #1704: an exactly-typed punctuated file label must resolve through explain,
    # just like it does through path/query.
    G = make_loaded(nodes=[
        {"id": "f1", "label": "blockStream.ts", "norm_label": "blockstream.ts", "source_file": "lib/blockStream.ts", "source_location": "L1"},
        {"id": "f2", "label": "blockStream.test.ts", "norm_label": "blockstream.test.ts", "source_file": "lib/blockStream.test.ts", "source_location": "L1"},
    ])
    assert _find_node(G, "blockStream.ts")[0] == "f1"
    assert _find_node(G, "blockStream.test.ts")[0] == "f2"


def test_find_node_resolves_when_label_and_norm_label_diverge():
    # #1704 hardening: the tokenized-label tier only rescues the match by
    # coincidence (label tokenizes the same as the query). When `label` and
    # `norm_label` diverge, only the symmetric `norm_query == norm_label` match
    # resolves it. Here label tokenizes to "blockstream" but norm_label is
    # "blockstream.ts" — this fails without the norm_query path.
    G = make_loaded(nodes=[{"id": "n1", "label": "BlockStream", "norm_label": "blockstream.ts", "source_file": "lib/x.ts", "source_location": "L1"}])
    assert _find_node(G, "blockStream.ts") == ["n1"]


# --- native predicate candidate selection ---


def _make_big_graph(n: int = 150) -> Any:
    """A graph large enough that the selectivity guard lets the fast-path fire for
    rare terms and fall back for common ones. Most labels share the 'item'/'node'
    stem (common), plus a few distinctive rare labels and one punctuated label."""
    nodes = [
        {"id": f"id{i}", "label": f"item node {i}", "source_file": f"pkg/item_{i}.py"}
        for i in range(n)
    ]
    nodes.extend([
        {"id": "rareA", "label": "ZebraQuokkaWidget", "source_file": "zoo/zqw.py"},
        {"id": "rareB", "label": "MarmosetGadget handler", "source_file": "zoo/marmoset.py"},
        {"id": "punct", "label": "Foo.Bar:Baz", "source_file": "pkg/foobar.py"},
    ])
    return make_loaded(nodes=nodes)


def test_native_candidates_find_rare_label_without_python_index():
    G = _make_big_graph()
    candidates = _query(G).candidate_ids(["zebraquokkawidget"])
    assert candidates == ["rareA"]


def test_native_candidates_cover_common_and_short_terms():
    G = _make_big_graph()
    assert len(_query(G).candidate_ids(["item"])) == 150
    assert _query(G).candidate_ids(["ab"]) == []


def test_find_node_label_tokens_branch_covered_by_index():
    # "foo bar baz" matches label "Foo.Bar:Baz" only via the tokenized label_tokens
    # form (the dotted/colon norm_label never contains the spaced query). The index
    # must surface this node as a candidate, or the prefilter would silently drop it.
    G = _make_big_graph()
    assert _find_node(G, "Foo Bar Baz") == ["punct"]


def test_find_node_source_file_path_prefers_file_level_node():
    source_file = "app/api/example/route.ts"
    # Insert the function node first to prove source-file lookup reorders the
    # file-level node ahead of other nodes from the same file.
    G = make_loaded(nodes=[
        {"id": "example_route_get", "label": "GET()", "source_file": source_file, "source_location": "L42"},
        {"id": "example_route", "label": "route.ts", "source_file": source_file, "source_location": "L1"},
    ])

    matches = _find_node(G, source_file)

    assert matches[0] == "example_route"
    assert "example_route_get" in matches
def test_query_terms_strips_search_punctuation():
    # "what" is a question stopword (dropped); punctuation is still stripped from "extract?".
    assert _query_terms("what calls extract?") == ["calls", "extract"]


def test_query_terms_drops_question_stopwords():
    # Natural-language question words are dropped so content words drive seeding:
    # "how does the frontier cache work" must reduce to the content terms, or it
    # seeds on "how"/"the"/"work" (which prefix-match prose labels) instead.
    assert _query_terms("how does the frontier cache work") == ["frontier", "cache"]


def test_query_terms_all_stopwords_falls_back_to_unfiltered():
    # An all-stopword query keeps its terms rather than seeding on nothing.
    assert _query_terms("how does it work") == ["how", "does", "work"]


def test_query_terms_drops_german_question_stopwords():
    # #1900: German full-sentence queries must reduce to the content noun.
    # In a mostly-English corpus "wie"/"funktioniert" are rare, get high IDF
    # weight, and out-seed the actual keyword unless dropped here.
    assert _query_terms("Wie funktioniert die Authentifizierung?") == ["authentifizierung"]


def test_query_terms_all_german_stopwords_falls_back_to_unfiltered():
    # Existing all-stopword fallback applies to German fillers too: the query
    # keeps its terms rather than seeding on nothing.
    terms = _query_terms("wie funktioniert das")
    assert terms == ["wie", "funktioniert", "das"]


def test_pick_seeds_german_query_seeds_content_node_not_heading_noise():
    """End-to-end for #1900: a German question over a graph with German
    heading-noise nodes must seed on the content noun, not on nodes that
    happen to contain 'die'/'wie'/'wird'."""
    G = make_loaded(
        kind="digraph",
        nodes=[
            {"id": "cfg", "label": "Die Konfiguration", "source_file": "docs/konfiguration.md"},
            {"id": "sec", "label": "Wie wird gesichert", "source_file": "docs/sicherheit.md"},
            {"id": "auth", "label": "Authentifizierung", "source_file": "src/auth.py"},
            {"id": "helper", "label": "login_helper", "source_file": "src/auth.py"},
        ],
        edges=[{"source": "helper", "target": "auth"}],
    )

    q = "Wie funktioniert die Authentifizierung?"
    terms = _query_terms(q)
    # #1918: _score_query does combined scoring + per-term singleton winners in
    # one traversal; _pick_seeds consumes best_seed_by_term for the per-term
    # guarantee (replaces the old terms= per-term rescoring).
    qs = _score_query(G, terms, collect_per_term_seeds=True)
    seeds = _pick_seeds(qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term)
    assert "auth" in seeds
    assert "cfg" not in seeds
    assert "sec" not in seeds


def test_query_terms_filters_only_short_english_terms(monkeypatch):
    import graphify.serve as serve_mod

    class FakeJieba:
        def cut(self, text):
            return {
                "前端": ["前端"],
                "依赖": ["依赖"],
                "安装": ["安装"],
                "包管理器": ["包", "管理器"],
                "项目约定": ["项目", "约定"],
                "a前": ["a", "前"],
            }[text]

    monkeypatch.setattr(serve_mod, "_jieba", FakeJieba())
    terms = _query_terms("前端 dependency 依赖 install 安装 to of 包管理器 项目约定 a前")
    assert terms == ["前端", "dependency", "依赖", "install", "安装", "包", "管理器", "包管理器", "项目", "约定", "项目约定", "前", "a前"]


def test_query_graph_text_keeps_short_non_english_terms():
    G = make_loaded(nodes=[{"id": "frontend", "label": "前端", "source_file": "docs/前端.md", "source_location": "L1", "community": 0}])
    text = _query_graph_text(G, "前端", mode="bfs", depth=1)
    assert "No matching nodes found." not in text
    assert "NODE 前端" in text


def test_infer_context_filters_for_calls_question():
    assert _infer_context_filters("who calls extract") == ["call"]


def test_resolve_context_filters_explicit_overrides_heuristic():
    filters, source = _resolve_context_filters("who calls extract", ["field"])
    assert filters == ["field"]
    assert source == "explicit"


# --- _bfs ---

def test_bfs_depth_1():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited  # direct neighbor
    assert "n3" not in visited  # 2 hops away

def test_bfs_depth_2():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=2)
    assert "n3" in visited  # n1 -> n2 -> n3

def test_bfs_disconnected():
    G = _make_graph()
    visited, edges = _bfs(G, ["n5"], depth=3)
    assert visited == {"n5"}  # isolated node

def test_bfs_returns_edges():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert len(edges) >= 1
    assert any(edge.source == "n1" or edge.target == "n1" for edge in edges)


def test_filter_graph_by_context_limits_traversal():
    G = _make_graph()
    filtered, filters = _filter_graph_by_context(G, ["call"])
    visited, edges = _bfs(filtered, ["n1"], depth=2, context_filters=filters)
    assert "n2" in visited
    assert "n3" not in visited
    assert [(edge.source, edge.target) for edge in edges] == [("n1", "n2")]


# --- _dfs ---

def test_dfs_depth_1():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited
    assert "n3" not in visited

def test_dfs_full_chain():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=5)
    assert {"n1", "n2", "n3", "n4"}.issubset(visited)


# --- _subgraph_to_text ---

def test_subgraph_to_text_contains_labels():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, _edge_records(G, ("n1", "n2")))
    assert "extract" in text
    assert "cluster" in text

def test_subgraph_to_text_truncates():
    G = _make_graph()
    # Very small budget forces truncation
    text = _subgraph_to_text(G, {"n1", "n2", "n3", "n4"}, _edge_records(G, ("n1", "n2")), token_budget=1)
    assert "truncated" in text

def test_subgraph_to_text_edge_included():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, _edge_records(G, ("n1", "n2")))
    assert "EDGE" in text
    assert "calls" in text


def test_subgraph_to_text_includes_edge_context():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, _edge_records(G, ("n1", "n2")))
    assert "context=call" in text


# --- work-memory overlay annotation on NODE lines -----------------------------

def test_subgraph_to_text_annotates_node_with_learning_status():
    """An annotated node gets a `learning=<status>` suffix inside its NODE
    bracket; an un-annotated node gets none."""
    G = _make_graph()
    overlay = {
        "n1": {"status": "preferred", "stale": False},
    }
    text = _subgraph_to_text(
        G,
        {"n1", "n2"},
        _edge_records(G, ("n1", "n2")),
        learning_overlay=overlay,
    )
    lines = {l.split()[1]: l for l in text.splitlines() if l.startswith("NODE ")}
    assert "learning=preferred]" in lines["extract"]
    assert "learning=" not in lines["cluster"]  # un-annotated node


def test_subgraph_to_text_marks_stale_status():
    G = _make_graph()
    overlay = {"n1": {"status": "contested", "stale": True}}
    text = _subgraph_to_text(G, {"n1"}, [], learning_overlay=overlay)
    assert "learning=contested:stale]" in text


def test_subgraph_to_text_learning_suffix_counts_against_budget():
    """The learning= suffix is part of the NODE line BEFORE the budget cut, so it
    is included in the char_budget accounting (a budget tight enough to fit the
    bare line but not the suffixed line forces truncation)."""
    G = _make_graph()
    bare = _subgraph_to_text(G, {"n1", "n2", "n3"}, [])
    # token_budget chosen so the un-annotated render fits without truncation...
    budget = (len(bare) // 3) + 1
    assert "truncated" not in _subgraph_to_text(G, {"n1", "n2", "n3"}, [],
                                                token_budget=budget)
    # ...but once every node carries a learning= suffix, the same budget overflows.
    overlay = {
        n: {"status": "preferred", "stale": False} for n in ("n1", "n2", "n3")
    }
    annotated = _subgraph_to_text(
        G,
        {"n1", "n2", "n3"},
        [],
        token_budget=budget,
        learning_overlay=overlay,
    )
    assert "learning=preferred" in annotated
    assert "truncated" in annotated


def test_subgraph_to_text_no_overlay_is_unchanged():
    """With no overlay on the graph, NODE lines carry no learning= suffix."""
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, _edge_records(G, ("n1", "n2")))
    assert "learning=" not in text


def test_query_graph_text_explicit_context_filter_changes_traversal():
    G = _make_graph()
    text = _query_graph_text(G, "extract", mode="bfs", depth=2, token_budget=2000, context_filters=["call"])
    assert "Context: call (explicit)" in text
    assert "cluster" in text
    assert "build" not in text


def test_query_graph_text_heuristic_context_filter_changes_traversal():
    G = _make_graph()
    text = _query_graph_text(G, "who calls extract", mode="bfs", depth=2, token_budget=2000)
    assert "Context: call (heuristic)" in text
    assert "cluster" in text
    assert "build" not in text


# --- _load_graph ---

def test_load_graph_roundtrip(tmp_path):
    loaded = make_loaded(
        tmp_path,
        nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        edges=[{"source": "a", "target": "b", "relation": "calls"}],
    )
    loaded_again = _load_graph(str(loaded.store_path))
    assert loaded_again.graph.node_count == 2
    assert loaded_again.graph.edge_count == 1

def test_load_graph_missing_file(tmp_path):
    graphify_dir = tmp_path / "graphify-out"
    graphify_dir.mkdir()
    with pytest.raises(SystemExit):
        _load_graph(str(graphify_dir / "nonexistent.helix"))


# --- #874: MCP hot-reload ---

def _write_graph(path, nodes: list[str]) -> None:
    """Activate a minimal native generation with the given node IDs."""
    make_loaded(path.parent, nodes=[{"id": n, "label": n, "community": 0} for n in nodes], kind="digraph")


def test_maybe_reload_detects_graph_change(tmp_path):
    """serve() sees a newly activated native generation after startup (#874)."""

    out = tmp_path / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.helix"
    _write_graph(graph_path, ["alpha", "beta"])

    # Bootstrap _load_graph + _communities_from_graph to verify the reload path
    first = _load_graph(str(graph_path))
    assert {node.id for node in first.graph.nodes()} == {"alpha", "beta"}

    _write_graph(graph_path, ["alpha", "beta", "gamma"])

    second = _load_graph(str(graph_path))
    assert second.generation != first.generation
    assert second.graph.contains_node("gamma")


def test_load_graph_generation_changes_with_content(tmp_path):
    """Atomic activation gives every graph version a distinct generation ID."""
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.helix"
    _write_graph(graph_path, ["a"])
    first = _load_graph(str(graph_path))
    _write_graph(graph_path, ["a", "b"])
    second = _load_graph(str(graph_path))
    assert first.generation != second.generation


# --- IDF weighting tests (#897) ---

def _make_noisy_graph() -> Any:
    """20 error-handler nodes + 1 rare identifier: FooBarService."""
    nodes = []
    edges = []
    for i in range(20):
        nodes.append({"id": f"err{i}", "label": f"error_handler_{i}", "source_file": f"err{i}.py", "community": 0})
        if i > 0:
            edges.append({"source": f"err{i-1}", "target": f"err{i}", "relation": "calls", "confidence": "EXTRACTED"})
    nodes.extend([
        {"id": "fbs", "label": "FooBarService", "source_file": "service.py", "community": 1},
        {"id": "fbs_dep", "label": "ServiceClient", "source_file": "client.py", "community": 1},
    ])
    edges.append({"source": "fbs", "target": "fbs_dep", "relation": "uses", "confidence": "EXTRACTED"})
    return make_loaded(nodes=nodes, edges=edges)


def test_idf_downweights_common_terms():
    """'error' matches 20 nodes, 'foobarservice' matches 1 — IDF should make
    FooBarService rank first despite error's higher raw frequency."""
    G = _make_noisy_graph()
    scored = _score_nodes(G, ["foobarservice", "error"])
    assert scored, "should have results"
    assert scored[0][1] == "fbs", (
        f"FooBarService should rank first, got {scored[0][1]}"
    )


def test_idf_uses_native_counts_without_python_cache():
    G = _make_graph()
    assert _query(G).document_frequencies(["extract"]) == {"extract": 1}
    assert not hasattr(_graph(G), "_graphify_cache")


def test_idf_rare_term_gets_high_weight():
    """A term matching only 1 of N nodes should get IDF > 1."""
    import math
    G = _make_graph()  # 5 nodes
    idf = _compute_idf(G, ["extract"])
    # extract matches only n1: IDF = log(1 + 5/2) ≈ 1.25
    assert idf["extract"] > 1.0


def test_idf_common_term_gets_low_weight():
    """A term matching most nodes should get IDF < 1."""
    import math
    G = make_loaded(nodes=[
        {"id": f"n{i}", "label": f"handle_{i}", "source_file": f"f{i}.py"}
        for i in range(20)
    ])
    idf = _compute_idf(G, ["handle"])
    assert idf["handle"] < 1.0


# --- _pick_seeds tests (#897) ---

def test_pick_seeds_dominant_identifier_gives_one_seed():
    """FooBarService at 1000 vs error nodes at 1.0 → only 1 seed chosen."""
    scored = [(1000.0, "fbs"), (1.0, "err1"), (0.9, "err2")]
    seeds = _pick_seeds(scored)
    assert seeds == ["fbs"]


def test_pick_seeds_close_scores_keeps_multiple():
    """When all scores are within 20% of the top, keep up to 3 seeds."""
    scored = [(10.0, "a"), (9.0, "b"), (8.5, "c")]
    seeds = _pick_seeds(scored)
    assert len(seeds) == 3


def test_pick_seeds_empty():
    assert _pick_seeds([]) == []


def test_pick_seeds_single():
    assert _pick_seeds([(5.0, "x")]) == ["x"]


def test_pick_seeds_respects_max_k():
    """Never return more than max_k seeds even when all scores are close."""
    scored = [(10.0, f"n{i}") for i in range(10)]
    seeds = _pick_seeds(scored, max_k=3)
    assert len(seeds) == 3


def test_pick_seeds_without_diversity_args_is_unchanged():
    """G/best_seed_by_term are optional and default to None: existing callers
    see identical behavior to before this change."""
    scored = [(1000.0, "fbs"), (1.0, "err1"), (0.9, "err2")]
    assert _pick_seeds(scored) == ["fbs"]


def test_pick_seeds_diversity_recovers_starved_term(monkeypatch):
    """Reproduces #1445: a vague natural-language query where one term's
    incidental EXACT match on an unrelated node (e.g. a common word also used
    as an unrelated field/identifier) outscores every SUBSTRING match on the
    query's other, actually-relevant terms by ~1000x. Without
    G/best_seed_by_term, the 20%-gap cutoff discards the relevant candidate
    entirely; with them, it is recovered as a guaranteed per-term seed.
    """
    # "unrelated" is an exact label match for the query term "unrelated" and
    # has no connection to the actually-relevant "target" node.
    # "target" only substring-matches the query term "widget" via its label.
    G = make_loaded(
        kind="digraph",
        nodes=[
            {"id": "noise", "label": "unrelated", "source_file": "design_tokens.json"},
            {"id": "target", "label": "rate_limit_widget", "source_file": "src/widget.py"},
            {"id": "other", "label": "something_else", "source_file": "src/other.py"},
        ],
        edges=[{"source": "other", "target": "target"}],
    )

    terms = ["unrelated", "widget"]
    # `_score_query` does the combined scoring and the per-term singleton
    # winner tracking in one traversal; `_pick_seeds` consumes its
    # `best_seed_by_term` to satisfy the per-term guarantee without rescoring.
    qs = _score_query(G, terms, collect_per_term_seeds=True)
    scored = qs.ranked

    # Sanity check the premise: without diversity, only the exact match survives.
    seeds_before = _pick_seeds(scored)
    assert seeds_before == ["noise"]

    seeds_after = _pick_seeds(scored, G=G, best_seed_by_term=qs.best_seed_by_term)
    assert "noise" in seeds_after
    assert "target" in seeds_after


# --- generic-symbol seed flooding (#1766) ---

def test_pick_seeds_dedups_homonymous_generic_labels():
    """Many nodes sharing one generic label (e.g. framework `GET` handlers)
    must contribute at most ONE seed, not consume every slot (#1766). A
    distinct, relevant label still gets its own seed."""
    G = make_loaded(kind="digraph", nodes=[
        *[{"id": f"get{i}", "label": "GET", "source_file": f"routes/r{i}.py"} for i in range(5)],
        {"id": "um", "label": "users_model", "source_file": "models/users.py"},
    ])
    # Score all the GET nodes above users_model so, pre-fix, they'd take every slot.
    scored = [(1000.0, f"get{i}") for i in range(5)] + [(900.0, "um")]
    seeds = _pick_seeds(scored, G=G)
    get_seeds = [s for s in seeds if s.startswith("get")]
    assert len(get_seeds) == 1, f"expected one GET representative, got {get_seeds}"
    # A different, well-within-gap label is not starved out by the GET flood.
    assert "um" in seeds


def test_pick_seeds_dedup_key_is_case_and_diacritic_normalized():
    """`GET`/`Get`/`get` are the same generic label and must dedup together."""
    G = make_loaded(kind="digraph", nodes=[
        {"id": "a", "label": "GET", "source_file": "a.py"},
        {"id": "b", "label": "Get", "source_file": "b.py"},
        {"id": "c", "label": "get", "source_file": "c.py"},
    ])
    scored = [(1000.0, "a"), (990.0, "b"), (980.0, "c")]
    seeds = _pick_seeds(scored, G=G)
    assert len(seeds) == 1, f"case-variant duplicates not collapsed: {seeds}"


def test_pick_seeds_per_term_guarantee_does_not_reintroduce_generic_dupe(monkeypatch):
    """The per-term guarantee loop must honor the same per-label cap, so it can't
    add a second `GET` after dedup already seeded one (#1766)."""
    G = make_loaded(
        kind="digraph",
        nodes=[
            *[{"id": f"get{i}", "label": "GET", "source_file": f"r{i}.py"} for i in range(3)],
            {"id": "um", "label": "users_model", "source_file": "users.py"},
        ],
        edges=[{"source": "um", "target": "get0"}],
    )
    terms = ["get", "users"]
    qs = _score_query(G, terms, collect_per_term_seeds=True)
    seeds = _pick_seeds(qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term)
    get_seeds = [s for s in seeds if s.startswith("get")]
    assert len(get_seeds) == 1, f"per-term guarantee reintroduced a GET dupe: {seeds}"


def test_score_nodes_scores_identical_labels_equally():
    """Guard against a per-label multiplicity penalty leaking into _score_nodes
    (shared by shortest_path / explain endpoint resolution): two nodes with the
    SAME label must receive the SAME score for a query, i.e. the fix lives in
    seed selection, not in the shared scorer (#1766 followup)."""
    G = make_loaded(kind="digraph", nodes=[
        {"id": "g1", "label": "GET", "source_file": "a.py"},
        {"id": "g2", "label": "GET", "source_file": "b.py"},
        {"id": "g3", "label": "GET", "source_file": "c.py"},
    ])
    by_id = {nid: s for s, nid in _score_nodes(G, ["get"])}
    assert by_id["g1"] == by_id["g2"] == by_id["g3"], (
        f"identical-label nodes scored differently: {by_id}"
    )


# --- actionable truncation hint (#897) ---

def test_subgraph_to_text_truncation_hint_is_actionable():
    """Truncation message must tell Claude what to do, not just say truncated."""
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2", "n3", "n4"}, _edge_records(G, ("n1", "n2")), token_budget=1)
    assert "truncated" in text
    assert "get_node" in text or "context_filter" in text


# --- integration: identifier + noise query seeds from identifier (#897) ---

def test_query_seeds_from_identifier_not_noise():
    """'FooBarService error handling' should expand from FooBarService,
    not from error-handler nodes, so ServiceClient appears in results."""
    G = _make_noisy_graph()
    text = _query_graph_text(G, "FooBarService error handling", mode="bfs", depth=2)
    assert "FooBarService" in text
    assert "ServiceClient" in text


def test_query_graph_text_parameter_type_context_filter_changes_traversal():
    graph = make_loaded(
        nodes=[
            {"id": "process", "label": "process", "source_file": "sample.cs", "source_location": "L20"},
            {"id": "payload", "label": "Payload", "source_file": "sample.cs", "source_location": "L5"},
            {"id": "other", "label": "PayloadFactory", "source_file": "sample.cs", "source_location": "L40"},
        ],
        edges=[
            {"source": "process", "target": "payload", "relation": "references", "context": "parameter_type", "confidence": "EXTRACTED"},
            {"source": "process", "target": "other", "relation": "calls", "context": "call", "confidence": "EXTRACTED"},
        ],
    )

    text = _query_graph_text(graph, "who accepts Payload", context_filters=["parameter_type"])

    assert "parameter_type" in text
    assert "Payload" in text
    assert "PayloadFactory" not in text


def test_query_graph_text_context_filter_aliases_resolve():
    from graphify.serve import _normalize_context_filters

    assert _normalize_context_filters(["param"]) == ["parameter_type"]
    assert _normalize_context_filters(["parameter"]) == ["parameter_type"]
    assert _normalize_context_filters(["return"]) == ["return_type"]
    assert _normalize_context_filters(["returns"]) == ["return_type"]
    assert _normalize_context_filters(["generic"]) == ["generic_arg"]
    assert _normalize_context_filters(["generics"]) == ["generic_arg"]
    assert _normalize_context_filters(["annotation"]) == ["attribute"]
    assert _normalize_context_filters(["decorator"]) == ["attribute"]
    # Pass-through for already-canonical values
    assert _normalize_context_filters(["parameter_type"]) == ["parameter_type"]
    assert _normalize_context_filters(["field"]) == ["field"]


# --- Chinese segmentation ---

def test_query_terms_chinese_segments_with_cached_jieba(monkeypatch):
    """Chinese text should use the cached jieba module and keep the original term."""
    import graphify.serve as serve_mod

    class FakeJieba:
        def cut(self, text):
            assert text == "页面路由"
            return ["页面", "路由"]

    monkeypatch.setattr(serve_mod, "_jieba", FakeJieba())
    terms = _query_terms("页面路由")
    assert terms == ["页面", "路由", "页面路由"]


def test_query_terms_chinese_mixed():
    """Mixed Chinese and English text should be handled correctly."""
    terms = _query_terms("前端 router 路由配置")
    assert "前端" in terms
    assert "router" in terms
    assert "路由" in terms
    assert "配置" in terms


def test_query_terms_non_chinese_scripts_are_not_segmented():
    """Japanese kana and Hangul are kept as terms but not segmented as Chinese."""
    import graphify.serve as serve_mod

    assert not serve_mod._has_chinese("かなカナ한글")
    assert serve_mod._query_terms("かなカナ한글") == ["かなカナ한글"]


def test_query_terms_chinese_no_jieba_fallback(monkeypatch):
    """When jieba is not installed, fallback to character bigrams."""
    import graphify.serve as serve_mod

    monkeypatch.setattr(serve_mod, "_jieba", None)
    terms = serve_mod._query_terms("页面路由")
    # bigram fallback: ["页面", "面路", "路由"] + original "页面路由"
    assert "页面" in terms
    assert "路由" in terms
    assert "页面路由" in terms
    assert len(terms) == 4


def test_score_nodes_chinese_substring_match():
    """Searching for '路由' should match a node with label containing '路由'."""
    G = make_loaded(nodes=[
        {"id": "n1", "label": "路由桥接核对表", "source_file": "doc.md", "community": 0},
        {"id": "n2", "label": "其他内容", "source_file": "doc.md", "community": 0},
    ])
    scored = _score_nodes(G, ["路由"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids
    assert "n2" not in nids


def test_query_text_chinese_finds_routing_nodes():
    """Full pipeline: '页面路由' should find nodes with '路由' in label."""
    G = make_loaded(
        nodes=[
            {"id": "parent", "label": "页面路由规范", "source_file": "doc.md", "source_location": "L1", "community": 0},
            {"id": "child", "label": "路由桥接核对表", "source_file": "doc.md", "source_location": "L10", "community": 0},
        ],
        edges=[{"source": "parent", "target": "child", "relation": "contains", "confidence": "EXTRACTED"}],
    )
    text = _query_graph_text(G, "页面路由", mode="bfs", depth=2)
    assert "No matching nodes found." not in text
    assert "路由" in text


# --- get_community header (#1448): show the community name, no placeholder doubling ---

def test_community_header_shows_real_name():
    assert _community_header(12, "Auth & Sessions") == "Community 12 — Auth & Sessions"


def test_community_header_skips_placeholder_name():
    # community_name is written as the "Community N" placeholder for unnamed
    # communities; the header must not read "Community 12 — Community 12".
    assert _community_header(12, "Community 12") == "Community 12"


def test_community_header_falls_back_when_no_name():
    assert _community_header(7, None) == "Community 7"
    assert _community_header(7, "") == "Community 7"


def test_community_header_sanitizes_name():
    # control characters in an LLM-derived name are stripped (F-010)
    out = _community_header(3, "Pay\x00ments\x1b[31m")
    assert out.startswith("Community 3 — ")
    assert "\x00" not in out and "\x1b" not in out


# --- single-pass scoring refactor: reference-impl equality + one-traversal ---


def _reference_best_seed_by_term(G: Any, terms: list[str]) -> dict[str, str]:
    """Test-only oracle for the legacy per-term `_pick_seeds(terms=...)` loop.

    Re-creates what `_pick_seeds` did before the single-pass refactor: rescore
    the whole graph per token via `_score_nodes(G, [token])`, take the top-
    scoring ties, and break them by `max(tied, key=degree)` (which, over a
    list sorted by `(-score, label_len, nid)`, returns the highest-degree node
    with ties broken toward the shortest label then the smallest node id).
    This is the semantics `_score_query(..., collect_per_term_seeds=True)` now
    produces inline during its single traversal.
    """
    norm_terms = sorted({tok for t in terms for tok in _search_tokens(t)})
    best: dict[str, str] = {}
    for term in norm_terms:
        term_scored = _score_nodes(G, [term])
        if not term_scored:
            continue
        best_score = term_scored[0][0]
        tied = [nid for s, nid in term_scored if s == best_score]
        best_nid = max(tied, key=lambda n: _graph(G).degree(n).degree) if len(tied) > 1 else term_scored[0][1]
        best[term] = best_nid
    return best


def _make_random_scoring_graph(n: int, *, seed: int) -> Any:
    """Reproducible broad-match DiGraph: short constructed labels + edge noise.

    Labels draw from a small syllable pool so tokens collide across nodes,
    forcing the trigram prefilter to be selective and exercising score ties
    on common tokens. Edge noise provides degree variance so the legacy
    tie-break (`max(tied, key=degree)`) is exercised against the new
    `(-singleton, -degree, label_len, nid)` key tuple.
    """
    import random

    rng = random.Random(seed)
    syllables = [
        "foo", "bar", "baz", "get", "set", "run", "user", "name", "path",
        "build", "report", "extract", "router", "config", "service",
        "handler", "token", "auth", "rate", "limit", "widget", "model",
    ]
    nodes = []
    for i in range(n):
        label = "_".join(rng.sample(syllables, rng.randint(1, 3)))
        nodes.append({"id": f"n{i}", "label": label, "source_file": f"src/{label[:8]}.py"})
    pairs: set[tuple[int, int]] = set()
    for _ in range(n * 2):
        a, b = rng.randrange(n), rng.randrange(n)
        if a != b:
            pairs.add((a, b))
    edges = [
        {"source": f"n{a}", "target": f"n{b}", "relation": "calls", "confidence": "EXTRACTED"}
        for a, b in sorted(pairs)
    ]
    return make_loaded(nodes=nodes, edges=edges, kind="digraph")


SYLLABLE_QUERIES = [
    ["get"],                                      # single token, exact-match
    ["get", "user"],                              # two distinct tokens
    ["router", "service", "handler"],             # multi-token identifier
    ["extract", "build", "report", "path"],       # broad term
    ["nonexistent"],                              # no matches
    ["nonexistent", "get"],                       # one missing term + match
    ["bar", "bar"],                               # repeated token (must dedupe)
    ["baz", "run", "set", "auth", "rate", "limit"], # many tokens
]


@pytest.mark.parametrize("terms", SYLLABLE_QUERIES)
def test_score_query_ranked_matches_score_nodes_byte_identical(terms):
    """`_score_query(..., collect_per_term_seeds=False).ranked` is the byte-for-
    byte match of `_score_nodes(G, terms)` — guaranteeing path/explain/tests see
    no behavior change from the refactor."""
    G = _make_random_scoring_graph(80, seed=7)
    assert _score_query(G, terms, collect_per_term_seeds=False).ranked == _score_nodes(G, terms)


@pytest.mark.parametrize("terms", SYLLABLE_QUERIES)
def test_score_query_best_seed_by_term_matches_legacy_singleton_scoring(terms):
    """Per-token winner the single-pass scorer records matches the legacy
    `_score_nodes([token])` + `max(tied, key=degree)` oracle exactly."""
    G = _make_random_scoring_graph(80, seed=7)
    ref = _reference_best_seed_by_term(G, terms)
    opt = _score_query(G, terms, collect_per_term_seeds=True).best_seed_by_term
    assert ref == opt, f"terms={terms}: legacy={ref} optimized={opt}"


@pytest.mark.parametrize("terms", SYLLABLE_QUERIES)
def test_pick_seeds_with_optimized_best_seed_matches_legacy_semantics(terms):
    """The seeds produced by `_pick_seeds(qs.ranked, G=G, best_seed_by_term=
    qs.best_seed_by_term)` exactly match what the legacy `_pick_seeds(terms=...)`
    loop would have produced (recreated via the reference oracle)."""
    G = _make_random_scoring_graph(80, seed=7)
    qs = _score_query(G, terms, collect_per_term_seeds=True)
    ref_best = _reference_best_seed_by_term(G, terms)
    # Legacy `_pick_seeds(terms=...)` ran `_score_nodes(G, [term])` per token
    # to build ref_best, then deduped by label key. The new `_pick_seeds(
    # best_seed_by_term=...)` only swaps the source of the per-token winners,
    # so it must produce the same seeds given equivalent inputs.
    opt_seeds = _pick_seeds(qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term)
    ref_seeds = _pick_seeds(qs.ranked, G=G, best_seed_by_term=ref_best)
    assert opt_seeds == ref_seeds, f"terms={terms}: ref={ref_seeds} opt={opt_seeds}"
    # Per-term guarantee: every legacy winner with a non-empty seed slot is
    # accounted for — either it appears in the seed list or another node with
    # the same normalized label already claimed the slot (#1766 label dedup).
    ref_seed_set = set(ref_seeds)
    for term, nid in ref_best.items():
        if nid in ref_seed_set:
            continue
        nid_data = node_attributes(_graph(G), nid)
        nid_label = (nid_data.get("norm_label")
                     or nid_data.get("label")
                     or nid)
        seeded_with_same_label = any(
            (node_attributes(_graph(G), s).get("norm_label")
             or node_attributes(_graph(G), s).get("label") or s) == nid_label
            for s in ref_seeds
        )
        assert seeded_with_same_label, (
            f"term {term!r} winner {nid!r} dropped without label-dedup reason"
        )


def test_score_query_matches_legacy_across_random_deterministic_graphs():
    """Across many deterministic random graphs and many random multi-term
    queries, the single-pass scorer's combined ranking, per-token winners,
    and resulting seed list all match the legacy semantics. Exercises label
    collisions, ties, broad terms, missing terms, and graph size variance."""
    import random

    rng = random.Random(42)
    syllables = [
        "foo", "bar", "baz", "get", "set", "run", "user", "name", "path",
        "build", "report", "extract", "router", "config", "service",
        "handler", "token", "auth", "rate", "limit", "widget", "model",
    ]
    for trial in range(30):
        n = rng.randint(20, 200)
        G = _make_random_scoring_graph(n, seed=rng.randint(0, 10**9))
        nq = rng.randint(1, 5)
        terms = [rng.choice(syllables) for _ in range(nq)]
        ref_best = _reference_best_seed_by_term(G, terms)
        opt = _score_query(G, terms, collect_per_term_seeds=True)
        # (a) Combined ranking unchanged.
        assert opt.ranked == _score_nodes(G, terms), (
            f"trial {trial}: combined ranking diverged for terms={terms}"
        )
        # (b) Per-token winners match the legacy per-term rescoring loop.
        assert opt.best_seed_by_term == ref_best, (
            f"trial {trial}: best_seed_by_term diverged; ref={ref_best} opt={opt.best_seed_by_term}"
        )
        # (c) Final seed list is identical under the legacy semantics.
        ref_seeds = _pick_seeds(opt.ranked, G=G, best_seed_by_term=ref_best)
        opt_seeds = _pick_seeds(opt.ranked, G=G, best_seed_by_term=opt.best_seed_by_term)
        assert opt_seeds == ref_seeds, (
            f"trial {trial}: seeds diverged; ref={ref_seeds} opt={opt_seeds}"
        )


def test_score_query_uses_native_candidate_predicates():
    """Combined and singleton scoring share native bounded candidates."""
    terms = ["router", "service", "handler"]
    G = _make_random_scoring_graph(80, seed=19)
    ref_best = _reference_best_seed_by_term(G, terms)
    opt = _score_query(G, terms, collect_per_term_seeds=True)
    assert opt.ranked == _score_nodes(G, terms)
    assert opt.best_seed_by_term == ref_best


def test_query_graph_text_makes_exactly_one_score_query_call(monkeypatch):
    """`_query_graph_text` must invoke `_score_query` exactly once per query,
    regardless of how many tokens the query has — eliminating the legacy
    T+1-pass rescoring. `_score_nodes` must NOT be called from the query path
    (only path/explain still call it)."""
    import graphify.serve as serve_mod

    G = _make_random_scoring_graph(60, seed=23)
    original_sq = serve_mod._score_query
    original_sn = serve_mod._score_nodes

    state = {"sq": 0, "sn": 0}

    def counting_sq(*a, **k):
        state["sq"] += 1
        return original_sq(*a, **k)

    def counting_sn(*a, **k):
        state["sn"] += 1
        return original_sn(*a, **k)

    monkeypatch.setattr("graphify.serve._score_query", counting_sq)
    monkeypatch.setattr("graphify.serve._score_nodes", counting_sn)

    queries = [
        "foo",                                              # one term
        "foo bar",                                          # two
        "router service handler",                          # three (the scenario the RFC targets)
        "get user run name path",                          # five
        "extract build report router config service token rate limit widget",  # ten
    ]
    for q in queries:
        state["sq"] = 0
        state["sn"] = 0
        _query_graph_text(G, q, mode="bfs", depth=1)
        assert state["sq"] == 1, (
            f"expected exactly one _score_query call for {q!r}, got {state['sq']}"
        )
        assert state["sn"] == 0, (
            f"query path must not call _score_nodes; got {state['sn']} call(s) for {q!r}"
        )


def test_score_query_collect_per_term_seeds_false_omits_tracking(monkeypatch):
    """`collect_per_term_seeds=False` returns empty `best_seed_by_term` and
    does not pay for per-token best tracking — preserving the cost contract
    for path/explain/tests callers that only want the combined ranking."""
    G = _make_random_scoring_graph(50, seed=29)
    qs = _score_query(G, ["foo", "bar", "baz"], collect_per_term_seeds=False)
    assert qs.best_seed_by_term == {}
    # And the combined output is still byte-identical to _score_nodes.
    assert qs.ranked == _score_nodes(G, ["foo", "bar", "baz"])


# --- BUG2: seed survival, truncation notice, deterministic ordering ----------

def _star_graph(n_spokes=40):
    """A high-degree hub plus a low-degree answer node, to force the answer past
    a pure degree-sorted / BFS cut unless seed-first ordering protects it."""
    G = nx.Graph()
    G.add_node("hub", label="Hub", source_file="hub.py", source_location="L1", community=0)
    for i in range(n_spokes):
        G.add_node(f"s{i}", label=f"spoke{i}", source_file=f"s{i}.py", source_location="L1", community=0)
        G.add_edge("hub", f"s{i}", relation="calls", confidence="EXTRACTED")
    # low-degree answer node, attached to one spoke
    G.add_node("answer", label="CompanySpacingGate", source_file="gate.py",
               source_location="L12", community=0)
    G.add_edge("s0", "answer", relation="calls", confidence="EXTRACTED")
    return G


def test_subgraph_to_text_seed_survives_truncation():
    """BUG2: a low-degree answer node passed as a seed is rendered first and
    survives a tiny budget, and truncation is announced."""
    G = _star_graph()
    nodes = set(G.nodes)
    text = _subgraph_to_text(G, nodes, list(G.edges()), token_budget=30, seeds=["answer"])
    assert "CompanySpacingGate" in text, "seed node was cut (BUG2)"
    node_lines = [l for l in text.splitlines() if l.startswith("NODE ")]
    assert "CompanySpacingGate" in node_lines[0], "seed must render first"
    assert "TRUNCATED" in text


def test_query_graph_text_passes_seeds_so_answer_survives():
    """BUG2 regression guard: the query path must pass seeds to the renderer (a
    branch merge had dropped the argument), so a queried low-degree symbol
    appears in the body even when the output is truncated."""
    G = _star_graph()
    text = _query_graph_text(G, "CompanySpacingGate", mode="bfs", depth=2, token_budget=40)
    # Present in the body, not merely the Start: header.
    body = text.split("\n\n", 1)[-1]
    assert "CompanySpacingGate" in body


def test_subgraph_to_text_truncation_notice_at_top():
    G = _star_graph()
    text = _subgraph_to_text(G, set(G.nodes), list(G.edges()), token_budget=30, seeds=["answer"])
    assert text.startswith("[!] TRUNCATED"), f"notice not at top: {text[:60]!r}"
    assert "of" in text.splitlines()[0] and "nodes" in text.splitlines()[0]
    assert "truncated" in text  # end marker still present


def test_subgraph_to_text_no_notice_when_under_budget():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")], token_budget=2000)
    assert "TRUNCATED" not in text and "truncated" not in text


def test_subgraph_to_text_order_is_deterministic():
    """Equal-degree nodes render in a stable order regardless of set iteration."""
    G = nx.Graph()
    for i in range(10):
        G.add_node(f"z{i}", label=f"z{i}", source_file=f"z{i}.py", source_location="L1", community=0)
    nodes = set(G.nodes)
    a = _subgraph_to_text(G, nodes, [])
    b = _subgraph_to_text(G, set(reversed(list(nodes))), [])
    assert a == b


# --- #2069: token budget on get_neighbors / get_community line lists ----------

def test_cut_lines_to_budget_under_budget_is_byte_identical():
    lines = ["Neighbors of X:", "  --> a [calls] [EXTRACTED]", "  --> b [calls] [EXTRACTED]"]
    out = _cut_lines_to_budget(lines, token_budget=2000, narrow_hint="use relation_filter")
    assert out == "\n".join(lines)
    assert "TRUNCATED" not in out and "truncated" not in out


def test_cut_lines_to_budget_over_budget_announces_at_top():
    lines = [f"  --> node{i} [calls] [EXTRACTED]" for i in range(200)]
    out = _cut_lines_to_budget(lines, token_budget=20, narrow_hint="use get_node for a specific symbol")
    # Top notice (silence must not read as absence) + accurate counts + bottom marker + hint.
    assert out.startswith("[!] TRUNCATED: showing ")
    first = out.splitlines()[0]
    assert "of 200 lines" in first
    assert "use get_node for a specific symbol" in out
    assert "truncated" in out  # end marker retained
    # shown count in the notice matches the actual kept line count.
    import re
    shown = int(re.search(r"showing (\d+) of", first).group(1))
    body = out.split("\n\n", 1)[1].split("\n... (truncated", 1)[0]
    assert body.count("\n") + 1 == shown


def test_subgraph_to_text_ignores_dangling_src_tgt(monkeypatch):
    """#2080 review: a stray/dangling _src/_tgt on an edge (hand-edited or
    adversarial graph.json) must NOT crash rendering; fall back to (u, v)."""
    G = nx.Graph()
    G.add_node("a", label="Alpha", source_file="a.py", source_location="L1", community=0)
    G.add_node("b", label="Beta", source_file="b.py", source_location="L2", community=0)
    # _src names a node that doesn't exist -> must be ignored, no KeyError.
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED", _src="ghost", _tgt="b")
    out = _subgraph_to_text(G, {"a", "b"}, [("a", "b")])
    assert "EDGE" in out and "Alpha" in out and "Beta" in out  # rendered, didn't crash


def test_subgraph_to_text_honors_valid_src_tgt_direction():
    """#2080: a valid _src/_tgt (the stored direction) is honored even when the
    traversal tuple is reversed."""
    G = nx.Graph()
    G.add_node("caller", label="caller", source_file="c.py", source_location="L1", community=0)
    G.add_node("callee", label="callee", source_file="d.py", source_location="L2", community=0)
    # Edge collected as (callee, caller) by traversal, but stored direction is caller->callee.
    G.add_edge("callee", "caller", relation="calls", confidence="EXTRACTED", _src="caller", _tgt="callee")
    out = _subgraph_to_text(G, {"caller", "callee"}, [("callee", "caller")])
    edge_line = next(l for l in out.splitlines() if l.startswith("EDGE"))
    assert "caller --calls" in edge_line and "--> callee" in edge_line
