"""Tests for hyperedge support in graphify."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

import networkx as nx
import pytest

from graphify.build import (
    MIN_HYPEREDGE_MEMBERS,
    build_from_json,
    canonical_hyperedge,
    gate_hyperedges,
    gate_hyperedges_against_graph,
    member_in_id_space,
    node_id_set,
)
from graphify.export import attach_hyperedges, to_json
from graphify.report import generate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_EXTRACTION = {
    "nodes": [
        {"id": "BasicAuth", "label": "BasicAuth", "file_type": "code", "source_file": "auth.py"},
        {"id": "DigestAuth", "label": "DigestAuth", "file_type": "code", "source_file": "auth.py"},
        {"id": "Request", "label": "Request", "file_type": "code", "source_file": "http.py"},
        {"id": "Response", "label": "Response", "file_type": "code", "source_file": "http.py"},
        {"id": "BaseClient", "label": "BaseClient", "file_type": "code", "source_file": "client.py"},
    ],
    "edges": [
        {"source": "BasicAuth", "target": "Request", "relation": "uses", "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "auth.py"},
    ],
    "hyperedges": [
        {
            "id": "auth_flow",
            "label": "Auth Flow",
            "nodes": ["BasicAuth", "DigestAuth", "Request", "Response", "BaseClient"],
            "relation": "participate_in",
            "confidence": "INFERRED",
            "confidence_score": 0.75,
            "source_file": "auth.py",
        }
    ],
    "input_tokens": 10,
    "output_tokens": 5,
}

SAMPLE_DETECTION = {
    "total_files": 3,
    "total_words": 500,
    "files": {"code": ["auth.py", "http.py", "client.py"]},
    "skipped_sensitive": [],
    "warning": None,
}


# ---------------------------------------------------------------------------
# 1. Hyperedges survive build_from_json round-trip
# ---------------------------------------------------------------------------

def test_build_from_json_stores_hyperedges():
    G = build_from_json(SAMPLE_EXTRACTION)
    assert "hyperedges" in G.graph
    assert len(G.graph["hyperedges"]) == 1
    assert G.graph["hyperedges"][0]["id"] == "auth_flow"


def test_build_from_json_relativizes_hyperedge_source_file(tmp_path):
    """build_from_json(root=...) must relativize hyperedge source_file like it
    already does for nodes and edges. to_json writes G.graph['hyperedges']
    verbatim and has no root parameter, so an absolute path emitted by a semantic
    subagent would otherwise leak into graph.json (#1418)."""
    base = tmp_path.resolve()
    abs_doc = base / "docs" / "CLAUDE.md"
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "document", "source_file": str(abs_doc)},
            {"id": "b", "label": "B", "file_type": "document", "source_file": str(abs_doc)},
            {"id": "c", "label": "C", "file_type": "document", "source_file": str(abs_doc)},
        ],
        "edges": [],
        "hyperedges": [
            {
                "id": "arch",
                "label": "Architecture",
                "nodes": ["a", "b", "c"],
                "relation": "participate_in",
                "confidence": "INFERRED",
                "confidence_score": 0.75,
                "source_file": str(abs_doc),
            }
        ],
    }
    G = build_from_json(extraction, root=str(base))
    assert G.graph["hyperedges"][0]["source_file"] == "docs/CLAUDE.md"
    # Anchor: the node path is relativized the same way (the contract this mirrors).
    assert G.nodes["a"]["source_file"] == "docs/CLAUDE.md"


def test_build_from_json_no_hyperedges():
    extraction = {**SAMPLE_EXTRACTION, "hyperedges": []}
    G = build_from_json(extraction)
    assert G.graph.get("hyperedges", []) == []


def test_build_from_json_missing_hyperedges_key():
    extraction = {k: v for k, v in SAMPLE_EXTRACTION.items() if k != "hyperedges"}
    G = build_from_json(extraction)
    assert G.graph.get("hyperedges", []) == []


# ---------------------------------------------------------------------------
# 2. attach_hyperedges deduplicates by id
# ---------------------------------------------------------------------------

