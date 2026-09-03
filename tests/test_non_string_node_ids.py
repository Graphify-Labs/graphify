"""Non-string node ids from LLM backends must not crash the build (#2326).

A backend can emit ``{"id": 10}`` where the schema says ``{"id": "10"}``. Every
id consumer downstream assumes ``str``, so an int id used to abort the whole
build in three different places. These tests pin the crash sites and the
edge/hyperedge linkage that a node-only coercion would silently break.
"""
import networkx as nx
import pytest

from graphify.build import build, build_from_json


def _node(nid, label, **kw):
    return {
        "id": nid,
        "label": label,
        "file_type": "concept",
        "source_file": "a.py",
        **kw,
    }


def _edge(src, tgt):
    return {"source": src, "target": tgt, "relation": "uses", "confidence": "EXTRACTED"}


def test_pick_winner_survives_int_id_in_duplicate_group():
    """dedup._pick_winner regex-searched the raw id (the issue's traceback).

    Driven through ``build`` because that is dedup's only production caller, so
    ``build`` is where the coercion has to land for this path to be fixed.
    """
    ext = {"nodes": [_node(10, "Alpha"), _node("alpha_c1", "Alpha")], "edges": []}
    G = build([ext], dedup=True)
    assert all(isinstance(nid, str) for nid in G.nodes)


def test_build_accepts_a_single_int_id_node_with_no_duplicate():
    """build_from_json's sorted(node_set) crashed even with nothing to dedup."""
    ext = {"nodes": [_node(10, "Alpha"), _node("b", "Beta")], "edges": [_edge(10, "b")]}
    G = build([ext], dedup=True)
    assert "10" in G.nodes
    assert 10 not in G.nodes


def test_int_id_endpoints_stay_connected_after_coercion():
    """Coercing node ids without coercing endpoints would orphan the edge."""
    ext = {"nodes": [_node(10, "Alpha"), _node(20, "Beta")], "edges": [_edge(10, 20)]}
    G = build([ext], dedup=True)
    assert G.has_edge("10", "20")


def test_int_id_survives_a_fuzzy_dedup_group():
    ext = {
        "nodes": [_node(10, "PaymentProcessor"), _node("b", "PaymentProcessors")],
        "edges": [_edge(10, "b")],
    }
    G = build([ext], dedup=True)
    assert all(isinstance(nid, str) for nid in G.nodes)


def test_float_id_is_coerced_too():
    ext = {"nodes": [_node(1.5, "Alpha"), _node("b", "Beta")], "edges": [_edge(1.5, "b")]}
    G = build([ext], dedup=True)
    assert G.has_edge("1.5", "b")


def test_legacy_from_to_endpoints_are_coerced():
    """dedup reads the legacy from/to aliases (#803), so they need it as well."""
    ext = {
        "nodes": [_node(10, "Alpha"), _node("b", "Beta"), _node("c", "Gamma")],
        "edges": [{"from": 10, "to": "b", "relation": "uses", "confidence": "EXTRACTED"}],
    }
    G = build([ext], dedup=True)
    assert G.has_edge("10", "b")


def test_node_id_set_coerces_numeric_ids_like_members_are():
    """#2326 heals numeric node ids to their string form, and member coercion
    does the same to member refs — so the comparison set has to be built in the
    same space. Keyed on raw values, `"7" in {7}` is False and every member of
    an otherwise valid group is dropped."""
    from graphify.build import gate_hyperedges, node_id_set

    nodes = [{"id": 7}, {"id": 8}, {"id": 9}]
    assert node_id_set(nodes) == {"7", "8", "9"}

    kept, dropped = gate_hyperedges([{"id": "g", "nodes": [7, 8, 9]}], nodes)
    assert dropped == 0, "a group over numeric node ids must survive"
    assert kept[0]["nodes"] == [7, 8, 9], (
        "the raw writers persist `nodes` unchanged, so surviving members have "
        "to come back in the node list's own id space"
    )


