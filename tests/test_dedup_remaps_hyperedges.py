"""Dedup must rewire hyperedge members onto survivors, not drop them.

`build()` rewires EDGE endpoints to dedup survivors, but `combined["hyperedges"]`
never went through the same remap. The member naming a merged-away id was simply
absent from the rebuilt graph, so the group lost a participant — and could fall
under the 3-member threshold that makes it a hyperedge at all — with nothing on
stderr and, crucially, **no dangling reference**, so a referential-integrity
check saw a perfectly consistent graph (#2805).

`_normalize_hyperedge_members` / `_coerce_hyperedge_member_refs` normalise member
SHAPE (bare id vs object) but never resolve a member against surviving node ids,
which is why they do not cover this.
"""
import pytest

from graphify.build import build
from graphify.dedup import _remap_hyperedge_members, deduplicate_entities


def _node(nid, label):
    return {"id": nid, "label": label, "file_type": "concept",
            "source_file": "notes/a.md"}


def _extraction(members, key="nodes"):
    """Two nodes that normalise to the same label, so dedup merges them; the
    hyperedge names the id that loses. `key` lets a test spell the member list
    with a legacy alias (`members` / `node_ids`) instead of canonical `nodes`."""
    return {
        "nodes": [
            _node("alpha_a", "Alpha Concept"),
            _node("alpha_concept_long_variant_id", "alpha concept"),
            _node("beta_node", "Beta"),
            _node("gamma_node", "Gamma"),
        ],
        "edges": [],
        "hyperedges": [{"id": "the_group", "label": "The Group",
                        key: members, "relation": "participate_in",
                        "confidence": "INFERRED", "confidence_score": 0.75,
                        "source_file": "notes/a.md"}],
    }


def _members(G):
    hes = G.graph.get("hyperedges", [])
    assert len(hes) == 1, hes
    return [m if isinstance(m, str) else m.get("id") for m in hes[0]["nodes"]]


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------

def test_member_follows_the_survivor_instead_of_vanishing():
    G = build([_extraction(
        ["alpha_concept_long_variant_id", "beta_node", "gamma_node"])])
    assert _members(G) == ["alpha_a", "beta_node", "gamma_node"]


def test_the_group_keeps_its_size():
    """The quiet part: a group of 3 became a group of 2, which can drop it below
    the threshold that makes it a hyperedge."""
    G = build([_extraction(
        ["alpha_concept_long_variant_id", "beta_node", "gamma_node"])])
    assert len(_members(G)) == 3


def test_no_member_is_left_pointing_at_a_merged_away_id():
    G = build([_extraction(
        ["alpha_concept_long_variant_id", "beta_node", "gamma_node"])])
    assert all(m in G.nodes for m in _members(G))
    assert "alpha_concept_long_variant_id" not in G.nodes


def test_object_shaped_members_are_remapped_too():
    """Members are tolerated as bare ids or as objects carrying one."""
    G = build([_extraction([
        {"id": "alpha_concept_long_variant_id", "role": "subject"},
        {"id": "beta_node"}, {"id": "gamma_node"},
    ])])
    assert _members(G) == ["alpha_a", "beta_node", "gamma_node"]


def test_an_untouched_hyperedge_is_unchanged():
    G = build([_extraction(["alpha_a", "beta_node", "gamma_node"])])
    assert _members(G) == ["alpha_a", "beta_node", "gamma_node"]


def test_an_alias_keyed_hyperedge_is_remapped_not_deleted():
    """A `members`-keyed group reaches dedup BEFORE build_from_json canonicalizes
    it (#1561 fold runs later). It must be normalized first and then rewired like
    any other hyperedge — not deleted for lacking a `nodes` list."""
    G = build([_extraction(
        ["alpha_concept_long_variant_id", "beta_node", "gamma_node"], key="members")])
    assert _members(G) == ["alpha_a", "beta_node", "gamma_node"]


# ---------------------------------------------------------------------------
# _remap_hyperedge_members directly
# ---------------------------------------------------------------------------

def test_two_members_collapsing_onto_one_survivor_dedupe():
    """They were the same entity, so one entry is right. The old code shrank the
    group AND lost the participant; this shrinks it because the members really
    were duplicates."""
    hes = [{"id": "h", "nodes": ["a_old", "a_new", "b", "c"]}]
    _remap_hyperedge_members(hes, {"a_old": "a", "a_new": "a"})
    assert hes[0]["nodes"] == ["a", "b", "c"]


def test_member_order_is_preserved():
    hes = [{"id": "h", "nodes": ["c", "b_old", "a"]}]
    _remap_hyperedge_members(hes, {"b_old": "b"})
    assert hes[0]["nodes"] == ["c", "b", "a"]