def test_attach_hyperedges_adds_new():
    """A fresh hyperedge is stored in the graph's metadata."""
    G = nx.Graph()
    G.add_nodes_from(["A", "B", "C"])
    attach_hyperedges(G, [{"id": "auth_flow", "label": "Auth Flow", "nodes": ["A", "B", "C"]}])
    assert len(G.graph["hyperedges"]) == 1


def test_attach_hyperedges_deduplicates():
    """Attaching the same id twice must not duplicate the entry."""
    G = nx.Graph()
    G.add_nodes_from(["A", "B", "C"])
    h = {"id": "auth_flow", "label": "Auth Flow", "nodes": ["A", "B", "C"]}
    attach_hyperedges(G, [h])
    attach_hyperedges(G, [h])  # second call with same id should not duplicate
    assert len(G.graph["hyperedges"]) == 1


def test_attach_hyperedges_multiple_different_ids():
    """Distinct ids all land in the metadata list."""
    G = nx.Graph()
    G.add_nodes_from(["A", "B", "C", "D", "E", "F"])
    attach_hyperedges(G, [
        {"id": "flow_a", "label": "Flow A", "nodes": ["A", "B", "C"]},
        {"id": "flow_b", "label": "Flow B", "nodes": ["D", "E", "F"]},
    ])
    assert len(G.graph["hyperedges"]) == 2


def test_attach_hyperedges_skips_entry_without_id():
    """An id-less incoming entry is not attached."""
    G = nx.Graph()
    G.add_nodes_from(["A", "B", "C"])
    attach_hyperedges(G, [{"label": "No ID", "nodes": ["A", "B", "C"]}])
    assert G.graph.get("hyperedges", []) == []


def test_attach_hyperedges_tolerates_id_less_persisted():
    """#2775: an id-less entry already persisted must not raise KeyError."""
    # Regression for #2775: the semantic extractor emits hyperedges with no `id`
    # and build.py persists them verbatim, so a prior graph.json can carry id-less
    # hyperedges. On the next (incremental) run, attach_hyperedges read that
    # persisted set with a hard `h["id"]` and died with `KeyError: 'id'`, writing
    # nothing. Reading the persisted set must tolerate missing ids.
    G = nx.DiGraph()
    G.add_nodes_from(["a", "b", "c", "A", "B", "C"])
    G.graph["hyperedges"] = [
        {"nodes": ["a", "b", "c"], "type": "project", "attributes": {}}
    ]
    attach_hyperedges(G, [{"id": "flow_a", "label": "Flow A", "nodes": ["A", "B", "C"]}])
    # No crash; the id-less persisted entry is retained and the new id-bearing
    # incoming hyperedge is appended.
    assert len(G.graph["hyperedges"]) == 2


def test_attach_hyperedges_tolerates_many_id_less_persisted():
    """The real corpus had 183/234 persisted hyperedges id-less: all of them must
    load without crashing and be retained (#2775)."""
    G = nx.DiGraph()
    G.add_nodes_from(["a", "b", "c", "A", "B", "C"])
    G.graph["hyperedges"] = [
        {"nodes": ["a", "b", "c"], "type": "project", "attributes": {}} for _ in range(5)
    ]
    attach_hyperedges(G, [{"id": "flow_a", "nodes": ["A", "B", "C"]}])
    assert len(G.graph["hyperedges"]) == 6  # 5 id-less retained + 1 appended


def test_attach_hyperedges_treats_empty_id_as_id_less():
    """An empty-string id is falsy, so it is treated the same as a missing id:
    it seeds nothing into the dedup set and does not crash."""
    G = nx.DiGraph()
    G.add_nodes_from(["a", "b", "c", "A", "B", "C"])
    G.graph["hyperedges"] = [{"id": "", "nodes": ["a", "b", "c"], "type": "project"}]
    attach_hyperedges(G, [{"id": "flow_a", "nodes": ["A", "B", "C"]}])
    assert len(G.graph["hyperedges"]) == 2