def test_gate_hyperedges_returns_members_in_the_node_lists_own_id_space():
    """The raw `--no-cluster` writers gate against the node records they are
    about to persist and write those records unchanged. Coercing only the
    comparison side left the file holding nodes `[7, 8, 9]` and members
    `["7", "8", "9"]` — a dangling reference, the shape #1916 removed, written
    by the gate that exists to prevent it. Compare coerced, return raw."""
    from graphify.build import gate_hyperedges
    from graphify.watch import _gated_hyperedges

    nodes = [{"id": 7}, {"id": 8}, {"id": 9}]
    written_ids = {n["id"] for n in nodes}

    kept, _ = gate_hyperedges([{"id": "g", "nodes": [7, 8, 9]}], nodes)
    assert set(kept[0]["nodes"]) <= written_ids, (
        f"members {kept[0]['nodes']} must name nodes actually written "
        f"{sorted(written_ids, key=str)}"
    )

    # watch's raw writer shares the gate and writes the same node records.
    members = _gated_hyperedges([{"id": "g", "nodes": [7, 8, 9]}], nodes)[0]["nodes"]
    assert set(members) <= written_ids


def test_prune_graph_json_sources_keeps_the_files_own_node_id_space():
    """An externally produced or legacy graph.json can carry numeric node ids.
    The pruner rewrites hyperedges but leaves the node records alone, so a
    coerced member list would turn a valid group into a dangling one on disk."""
    import json

    from graphify.cli import _prune_graph_json_sources

    graph_path = tmp_graph_json(
        nodes=[
            {"id": 7, "source_file": "a.py"},
            {"id": 8, "source_file": "a.py"},
            {"id": 9, "source_file": "a.py"},
            {"id": 99, "source_file": "gone.py"},
        ],
        hyperedges=[{"id": "g", "source_file": "a.py", "nodes": [7, 8, 9, 99]}],
    )
    _prune_graph_json_sources(graph_path, ["gone.py"])

    data = json.loads(graph_path.read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in data["nodes"]}
    members = data["hyperedges"][0]["nodes"]
    assert node_ids == {7, 8, 9}, "the stale source's node is pruned"
    assert set(members) <= node_ids, (
        f"members {members} must name nodes actually written "
        f"{sorted(node_ids, key=str)}"
    )


