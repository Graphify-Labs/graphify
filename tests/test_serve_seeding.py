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


# ===== C2 — covered-term guarantee skip (#41) ================================
#
# A query term that an already-picked seed's normalized label plainly matches —
# the scorer's own weakest tier, so "this seed would have matched the term in
# scoring" — is not *starved*, and starvation is the only thing the #1445
# guarantee exists to prevent. It therefore claims no additional seed. The
# refined invariant: every term with any match is matched by at least one seed
# (previously: every term's own singleton winner gets a slot).
#
# Assertions here read external behavior only: the `Start:` header, the rendered
# NODE lines, the header's node count, and the seed lists the prior seeding
# tests already assert on.

from graphify.serve import _bfs, _demote_relational_intent_terms  # noqa: E402

from tests.seeding_fixtures import DOC, HUB  # noqa: E402

_GENERIC_NOUN_QUESTION = "what code uses ChargeCustomerService to charge a customer"
# The hub's 12 members sit one `references` hop past the service, so they enter a
# depth-2 traversal only when the hub itself is seeded. Depth 2 is also the depth
# the spec's measurements were taken at.
_GENERIC_NOUN_DEPTH = 2
# Terms that exercise both sides of the refined invariant on this fixture:
# "customer" is covered by the `ChargeCustomerService` seed's label, "code" is
# covered by no seed at all (its winner is the `coder.md` prefix decoy — the
# documented residual, and here the load-bearing proof that recovery survives).
_COVERED_AND_STARVED_QUESTION = "ChargeCustomerService customer code"


def _nodes_found(text: str) -> int:
    """The `N nodes found` count from a `_query_graph_text` header."""
    for part in text.split("\n", 1)[0].split(" | "):
        if part.endswith(" nodes found"):
            return int(part.split(" ", 1)[0])
    raise AssertionError(f"no node count in header: {text.splitlines()[:1]}")


def test_generic_noun_phrasing_seeds_no_hub_and_stays_bounded():
    """"what code uses X to charge a customer" must not seed the `Customer` hub.

    "customer" and "charge" are both substrings of the `ChargeCustomerService`
    seed's label, so neither is starved and neither buys a seat. Measured on this
    fixture: 22 nodes with the hub seeded (12 of them the hub's member fan-out)
    against 10 without it — so the bound is asserted against the pre-C2 seed
    list's own traversal rather than a hard-coded number. This phrasing triggers
    no context filter, so the comparison traversal is unfiltered like the
    pipeline's.
    """
    G = make_charge_fixture()
    text = _query_graph_text(
        G, _GENERIC_NOUN_QUESTION, mode="bfs", depth=_GENERIC_NOUN_DEPTH
    )
    seeds = start_labels(text)
    shown = shown_nodes(text)

    assert label_of(SERVICE) in seeds
    assert label_of(HUB) not in seeds, f"generic-noun hub still seeded: {seeds}"
    for caller in caller_labels():
        assert caller in shown, f"caller {caller!r} missing from shown output:\n{text}"

    hub_fanout = [lbl for lbl in shown if lbl.startswith(label_of(HUB) + ".")]
    assert not hub_fanout, f"hub member fan-out flooded the answer: {hub_fanout}"

    qs = _score_query(G, _query_terms(_GENERIC_NOUN_QUESTION), collect_per_term_seeds=True)
    pre_c2_seeds = _pick_seeds(
        qs.ranked, G=G, best_seed_by_term=_demote_relational_intent_terms(qs.best_seed_by_term)
    )
    pre_c2_nodes, _edges = _bfs(G, pre_c2_seeds, _GENERIC_NOUN_DEPTH)
    assert _nodes_found(text) < len(pre_c2_nodes), (
        f"traversal not bounded: {_nodes_found(text)} nodes from {seeds} is no smaller "
        f"than the {len(pre_c2_nodes)} the pre-C2 seed list {pre_c2_seeds} reached"
    )


def test_covered_term_skips_guarantee_while_starved_term_is_still_recovered():
    """The picker seam, where the starvation-recovery and dedup prior art sits.

    Both halves of the refined invariant in one test: the covered term loses its
    guaranteed seat, and the genuinely starved term keeps its — C2 provably
    cannot reintroduce starvation.
    """
    G = make_charge_fixture()
    qs = _score_query(
        G, _query_terms(_COVERED_AND_STARVED_QUESTION), collect_per_term_seeds=True
    )
    seeds = _pick_seeds(
        qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term, skip_covered_terms=True
    )

    assert SERVICE in seeds
    assert HUB not in seeds, (
        "'customer' is a substring of the picked seed's label, so it is not starved"
    )
    assert DOC in seeds, (
        "'code' is matched by no picked seed's label — the #1445 guarantee must still fire"
    )


def test_covered_term_skip_is_off_unless_the_caller_opts_in():
    """Default-off: identical results for every caller that does not opt in.

    `path`, `explain`, the legacy-equality property tests and the benchmark's two
    arms all reach `_pick_seeds` without the flag; passing it explicitly False
    must be the same call.
    """
    G = make_charge_fixture()
    qs = _score_query(
        G, _query_terms(_COVERED_AND_STARVED_QUESTION), collect_per_term_seeds=True
    )
    legacy = _pick_seeds(qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term)

    assert legacy == _pick_seeds(
        qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term, skip_covered_terms=False
    )
    assert HUB in legacy, f"the covered-term skip leaked into the default picker: {legacy}"
    assert DOC in legacy