def test_attach_hyperedges_drops_legacy_two_member_entries():
    """A two-member group persisted by an older version is pruned on attach."""
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c"])
    G.graph["hyperedges"] = [{"id": "legacy_pair", "nodes": ["a", "b"]}]

    attach_hyperedges(G, [{"id": "valid_group", "nodes": ["a", "b", "c"]}])

    assert [he["id"] for he in G.graph["hyperedges"]] == ["valid_group"]


def test_attach_hyperedges_canonicalizes_members_before_validating():
    """merge-graphs feeds persisted hyperedge metadata straight through this
    boundary with no build_from_json in between (#1561 alias fold never ran), so
    the member gate must canonicalize first: an alias-keyed group and one with
    object-shaped members are both valid three-member hyperedges, not junk to
    drop. The caller's dicts are left untouched."""
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c"])
    alias_shaped = {"id": "alias_group", "members": ["a", "b", "c"]}
    object_shaped = {"id": "object_group", "nodes": [{"id": "a"}, "b", "c"]}

    attach_hyperedges(G, [alias_shaped, object_shaped])

    attached = {he["id"]: he for he in G.graph["hyperedges"]}
    assert set(attached) == {"alias_group", "object_group"}
    assert attached["alias_group"]["nodes"] == ["a", "b", "c"]
    assert "members" not in attached["alias_group"]
    assert attached["object_group"]["nodes"] == ["a", "b", "c"]
    assert alias_shaped == {"id": "alias_group", "members": ["a", "b", "c"]}


# ---------------------------------------------------------------------------
# 2b. canonical_hyperedge — the one gate every persistence boundary shares
# ---------------------------------------------------------------------------

def test_canonical_hyperedge_folds_alias_keys():
    """A `members`/`node_ids` group is valid (#1561); the gate must read it."""
    he = {"id": "h", "members": ["a", "b", "c"]}
    out = canonical_hyperedge(he)
    assert out["nodes"] == ["a", "b", "c"]
    assert "members" not in out
    assert he == {"id": "h", "members": ["a", "b", "c"]}, "caller's dict must be untouched"


def test_canonical_hyperedge_counts_distinct_members():
    """Positions are not members: a repeated id must not inflate the count."""
    assert canonical_hyperedge({"id": "h", "nodes": ["a", "a", "b", "c"]})["nodes"] == ["a", "b", "c"]
    assert canonical_hyperedge({"id": "h", "nodes": ["a", "a", "b"]}) is None


def test_canonical_hyperedge_coerces_object_members():
    """Members are tolerated as bare ids or as objects carrying one."""
    out = canonical_hyperedge({"id": "h", "nodes": [{"id": "a"}, "b", {"id": "c"}]})
    assert out["nodes"] == ["a", "b", "c"]


@pytest.mark.parametrize("container", [
    {"a", "b", "c"},
    nx.Graph([("a", "b"), ("b", "c")]),
])
def test_gate_filters_members_to_the_node_set(container):
    """A member with no backing node is dropped; the group dies below the minimum.

    Membership lives in the gate rather than in canonical_hyperedge, because it
    needs the id-space bridge — compare normalized, return the container's own
    ids. Both a plain set and an nx.Graph are valid containers."""
    kept, _ = gate_hyperedges_against_graph(
        [{"id": "h", "nodes": ["a", "b", "c", "ghost"]}], container
    )
    assert kept[0]["nodes"] == ["a", "b", "c"]
    assert gate_hyperedges_against_graph(
        [{"id": "h", "nodes": ["a", "b", "ghost"]}], container
    ) == ([], 1)


def test_canonical_hyperedge_alone_does_not_check_membership():
    """The cache and the pre-stamp gate have no node set, so they call
    canonical_hyperedge directly and get shape and cardinality only."""
    out = canonical_hyperedge({"id": "h", "nodes": ["ghost1", "ghost2", "ghost3"]})
    assert out["nodes"] == ["ghost1", "ghost2", "ghost3"]


@pytest.mark.parametrize("empty", [set(), nx.Graph()])
def test_gate_treats_an_empty_node_set_as_empty_not_absent(empty):
    """`set()` and `nx.Graph()` are both FALSY, so a truthiness guard anywhere on
    this path would skip membership entirely and keep a group whose every member
    dangles. An empty container must drop everything."""
    assert gate_hyperedges_against_graph(
        [{"id": "h", "nodes": ["a", "b", "c"]}], empty
    ) == ([], 1)