def test_prune_graph_json_sources_tolerates_a_non_dict_graph_value():
    """A legacy or hand-edited graph.json can carry a non-dict `graph` value.
    Reading the nested slot as `(data.get("graph") or {}).get(...)` raised
    AttributeError straight out of the function — the try above it wraps only
    the JSON load — so the whole exclusion-only prune aborted. The nested-sync
    code further down already guards with isinstance; this read must too."""
    import json

    from graphify.cli import _prune_graph_json_sources

    for bad in ("oops", [1, 2], 5, True):
        path = tmp_graph_json(
            nodes=[{"id": "a", "source_file": "gone.py"},
                   {"id": "b", "source_file": "live.py"}],
            hyperedges=[],
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        data["graph"] = bad
        # The nested read is only reached when the TOP-LEVEL slot is not a list,
        # so leaving `"hyperedges": []` here would skip the branch under test
        # entirely and the assertion would pass for the wrong reason.
        del data["hyperedges"]
        path.write_text(json.dumps(data), encoding="utf-8")

        removed = _prune_graph_json_sources(path, ["gone.py"])
        assert removed == 1, f"the prune must still run with graph={bad!r}"
        assert {n["id"] for n in json.loads(path.read_text())["nodes"]} == {"b"}


def test_gate_coerces_a_raw_set_container_like_every_other_kind():
    """A set was once trusted as already coerced, which made numeric ids behave
    differently from a list or a graph: members became `"7"` and then failed
    membership against `{7, 8, 9}`, dropping a valid group. Every container kind
    goes through the same coercion now; this pins it so the exemption cannot
    come back as an optimization."""
    from graphify.build import gate_hyperedges_against_graph

    for container in ({7, 8, 9}, frozenset({7, 8, 9}), [7, 8, 9]):
        kept, dropped = gate_hyperedges_against_graph(
            [{"id": "g", "nodes": [7, 8, 9]}], container
        )
        assert dropped == 0, f"a valid group must survive against {container!r}"
        assert kept[0]["nodes"] == [7, 8, 9], "in the container's own id space"


def tmp_graph_json(*, nodes, hyperedges):
    """Write a minimal hand-authored graph.json and return its path."""
    import json
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "graph.json"
    path.write_text(
        json.dumps({"nodes": nodes, "edges": [], "hyperedges": hyperedges}),
        encoding="utf-8",
    )
    return path


def test_graph_container_membership_uses_the_coerced_id_space():
    """`attach_hyperedges`, `to_json` and `build_merge` pass the graph itself as
    the container. Coercing only the member side left `"7" in nx.Graph([7])`
    False, so every member of a valid group over numeric node ids was dropped —
    the list path was fixed by node_id_set, the container path was not."""
    import json
    import tempfile
    from pathlib import Path

    import networkx as nx

    from graphify.build import gate_hyperedges_against_graph
    from graphify.export import attach_hyperedges, to_json

    G = nx.Graph()
    G.add_nodes_from([7, 8, 9])
    kept, _ = gate_hyperedges_against_graph([{"id": "g", "nodes": [7, 8, 9]}], G)
    assert kept[0]["nodes"] == [7, 8, 9], "in the graph's own id space"

    H = nx.Graph()
    H.add_nodes_from([7, 8, 9])
    attach_hyperedges(H, [{"id": "g", "nodes": [7, 8, 9]}])
    assert [h["id"] for h in H.graph.get("hyperedges", [])] == ["g"]

    J = nx.Graph()
    J.add_nodes_from([7, 8, 9])
    J.graph["hyperedges"] = [{"id": "g", "nodes": [7, 8, 9]}]
    out = Path(tempfile.mkdtemp()) / "graph.json"
    to_json(J, {0: [7, 8, 9]}, str(out))
    assert [h["id"] for h in json.loads(out.read_text())["hyperedges"]] == ["g"]


def test_to_json_writes_members_in_the_graphs_own_id_space():
    """Coercing only the comparison side left graph.json internally inconsistent:
    node_link_data writes `{"id": 7}` while the surviving member reads `"7"`, so
    the written file carries a dangling member — the very shape #1916 removed.
    Whatever the gate keeps has to come back out in the node ids' own space."""
    import json
    import tempfile
    from pathlib import Path

    import networkx as nx

    from graphify.export import to_json

    G = nx.Graph()
    G.add_nodes_from([7, 8, 9])
    G.graph["hyperedges"] = [{"id": "g", "nodes": [7, 8, 9]}]
    out = Path(tempfile.mkdtemp()) / "graph.json"
    to_json(G, {0: [7, 8, 9]}, str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in data["nodes"]}
    assert data["hyperedges"], "the group must survive"
    members = data["hyperedges"][0]["nodes"]
    assert set(members) <= node_ids, (
        f"members {members} must name nodes actually written {sorted(node_ids, key=str)}"
    )


def test_semantic_cleanup_keeps_a_group_over_numeric_node_ids():
    """Member refs are coerced, so the surviving-id set has to be read in the
    same space or every member of a valid numeric group is filtered out.

    Members come back as the fragment's own node ids rather than the coerced
    spelling: this pass now delegates to the shared gate, which returns the
    container's ids so a member always names a node that is actually there.
    An earlier revision of this test asserted `["7", "8", "9"]`, which was the
    weaker guarantee the pass made when it filtered members itself.
    """
    from graphify.semantic_cleanup import sanitize_semantic_fragment

    fragment = {
        "nodes": [
            {"id": n, "label": f"N{n}", "file_type": "code", "source_file": "a.py"}
            for n in (7, 8, 9)
        ],
        "edges": [],
        "hyperedges": [{"id": "g", "nodes": [7, 8, 9]}],
    }
    out = sanitize_semantic_fragment(fragment)
    assert [h["id"] for h in out["hyperedges"]] == ["g"]
    assert out["hyperedges"][0]["nodes"] == [7, 8, 9]
    assert set(out["hyperedges"][0]["nodes"]) <= {n["id"] for n in out["nodes"]}


def test_prefix_graph_for_global_builds_the_relabel_map_once(monkeypatch):
    """The coerced relabel map must be built once per graph, not once per
    hyperedge — rebuilding it inside the loop makes prefixing O(nodes x
    hyperedges), and a semantic graph can carry thousands of groups."""
    import networkx as nx

    import graphify.build as buildmod

    calls = {"n": 0}
    real = buildmod._coerce_id

    def counting(value):
        """Count every _coerce_id call so the map rebuild is detectable."""
        calls["n"] += 1
        return real(value)

    monkeypatch.setattr(buildmod, "_coerce_id", counting)

    nodes = list(range(50))
    G = nx.Graph()
    G.add_nodes_from(nodes)
    G.graph["hyperedges"] = [
        {"id": f"h{i}", "nodes": [0, 1, 2]} for i in range(20)
    ]
    buildmod.prefix_graph_for_global(G, "repo")

    # 50 nodes + 20 groups x 3 members = 110 if the map is built once; rebuilding
    # it per hyperedge costs 50 x 20 = 1000 extra coercions on its own.
    assert calls["n"] < 500, (
        f"_coerce_id called {calls['n']} times — the relabel map is being "
        f"rebuilt per hyperedge"
    )


def test_attach_hyperedges_builds_the_graph_id_map_once(monkeypatch):
    """Same defect class as the prefix_graph_for_global map above, in the other
    direction: gating one candidate at a time rebuilt the graph's coerced id map
    for every hyperedge, so merge-graphs went from linear to O(nodes x groups)
    on exactly the thousands-of-groups corpora this gate was added for."""
    import networkx as nx

    import graphify.build as buildmod
    from graphify.export import attach_hyperedges

    calls = {"n": 0}
    real = buildmod._coerce_id

    def counting(value):
        """Count every _coerce_id call so a per-candidate rebuild is visible."""
        calls["n"] += 1
        return real(value)

    monkeypatch.setattr(buildmod, "_coerce_id", counting)

    G = nx.Graph()
    G.add_nodes_from(range(50))
    attach_hyperedges(G, [{"id": f"h{i}", "nodes": [0, 1, 2]} for i in range(20)])

    assert [h["id"] for h in G.graph["hyperedges"]] == [f"h{i}" for i in range(20)]
    # 50 nodes + 20 groups x 3 members = 110 with the map built once; per
    # candidate it costs 50 x 20 = 1000 extra coercions on its own.
    assert calls["n"] < 500, (
        f"_coerce_id called {calls['n']} times — the graph id map is being "
        f"rebuilt per hyperedge"
    )


def test_semantic_cleanup_resolves_normalized_members():
    """`sanitize_semantic_fragment` filtered members with an exact `in` test, so
    a member the gate and build_from_json both resolve was removed and the group
    dropped below the minimum. Every membership decision in the feature has to
    use one resolution rule."""
    from graphify.semantic_cleanup import sanitize_semantic_fragment

    fragment = {
        "nodes": [
            {"id": n, "label": n, "file_type": "code", "source_file": "a.py"}
            for n in ("foo_bar", "b", "c")
        ],
        "edges": [],
        "hyperedges": [{"id": "g", "nodes": ["Foo-Bar", "b", "c"]}],
    }
    out = sanitize_semantic_fragment(fragment)
    assert [h["id"] for h in out["hyperedges"]] == ["g"]
    assert out["hyperedges"][0]["nodes"] == ["foo_bar", "b", "c"]


def test_watch_reconcile_keeps_a_group_with_normalized_members(tmp_path):
    """`_reconcile_existing_graph` drops a preserved group when ANY member is
    absent, using a raw `in` test upstream of the gate — so an unrelated watch
    rebuild deleted a group the gate resolves and keeps. The whole-group drop
    semantics stay; only the resolution changes."""
    import json

    from graphify.watch import _reconcile_existing_graph

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({
        "nodes": [
            {"id": n, "source_file": "keep.py", "_origin": "ast",
             "source_location": "L1"}
            for n in ("foo_bar", "baz_qux", "third")
        ],
        "edges": [],
        "hyperedges": [{"id": "g", "nodes": ["Foo-Bar", "Baz Qux", "THIRD"],
                        "source_file": "keep.py"}],
    }), encoding="utf-8")

    merged, _ = _reconcile_existing_graph(
        graph_path,
        {"nodes": [], "edges": [], "hyperedges": []},
        out=tmp_path,
        project_root=tmp_path,
        watch_root=tmp_path,
        code_files=[tmp_path / "keep.py"],
        extract_targets=[],
        full_rebuild=False,
        deleted_paths=set(),
        deleted_source_identities=set(),
    )
    assert [h["id"] for h in merged.get("hyperedges", [])] == ["g"], (
        "a group whose members resolve must survive reconciliation"
    )


