"""Seeding hygiene for natural-language impact questions (fork issue #37).

C1 — relational-intent demotion: a word that names the *relation* being asked
about ("calls", "callers", "uses") no longer buys an unconditional seed through
the per-term guarantee (#1445). It still scores, still competes for seeds on
merit, and is never stopworded.

Assertions read external behavior only — the `Start:` header, the rendered NODE
lines, and the seed lists the existing seeding tests already assert on — never
the vocabulary set itself, so tuning the vocabulary can't break these tests.
"""
from graphify.serve import _pick_seeds, _query_graph_text, _query_terms, _score_query

from tests.seeding_fixtures import (
    CALLERS_DECOY,
    CALLS_SYMBOL,
    DECOY,
    SERVICE,
    USES_DECOY,
    caller_labels,
    label_of,
    make_charge_fixture,
    shown_nodes,
    start_labels,
)


def test_who_calls_phrasing_does_not_seed_verb_prefix_decoy():
    """"Who calls ChargeCustomerService?" must not seed `callStoreWithAmount()`.

    The decoy loses everywhere on merit (it scores ~9x below the gap-window
    cutoff); it only ever entered the seed list because "calls" held an
    unconditional per-term seat. Seed-level only: the `call` context filter this
    phrasing infers strands the class seed, which is #42's problem, not this one.
    """
    G = make_charge_fixture()
    seeds = start_labels(
        _query_graph_text(G, "Who calls ChargeCustomerService?", mode="bfs", depth=2)
    )
    assert label_of(SERVICE) in seeds
    assert label_of(DECOY) not in seeds, f"verb-prefix decoy still seeded: {seeds}"


def test_callers_of_phrasing_renders_all_callers_and_drops_junk_seed():
    """"callers of X" — the agent-noun phrasing, which triggers no context
    filter — must render all three known callers with no junk seed and no junk
    neighborhood in the shown output."""
    G = make_charge_fixture()
    text = _query_graph_text(G, "callers of ChargeCustomerService", mode="bfs", depth=2)
    seeds = start_labels(text)
    shown = shown_nodes(text)

    assert label_of(SERVICE) in seeds
    assert label_of(CALLERS_DECOY) not in seeds, f"junk test-method seeded: {seeds}"
    for caller in caller_labels():
        assert caller in shown, f"caller {caller!r} missing from shown output:\n{text}"
    # The junk seed's whole neighborhood is what used to eat the budget.
    assert label_of(DECOY) not in shown
    assert label_of(CALLERS_DECOY) not in shown


def test_all_relational_query_keeps_its_per_term_guarantee():
    """A query made only of relational words keeps the guarantee (mirroring the
    all-stopword fallback in `_query_terms`): demoting every term would leave
    nothing to guarantee, so the winner map is kept unfiltered.

    "uses"' winner scores ~25x below the gap-window cutoff here, so it is seeded
    only if the guarantee survives — which is what makes this test load-bearing
    rather than decorative.
    """
    G = make_charge_fixture()
    seeds = start_labels(_query_graph_text(G, "calls uses", mode="bfs", depth=2))
    assert label_of(DECOY) in seeds
    assert label_of(USES_DECOY) in seeds, (
        f"all-relational query lost its per-term guarantee: {seeds}"
    )


def test_relational_word_with_exact_match_still_seeds_on_merit():
    """Demotion is not stopwording: a corpus symbol literally labelled `calls`
    keeps its exact-match dominance and is seeded through the ordinary gap
    window, while the unrelated verb-prefix decoy stays out."""
    G = make_charge_fixture(calls_symbol=True)
    seeds = start_labels(
        _query_graph_text(G, "Who calls ChargeCustomerService?", mode="bfs", depth=2)
    )
    assert label_of(CALLS_SYMBOL) in seeds, (
        f"exact-match `calls` symbol lost its seed: {seeds}"
    )
    assert label_of(SERVICE) in seeds
    assert label_of(DECOY) not in seeds


def test_scorer_and_picker_are_unchanged_for_direct_callers():
    """C1 is wired from the query pipeline only. Callers that drive the scorer
    and the seed picker directly — `path`, `explain`, the legacy-equality
    property tests, the benchmark's two arms — must still see the relational
    term score and still receive its guaranteed seed."""
    G = make_charge_fixture()
    terms = _query_terms("Who calls ChargeCustomerService?")
    qs = _score_query(G, terms, collect_per_term_seeds=True)

    assert qs.best_seed_by_term.get("calls") == DECOY, (
        "scorer stopped recording the relational term's per-term winner"
    )
    seeds = _pick_seeds(qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term)
    assert DECOY in seeds, "demotion leaked into _pick_seeds' semantics"


# --------------------------------------------------------------------------- #
# C3 — heuristic-context-filter starvation fallback (#42)                      #
#                                                                              #
# A class node has no call-context edges of its own: calls attach to its       #
# methods, and the class->member edge carries `context=None`. So the `call`    #
# filter that "Who calls X?" infers strands a perfectly-seeded class seed at   #
# exactly one node. When an *inferred* filter discovers nothing beyond the     #
# seeds, the query retraverses unfiltered and says so in the header; an        #
# *explicit* filter is always honored. Assertions read the header and the      #
# rendered NODE lines only.                                                    #
# --------------------------------------------------------------------------- #

from tests.seeding_fixtures import CALLERS, SERVICE_METHOD  # noqa: E402


