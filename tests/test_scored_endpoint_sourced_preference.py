"""The scored-endpoint path must prefer a sourced node over a sourceless stub
(#54, extending #49's rule from `_find_node` to `_score_nodes`).

`_find_node_tiers` drops sourceless nodes from a mixed exact tier (#49), so
`explain` and `affected` resolve `FooRepository` to the real declaration. The
scored path `graphify query` / `shortest_path` run on — `_score_nodes` ranking,
then `_pick_scored_endpoint` / `_pick_seeds` — never learned that rule: a stub
and a sourced declaration sharing a label score *identically* (5619.08 on the
two-node repro below), so the score sort fell through to its node-id tie-break
and answered with whichever id sorted first. `graphify query` then traversed a
stub's neighborhood and `shortest_path` anchored on a disconnected placeholder
and reported "No path found" — while `explain` confidently named the other node.
The comment at serve.py:515-520 states the design intent this violated: `path`
and `query` resolve the same node `explain` does.

The carve-out is #49's: the rule demotes a stub against a real declaration, it
does not delete it. When every candidate is sourceless the stub still wins.
"""
from __future__ import annotations

import pytest
from networkx.readwrite import json_graph

from graphify.affected import resolve_seed
from graphify.serve import (
    _find_node,
    _pick_scored_endpoint,
    _query_graph_text,
    _score_nodes,
    _score_query,
    _shortest_path_text,
)


LABEL = "FooRepository"
SOURCED_ID = "zzz_src"
SOURCE_FILE = "app/bindings.php"


def _stub(index: int = 0, *, omit_source_key: bool = False) -> dict:
    """A sourceless stub, id-sorted *ahead* of the sourced node (the repro shape).

    `omit_source_key` reproduces the attributeless node serve materializes for a
    dangling edge endpoint (no `source_file` key at all, not an empty one).
    """
    node = {"id": f"aaa_stub{index}", "label": LABEL, "community": 0}
    if not omit_source_key:
        node["source_file"] = ""
    return node


def _sourced() -> dict:
    return {"id": SOURCED_ID, "label": LABEL, "source_file": SOURCE_FILE,
            "source_location": "L10", "community": 0}


def _load(nodes: list[dict], links: list[dict] | None = None):
    return json_graph.node_link_graph(
        {"directed": True, "multigraph": False, "graph": {},
         "nodes": nodes, "links": links or []},
        edges="links",
    )


def _endpoint(G, query: str = LABEL) -> str:
    """Resolve `query` exactly as `shortest_path` resolves each of its endpoints."""
    scored = _score_nodes(G, [t.lower() for t in query.split()])
    assert scored, "precondition: the query must match something"
    return _pick_scored_endpoint(G, scored, query)


# --- criterion 1: the reviewer's two-node repro ------------------------------


def test_scored_endpoint_prefers_the_sourced_node():
    """Both nodes score 5619.08; the id sort used to hand back the stub."""
    G = _load([_stub(), _sourced()])
    scored = _score_nodes(G, ["foorepository"])
    assert {nid for _s, nid in scored} == {"aaa_stub0", SOURCED_ID}
    assert scored[0][0] == pytest.approx(scored[1][0]), "the repro is a score tie"
    assert _pick_scored_endpoint(G, scored, LABEL) == SOURCED_ID


@pytest.mark.parametrize("stub_count", [1, 2, 3, 18])
def test_scored_endpoint_prefers_the_sourced_node_at_any_stub_count(stub_count):
    """The rule is a presence test on `source_file`, never a count threshold."""
    G = _load([_stub(i) for i in range(stub_count)] + [_sourced()])
    assert _endpoint(G) == SOURCED_ID


def test_scored_endpoint_answer_does_not_depend_on_node_order():
    stubs = [_stub(i) for i in range(3)]
    forward = _load(stubs + [_sourced()])
    reverse = _load([_sourced()] + list(reversed(stubs)))
    assert _endpoint(forward) == _endpoint(reverse) == SOURCED_ID


def test_attributeless_dangling_endpoints_are_also_stubs():
    """A dangling edge endpoint has no `source_file` key at all — same rule."""
    G = _load([_stub(i, omit_source_key=True) for i in range(3)] + [_sourced()])
    assert _endpoint(G) == SOURCED_ID


# --- criterion 2: a stub with no sourced rival is still an answer ------------


@pytest.mark.parametrize("omit_source_key", [False, True])
def test_lone_stub_with_no_sourced_rival_still_resolves(omit_source_key):
    """#49's carve-out: demoted against a real declaration, never deleted."""
    stub = _stub(0, omit_source_key=omit_source_key)
    G = _load([stub])
    assert _endpoint(G) == stub["id"]


@pytest.mark.parametrize("stub_count", [2, 18])
def test_all_sourceless_candidates_still_return_one(stub_count):
    """Never return nothing where today something returns."""
    G = _load([_stub(i) for i in range(stub_count)])
    assert _endpoint(G) in {f"aaa_stub{i}" for i in range(stub_count)}