@pytest.mark.parametrize("nodes_value", [
    None,                            # explicit null
    "a,b,c",                         # a string: iterating it yields characters
    {"a": 1, "b": 2, "c": 3},        # a dict: iterating it yields keys
])
def test_canonical_hyperedge_rejects_a_non_list_nodes_value(nodes_value):
    """Normalization only assigns `nodes` when `nodes` or an alias is already a
    list, so a malformed value survives to the membership step. Without an
    explicit list guard a string or dict is *fabricated* into a well-formed
    3-member group (its characters / keys pass membership), and an absent or
    null value raises. Every shape must be rejected outright."""
    assert canonical_hyperedge({"id": "h", "nodes": nodes_value}) is None
    assert gate_hyperedges_against_graph(
        [{"id": "h", "nodes": nodes_value}], {"a", "b", "c"}
    ) == ([], 1)


def test_canonical_hyperedge_rejects_a_member_less_entry():
    """No `nodes` key and no alias at all — same guard as the shapes above."""
    assert canonical_hyperedge({"id": "h", "label": "x"}) is None
    assert gate_hyperedges_against_graph(
        [{"id": "h", "label": "x"}], {"a", "b", "c"}
    ) == ([], 1)


@pytest.mark.parametrize("he", ["not-a-dict", None, 7, ["a", "b", "c"]])
def test_canonical_hyperedge_rejects_a_non_dict(he):
    """Anything that is not a dict is not a hyperedge."""
    assert canonical_hyperedge(he) is None


@pytest.mark.parametrize("junk", [None, "", True, False])
def test_canonical_hyperedge_rejects_an_unusable_member_id_in_object_form(junk):
    """The bare and object member branches must apply the SAME rule. They drifted
    twice: the object branch rejected `{"id": None}` while a bare `None` was kept,
    and then the reverse once booleans were added to the bare branch only."""
    assert canonical_hyperedge({"id": "h", "nodes": ["a", "b", {"id": junk}]}) is None


@pytest.mark.parametrize("junk", [None, "", True, False])
def test_canonical_hyperedge_does_not_count_an_unusable_member_id(junk):
    """`None` and `""` can never name a node, so they must not pad the count.

    They are hashable, so they used to survive member coercion — unlike the
    equivalent object member `{"id": None}`, which was already dropped. That
    asymmetry let a two-real-member group pass the cache gate (which has no node
    set to filter against) and then be dropped on replay by build_from_json,
    leaving a cache hit that yields no semantic data and never re-dispatches."""
    assert canonical_hyperedge({"id": "h", "nodes": ["a", "b", junk]}) is None
    kept = canonical_hyperedge({"id": "h", "nodes": ["a", "b", junk, "c"]})
    assert kept["nodes"] == ["a", "b", "c"]


@pytest.mark.parametrize("number", [7, 0])
def test_canonical_hyperedge_canonicalizes_a_numeric_member(number):
    """A numeric id is legitimate and is canonicalized to its string form, the
    same coercion `_coerce_non_string_ids` applies on the build path. `0` in
    particular must survive the boolean rejection sitting next to it."""
    assert canonical_hyperedge({"id": "h", "nodes": ["a", "b", number]})["nodes"] == [
        "a", "b", str(number),
    ]


def test_canonical_hyperedge_counts_a_numeric_and_its_string_form_once():
    """`7` and `"7"` are the same node id — `_coerce_non_string_ids` str-coerces
    numeric members on the build path. Deduplicating on the raw Python value
    counted them separately, so `[7, "7", "b"]` passed the cache gate as three
    members and then collapsed to two on replay and was dropped: precisely the
    empty-cache-hit the gate exists to prevent."""
    assert canonical_hyperedge({"id": "h", "nodes": [7, "7", "b"]}) is None
    kept = canonical_hyperedge({"id": "h", "nodes": [7, "7", "b", "c"]})
    assert kept["nodes"] == ["7", "b", "c"]