def test_watch_reconcile_keeps_a_group_over_numeric_node_ids(tmp_path):
    """Routing watch's membership check through the shared lookup order is not
    enough on its own: `all_ids` holds the node ids raw, so a numeric node id
    stays `7` while its member coerces to `"7"` and the group is evicted. The
    member-side set has to be built in the shared key space. `all_ids` itself
    stays raw, because the edge-endpoint checks above compare raw endpoints."""
    import json

    from graphify.watch import _reconcile_existing_graph

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({
        "nodes": [
            {"id": n, "source_file": "keep.py", "_origin": "ast",
             "source_location": "L1"}
            for n in (7, 8, 9)
        ],
        "edges": [],
        "hyperedges": [{"id": "g", "nodes": [7, 8, 9], "source_file": "keep.py"}],
    }), encoding="utf-8")

    merged, _ = _reconcile_existing_graph(
        graph_path,
        {"nodes": [], "edges": [], "hyperedges": []},
        out=tmp_path,
        project_root=tmp_path,
        watch_root=tmp_path,
        code_files=[tmp_path / "keep.py"],
        extract_targets=[],
        full_rebuild=False,
        deleted_paths=set(),
        deleted_source_identities=set(),
    )
    assert [h["id"] for h in merged.get("hyperedges", [])] == ["g"]