def test_query_over_only_stubs_still_traverses_them():
    G = _load(
        [_stub(0), {"id": "beta", "label": "BetaService", "source_file": "app/Beta.php",
                    "community": 0}],
        [{"source": "aaa_stub0", "target": "beta", "context": "call"}],
    )
    out = _query_graph_text(G, LABEL)
    assert "No matching nodes found." not in out
    assert "BetaService" in out


# --- criterion 3: query / shortest_path agree with explain's _find_node ------


@pytest.mark.parametrize("stub_count", [1, 2, 18])
def test_scored_path_agrees_with_find_node_and_resolve_seed(stub_count):
    G = _load([_stub(i) for i in range(stub_count)] + [_sourced()])
    assert _endpoint(G) == _find_node(G, LABEL)[0] == resolve_seed(G, LABEL) == SOURCED_ID


def _repro_graph_with_neighbors():
    """The repro pair, each node in its own component.

    `AlphaService` hangs off the sourced declaration, `BetaService` off the stub,
    so which endpoint got picked is visible in the traversal output and in
    whether `shortest_path` finds a path at all. Both edges point away from the
    `FooRepository` node so the directed defaults of `query` and `shortest_path`
    reach the neighbor. The two rivals necessarily share a label, so the endpoint
    is identified by which neighbor the answer reaches, not by name.
    """
    return _load(
        [
            _stub(),
            _sourced(),
            {"id": "alpha", "label": "AlphaService", "source_file": "app/Alpha.php",
             "source_location": "L4", "community": 0},
            {"id": "beta", "label": "BetaService", "source_file": "app/Beta.php",
             "source_location": "L4", "community": 0},
        ],
        [
            {"source": SOURCED_ID, "target": "alpha", "context": "call"},
            {"source": "aaa_stub0", "target": "beta", "context": "call"},
        ],
    )


def test_shortest_path_anchors_on_the_sourced_node():
    """Anchored on the stub, this query was a false "No path found"."""
    G = _repro_graph_with_neighbors()
    out = _shortest_path_text(G, {"source": LABEL, "target": "AlphaService"})
    assert "No path" not in out and "No directed path" not in out
    assert "FooRepository --related--> AlphaService" in out


def test_query_traverses_the_sourced_nodes_neighborhood():
    G = _repro_graph_with_neighbors()
    out = _query_graph_text(G, LABEL)
    assert "AlphaService" in out
    assert "BetaService" not in out


# --- the per-term seed winner needs the rule too ----------------------------


def _decorated_pair():
    """A stub whose label normalizes *differently* from its sourced rival's.

    `_pick_seeds` dedupes seeds by normalized label, so on the same-label repro
    above the stub's per-term entry is dropped before it can be seeded and the
    combined-ranking half of the fix carries the whole outcome. A decorated
    declaration breaks that cover: `handle` and `handle()` are distinct dedup
    keys, so the stub keeps its own seat and `best_seed_by_term`'s own tie-break
    is the only thing deciding which node fills it (the #49 suite pins the same
    pair for `resolve_seed`'s bare-name pass).
    """
    return _load([
        {"id": "aaa_stub_handle", "label": "handle", "source_file": "", "community": 0},
        {"id": "zzz_app_svc_handle", "label": "handle()",
         "source_file": "app/Svc.php", "source_location": "L9", "community": 0},
    ])


def test_per_term_seed_winner_prefers_the_sourced_node():
    """Pins the `best_seed_by_term` half of the fix, which the same-label repro
    cannot reach — goes red if the singleton tie-break key drops its sourced
    preference."""
    G = _decorated_pair()
    qs = _score_query(G, ["handle"], collect_per_term_seeds=True)
    assert qs.best_seed_by_term == {"handle": "zzz_app_svc_handle"}


def test_query_ranks_the_sourced_node_first_for_a_decorated_declaration():
    """The same pair through the query pipeline. Both labels survive the seed
    dedupe here, so both get seeded — what the rule decides is the order, and the
    top seed is what `_pick_seeds`' coverage check and the seed-first rendering
    both key off.
    """
    G = _decorated_pair()
    out = _query_graph_text(G, "handle")
    assert "Start: ['handle()', 'handle']" in out
    assert out.index("NODE handle() [src=app/Svc.php") < out.index("NODE handle [src=")


# --- the pre-existing sourced-vs-sourced tie is untouched -------------------


def test_two_sourced_rivals_keep_their_existing_tie_break():
    """Sourced-vs-sourced (#2032's symbol case) still resolves by the id sort."""
    G = _load([
        {"id": "chat_port", "label": "MetricsPort",
         "source_file": "services/chat/ports/metrics.port.ts", "community": 0},
        {"id": "scrape_port", "label": "MetricsPort",
         "source_file": "services/scraping/ports/metrics.port.ts", "community": 0},
    ])
    assert _endpoint(G, "MetricsPort") == "chat_port"