def test_canonical_hyperedge_keeps_a_group_exactly_at_the_minimum():
    """The threshold is inclusive — MIN_HYPEREDGE_MEMBERS distinct members pass."""
    members = [f"n{i}" for i in range(MIN_HYPEREDGE_MEMBERS)]
    assert canonical_hyperedge({"id": "h", "nodes": members})["nodes"] == members
    assert canonical_hyperedge({"id": "h", "nodes": members[:-1]}) is None


def test_to_json_tolerates_non_list_hyperedge_metadata(tmp_path):
    """A direct caller can leave `G.graph["hyperedges"]` as None; iterating it
    raised TypeError before the graph was written at all."""
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c"])
    G.graph["hyperedges"] = None
    out = tmp_path / "graph.json"
    assert to_json(G, {0: ["a", "b", "c"]}, str(out))
    assert json.loads(out.read_text(encoding="utf-8"))["hyperedges"] == []


def test_to_json_gates_hyperedges_written_by_a_direct_caller(tmp_path):
    """to_json is public API and the final persistence boundary. A library caller
    that populates G.graph["hyperedges"] itself bypasses build_from_json,
    build_merge and attach_hyperedges, so the minimum-cardinality invariant has
    to hold here too — in both JSON slots."""
    G = nx.Graph()
    G.add_nodes_from(["a", "b", "c"])
    G.graph["hyperedges"] = [
        {"id": "pair", "nodes": ["a", "b"]},
        {"id": "dupes", "nodes": ["a", "a", "b"]},
        {"id": "dangling", "nodes": ["a", "b", "ghost"]},
        {"id": "alias", "members": ["a", "b", "c"]},
        {"id": "good", "nodes": ["a", "b", "c"]},
    ]
    out = tmp_path / "graph.json"
    assert to_json(G, {0: ["a", "b", "c"]}, str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    assert {h["id"] for h in data["hyperedges"]} == {"alias", "good"}
    assert {h["id"] for h in data["graph"]["hyperedges"]} == {"alias", "good"}
    assert next(h for h in data["hyperedges"] if h["id"] == "alias")["nodes"] == ["a", "b", "c"]
    # The caller's own graph must not be mutated by an export.
    assert len(G.graph["hyperedges"]) == 5


# ---------------------------------------------------------------------------
# 2c. node_id_set / gate_hyperedges — the reusable pair the writers share
# ---------------------------------------------------------------------------

def test_node_id_set_skips_ids_that_cannot_be_members():
    """An id-less node contributes nothing, and an unhashable id must be skipped
    rather than poisoning the set (`None` would let a null member count) or
    raising (a persisted list/dict id is deliberately left for the validator)."""
    nodes = [
        {"id": "a"}, {"id": "b"},
        {"label": "no id at all"},
        {"id": None},
        {"id": ["malformed", "list"]},
        {"id": {"also": "malformed"}},
        "not-a-dict",
    ]
    assert node_id_set(nodes) == {"a", "b"}


def test_gate_hyperedges_without_a_node_list_checks_shape_only():
    """The pre-stamp and cache callers have no node set: members are not checked
    for membership, only the group's shape and distinct cardinality."""
    kept, dropped = gate_hyperedges([
        {"id": "ghosts", "nodes": ["nope_a", "nope_b", "nope_c"]},
        {"id": "pair", "nodes": ["a", "b"]},
    ])
    assert [h["id"] for h in kept] == ["ghosts"]
    assert dropped == 1


def test_gate_hyperedges_filters_against_the_given_nodes():
    """The writer callers pass the node list about to be persisted."""
    nodes = [{"id": n} for n in ("a", "b", "c")]
    kept, dropped = gate_hyperedges([
        {"id": "ok", "nodes": ["a", "b", "c"]},
        {"id": "dangling", "nodes": ["a", "b", "ghost"]},
        {"id": "alias", "members": ["a", "b", "c"]},
    ], nodes)
    assert [h["id"] for h in kept] == ["ok", "alias"]
    assert kept[1]["nodes"] == ["a", "b", "c"], "alias folded onto nodes"
    assert dropped == 1


def test_gate_hyperedges_resolves_members_through_the_normalized_id_space():
    """The clustered path heals casing/punctuation drift in member refs through
    `norm_to_id` in build_from_json, so a group naming `Foo-Bar` for node
    `foo_bar` survives there. The raw `--no-cluster` and watch writers never
    reach build_from_json, so an exact-membership filter dropped a group that
    is perfectly resolvable — a group silently lost by the gate that was added
    to protect it. Resolve through the same normalized space, and hand back the
    ids the nodes actually carry."""
    nodes = [{"id": "foo_bar"}, {"id": "baz_qux"}, {"id": "third"}]
    kept, dropped = gate_hyperedges(
        [{"id": "g", "nodes": ["Foo-Bar", "Baz Qux", "THIRD"]}], nodes
    )
    assert dropped == 0, "a resolvable group must not be dropped"
    assert kept[0]["nodes"] == ["foo_bar", "baz_qux", "third"], (
        "members come back as the persisted node ids, not the drifted refs"
    )


def test_gate_hyperedges_counts_a_drifted_and_exact_ref_to_one_node_once():
    """Two refs that normalize onto the same node are one member, not two —
    otherwise normalized resolution would let a pair pass as a group."""
    nodes = [{"id": "foo_bar"}, {"id": "other"}]
    assert gate_hyperedges(
        [{"id": "g", "nodes": ["foo_bar", "Foo-Bar", "other"]}], nodes
    ) == ([], 1)


def test_gate_hyperedges_prefers_an_exact_match_over_a_normalized_one():
    """An exact id must never be redirected to a different node that merely
    normalizes the same way."""
    nodes = [{"id": "Foo-Bar"}, {"id": "foo_bar"}, {"id": "a"}, {"id": "b"}]
    kept, _ = gate_hyperedges(
        [{"id": "g", "nodes": ["Foo-Bar", "a", "b"]}], nodes
    )
    assert kept[0]["nodes"] == ["Foo-Bar", "a", "b"]


def test_gate_hyperedges_reports_the_drop_count_for_the_caller_message():
    """Callers word their own stderr line, so the count comes back rather than
    being printed here — the three writers say different things."""
    assert gate_hyperedges([], None) == ([], 0)
    assert gate_hyperedges(None, None) == ([], 0)
    _, dropped = gate_hyperedges([{"id": "p", "nodes": ["a", "b"]}], None)
    assert dropped == 1


# ---------------------------------------------------------------------------
# 2d. member_in_id_space — the yes/no predicate canonicalizes its own argument
# ---------------------------------------------------------------------------

MEMBER_SPACE = node_id_set([{"id": "foo_bar"}, {"id": 7}])


@pytest.mark.parametrize(
    "member",
    ["foo_bar", {"id": "foo_bar"}, "Foo-Bar", {"id": "Foo-Bar"}],
    ids=["bare", "object", "drifted-bare", "drifted-object"],
)
def test_member_in_id_space_resolves_a_string_member_in_either_shape(member):
    """An object-shaped member names its `id`, exactly as it does everywhere else.

    `_normalize_hyperedge_members` flattens `{"id": "a"}` to `"a"`, but the
    yes/no callers test members straight off a persisted group that has not
    been through it — watch's reconciliation drop reads
    `edge["nodes"]` verbatim. An unwrapped dict is unhashable, so it named
    nothing, and watch DELETED a group whose members are all alive.
    """
    assert member_in_id_space(member, MEMBER_SPACE) is True


@pytest.mark.parametrize("member", [7, "7", {"id": 7}, {"id": "7"}])
def test_member_in_id_space_coerces_a_numeric_member(member):
    """`node_id_set` keys are `_coerce_id`-coerced, so the member side has to be
    too. The cache's skipped-node prune passes members raw, so a numeric one
    missed the node it named and the group was cached referencing a node
    deliberately not written."""
    assert member_in_id_space(member, MEMBER_SPACE) is True


@pytest.mark.parametrize(
    "member",
    ["ghost", {"id": "ghost"}, {"id": None}, {"label": "no id"}, {}, None,
     ["unhashable"]],
)
def test_member_in_id_space_rejects_what_names_nothing(member):
    """Canonicalizing must not invent a resolution: a member with no usable id,
    in either shape, still names nothing."""
    assert member_in_id_space(member, MEMBER_SPACE) is False


# ---------------------------------------------------------------------------
# 3. to_json includes hyperedges key
# ---------------------------------------------------------------------------

def test_to_json_includes_hyperedges():
    """to_json writes the hyperedge set into graph.json."""
    G = build_from_json(SAMPLE_EXTRACTION)
    communities = {0: list(G.nodes())}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    to_json(G, communities, path)
    data = json.loads(Path(path).read_text())
    assert "hyperedges" in data
    assert len(data["hyperedges"]) == 1
    assert data["hyperedges"][0]["id"] == "auth_flow"


def test_to_json_hyperedges_empty_when_none():
    """With no hyperedges the written key is an empty list."""
    extraction = {**SAMPLE_EXTRACTION, "hyperedges": []}
    G = build_from_json(extraction)
    communities = {0: list(G.nodes())}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    to_json(G, communities, path)
    data = json.loads(Path(path).read_text())
    assert "hyperedges" in data
    assert data["hyperedges"] == []


# ---------------------------------------------------------------------------
# 4. Hyperedges loaded from graph.json via build_from_json
# ---------------------------------------------------------------------------

def test_hyperedges_roundtrip_via_json_file():
    """Write graph.json then reload it - hyperedges must survive."""
    G = build_from_json(SAMPLE_EXTRACTION)
    communities = {0: list(G.nodes())}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    to_json(G, communities, path)

    # Reload the JSON as if build_from_json were called on it
    data = json.loads(Path(path).read_text())
    G2 = build_from_json({
        "nodes": [{"id": n["id"], **{k: v for k, v in n.items() if k != "id"}} for n in data["nodes"]],
        "edges": [{"source": e["source"], "target": e["target"], **{k: v for k, v in e.items() if k not in ("source", "target")}} for e in data.get("links", [])],
        "hyperedges": data.get("hyperedges", []),
    })
    assert G2.graph.get("hyperedges", []) != []
    assert G2.graph["hyperedges"][0]["id"] == "auth_flow"


# ---------------------------------------------------------------------------
# 5. Report includes hyperedges section when hyperedges present
# ---------------------------------------------------------------------------

def _make_report(G):

    """Render a report for *G* with every node in one community."""
    communities = {0: list(G.nodes())}
    cohesion = {0: 1.0}
    labels = {0: "All"}
    gods = [{"label": "BasicAuth", "degree": 2}]
    surprises = []
    return generate(G, communities, cohesion, labels, gods, surprises, SAMPLE_DETECTION, {"input": 10, "output": 5}, ".")


def test_report_includes_hyperedges_section():
    """A non-empty hyperedge set renders a hyperedges section in the report."""
    G = build_from_json(SAMPLE_EXTRACTION)
    report = _make_report(G)
    assert "## Hyperedges (group relationships)" in report
    assert "Auth Flow" in report
    assert "INFERRED 0.75" in report


def test_report_includes_hyperedge_node_list():


    """The hyperedges section lists each group's member ids."""
    G = build_from_json(SAMPLE_EXTRACTION)
    report = _make_report(G)
    # Node IDs should appear in the report line
    assert "BasicAuth" in report
    assert "DigestAuth" in report


# ---------------------------------------------------------------------------
# 6. Report skips hyperedges section when none present
# ---------------------------------------------------------------------------

def test_report_skips_hyperedges_section_when_empty():
    """An empty hyperedge set renders no hyperedges section in the report."""
    extraction = {**SAMPLE_EXTRACTION, "hyperedges": []}
    G = build_from_json(extraction)
    report = _make_report(G)
    assert "## Hyperedges" not in report


def test_report_skips_hyperedges_section_when_key_missing():
    """An extraction with no `hyperedges` key at all gets no report section."""
    extraction = {k: v for k, v in SAMPLE_EXTRACTION.items() if k != "hyperedges"}
    G = build_from_json(extraction)
    report = _make_report(G)
    assert "## Hyperedges" not in report


# ---------------------------------------------------------------------------
# 7. Hyperedge member-key alias normalization (#1561)
# ---------------------------------------------------------------------------

def _alias_extraction():
    """Three hyperedges, one per member-key spelling: nodes / members / node_ids."""
    return {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "m.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "m.py"},
            {"id": "c", "label": "C", "file_type": "code", "source_file": "m.py"},
        ],
        "edges": [],
        "hyperedges": [
            {"id": "he_nodes", "label": "canon", "nodes": ["a", "b", "c"]},
            {"id": "he_members", "label": "alias1", "members": ["a", "b", "c"]},
            {"id": "he_node_ids", "label": "alias2", "node_ids": ["a", "b", "c"]},
        ],
    }


