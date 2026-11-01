"""INC-QML-33 validates generic C++ file provenance at both Qt file joins."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_source_containment import attach_qt_file_sites
from tests.test_qt_project_membership import apply, facts, fixture


def cpp_fixture(root):
    """Real C++ transport owns includes/shadows; an opaque constructor lacks an owner."""
    fixture(root)
    (root / "backend.cpp").write_text(
        '#include "missing.hpp"\nusing QObject = int;\n'
        'class Backend { public: Backend(Unknown count); };\n'
        'Backend::Backend(Unknown count) { emit ready(); }\n',
        encoding="utf-8", newline="")
    from graphify.extract import extract
    paths = [root / name for name in ("backend.cpp", "CMakeLists.txt", "resources.qrc", "qml/ResizeHandle.qml")]
    result = extract(paths, root=root, cache_root=root, parallel=False)
    assert not result.get("qml_failures")
    return result


def file_node(nodes):
    return next(node for node in nodes if node.get("label") == "backend.cpp"
                and node.get("source_file") == "backend.cpp" and not node.get("_callable_class"))


def project(root, nodes, edges, declarations, boundary, fresh_ids=()):
    """Both production joins consume borrowed facts without mutating their dictionaries."""
    if boundary == "membership":
        sites = apply(root, nodes, edges, declarations, fresh_ast_ids=fresh_ids)
        assert len(sites) == 1
        md = qml_metadata(sites[0])
        return md["target_id"], md["reason"]
    unknown = [node for node in nodes if qt_metadata(node).get("kind") == "emission"
               and not qt_metadata(node).get("owner_id")]
    assert unknown
    active = {root / "backend.cpp": {"nodes": unknown, "edges": []}}
    added = attach_qt_file_sites(active, nodes, [], root=root, fresh_ast_ids=fresh_ids)
    assert all(edge["context"] == "qt_source_file" and edge["confidence"] == "EXTRACTED" for edge in added)
    assert all(edge["source"] == edge["_src"] and edge["target"] == edge["_tgt"] for edge in added)
    assert all(not qt_metadata(node)["owner_id"] for node in unknown)
    return added[0]["source"] if added else "", ""


@pytest.mark.parametrize("boundary", ["membership", "containment"])
@pytest.mark.parametrize("transport", ["producer", "incomplete", "legacy", "fresh", "reload"])
def test_req_qml020_ac01_ac03_cpp_file_transport_retains_exact_file_identity(tmp_path, boundary, transport):
    """Current/old/incomplete/fresh/reloaded file facts retain explicit source links."""
    result = cpp_fixture(tmp_path)
    if transport == "reload":
        output = tmp_path / "graph.json"
        assert to_json(build_from_json(result, root=tmp_path), {}, str(output))
        result = json.loads(output.read_text(encoding="utf-8"))
    nodes = copy.deepcopy(result["nodes"])
    edges = copy.deepcopy(result.get("edges", result.get("links", [])))
    target = file_node(nodes)
    if transport == "incomplete":
        target["metadata"]["cpp_constructor_types"]["complete"] = False
    elif transport == "legacy":
        target.pop("metadata")
    elif transport == "fresh":
        target.pop("_origin")
    declarations = [next(node for node in nodes if qml_metadata(node).get("kind") == "qt_source"
                         and qml_metadata(node).get("source_kind") == "cpp")]
    borrowed = list(nodes)
    before = copy.deepcopy(borrowed)
    target_id, reason = project(tmp_path, nodes, edges, declarations, boundary,
                                {target["id"]} if transport == "fresh" else ())
    assert target_id == target["id"] and not reason
    assert borrowed == before


CORRUPTIONS = ["foreign", "outside_root", "duplicate", "callable", "class", "function_type",
               "non_ast", "unmarked", "location", "label", "file_type",
               "other_metadata", "record_scalar", "version", "bool_version", "complete",
               "negative_size", "bool_size", "size_type", "includes_type", "includes_limit",
               "include_encoding", "include_kind", "include_span", "include_position",
               "include_bounds", "include_foreign", "shadows_type", "shadows_limit",
               "shadow_encoding", "shadow_scope", "shadow_role", "shadow_position"]


def corrupt(nodes, target, corruption):
    """Change actual producer transport, never a fake decoder or resolver result."""
    record = target["metadata"]["cpp_constructor_types"]
    if corruption in {"foreign", "outside_root"}:
        target["source_file"] = "foreign.cpp" if corruption == "foreign" else "../backend.cpp"
    elif corruption == "duplicate":
        nodes.append({**copy.deepcopy(target), "id": target["id"] + "_competing"})
    elif corruption in {"callable", "class"}:
        target["_callable" if corruption == "callable" else "_callable_class"] = True
    elif corruption == "function_type":
        target["type"] = "function"
    elif corruption in {"non_ast", "unmarked"}:
        target["_origin"] = "semantic" if corruption == "non_ast" else None
    elif corruption in {"location", "label", "file_type"}:
        target[{"location": "source_location", "label": "label", "file_type": "file_type"}[corruption]] = "wrong"
    elif corruption == "other_metadata":
        target["metadata"]["semantic"] = {"kind": "function"}
    elif corruption == "record_scalar":
        target["metadata"]["cpp_constructor_types"] = []
    elif corruption in {"version", "bool_version", "complete", "negative_size", "bool_size", "size_type"}:
        key, value = {"version": ("contract_version", 2), "bool_version": ("contract_version", True),
                      "complete": ("complete", 1), "negative_size": ("source_size", -1),
                      "bool_size": ("source_size", True), "size_type": ("source_size", "100")}[corruption]
        record[key] = value
    elif corruption.endswith("_type"):
        record[corruption.removesuffix("_type")] = {}
    elif corruption.endswith("_limit"):
        record[corruption.removesuffix("_limit")] *= 51
    elif corruption.startswith("include_"):
        item = record["includes"][0]
        if corruption == "include_encoding":
            item["literal_b64"] = "invalid!"
        elif corruption == "include_kind":
            item["kind"] = "dynamic"
        elif corruption == "include_span":
            item["span"]["end_row"] = item["span"]["start_row"]
            item["span"]["end_column"] += 1
        elif corruption == "include_position":
            item["end_byte"] += 1
        elif corruption == "include_bounds":
            item["span"]["end_byte"] = record["source_size"] + 1
        else:
            import base64
            item["literal_b64"] = base64.b64encode(b"/foreign.hpp").decode()
    else:
        item = record["shadows"][0]
        if corruption in {"shadow_encoding", "shadow_scope"}:
            item["scope_b64"] = "invalid!" if corruption == "shadow_encoding" else "YmFkLXNjb3Bl"
        elif corruption == "shadow_role":
            item["class_scope"] = 1
        else:
            item["start_byte"] += 1


@pytest.mark.parametrize("boundary", ["membership", "containment"])
@pytest.mark.parametrize("corruption", CORRUPTIONS)
def test_req_qml020_ac02_cpp_file_transport_cannot_authorize_corrupted_file_role(tmp_path, boundary, corruption):
    """Foreign/duplicate/semantic/ill-typed file evidence creates no guessed endpoint."""
    result = cpp_fixture(tmp_path)
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    target = file_node(nodes)
    declarations = [next(node for node in nodes if qml_metadata(node).get("kind") == "qt_source"
                         and qml_metadata(node).get("source_kind") == "cpp")]
    corrupt(nodes, target, corruption)
    borrowed, before = list(nodes), copy.deepcopy(nodes)
    target_id, reason = project(tmp_path, nodes, edges, declarations, boundary)
    assert not target_id
    if boundary == "membership":
        assert reason in {"membership_target_outside_accepted_corpus", "duplicate_provider"}
    assert borrowed == before


@pytest.mark.parametrize("complete", [False, True])
def test_req_qml008_ac02_cpp_file_role_preserves_separate_constructor_type_authority(tmp_path, complete):
    """A valid file record can contain sites while incomplete type proof stays unusable."""
    from graphify.extractors.cpp_constructor_type_authority import ConstructorTypeAuthority, valid_source_transport
    from graphify.qt_source_file_role import generic_file_role

    result = cpp_fixture(tmp_path)
    target = file_node(result["nodes"])
    target["metadata"]["cpp_constructor_types"]["complete"] = complete
    record = target["metadata"]["cpp_constructor_types"]
    before = copy.deepcopy(target)
    assert valid_source_transport(record)
    assert generic_file_role(target, "backend.cpp")
    authority = ConstructorTypeAuthority([target])
    assert bool(authority._fact("backend.cpp")) is complete
    assert target == before


@pytest.mark.parametrize("boundary", ["membership", "containment"])
def test_req_qml020_ac02_cpp_file_joins_read_no_source_and_execute_no_corpus(tmp_path, monkeypatch, boundary):
    """After real extraction, both joins use accepted dictionaries only."""
    import builtins
    import subprocess
    from pathlib import Path
    result = cpp_fixture(tmp_path)
    declarations = [node for node in facts(result, "qt_source") if qml_metadata(node)["source_kind"] == "cpp"]
    target = file_node(result["nodes"])

    def forbidden(*_args, **_kwargs):
        raise AssertionError("File identity must not read or execute corpus sources")

    for method in ("open", "read_bytes", "read_text", "glob", "rglob"):
        monkeypatch.setattr(Path, method, forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert project(tmp_path, result["nodes"], result["edges"], declarations, boundary)[0] == target["id"]
