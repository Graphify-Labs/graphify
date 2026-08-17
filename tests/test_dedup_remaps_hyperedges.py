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
from graphify.dedup import _remap_hyperedge_members


def _node(nid, label):
    return {"id": nid, "label": label, "file_type": "concept",
            "source_file": "notes/a.md"}


def _extraction(members):
    """Two nodes that normalise to the same label, so dedup merges them; the
    hyperedge names the id that loses."""
    return {
        "nodes": [
            _node("alpha_a", "Alpha Concept"),
            _node("alpha_concept_long_variant_id", "alpha concept"),
            _node("beta_node", "Beta"),
            _node("gamma_node", "Gamma"),
        ],
        "edges": [],
        "hyperedges": [{"id": "the_group", "label": "The Group",
                        "nodes": members, "relation": "participate_in",
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


# ---------------------------------------------------------------------------
# _remap_hyperedge_members directly
# ---------------------------------------------------------------------------

def test_two_members_collapsing_onto_one_survivor_dedupe():
    """They were the same entity, so one entry is right. The old code shrank the
    group AND lost the participant; this shrinks it because the members really
    were duplicates."""
    hes = [{"id": "h", "nodes": ["a_old", "a_new", "b"]}]
    _remap_hyperedge_members(hes, {"a_old": "a", "a_new": "a"})
    assert hes[0]["nodes"] == ["a", "b"]


def test_member_order_is_preserved():
    hes = [{"id": "h", "nodes": ["c", "b_old", "a"]}]
    _remap_hyperedge_members(hes, {"b_old": "b"})
    assert hes[0]["nodes"] == ["c", "b", "a"]


def test_object_members_keep_their_other_fields():
    hes = [{"id": "h", "nodes": [{"id": "x_old", "role": "subject"}]}]
    _remap_hyperedge_members(hes, {"x_old": "x"})
    assert hes[0]["nodes"] == [{"id": "x", "role": "subject"}]


@pytest.mark.parametrize("he", [
    {"id": "h"},                       # no members key
    {"id": "h", "nodes": None},        # members not a list
    {"id": "h", "nodes": []},          # empty
    {"id": "h", "nodes": [None, 7]},   # junk members
    "not-a-dict",
])
def test_malformed_hyperedges_do_not_raise(he):
    _remap_hyperedge_members([he], {"a": "b"})


def test_an_empty_remap_changes_nothing():
    hes = [{"id": "h", "nodes": ["a", "b", "c"]}]
    _remap_hyperedge_members(hes, {})
    assert hes[0]["nodes"] == ["a", "b", "c"]


def test_chained_collapse_lands_on_the_final_survivor():
    """A dedup remap built from union-find is fully flattened (path-compressed),
    so a member of a chained component (a_old -> a_mid -> a) rewires directly to
    the final survivor in a single lookup, never to an intermediate."""
    hes = [{"id": "h", "nodes": ["a_old", "a_mid", "b"]}]
    # what components()/UnionFind produces: every non-winner maps to the winner
    _remap_hyperedge_members(hes, {"a_old": "a", "a_mid": "a"})
    assert hes[0]["nodes"] == ["a", "b"]


def test_a_hyperedge_collapsing_to_one_member_is_kept():
    """Sub-two-member hyperedges are kept by design (build_from_json only drops
    the zero-valid-member case). Pin it so a future refactor doesn't silently
    start dropping a 1-member group after a collapse."""
    hes = [{"id": "h", "nodes": ["a_old", "a_new"]}]
    _remap_hyperedge_members(hes, {"a_old": "a", "a_new": "a"})
    assert hes[0]["nodes"] == ["a"]  # collapsed to one, still present