def test_build_normalizes_member_aliases_to_nodes():
    """Both `members` and `node_ids` aliases fold onto the canonical `nodes` key."""
    G = build_from_json(_alias_extraction())
    hes = {he["id"]: he for he in G.graph["hyperedges"]}
    for hid in ("he_nodes", "he_members", "he_node_ids"):
        assert hes[hid]["nodes"] == ["a", "b", "c"], hid
        # alias keys are dropped post-normalization
        assert "members" not in hes[hid]
        assert "node_ids" not in hes[hid]


def test_build_dedups_alias_members_preserving_order():
    """Alias members are deduped in first-seen order."""
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "m.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "m.py"},
            {"id": "c", "label": "C", "file_type": "code", "source_file": "m.py"},
        ],
        "edges": [],
        "hyperedges": [{"id": "h", "label": "x", "members": ["a", "a", "b", "c"]}],
    }
    G = build_from_json(extraction)
    assert G.graph["hyperedges"][0]["nodes"] == ["a", "b", "c"]
    assert "members" not in G.graph["hyperedges"][0]


def test_build_canonical_nodes_wins_over_alias():
    """When both are present the canonical `nodes` key wins and the alias is dropped."""
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "m.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "m.py"},
            {"id": "x", "label": "X", "file_type": "code", "source_file": "m.py"},
        ],
        "edges": [],
        "hyperedges": [
            {"id": "h", "label": "x", "nodes": ["a", "b", "x"], "members": ["b"]},
        ],
    }
    G = build_from_json(extraction)
    he = G.graph["hyperedges"][0]
    assert he["nodes"] == ["a", "b", "x"]  # canonical untouched
    assert "members" not in he  # stray alias dropped