def test_prefix_graph_for_global_prefixes_normalized_members():
    """The gate resolves a member that drifted in casing or punctuation, so the
    cross-repo relabel has to resolve it the same way. Keyed on the coerced
    spelling only, `Foo-Bar` stayed unprefixed while its node became
    `repo::foo_bar`, and `attach_hyperedges` then dropped the whole group — a
    valid group lost to two halves of one invariant disagreeing."""
    import networkx as nx

    from graphify.build import prefix_graph_for_global
    from graphify.export import attach_hyperedges

    G = nx.Graph()
    G.add_nodes_from(["foo_bar", "baz_qux", "third"])
    G.graph["hyperedges"] = [{"id": "g", "nodes": ["Foo-Bar", "Baz Qux", "THIRD"]}]

    H = prefix_graph_for_global(G, "repo")
    assert H.graph["hyperedges"][0]["nodes"] == [
        "repo::foo_bar", "repo::baz_qux", "repo::third",
    ]

    merged = nx.Graph()
    merged.add_nodes_from(H.nodes)
    attach_hyperedges(merged, [dict(H.graph["hyperedges"][0])])
    assert [h["id"] for h in merged.graph.get("hyperedges", [])] == ["repo::g"]


def test_prefix_graph_for_global_counts_two_refs_to_one_node_once():
    """Normalized resolution must not let a pair through: an exact and a drifted
    ref to the same node prefix to one member, so the group is under the
    minimum and the attach boundary drops it."""
    import networkx as nx

    from graphify.build import prefix_graph_for_global
    from graphify.export import attach_hyperedges

    G = nx.Graph()
    G.add_nodes_from(["foo_bar", "other"])
    G.graph["hyperedges"] = [{"id": "g", "nodes": ["foo_bar", "Foo-Bar", "other"]}]

    H = prefix_graph_for_global(G, "repo")
    assert H.graph["hyperedges"][0]["nodes"] == ["repo::foo_bar", "repo::other"]

    merged = nx.Graph()
    merged.add_nodes_from(H.nodes)
    attach_hyperedges(merged, [dict(H.graph["hyperedges"][0])])
    assert merged.graph.get("hyperedges", []) == []


