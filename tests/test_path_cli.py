"""Regression tests for `graphify path` arrow direction (#849) and determinism +
honest edge labels (#2074)."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import networkx as nx
import pytest
from networkx.readwrite import json_graph
import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "create_patch", "label": "createPatchHandler()",
             "source_file": "server/create-patch-handler.ts", "community": 0},
            {"id": "validate", "label": "validateSanitySession()",
             "source_file": "server/sanity-validate-session.ts", "community": 0},
        ],
        "links": [
            {"source": "create_patch", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, graph_path, src, tgt, capsys, *extra):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", src, tgt, "--graph", str(graph_path), *extra])
    mainmod.main()
    return capsys.readouterr().out


def test_forward_arrow(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", "validateSanitySession", capsys)
    assert "Shortest path (1 hops):" in out
    assert "createPatchHandler() --calls [EXTRACTED]--> validateSanitySession()" in out


def test_reverse_arrow(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    # #2487: path is directed by default, so walking the stored edge backwards
    # needs the --undirected opt-out to exercise the reverse-arrow rendering.
    out = _run(monkeypatch, p, "validateSanitySession", "createPatchHandler", capsys,
               "--undirected")
    assert "Shortest path (1 hops):" in out
    assert "validateSanitySession() <--calls [EXTRACTED]-- createPatchHandler()" in out
    assert "validateSanitySession() --calls [EXTRACTED]--> createPatchHandler()" not in out


def _write_misranking_graph(tmp_path):
    """Graph where IDF scoring ranks a partial-token decoy above the full match.

    Query "Reject-everything judge": the decoy "Rejection Summary" prefix-matches
    the rare token "reject" and out-scores "Degenerate Reject-Everything Judge"
    (whose full-query tier never fires — the query is a token subset of the
    label, not a prefix). The filler nodes make "judge"/"everything" common so
    their IDF stays low. Decoy and target live in different components: resolving
    the source to the decoy yields a false "No path found".
    """
    nodes = [
        {"id": "target", "label": "Degenerate Reject-Everything Judge", "community": 0},
        {"id": "decoy", "label": "Rejection Summary", "community": 0},
    ]
    for i in range(30):
        nodes.append({"id": f"j{i}", "label": f"Judge Helper {i}", "community": 0})
        nodes.append({"id": f"e{i}", "label": f"Everything Widget {i}", "community": 0})
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": nodes,
        "links": [
            {"source": "target", "target": "j0",
             "relation": "verified_by", "confidence": "EXTRACTED"},
            {"source": "decoy", "target": "e0",
             "relation": "mentions", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_endpoint_prefers_full_token_match(monkeypatch, tmp_path, capsys):
    """A token-subset query resolves to the full-match node, not the IDF head."""
    p = _write_misranking_graph(tmp_path)
    out = _run(monkeypatch, p, "Reject-everything judge", "Judge Helper 0", capsys)
    assert "Shortest path (1 hops):" in out
    assert "Degenerate Reject-Everything Judge" in out
    assert "No path found" not in out


def test_endpoint_falls_back_to_score_head(monkeypatch, tmp_path, capsys):
    """No full-token candidate -> behavior identical to the old scored[0] pick."""
    p = _write_misranking_graph(tmp_path)
    # "Rejection judge" full-matches nothing ("rejection" only appears in the
    # decoy, "judge" never joins it), so the IDF head (the decoy) still wins,
    # and the disconnected components make that a "No path found" exit(0).
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", "Rejection judge", "Judge Helper 0", "--graph", str(p)])
    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 0
    # #2487: path is directed by default, so the flagless no-path message is
    # now the directed one (the decoy/target components stay disconnected
    # either way — this test is about endpoint resolution, not direction).
    assert "No directed path found" in capsys.readouterr().out


# ── #2074: deterministic route + honest edge relation ────────────────────────

def _diamond_graph(tmp_path):
    """Two equal-length routes A->P->B and A->Q->B — a tie the traversal must
    resolve deterministically."""
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "a", "label": "Alpha", "source_file": "a.py"},
            {"id": "p", "label": "Pmid", "source_file": "p.py"},
            {"id": "q", "label": "Qmid", "source_file": "q.py"},
            {"id": "b", "label": "Beta", "source_file": "b.py"},
        ],
        "links": [
            {"source": "a", "target": "p", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "p", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "a", "target": "q", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "q", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    return p


def _arrow_line(stdout: str) -> str:
    return next((l.strip() for l in stdout.splitlines() if "-->" in l or "<--" in l), "")


def test_path_deterministic_across_hash_seeds(tmp_path):
    """#2074: the same graph must yield the same route regardless of
    PYTHONHASHSEED. pytest fixes the seed per process, so run out-of-process."""
    gp = _diamond_graph(tmp_path)
    routes = set()
    for seed in ("0", "1", "2", "3", "4", "5", "6", "7"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run(
            [sys.executable, "-m", "graphify", "path", "Alpha", "Beta", "--graph", str(gp)],
            capture_output=True, text=True, env=env, cwd=str(tmp_path),
        )
        assert r.returncode == 0, r.stderr
        routes.add(_arrow_line(r.stdout))
    assert len(routes) == 1, f"non-deterministic path across hash seeds: {routes}"
    # Canonical tie-break picks the lexicographically-smaller mid node (Pmid).
    assert "Pmid" in next(iter(routes))


def test_path_relation_matches_stored_edge_not_fabricated(monkeypatch, tmp_path, capsys):
    """#2074: the printed relation must be the edge's ACTUAL stored relation,
    never a hardcoded/fabricated `calls`."""
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "a", "label": "Alpha", "source_file": "a.py"},
            {"id": "b", "label": "Beta", "source_file": "b.py"},
        ],
        "links": [
            {"source": "a", "target": "b", "relation": "references", "confidence": "INFERRED"},
        ],
    }
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(data))
    out = _run(monkeypatch, gp, "Alpha", "Beta", capsys)
    assert "--references [INFERRED]-->" in out
    assert "calls" not in out


def test_path_relation_fallback_related_when_missing(monkeypatch, tmp_path, capsys):
    """#2074: an edge with no stored relation prints an honest 'related', not an
    empty '---->' arrow and not a fabricated relation."""
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "a", "label": "Alpha", "source_file": "a.py"},
            {"id": "b", "label": "Beta", "source_file": "b.py"},
        ],
        "links": [{"source": "a", "target": "b"}],
    }
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(data))
    out = _run(monkeypatch, gp, "Alpha", "Beta", capsys)
    assert "--related-->" in out
    assert "---->" not in out.replace("--related-->", "")


# ── #2309: hop direction must honor _src/_tgt markers, not stored arc order ──

def _flipped_marker_graph(tmp_path):
    """3-node chain where the middle link is PERSISTED in flipped endpoint
    order (source/target swapped) but carries its direction truth in the
    per-link _src/_tgt markers — the shape produced by pre-#563 graphs, raw
    node_link_data dumps, and undirected-storage canonicalization."""
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "ingest", "label": "ingest.ts", "source_file": "src/ingest.ts"},
            {"id": "logger", "label": "logger.ts", "source_file": "src/logger.ts"},
            {"id": "draft", "label": "draft-generator.ts",
             "source_file": "src/draft-generator.ts"},
        ],
        "links": [
            # Canonical order + matching markers.
            {"source": "ingest", "target": "logger",
             "_src": "ingest", "_tgt": "logger",
             "relation": "calls", "confidence": "EXTRACTED"},
            # FLIPPED persisted order; truth is draft --imports_from--> logger.
            {"source": "logger", "target": "draft",
             "_src": "draft", "_tgt": "logger",
             "relation": "imports_from", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    return p


def test_path_direction_recovered_from_src_tgt_markers(monkeypatch, tmp_path, capsys):
    """#2309: a hop over a link stored in flipped order must render the TRUE
    direction from its _src/_tgt markers, not the persisted arc order."""
    p = _flipped_marker_graph(tmp_path)
    # #2487: the two hops point in opposite TRUE directions (ingest->logger,
    # draft->logger), so this mixed-direction route only exists undirected.
    out = _run(monkeypatch, p, "ingest", "draft-generator", capsys, "--undirected")
    assert "Shortest path (2 hops):" in out
    assert "ingest.ts --calls [EXTRACTED]--> logger.ts" in out
    # True direction is draft -> logger, so the logger->draft hop is reversed.
    assert "logger.ts <--imports_from [EXTRACTED]-- draft-generator.ts" in out
    assert "--imports_from [EXTRACTED]-->" not in out


def test_path_canonical_marker_graph_still_forward(monkeypatch, tmp_path, capsys):
    """#2309 control: a to_json-shaped graph whose markers AGREE with the
    persisted source/target order keeps rendering forward (no regression)."""
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "a", "label": "Alpha", "source_file": "a.py"},
            {"id": "b", "label": "Beta", "source_file": "b.py"},
        ],
        "links": [
            {"source": "a", "target": "b", "_src": "a", "_tgt": "b",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(data))
    out = _run(monkeypatch, gp, "Alpha", "Beta", capsys)
    assert "Alpha --calls [EXTRACTED]--> Beta" in out
    # And walking the same edge backwards still reverses the arrow (#2487:
    # backwards traversal now requires the --undirected opt-out).
    out = _run(monkeypatch, gp, "Beta", "Alpha", capsys, "--undirected")
    assert "Beta <--calls [EXTRACTED]-- Alpha" in out


# ── #3878: a `contains` edge has no reverse hop back out to its file ────────

def _file_to_symbol_only_graph(tmp_path):
    """`a.py` imports `helper()`, which `b.py` contains — but no edge runs
    file-to-file directly, and `contains` only runs b.py -> helper()."""
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "a", "label": "a.py", "source_file": "a.py"},
            {"id": "b", "label": "b.py", "source_file": "b.py"},
            {"id": "helper", "label": "helper()", "source_file": "b.py"},
        ],
        "links": [
            {"source": "a", "target": "helper", "relation": "imports", "confidence": "EXTRACTED"},
            {"source": "b", "target": "helper", "relation": "contains", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    return p


def test_path_routes_through_a_contains_edge_to_reach_the_file(monkeypatch, tmp_path, capsys):
    """A file-to-file dependency that only closes through a contained symbol
    must still resolve, not report no path despite both halves existing."""
    p = _file_to_symbol_only_graph(tmp_path)
    out = _run(monkeypatch, p, "a.py", "b.py", capsys)
    assert "Shortest path (2 hops):" in out
    assert "a.py --imports [EXTRACTED]--> helper() <--contains [EXTRACTED]-- b.py" in out
    assert "No directed path found" not in out


def test_explain_direction_recovered_from_src_tgt_markers(monkeypatch, tmp_path, capsys):
    """#2309: explain's in/out classification must honor _src markers — an
    edge persisted as hub->spoke but truly spoke->hub is an IN edge of hub."""
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "hub", "label": "hub.ts", "source_file": "src/hub.ts"},
            {"id": "spoke", "label": "spoke.ts", "source_file": "src/spoke.ts"},
        ],
        "links": [
            # Persisted arc hub->spoke, but the markers say spoke calls hub.
            {"source": "hub", "target": "spoke",
             "_src": "spoke", "_tgt": "hub",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(data))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "hub", "--graph", str(gp)])
    mainmod.main()
    out = capsys.readouterr().out
    assert "<-- spoke.ts [calls]" in out
    assert "--> spoke.ts" not in out


# ── #3913: endpoints resolve like `explain` (refuse ambiguity, honor ::/id) ──

def _twin_method_graph(tmp_path):
    """`.nonce()` defined on a class in each of two files, both reachable from run()."""
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "src_main", "label": "main.ts", "source_file": "src/main.ts",
             "source_location": "L1"},
            {"id": "src_main_run", "label": "run()", "source_file": "src/main.ts",
             "source_location": "L3"},
            {"id": "src_a", "label": "a.ts", "source_file": "src/a.ts",
             "source_location": "L1"},
            {"id": "src_a_alphaclient", "label": "AlphaClient", "source_file": "src/a.ts",
             "source_location": "L1"},
            {"id": "src_a_alphaclient_nonce", "label": ".nonce()", "source_file": "src/a.ts",
             "source_location": "L1"},
            {"id": "src_b", "label": "b.ts", "source_file": "src/b.ts",
             "source_location": "L1"},
            {"id": "src_b_betaclient", "label": "BetaClient", "source_file": "src/b.ts",
             "source_location": "L1"},
            {"id": "src_b_betaclient_nonce", "label": ".nonce()", "source_file": "src/b.ts",
             "source_location": "L1"},
        ],
        "links": [
            {"source": "src_main", "target": "src_main_run", "relation": "contains",
             "confidence": "EXTRACTED"},
            {"source": "src_main_run", "target": "src_a_alphaclient", "relation": "calls",
             "confidence": "EXTRACTED"},
            {"source": "src_main_run", "target": "src_b_betaclient", "relation": "calls",
             "confidence": "EXTRACTED"},
            {"source": "src_a", "target": "src_a_alphaclient", "relation": "contains",
             "confidence": "EXTRACTED"},
            {"source": "src_b", "target": "src_b_betaclient", "relation": "contains",
             "confidence": "EXTRACTED"},
            {"source": "src_a_alphaclient", "target": "src_a_alphaclient_nonce",
             "relation": "method", "confidence": "EXTRACTED"},
            {"source": "src_b_betaclient", "target": "src_b_betaclient_nonce",
             "relation": "method", "confidence": "EXTRACTED"},
        ],
    }
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(data))
    return gp


@pytest.mark.parametrize("ends", [("run()", ".nonce()"), (".nonce()", "run()")])
def test_path_refuses_ambiguous_endpoint(monkeypatch, tmp_path, capsys, ends):
    """A bare label naming symbols in two files is refused with the candidate ids,
    as `explain` does, instead of a confident route through one of them — on
    either end of the path."""
    gp = _twin_method_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", *ends, "--graph", str(gp)])
    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Shortest path" not in captured.out
    assert "Ambiguous: '.nonce()' matches 2 nodes in different files." in captured.err
    assert "src_a_alphaclient_nonce" in captured.err
    assert "src_b_betaclient_nonce" in captured.err


@pytest.mark.parametrize("target", ["src/b.ts::.nonce()", "src_b_betaclient_nonce"])
def test_path_endpoint_selects_named_node(monkeypatch, tmp_path, capsys, target):
    """The two retry forms `explain` suggests (`path::symbol`, full node id) end
    the route at that method, not at its file or containing class."""
    gp = _twin_method_graph(tmp_path)
    out = _run(monkeypatch, gp, "run()", target, capsys)
    assert "Shortest path (2 hops):" in out
    assert "run() --calls [EXTRACTED]--> BetaClient --method [EXTRACTED]--> .nonce()" in out


def test_shortest_path_tool_refuses_ambiguous_endpoint(tmp_path):
    """The MCP `shortest_path` tool shares the resolution and refuses the same way."""
    from graphify.serve import _shortest_path_text
    raw = json.loads(_twin_method_graph(tmp_path).read_text())
    G = json_graph.node_link_graph({**raw, "directed": True}, edges="links")
    out = _shortest_path_text(G, {"source": "run()", "target": ".nonce()"})
    assert out.startswith("Ambiguous: '.nonce()' matches 2 nodes in different files.")
    out = _shortest_path_text(G, {"source": ".nonce()", "target": "run()"})
    assert out.startswith("Ambiguous: '.nonce()' matches 2 nodes in different files.")
    out = _shortest_path_text(G, {"source": "run()", "target": "src/b.ts::.nonce()"})
    assert "Shortest path (2 hops):" in out
    assert "BetaClient --method [EXTRACTED]--> .nonce()" in out


def _write_nodes(tmp_path, nodes, links):
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": i, "label": lbl, "source_file": sf, "source_location": loc}
            for i, lbl, sf, loc in nodes
        ],
        "links": [
            {"source": a, "target": b, "relation": rel, "confidence": "EXTRACTED"}
            for a, b, rel in links
        ],
    }))
    return gp


def _same_file_twin_graph(tmp_path):
    """`.nonce()` on two classes of one file, both reachable from run()."""
    return _write_nodes(tmp_path, [
        ("src_x", "x.ts", "src/x.ts", "L1"),
        ("src_x_run", "run()", "src/x.ts", "L3"),
        ("src_x_alphaclient", "AlphaClient", "src/x.ts", "L5"),
        ("src_x_alphaclient_nonce", ".nonce()", "src/x.ts", "L6"),
        ("src_x_betaclient", "BetaClient", "src/x.ts", "L9"),
        ("src_x_betaclient_nonce", ".nonce()", "src/x.ts", "L10"),
    ], [
        ("src_x", "src_x_run", "contains"),
        ("src_x_run", "src_x_alphaclient", "calls"),
        ("src_x_run", "src_x_betaclient", "calls"),
        ("src_x_alphaclient", "src_x_alphaclient_nonce", "method"),
        ("src_x_betaclient", "src_x_betaclient_nonce", "method"),
    ])


@pytest.mark.parametrize("target", [".nonce()", "src/x.ts::.nonce()"])
def test_path_refuses_same_file_duplicate_endpoint(monkeypatch, tmp_path, capsys, target):
    """Two same-named symbols in one file used to be split by graph order behind
    a score-tie warning; path::symbol cannot tell them apart either, so they are
    refused with the ids, the one form that can."""
    gp = _same_file_twin_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", "run()", target, "--graph", str(gp)])
    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Shortest path" not in captured.out
    assert f"Ambiguous: '{target}' matches 2 nodes in src/x.ts." in captured.err
    assert "src_x_alphaclient_nonce" in captured.err
    assert "src_x_betaclient_nonce" in captured.err
    assert "Retry with the full node id." in captured.err


def test_path_same_file_endpoints_still_resolve(monkeypatch, tmp_path, capsys):
    """The node id picks one of the twins, and a file-path query (file node plus
    its members, one file) stays a file lookup rather than an ambiguity."""
    gp = _same_file_twin_graph(tmp_path)
    out = _run(monkeypatch, gp, "run()", "src_x_betaclient_nonce", capsys)
    assert "run() --calls [EXTRACTED]--> BetaClient --method [EXTRACTED]--> .nonce()" in out
    out = _run(monkeypatch, gp, "src/x.ts", "src_x_betaclient_nonce", capsys)
    assert "Shortest path (3 hops):" in out


def test_ambiguity_hint_names_symbol_not_query(monkeypatch, tmp_path, capsys):
    """`index.ts::foo()` whose path suffix matches two files is refused; the retry
    hint shows `<path>::foo()`, not the query repeated behind another path."""
    from graphify.serve import _shortest_path_text
    gp = _write_nodes(tmp_path, [
        ("a_index_foo", "foo()", "a/index.ts", "L3"),
        ("b_index_foo", "foo()", "b/index.ts", "L3"),
    ], [])
    G = json_graph.node_link_graph(
        {**json.loads(gp.read_text()), "directed": True}, edges="links")
    out = _shortest_path_text(G, {"source": "index.ts::foo()", "target": "a_index_foo"})
    assert "(e.g. <path>::foo())" in out
    assert "<path>::index.ts::" not in out
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "index.ts::foo()", "--graph", str(gp)])
    with pytest.raises(SystemExit):
        mainmod.main()
    out = capsys.readouterr().out
    assert "(e.g. <path>::foo())" in out
    assert "<path>::index.ts::" not in out
