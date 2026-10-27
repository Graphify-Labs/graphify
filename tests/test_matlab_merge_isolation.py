"""MATLAB provenance isolates persisted relationships without hiding native matches."""

import networkx as nx
import pytest

from graphify.affected import load_graph
from graphify.build import build, build_merge, prefix_graph_for_global
from graphify.cross_repo_calls import link_cross_repo_member_calls
from graphify.cross_repo_types import link_shared_type_declarations
from graphify.export import to_json


def _node(node_id, label, source, *, matlab=False, kind="function", **metadata):
    if matlab:
        metadata.update(language="matlab", kind=f"matlab_{kind}")
    return {
        "id": node_id, "label": label, "source_file": source,
        "source_location": "L1", "file_type": "code", "type": "code",
        "_callable": kind != "file", "_callable_class": kind == "class",
        "metadata": metadata,
    }


def _edge(source, target, relation, source_file, confidence="EXTRACTED"):
    return {
        "source": source, "target": target, "relation": relation,
        "source_file": source_file, "source_location": "L3",
        "confidence": confidence, "weight": 1.0,
    }


def _persist(tmp_path, name, graph):
    path = tmp_path / f"{name}.json"
    to_json(graph, {}, str(path), force=True)
    return path, load_graph(path).to_undirected()


@pytest.mark.parametrize("native_file", ["Foo.h", "Foo.m", "Foo.mm", "Foo.c"])
@pytest.mark.parametrize("relation", ["calls", "imports", "imports_from", "references"])
@pytest.mark.parametrize("reverse", [False, True])
def test_persisted_matlab_native_homonyms_are_not_neighbors(
    tmp_path, native_file, relation, reverse,
):
    nodes = [
        _node("matlab", "Foo", "Foo.m", matlab=True),
        _node("native", "Foo", native_file),
        _node("native_target", "bar", "bar.m"),
    ]
    source, target = ("matlab", "native") if reverse else ("native", "matlab")
    graph = build([{"nodes": nodes, "edges": [
        _edge(source, target, relation, nodes[1 if not reverse else 0]["source_file"], "INFERRED"),
        _edge("native", "native_target", relation, native_file, "INFERRED"),
    ]}], dedup=False)
    _, reloaded = _persist(tmp_path, "mixed", graph)
    assert set(reloaded.neighbors("matlab")) == set()
    assert set(reloaded.neighbors("native")) == {"native_target"}
    assert reloaded.edges["native", "native_target"]["relation"] == relation


def _type_graph(*, matlab=False, source="Greeter.m", method="-greet"):
    return build([{"nodes": [
        _node("greeter", "Greeter", source, matlab=matlab, kind="class", namespace="Shared"),
        _node("greet", method, source, matlab=matlab, kind="method"),
    ], "edges": [_edge("greeter", "greet", "method", source)]}], dedup=False)


@pytest.mark.parametrize("native_sources", [[], ["Greeter.m"], ["Greeter.mm"], ["Greeter.m", "Greeter.mm"]])
def test_persisted_matlab_collision_does_not_answer_or_obscure_native_calls(tmp_path, native_sources):
    caller = build([{"nodes": [_node("caller", "run", "app.m", unresolved_calls=[{
        "lang": "objc", "receiver_type": "Greeter", "callee": "greet", "line": "L3",
    }])], "edges": []}], dedup=False)
    _, caller = _persist(tmp_path, "caller", caller)
    _, matlab = _persist(tmp_path, "matlab", _type_graph(matlab=True))
    graphs = [prefix_graph_for_global(caller, "app"), prefix_graph_for_global(matlab, "matlab")]
    for index, source in enumerate(native_sources):
        _, native = _persist(tmp_path, f"native{index}", _type_graph(source=source))
        graphs.append(prefix_graph_for_global(native, f"native{index}"))
    merged = nx.compose_all(graphs)
    link_cross_repo_member_calls(merged)
    _, merged = _persist(tmp_path, "merged", merged)
    expected = {"native0::greet"} if len(native_sources) == 1 else set()
    assert set(merged.neighbors("app::caller")) == expected
    assert set(merged.neighbors("matlab::greet")) == {"matlab::greeter"}