def context_segment(text: str) -> str:
    """The `Context: ...` segment of a `_query_graph_text` header, or "" if the
    query ran unfiltered. Read as a whole so the source and any relaxation note
    are asserted where the caller actually sees them."""
    for part in text.split("\n", 1)[0].split(" | "):
        if part.startswith("Context:"):
            return part
    return ""


def test_who_calls_phrasing_falls_back_when_heuristic_filter_strands_the_seed():
    """The measured phrasing A end-to-end: "Who calls ChargeCustomerService?"

    The inferred `call` filter leaves the class seed with nowhere to go, so the
    traversal relaxes and every known caller renders — including the one
    reachable only through its `references` edge (#38's extraction gap). The
    header keeps the failure mode visible: the heuristic context is still
    reported, annotated as relaxed, so a fallback answer never reads as a
    filtered one.
    """
    G = make_charge_fixture()
    text = _query_graph_text(G, "Who calls ChargeCustomerService?", mode="bfs", depth=2)
    seeds = start_labels(text)
    shown = shown_nodes(text)
    context = context_segment(text)

    assert label_of(SERVICE) in seeds
    assert label_of(DECOY) not in seeds, f"verb-prefix decoy seeded: {seeds}"
    for caller in caller_labels():
        assert caller in shown, f"caller {caller!r} missing from shown output:\n{text}"
    assert label_of(DECOY) not in shown, f"decoy neighborhood leaked in:\n{text}"
    assert "heuristic" in context, f"header lost the inferred context: {context!r}"
    assert "relaxed" in context, f"header does not report the relaxation: {context!r}"


def test_expanding_heuristic_filter_is_left_in_force():
    """A heuristic filter that does reach past the seeds is not second-guessed.

    Seeded on the *method* node, the same inferred `call` filter finds the two
    real call edges, so no fallback fires: the header carries no relaxation note
    and the `references`-only caller stays filtered out — which is what proves
    the filter is still doing its job rather than having been dropped.
    """
    G = make_charge_fixture()
    text = _query_graph_text(G, "Who calls ChargeCustomerService.charge?", mode="bfs", depth=2)
    shown = shown_nodes(text)
    context = context_segment(text)

    assert "heuristic" in context, f"header lost the inferred context: {context!r}"
    assert "relax" not in context, f"expanding filter was needlessly relaxed: {context!r}"
    assert label_of(CALLERS[0]) in shown
    assert label_of(CALLERS[1]) in shown
    assert label_of(CALLERS[2]) not in shown, (
        f"filter no longer in force — the import-edge caller leaked in:\n{text}"
    )


def test_explicit_context_filter_never_falls_back_even_when_stranded():
    """The identical stranding, with the filter passed explicitly: honored.

    An explicit instruction is never overridden, so the answer stays at the seed
    alone and the header reports an unqualified explicit filter.
    """
    G = make_charge_fixture()
    text = _query_graph_text(
        G, "Who calls ChargeCustomerService?", mode="bfs", depth=2,
        context_filters=["call"],
    )
    shown = shown_nodes(text)
    context = context_segment(text)

    assert shown == [label_of(SERVICE)], f"explicit filter was relaxed:\n{text}"
    assert "explicit" in context, f"header lost the explicit source: {context!r}"
    assert "relax" not in context, f"explicit filter was annotated as relaxed: {context!r}"


def test_starvation_fallback_is_identical_in_both_traversal_modes():
    """Mode choice must not change filter behavior: DFS relaxes exactly where
    BFS does, and reaches the same nodes."""
    G = make_charge_fixture()
    question = "Who calls ChargeCustomerService?"
    bfs = _query_graph_text(G, question, mode="bfs", depth=2)
    dfs = _query_graph_text(G, question, mode="dfs", depth=2)

    for mode, text in (("BFS", bfs), ("DFS", dfs)):
        context = context_segment(text)
        assert "relaxed" in context, f"{mode} did not relax: {context!r}"
        for caller in caller_labels():
            assert caller in shown_nodes(text), (
                f"{mode} missing caller {caller!r}:\n{text}"
            )
    assert set(shown_nodes(bfs)) == set(shown_nodes(dfs)), (
        "traversal modes disagree under the fallback:\n"
        f"BFS={shown_nodes(bfs)}\nDFS={shown_nodes(dfs)}"
    )


def test_single_node_expansion_is_not_starvation():
    """The threshold is *zero* expansion, not "few nodes" — one discovered node
    is enough to leave the filter alone.

    Local tweak: drop one of the service method's two call edges, so the
    heuristic `call` filter reaches exactly one node beyond the seeds. Pinning
    this boundary is what stops the threshold from drifting into a tuning
    constant (`<= len(seeds) + 1` and friends): such an implementation relaxes
    here, which this test rejects. Asserted for both modes, since the threshold
    is shared.
    """
    for mode in ("bfs", "dfs"):
        G = make_charge_fixture()
        G.remove_edge(CALLERS[1], SERVICE_METHOD)
        text = _query_graph_text(
            G, "Who calls ChargeCustomerService.charge?", mode=mode, depth=2
        )
        seeds = start_labels(text)
        shown = shown_nodes(text)

        assert set(shown) == set(seeds) | {label_of(CALLERS[0])}, (
            f"{mode}: expected exactly one node beyond the seeds:\n{text}"
        )
        assert "relax" not in context_segment(text), (
            f"{mode}: a filter that discovered a node was relaxed anyway — the "
            f"threshold is no longer zero expansion:\n{text}"
        )
