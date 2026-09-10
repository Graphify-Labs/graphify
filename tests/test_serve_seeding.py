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
    """"callers of X" — the agent-noun phrasing — must render all three known
    callers with no junk seed and no junk neighborhood in the shown output.

    Upstream 0.9.35 added "caller"/"callers" to `_CONTEXT_HINTS`' `call` entry
    (adopted in the 0.9.37 sync), so this phrasing now infers the same `call`
    filter "Who calls X?" does, and therefore inherits the same stranding on a
    class seed — where before that hint entry it traversed unfiltered. The
    answer is unchanged because C3 relaxes it back; what is new is the header's
    relaxation note, pinned below so the adopted hint cannot silently regress
    into the near-empty answer it causes without C3.
    """
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
    context = context_segment(text)
    assert "call (heuristic" in context, f"the adopted hint did not fire: {context!r}"
    assert "relaxed" in context, f"header does not report the relaxation: {context!r}"


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

import networkx as nx  # noqa: E402

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
        "'customer' is a substring of the top-ranked seed's label, so it is not starved"
    )
    assert DOC in seeds, (
        "'code' is matched by no picked seed's label — the #1445 guarantee must still fire"
    )


def test_only_the_top_ranked_seed_can_declare_a_term_covered():
    """A substring collision inside a *lower-ranked* seed must not starve a term.

    Coverage means "the query's dominant match already answers this term", which
    is a claim only the top-ranked seed is entitled to make. Let any picked seed
    make it and an unrelated one absorbs a term by coincidence: `ReportService`
    contains the letters of "port", so a corpus symbol literally named `port`
    loses the guaranteed seat that is the only way it can enter this seed list —
    the #1597 concern (a corpus may legitimately name a symbol after a common
    word) reappearing one layer down. Refinement of #37/C2, adopted from the
    Graphify-Labs#2516 review.

    Ranks are supplied directly rather than scored, the same way
    `test_coverage_is_judged_on_the_seed_label_never_its_node_id` does: the point
    is a specific gap-window shape (a dominant match, an unrelated runner-up that
    happens to contain the term, and the term's own winner below the cutoff), and
    naming it beats coaxing a synthetic corpus into producing it.
    """
    G = nx.Graph()
    G.add_node("cfg", label="port", source_file="src/config/server.py")
    G.add_node("report", label="ReportService", source_file="app/Reports/ReportService.php")
    G.add_node("boot", label="ServerBootstrap", source_file="src/server_bootstrap.py")

    qs = _score_query(G, ["port"], collect_per_term_seeds=True)
    # Premise: the term's winner is the exact-match node, by ~7300x — `port` is a
    # real symbol here, not a coincidence, and `ReportService` is the coincidence.
    assert qs.best_seed_by_term["port"] == "cfg"

    scored = [(1000.0, "boot"), (300.0, "report"), (1.0, "cfg")]
    seeds = _pick_seeds(
        scored, G=G, best_seed_by_term=qs.best_seed_by_term, skip_covered_terms=True
    )

    # Premise: both of the unrelated nodes clear the gap window, and the term's
    # own winner does not — so the guarantee is its only way in.
    assert seeds[0] == "boot", f"top-ranked seed is not the dominant match: {seeds}"
    assert "report" in seeds
    assert "cfg" in seeds, (
        "'port' was declared covered by `ReportService`, a lower-ranked seed that "
        f"merely contains the letters — the term's real winner was starved: {seeds}"
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


def test_coverage_is_judged_on_the_seed_label_never_its_node_id():
    """A labelless seed must not declare a term covered through its node id.

    `norm_label == ""` ghost nodes are real (see `_fold_node_aliases` in
    build.py: an alias-only node enters the graph with no label) and they can
    still be seeds, because the source-file tier scores them. The dedup gate
    falls back to the node id for such a node — it has to, since a labelless
    node needs *something* unique to dedup on — but the coverage predicate must
    not, or the ghost's path fragments silently cover unrelated terms and starve
    their winners. `_score_nodes`' substring tier reads `norm_label` only, so a
    seed with no label covers nothing.

    Still load-bearing under the top-ranked-seed-only rule: the ghost is forced
    to be the *only* gap-window seed below, so it IS `seeds[0]` — the one seed
    entitled to declare coverage. Narrowing which seed may cover does not narrow
    what this test traps.
    """
    ghost = "src/customer_utils.py::helper"
    G = nx.Graph()
    G.add_node(ghost, label="", source_file="src/customer_utils.py")
    G.add_node("cm", label="CustomerModel", source_file="app/Models/CustomerModel.php")

    qs = _score_query(G, ["customer"], collect_per_term_seeds=True)
    # Premise 1: the term's real winner is the labelled node.
    assert qs.best_seed_by_term["customer"] == "cm"
    # Premise 2: the labelless ghost still scores — via the source-file tier —
    # so it is a legitimate seed candidate rather than a hypothetical.
    assert dict((nid, s) for s, nid in qs.ranked)[ghost] > 0

    # Force the ghost to be the only gap-window seed, the way an unrelated exact
    # match does on a real corpus (the #1445 shape): `cm` can now enter only
    # through the per-term guarantee.
    seeds = _pick_seeds(
        [(1000.0, ghost), (1.0, "cm")],
        G=G,
        best_seed_by_term=qs.best_seed_by_term,
        skip_covered_terms=True,
    )
    assert ghost in seeds
    assert "cm" in seeds, (
        "'customer' was treated as covered by a seed with no label — coverage read "
        f"the node id, so the term's winner was starved: {seeds}"
    )


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

    Seeded on a *method* node — `BillingController.processPayment()`, whose
    identifier the question names directly — the inferred `call` filter walks
    two real call edges, so no fallback fires. What proves the filter is still
    doing its job rather than having been quietly dropped is what is *missing*:
    the `references`-only caller (#38's extraction gap) and the service class
    itself, whose `method` edge carries no context. Relaxing would pull both in.

    The question says "invoked" rather than "calls": same inferred `call`
    filter, but no fixture label matches it, so the seed set is exactly the one
    identifier and the assertions below read only C3's behavior.
    """
    G = make_charge_fixture()
    text = _query_graph_text(G, "Who invoked BillingController?", mode="bfs", depth=2)
    seeds = start_labels(text)
    shown = shown_nodes(text)
    context = context_segment(text)

    assert seeds == [label_of(CALLERS[0])], f"unexpected seed set: {seeds}"
    assert "heuristic" in context, f"header lost the inferred context: {context!r}"
    assert "relax" not in context, f"expanding filter was needlessly relaxed: {context!r}"
    assert label_of(SERVICE_METHOD) in shown
    assert label_of(CALLERS[1]) in shown
    for filtered_out in (label_of(CALLERS[2]), label_of(SERVICE)):
        assert filtered_out not in shown, (
            f"filter no longer in force — {filtered_out!r} is reachable only "
            f"through a non-`call` edge:\n{text}"
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

    Same single-seed scenario as the test above, with one local tweak: the other
    caller's call edge into the service method is dropped, so the heuristic
    `call` filter reaches exactly one node beyond the seed instead of two.
    Pinning this boundary is what stops the threshold from drifting into a
    tuning constant (`<= len(seeds) + 1` and friends): such an implementation
    relaxes here — throwing away a filter that had in fact found its match, and
    dragging in the class node and the hub — which this test rejects. Asserted
    for both modes, since the threshold is shared.
    """
    for mode in ("bfs", "dfs"):
        G = make_charge_fixture()
        G.remove_edge(CALLERS[1], SERVICE_METHOD)
        text = _query_graph_text(G, "Who invoked BillingController?", mode=mode, depth=2)
        seeds = start_labels(text)
        shown = shown_nodes(text)

        assert set(shown) == set(seeds) | {label_of(SERVICE_METHOD)}, (
            f"{mode}: expected exactly one node beyond the seeds:\n{text}"
        )
        assert "relax" not in context_segment(text), (
            f"{mode}: a filter that discovered a node was relaxed anyway — the "
            f"threshold is no longer zero expansion:\n{text}"
        )