def test_prefix_graph_for_global_prefixes_numeric_members():
    """`merge-graphs` relabels node `7` to `repo::7`, and member normalization
    turns the member into `"7"` — so the relabel lookup must be keyed in the
    coerced space too, or the member stays unprefixed and the attach boundary
    drops the group for having no member backed by a node."""
    import networkx as nx

    from graphify.build import prefix_graph_for_global
    from graphify.export import attach_hyperedges

    G = nx.Graph()
    G.add_nodes_from([7, 8, 9])
    G.graph["hyperedges"] = [{"id": "g", "nodes": [7, 8, 9]}]

    H = prefix_graph_for_global(G, "repo")
    assert H.graph["hyperedges"][0]["nodes"] == ["repo::7", "repo::8", "repo::9"]

    merged = nx.Graph()
    merged.add_nodes_from(H.nodes)
    attach_hyperedges(merged, [dict(H.graph["hyperedges"][0])])
    assert [h["id"] for h in merged.graph.get("hyperedges", [])] == ["repo::g"]


def test_hyperedge_members_are_coerced_with_their_nodes():
    """#2326: a numeric member is str-coerced alongside its node id."""
    ext = {
        "nodes": [_node(10, "Alpha"), _node("b", "Beta"), _node("c", "Gamma")],
        "edges": [],
        "hyperedges": [{"id": "he1", "label": "grp", "nodes": [10, "b", "c"]}],
    }
    G = build([ext], dedup=True)
    members = G.graph["hyperedges"][0]["nodes"]
    assert members == ["10", "b", "c"]


def test_build_from_json_coerces_on_the_direct_entry():
    """Reloading a persisted graph does not go through build()/dedup."""
    G = build_from_json({"nodes": [_node(10, "Alpha")], "edges": []})
    assert list(G.nodes) == ["10"]


def test_numeric_endpoint_with_no_matching_node_matches_the_string_case():
    """A numeric endpoint with no node of its own must behave like a string one.

    Both are dangling references, which build_from_json drops — the point is that
    coercion makes the int indistinguishable from the str, rather than crashing
    or leaving a half-typed endpoint behind.
    """
    def graph_for(target):
        G = build_from_json(
            {"nodes": [_node("a", "Alpha")], "edges": [_edge("a", target)]}
        )
        return sorted(G.nodes), sorted(G.edges)

    assert graph_for(99) == graph_for("99")


@pytest.mark.parametrize("bad", [None, ["x"], {"k": "v"}])
def test_non_scalar_ids_are_left_for_validation(bad):
    """Only numeric scalars are coerced; str(None) == 'None' would be a lie."""
    from graphify.build import _coerce_non_string_ids

    ext = {"nodes": [{"id": bad, "label": "Alpha"}], "edges": []}
    _coerce_non_string_ids(ext)
    assert ext["nodes"][0]["id"] == bad


def test_bool_id_is_not_coerced():
    from graphify.build import _coerce_non_string_ids

    ext = {"nodes": [{"id": True, "label": "Alpha"}], "edges": []}
    _coerce_non_string_ids(ext)
    assert ext["nodes"][0]["id"] is True


def test_string_ids_are_untouched():
    """Regression guard: the normal path must be byte-identical."""
    ext = {"nodes": [_node("a", "Alpha"), _node("b", "Beta")], "edges": [_edge("a", "b")]}
    G = build([ext], dedup=True)
    assert isinstance(G, nx.Graph)
    assert set(G.nodes) == {"a", "b"}
    assert G.has_edge("a", "b")
