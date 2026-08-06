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