def test_object_members_keep_their_other_fields():
    """Remapping an object-shaped member must preserve its non-id fields."""
    hes = [{
        "id": "h",
        "nodes": [
            {"id": "x_old", "role": "subject"},
            {"id": "y", "role": "object"},
            {"id": "z", "role": "context"},
        ],
    }]
    _remap_hyperedge_members(hes, {"x_old": "x"})
    assert hes[0]["nodes"] == [
        {"id": "x", "role": "subject"},
        {"id": "y", "role": "object"},
        {"id": "z", "role": "context"},
    ]


@pytest.mark.parametrize("he", [
    {"id": "h"},                       # no members key
    {"id": "h", "nodes": None},        # members not a list
    {"id": "h", "nodes": []},          # empty
    {"id": "h", "nodes": [None, 7]},   # junk members
    "not-a-dict",
])
def test_malformed_hyperedges_do_not_raise(he):
    _remap_hyperedge_members([he], {"a": "b"})


@pytest.mark.parametrize("members", [
    [None, 7, False],
    [None, None, None],
    ["a", None, False],
], ids=["mixed-junk", "all-null", "one-real-two-junk"])
def test_unusable_members_do_not_make_up_the_minimum(members):
    """The rewire appended every non-str, non-dict entry untouched and then
    counted list length, so a direct caller kept a three-POSITION group whose
    entries could not name a node at all — contradicting the cleanup this
    function is supposed to guarantee on every exit path."""
    hes = [{"id": "h", "nodes": list(members)}]
    _remap_hyperedge_members(hes, {})
    assert hes == [], f"none of {members!r} is a usable member id"


def test_a_numeric_member_is_canonicalized_while_rewiring():
    """A numeric id is usable and becomes its string form, matching the coercion
    every other member path applies, so it can be remapped and deduped."""
    hes = [{"id": "h", "nodes": [7, "b", "c"]}]
    _remap_hyperedge_members(hes, {"7": "seven"})
    assert hes[0]["nodes"] == ["seven", "b", "c"]


def test_an_empty_remap_changes_nothing():
    """With nothing merged, a canonical group passes through untouched."""
    hes = [{"id": "h", "nodes": ["a", "b", "c"]}]
    _remap_hyperedge_members(hes, {})
    assert hes[0]["nodes"] == ["a", "b", "c"]


def test_an_entry_without_a_nodes_list_is_passed_through_not_deleted():
    """The remap can only rewire a canonical `nodes` list. An entry it cannot
    interpret (alias-keyed here) must survive untouched for build_from_json to
    heal — the kept-list rewrite must never turn "skip" into "delete"."""
    hes = [{"id": "h", "members": ["a", "b", "c"]}]
    _remap_hyperedge_members(hes, {"a": "z"})
    assert hes == [{"id": "h", "members": ["a", "b", "c"]}]


def test_chained_collapse_lands_on_the_final_survivor():
    """A dedup remap built from union-find is fully flattened (path-compressed),
    so a member of a chained component (a_old -> a_mid -> a) rewires directly to
    the final survivor in a single lookup, never to an intermediate."""
    hes = [{"id": "h", "nodes": ["a_old", "a_mid", "b", "c"]}]
    # what components()/UnionFind produces: every non-winner maps to the winner
    _remap_hyperedge_members(hes, {"a_old": "a", "a_mid": "a"})
    assert hes[0]["nodes"] == ["a", "b", "c"]


def test_a_hyperedge_collapsing_to_one_member_is_dropped():
    """A deduplicated singleton is no longer a group relationship."""
    hes = [{"id": "h", "nodes": ["a_old", "a_new"]}]
    _remap_hyperedge_members(hes, {"a_old": "a", "a_new": "a"})
    assert hes == []


# ---------------------------------------------------------------------------
# deduplicate_entities(..., hyperedges=) must clean up on EVERY return path
# ---------------------------------------------------------------------------

_DISTINCT_NODES = [
    _node("alpha_concept_long_variant_id", "alpha concept"),
    _node("beta_node", "Beta"),
    _node("gamma_node", "Gamma"),
]


def test_a_pair_is_dropped_even_when_dedup_merges_nothing():
    """The cardinality cleanup must not depend on whether a merge happened: with
    an empty remap the early return used to skip _remap_hyperedge_members, so a
    direct caller kept a two-member "group" that every other path rejects."""
    hes = [
        {"id": "pair", "nodes": ["alpha_concept_long_variant_id", "beta_node"]},
        {"id": "trio", "nodes": ["alpha_concept_long_variant_id", "beta_node", "gamma_node"]},
    ]
    deduplicate_entities(list(_DISTINCT_NODES), [], communities={}, hyperedges=hes)
    assert [h["id"] for h in hes] == ["trio"]


