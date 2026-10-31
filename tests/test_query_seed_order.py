"""The per-term guaranteed seeds follow the strength of each term's best match, strongest first.

`_pick_seeds` guarantees one seed per query term (#1445). Those seeds used to be appended in alphabetical term
order, and the renderer prints seeds first, so on a long query a weak match on an early-alphabet term was printed
ahead of a specific term's exact match. `_score_query` now returns `term_order` (strongest per-term winner first,
the term breaking ties) and `_query_graph_text` passes it on. Which seeds are picked does not change, only their
order, and the order stays deterministic."""
from __future__ import annotations

import networkx as nx

from graphify.serve import _pick_seeds, _query_graph_text, _score_query


def _graph():
    G = nx.Graph()
    G.add_node("top", label="TopLevelRouter", source_file="router.py", source_location="L1")
    G.add_node("apple_weak", label="apple_pie_formatting_helper", source_file="fmt.py", source_location="L3")
    G.add_node("zebra_exact", label="zebra", source_file="zebra.py", source_location="L1")
    for i in range(6):   # make "apple" common, so its match weighs less
        G.add_node(f"apple{i}", label=f"apple_util_{i}", source_file=f"apples{i}.py", source_location="L1")
    G.add_edge("top", "apple_weak")
    G.add_edge("top", "zebra_exact")
    return G


def test_pick_seeds_follows_term_order_when_given():
    G = _graph()
    scored = [(1000.0, "top"), (1.0, "apple_weak"), (1.0, "zebra_exact")]
    best = {"apple": "apple_weak", "zebra": "zebra_exact"}
    assert _pick_seeds(scored, G=G, best_seed_by_term=best, term_order=("zebra", "apple")) == ["top", "zebra_exact", "apple_weak"]


def test_pick_seeds_keeps_sorted_term_order_without_it():
    G = _graph()
    scored = [(1000.0, "top"), (1.0, "apple_weak"), (1.0, "zebra_exact")]
    best = {"apple": "apple_weak", "zebra": "zebra_exact"}
    assert _pick_seeds(scored, G=G, best_seed_by_term=best) == ["top", "apple_weak", "zebra_exact"]


def test_pick_seeds_appends_terms_missing_from_term_order_in_sorted_order():
    G = _graph()
    scored = [(1000.0, "top")]
    best = {"apple": "apple_weak", "zebra": "zebra_exact"}
    assert _pick_seeds(scored, G=G, best_seed_by_term=best, term_order=("zebra",)) == ["top", "zebra_exact", "apple_weak"]


def test_score_query_orders_terms_by_their_best_match_strength():
    qs = _score_query(_graph(), ["apple", "zebra"], collect_per_term_seeds=True)
    assert set(qs.term_order) == set(qs.best_seed_by_term)
    assert qs.term_order[0] == "zebra"            # an exact label match on a rare term leads
    assert qs.best_seed_by_term["zebra"] == "zebra_exact"


def _five_term_graph():
    """Five terms with exact label matches; "apple" is common (eight more labels contain it), so its exact match
    carries less IDF weight than the rare "charlie". Three seeds fill the gap window; "apple" and "charlie" arrive
    through the per-term guarantee."""
    G = nx.Graph()
    for name in ("alpha", "bravo", "charlie", "zebra", "apple"):
        G.add_node(name, label=name, source_file=f"{name}.py", source_location="L1")
    for i in range(8):
        G.add_node(f"apple{i}", label=f"apple_util_{i}", source_file=f"apples{i}.py", source_location="L1")
    return G


def test_query_prints_the_stronger_guaranteed_seed_first_and_is_deterministic():
    G = _five_term_graph()
    text = _query_graph_text(G, "alpha bravo charlie apple zebra", mode="bfs", depth=1)
    assert text == _query_graph_text(G, "alpha bravo charlie apple zebra", mode="bfs", depth=1)
    start = text.split("Start: ", 1)[1].split("]", 1)[0]
    # Alphabetical term order printed the common term's seed ("apple") ahead of the rare exact match ("charlie").
    assert start.index("'charlie'") < start.index("'apple'"), start