def test_build_rekeys_alias_keyed_hyperedge_members():
    """Alias normalization must run BEFORE the semantic id-remap loop so a
    `members`-keyed hyperedge's refs get rekeyed alongside `nodes`-keyed ones."""
    # Non-AST node whose id uses the OLD short stem (`mod_foo`) for source_file
    # pkg/mod.py -> new canonical stem pkg_mod -> remap mod_foo => pkg_mod_foo.
    extraction = {
        "nodes": [
            {"id": "mod_foo", "label": "foo", "file_type": "code", "source_file": "pkg/mod.py"},
            {"id": "mod_bar", "label": "bar", "file_type": "code", "source_file": "pkg/mod.py"},
            {"id": "mod_baz", "label": "baz", "file_type": "code", "source_file": "pkg/mod.py"},
        ],
        "edges": [],
        "hyperedges": [
            {"id": "h", "label": "x", "members": ["mod_foo", "mod_bar", "mod_baz"]},
        ],
    }
    G = build_from_json(extraction)
    he = G.graph["hyperedges"][0]
    assert he["nodes"] == ["pkg_mod_foo", "pkg_mod_bar", "pkg_mod_baz"]


def test_build_warns_once_per_aliased_hyperedge(capsys):
    build_from_json(_alias_extraction())
    err = capsys.readouterr().err
    # one warning each for the two alias hyperedges, none for the nodes-keyed one
    assert err.count("normalizing") == 2
    assert "he_members" in err and "members" in err
    assert "he_node_ids" in err and "node_ids" in err
    assert "he_nodes" not in err