def test_a_pair_is_dropped_on_the_single_node_short_circuit():
    """Same contract on the other early return (nothing to dedup with one node)."""
    hes = [{"id": "pair", "nodes": ["beta_node", "gamma_node"]}]
    deduplicate_entities([_node("beta_node", "Beta")], [], communities={}, hyperedges=hes)
    assert hes == []


def test_a_pair_is_dropped_after_duplicate_id_collapse():
    """The third early return: two records sharing one id collapse to a single
    `unique_nodes` entry, so the function short-circuits AFTER the initial
    length check and used to skip the hyperedge pass on the way out."""
    hes = [{"id": "pair", "nodes": ["only_node", "beta_node"]}]
    deduplicate_entities(
        [_node("only_node", "Only"), _node("only_node", "Only Again")],
        [], communities={}, hyperedges=hes,
    )
    assert hes == []

def test_direct_dedup_keeps_members_in_the_returned_nodes_id_space():
    """A direct `deduplicate_entities(..., hyperedges=)` caller with numeric node
    ids and nothing to merge got its group mutated into dangling references:
    the remap pass coerces every member to `"7"` so it can be looked up, while
    the returned node records still carry `7`. Whatever comes back has to name
    the nodes that come back with it."""
    from graphify.dedup import deduplicate_entities

    nodes = [{"id": 7, "label": "A"}, {"id": 8, "label": "B"}, {"id": 9, "label": "C"}]
    hyperedges = [{"id": "g", "nodes": [7, 8, 9]}]
    out_nodes, _ = deduplicate_entities(
        nodes, [], communities=None, hyperedges=hyperedges
    )

    returned_ids = {n["id"] for n in out_nodes}
    assert set(hyperedges[0]["nodes"]) <= returned_ids, (
        f"members {hyperedges[0]['nodes']} must name the returned nodes "
        f"{sorted(returned_ids, key=str)}"
    )


def test_direct_dedup_does_not_rebind_a_member_to_a_colliding_node():
    """With two distinct nodes `7` and `"7"`, a member `7` coerces to `"7"` for
    lookup and the restore step then picked the exact string node — silently
    rebinding the member from the node it named to a different one. Worse than a
    dangling member, and a subset assertion cannot see it because both ids are
    present, so this asserts the member still names the node it started on."""
    from graphify.dedup import deduplicate_entities

    nodes = [
        {"id": 7, "label": "int seven"},
        {"id": "7", "label": "str seven"},
        {"id": "b", "label": "B"},
        {"id": "c", "label": "C"},
    ]
    hyperedges = [{"id": "g", "nodes": [7, "b", "c"]}]
    out_nodes, _ = deduplicate_entities(
        nodes, [], communities=None, hyperedges=hyperedges
    )

    by_id = {n["id"]: n["label"] for n in out_nodes}
    member = hyperedges[0]["nodes"][0]
    assert member == 7 and by_id.get(member) == "int seven", (
        f"member {member!r} must still name the node it named (int seven), "
        f"not the colliding {by_id.get(member)!r}"
    )



def test_a_dropped_group_does_not_shift_the_raw_form_capture():
    """Dropping an undersized group must not misalign the raw-form capture.

    The capture that protects a member from being rebound onto a colliding node
    is taken per hyperedge BEFORE the remap; the remap then drops undersized
    groups and compacts the list in place. Read back by position, every
    surviving group after the first drop was handed the raw forms of a
    DIFFERENT group — so with distinct nodes `7` and `"7"` present, `trio`'s
    member `"7"` was resolved through `pair`'s capture and silently rebound to
    the int node it never named. That is #3297's failure mode: not a dangling
    member, a wrong one.
    """
    hes = [
        {"id": "pair", "nodes": [7, "delta_node"]},
        {"id": "trio", "nodes": ["7", "beta_node", "gamma_node"]},
    ]
    deduplicate_entities(
        [
            _node(7, "Int Seven"),
            _node("7", "Str Seven"),
            _node("beta_node", "Beta"),
            _node("gamma_node", "Gamma"),
            _node("delta_node", "Delta"),
        ],
        [], communities={}, hyperedges=hes,
    )
    assert [h["id"] for h in hes] == ["trio"]
    assert hes[0]["nodes"] == ["7", "beta_node", "gamma_node"], (
        "the member must keep naming the string node it was written against"
    )