def test_namespace_matlab_classes_do_not_join_native_or_matlab_types(tmp_path):
    graphs = []
    for repo, matlab, source in [
        ("matlab1", True, "+Shared/Greeter.m"),
        ("matlab2", True, "+Shared/Greeter.m"),
        ("native1", False, "Greeter.cs"),
        ("native2", False, "Greeter.cs"),
    ]:
        _, graph = _persist(tmp_path, repo, _type_graph(matlab=matlab, source=source))
        graphs.append(prefix_graph_for_global(graph, repo))
    merged = nx.compose_all(graphs)
    link_shared_type_declarations(merged)
    _, merged = _persist(tmp_path, "merged", merged)
    assert set(merged.neighbors("matlab1::greeter")) == {"matlab1::greet"}
    assert set(merged.neighbors("matlab2::greeter")) == {"matlab2::greet"}
    assert set(merged.neighbors("native1::greeter")) == {"native1::greet", "native2::greeter"}
    assert merged.edges["native1::greeter", "native2::greeter"]["relation"] == "same_type_as"


def test_incremental_carry_forward_preserves_local_calls_and_source_inheritance(tmp_path):
    nodes = [
        _node("child_file", "Child.m", "+Shared/Child.m", matlab=True, kind="file",
              matlab_file_kind="class", matlab_primary_name="Child"),
        _node("child", "Child", "+Shared/Child.m", matlab=True, kind="class",
              namespace="Shared", scope_chain=[],
              matlab_superclasses=[{"name": "Shared.Base", "source_location": "L1"}]),
        _node("base_file", "Base.m", "+Shared/Base.m", matlab=True, kind="file",
              matlab_file_kind="class", matlab_primary_name="Base"),
        _node("base", "Base", "+Shared/Base.m", matlab=True, kind="class", namespace="Shared"),
        _node("run", "run", "+Shared/Child.m", matlab=True, kind="method"),
        _node("helper", "helper", "+Shared/Child.m", matlab=True),
    ]
    edges = [
        _edge("child_file", "child", "contains", "+Shared/Child.m"),
        _edge("base_file", "base", "contains", "+Shared/Base.m"),
        _edge("child", "base", "inherits", "+Shared/Child.m"),
        _edge("child", "run", "method", "+Shared/Child.m"),
        _edge("run", "helper", "calls", "+Shared/Child.m"),
    ]
    path, _ = _persist(tmp_path, "base", build([{"nodes": nodes, "edges": edges}], dedup=False))
    updated = build_merge([{
        "nodes": [_node("native", "Child", "Child.h")],
        "edges": [_edge("native", "child", "references", "Child.h", "INFERRED")],
    }], path, dedup=False)
    _, updated = _persist(tmp_path, "updated", updated)
    native = build([{"nodes": [
        _node("child", "Child", "Child.cs", kind="class", namespace="Shared"),
    ], "edges": []}], dedup=False)
    merged = nx.compose(prefix_graph_for_global(updated, "matlab"),
                        prefix_graph_for_global(native, "native"))
    link_cross_repo_member_calls(merged)
    link_shared_type_declarations(merged)
    _, merged = _persist(tmp_path, "merged", merged)
    assert set(merged.neighbors("matlab::native")) == set()
    assert set(merged.neighbors("matlab::run")) == {"matlab::child", "matlab::helper"}
    assert set(merged.neighbors("matlab::child")) == {
        "matlab::child_file", "matlab::run", "matlab::base",
    }
    assert merged.edges["matlab::run", "matlab::helper"]["confidence"] == "EXTRACTED"
    assert merged.edges["matlab::child", "matlab::base"]["relation"] == "inherits"
    assert merged.nodes["matlab::child"]["metadata"]["matlab_superclasses"] == [
        {"name": "Shared.Base", "source_location": "L1"},
    ]
    assert merged.nodes["matlab::child_file"]["metadata"]["matlab_primary_name"] == "Child"
