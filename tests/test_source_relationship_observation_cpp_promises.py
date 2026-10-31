"""INC117: nonwinning C++ type restrictions remain independent validated facts."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from graphify.build import add_source_relationship, build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.cpp_type_references import is_type_reference_unavailable, validate_type_reference_graph
from graphify.paths import load_node_link_graph
from graphify.source_relationships import is_source_graph
from tests.source_observation_helpers import observations, produce, state


def project(root, *, directed=False):
    """A real C# local activates storage for two independent rejected C++ source uses."""
    produce(root)
    cpp = root / "types.cpp"
    cpp.write_bytes(b"namespace Left {using Count=int;}\nnamespace Right {class Holder {Count*a;Count*b;};}\n"
                    b"void allowed(Left::Count*value){}\n")
    raw = extract([root / "Data.cs", cpp], root=root, cache_root=root, parallel=False)
    assert not raw["failed_sources"]
    assert sum("cpp_type_reference_version" in edge for edge in raw["edges"]) == 2
    return build_from_json(raw, root=root, directed=directed), raw["edges"]


def restricted(graph):
    return next((left, right, edge) for left, right, edge in graph.edges(data=True)
                if is_type_reference_unavailable(edge))


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("original", [False, True])
def test_req_qml014_ac03_nonwinning_cpp_promises_roundtrip_independently(tmp_path, directed, original):
    """Both original source spans remain unavailable after assembly/export/load/rebuild."""
    graph, links = project(tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), original_links=links if original else None)
    loaded = load_node_link_graph(output)
    rebuilt = build_from_json(json.loads(output.read_text()), root=tmp_path, directed=directed)
    for current in (graph, loaded, rebuilt):
        validate_type_reference_graph(current)
        _, _, edge = restricted(current)
        facts = [row["metadata"]["cpp_type_reference"] for row in observations(edge)
                 if "cpp_type_reference_version" in row]
        assert len(facts) == 2 and len({fact["type_span"]["start_byte"] for fact in facts}) == 2
        assert all(fact["resolution"] == "unavailable" for fact in facts)
        target = edge.get("_tgt")
        assert target is not None and not current.nodes[target]["source_file"]
    allowed = next(identity for identity, node in loaded.nodes(data=True) if node.get("label") == "allowed()")
    assert any(edge.get("_src", left) == allowed and edge.get("relation") == "references"
               and loaded.nodes[edge.get("_tgt", right)].get("source_file") == "types.cpp"
               for left, right, edge in loaded.edges(data=True))


@pytest.mark.parametrize("damage", ["marker", "span", "source_file", "strip_both"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml014_ac03_nested_cpp_damage_rejects_before_graph_and_disk_mutation(tmp_path, damage, force):
    """A nonwinning independent promise cannot hide corruption or disappear from a raw override."""
    graph, _ = project(tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    supplied = [{**deepcopy(edge), "source": left, "target": right} for left, right, edge in graph.edges(data=True)]
    parent = next(edge for edge in supplied if is_type_reference_unavailable(edge))
    row = next(item for item in parent["also_seen"] if "cpp_type_reference_version" in item)
    if damage == "marker":
        row["cpp_type_reference_version"] = True
    elif damage == "span":
        row["metadata"]["cpp_type_reference"]["type_span"]["start_byte"] = True
    elif damage == "source_file":
        row["source_file"] = "foreign.cpp"
    else:
        row.pop("cpp_type_reference_version")
        row["metadata"].pop("cpp_type_reference")
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = state(graph), deepcopy(supplied)
    assert to_json(graph, {}, str(output), force=force, original_links=supplied) is False
    assert (state(graph), supplied) == before and output.read_bytes() == accepted


@pytest.mark.parametrize("reverse", [False, True])
def test_req_qml014_ac03_winner_never_borrows_losing_context_or_cpp_authority(tmp_path, reverse):
    """The selected primary is a real complete record; independent restrictions remain secondary."""
    graph, _ = project(tmp_path)
    assert is_source_graph(graph)
    left, right, previous = restricted(graph)
    pair = previous["_src"], previous["_tgt"]
    plain = {"relation": "references", "confidence": "EXTRACTED", "source_file": "types.cpp", "source_location": "L2"}
    saved = deepcopy(previous)
    key = next(key for key, edge in graph[left][right].items() if edge is previous)
    graph.remove_edge(left, right, key)
    first, second = (plain, saved) if reverse else (saved, plain)
    add_source_relationship(graph, *pair, first)
    add_source_relationship(graph, *pair, second)
    current = graph.edges[pair[0], pair[1], key]
    if not reverse:
        assert "metadata" not in current and "context" not in current and "cpp_type_reference_version" not in current
    assert is_type_reference_unavailable(current)
    validate_type_reference_graph(graph)
    assert sum("cpp_type_reference_version" in row for row in observations(current)) == 2
