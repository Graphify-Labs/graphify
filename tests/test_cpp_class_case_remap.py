"""INC-QML-110: multi-file member remaps require actual endpoint provenance."""
from __future__ import annotations

from copy import deepcopy
import importlib

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_member_identity import augment_cpp_members, canonicalize_cpp_members, member_fact, proven_member_pairs
from graphify.extractors.cpp_member_remap import plan_member_remap
from graphify.extractors.qt_cpp_syntax import read_cpp


def cohort(root):
    paths = []
    header = root / "panel.hpp"
    header.write_bytes(b"struct Box{void run();};\nstruct box{void run();};\n")
    paths.append(header)
    for name, suffix in [("Box", ".cpp"), ("box", ".cc")]:
        path = root / ("panel" + suffix)
        path.write_bytes((f'#include "panel.hpp"\nvoid helper{name}(){{}}\nvoid {name}::run(){{helper{name}();}}\n').encode())
        paths.append(path)
    for name, text in [("other.hpp", "struct Other{void work();};"), ("other.cpp", "void Other::work(){}")]:
        path = root / name
        path.write_bytes(text.encode())
        paths.append(path)
    results = [extract_cpp(path) for path in paths]
    return ([node for result in results for node in result["nodes"]],
            [edge for result in results for edge in result["edges"]],
            [call for result in results for call in result.get("raw_calls", [])])


@pytest.mark.parametrize("damage", ["missing_file", "foreign_file", "missing_site", "foreign_site", "oversized_site", "unknown_target", "contradictory_target"])
def test_req_qml022_ac06_unproved_multitarget_carrier_retains_complete_bucket(tmp_path, damage):
    """Damage real source transport, retaining unrelated proven joins and every old endpoint."""
    nodes, edges, calls = cohort(tmp_path)
    pairs = proven_member_pairs(nodes, edges)
    bodies = [node for node, _, _ in pairs if member_fact(node).get("member_b64") == "cnVu"]
    assert len(bodies) == 2 and bodies[0]["id"] == bodies[1]["id"]
    old = bodies[0]["id"]
    observed = next(call for call in calls if call.get("caller_nid") == old and call.get("cpp_free_call"))
    if damage == "missing_file":
        observed.pop("source_file")
    elif damage == "foreign_file":
        observed["source_file"] = "foreign.cpp"
    elif damage == "missing_site":
        observed.pop("source_location")
    elif damage == "foreign_site":
        observed["source_location"] = "L999"
    elif damage == "oversized_site":
        observed["source_location"] = "L" + "9" * 5000
    else:
        inbound = deepcopy(next(edge for edge in edges if edge.get("target") == old and edge.get("relation") == "contains"))
        inbound["relation"] = "references"
        if damage == "contradictory_target":
            inbound["target_file"] = "foreign.cpp"
        edges.append(inbound)
    before = deepcopy((nodes, edges, calls))
    accepted, _ = plan_member_remap(pairs, edges, calls)
    assert (nodes, edges, calls) == before
    assert all(body["id"] != old for body, _, _ in accepted)
    canonicalize_cpp_members(nodes, edges, calls)
    assert [node["id"] for node in bodies] == [old, old]
    assert not any(member_fact(node).get("bound_owner_b64") for node in bodies)
    assert any(member_fact(node).get("bound_owner_b64") for node in nodes if node["label"] == "Other::work()")
    assert all(edge.get(key) in {node["id"] for node in nodes} for edge in edges for key in ("source", "target"))


def test_req_qml022_ac06_explicit_callee_file_remaps_without_using_caller_file(tmp_path):
    """An inbound reference with its own real target file selects that exact class body."""
    nodes, edges, calls = cohort(tmp_path)
    pairs = proven_member_pairs(nodes, edges)
    body, declaration, _ = next(pair for pair in pairs if pair[0]["label"] == "box::run()")
    inbound = deepcopy(next(edge for edge in edges if edge.get("target") == body["id"] and edge.get("relation") == "contains"))
    inbound.update(relation="references", target_file=body["source_file"])
    edges.append(inbound)
    original = deepcopy((nodes, edges, calls))
    selected, changes = plan_member_remap(pairs, edges, calls)
    assert len(selected) == 3 and (nodes, edges, calls) == original
    assert any(carrier is inbound and key == "target" and value == declaration["id"] for carrier, key, value in changes)
    canonicalize_cpp_members(nodes, edges, calls)
    assert inbound["target"] == declaration["id"]
    accepted = deepcopy((nodes, edges, calls))
    canonicalize_cpp_members(nodes, edges, calls)
    assert (nodes, edges, calls) == accepted


def test_req_qml022_ac02_standalone_member_augmentation_uses_literal_collision_index(tmp_path):
    """The compatibility default rebuilds the same source identity without Engine's binding table."""
    raw = b'\n#include "unit.hpp"\nvoid helper(){}\nvoid Box::run(){helper();}\nvoid box::run(){helper();}\n'
    (tmp_path / "unit.hpp").write_bytes(b"struct Box{void run();};struct box{void run();};")
    path = tmp_path / "unit.cpp"
    path.write_bytes(raw)
    result = extract_cpp(path)
    expected = {node["id"]: deepcopy(member_fact(node)) for node in result["nodes"] if member_fact(node)}
    for node in result["nodes"]:
        node.get("metadata", {}).pop("cpp_member", None)
    unit = read_cpp(path, tmp_path)
    augment_cpp_members(unit.tree, raw, result["nodes"], path)
    assert {node["id"]: member_fact(node) for node in result["nodes"] if member_fact(node)} == expected


def test_req_qml022_ac06_facade_does_not_undo_unproved_multiowner_join(tmp_path, monkeypatch):
    """The complete production pipeline retains rejected bodies instead of later choosing a class."""
    cohort(tmp_path)
    module = importlib.import_module("graphify.extract")
    original, observed = module._merge_decl_def_classes, []

    def damaged_inbound(nodes, edges, calls):
        pairs = proven_member_pairs(nodes, edges)
        body, _, _ = next(pair for pair in pairs if pair[0]["label"] == "Box::run()")
        inbound = deepcopy(next(edge for edge in edges if edge.get("target") == body["id"] and edge.get("relation") == "contains"))
        inbound["relation"] = "references"
        edges.append(inbound)
        original(nodes, edges, calls)
        observed.append(True)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_merge_decl_def_classes", damaged_inbound)
        result = extract(sorted(tmp_path.glob("*.?pp")) + sorted(tmp_path.glob("*.cc")), root=tmp_path, cache_root=tmp_path, parallel=False)
    assert observed and not result["failed_sources"]
    bodies = [node for node in result["nodes"] if member_fact(node).get("role") == "definition" and "::run()" in node["label"]]
    assert len(bodies) == 2 and len({node["id"] for node in bodies}) == 2
    assert not any(member_fact(node).get("bound_owner_b64") for node in bodies)
    prototypes = [node for node in result["nodes"] if member_fact(node).get("role") == "declaration" and node["label"] == ".run()"]
    assert len(prototypes) == 2 and not any(node.get("definition_file") for node in prototypes)
