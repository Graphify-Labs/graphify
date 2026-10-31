"""REQ-QML-022-AC05/06: literal exported QML identity is not a path alias."""
import copy
import json

import pytest

from graphify.extractors.qml_cmake import parse_cmake
from graphify.extractors.qml_facts import qml_metadata
from graphify.extract import extract
from graphify.qt_project_index import QtProjectIndex
from graphify.security import sanitize_metadata
from tests.qt_analysis_helpers import analysis


def source(properties="", files="Tree.qml Inside.qml", version="2.3"):
    """All metadata is literal and source-local; no CMake or QML object executes."""
    return properties + f"qt_add_qml_module(app URI Example VERSION {version} RESOURCE_PREFIX /ui QML_FILES {files})\n"


def build(root, properties, *, extra=None):
    corpus = {"CMakeLists.txt": source(properties), "Tree.qml": "Item { property int count: 1 }",
              "Inside.qml": "import Example 2.3\nBinaryTree {}", "Outside.qml": "import Example 2.3\nBinaryTree {}"}
    corpus.update(extra or {})
    result = analysis(root, corpus)
    return result, QtProjectIndex(result["nodes"], result["edges"], root=root)


def component(result, file="Tree.qml"):
    return next(n for n in result["nodes"] if n["source_file"] == file and qml_metadata(n).get("kind") == "component")


def test_req_qml022_ac05_type_name_versions_and_resource_alias_have_distinct_authority(tmp_path):
    """The physical file, exported name and runtime resource path remain separate facts."""
    result, index = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES '
                          'QT_QML_SOURCE_TYPENAME BinaryTree QT_QML_SOURCE_VERSIONS "1.1;2.2" '
                          'QT_RESOURCE_ALIAS Entry.qml)\n')
    target = component(result)["id"]
    assert index.resolve_component("Example", "BinaryTree", 1, 1).target_id == target
    assert index.resolve_component("Example", "BinaryTree", 2, 1).target_id is None
    assert index.resolve_component("Example", "BinaryTree", 2, 2).target_id == target
    assert index.resolve_component("Example", "BinaryTree", 2, 3).target_id == target
    assert index.resolve_component("Example", "Tree", 2, 3).target_id is None
    assert index.resolve_component("Example", "Entry", 2, 3).target_id is None
    assert index.resolve_url("qrc:/ui/Example/Entry.qml").target_id == target
    exports = [qml_metadata(n) for n in result["nodes"] if qml_metadata(n).get("kind") == "qt_qml_export"
               and qml_metadata(n).get("raw_name") == "BinaryTree"]
    assert {(m["major"], m["minor"]) for m in exports} == {(1, 1), (2, 2)}
    payload = json.loads(json.dumps(result))
    for item in payload["nodes"] + payload["edges"]:
        item["metadata"] = sanitize_metadata(item.get("metadata", {}))
    reloaded = QtProjectIndex(payload["nodes"], payload["edges"], root=tmp_path)
    assert reloaded.resolve_component("Example", "BinaryTree", 2, 3).target_id == target


def test_req_qml022_ac05_internal_type_requires_actual_importer_module_membership(tmp_path):
    """A neighbouring outsider cannot borrow internal visibility from the physical folder."""
    result, index = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES '
                          'QT_QML_SOURCE_TYPENAME BinaryTree QT_QML_INTERNAL_TYPE TRUE)\n')
    before = copy.deepcopy(result)
    target = component(result)["id"]
    assert index.resolve_component("Example", "BinaryTree", 2, 3, importer="Inside.qml").target_id == target
    assert index.resolve_component("Example", "BinaryTree", 2, 3, importer="Outside.qml").target_id is None
    assert index.resolve_component("Example", "BinaryTree", 2, 3).target_id is None
    sites = [n for n in result["nodes"] if qml_metadata(n).get("kind") == "type_use" and n.get("label") == "BinaryTree"]
    assert {n["source_file"]: qml_metadata(n)["status"] for n in sites} == {
        "Inside.qml": "resolved", "Outside.qml": "unavailable"}
    assert result == before


def test_req_qml022_ac05_physical_local_fallback_cannot_revive_renamed_or_internal_type(tmp_path):
    """Old filename lookup is suppressed in the actual QML facade after a source rename."""
    result, _ = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n',
                      extra={"Old.qml": "Tree {}", "New.qml": "import Example 2.3\nBinaryTree {}"})
    sites = {n["source_file"]: qml_metadata(n)["status"] for n in result["nodes"]
             if qml_metadata(n).get("kind") == "type_use" and n["source_file"] in {"Old.qml", "New.qml"}}
    assert sites == {"Old.qml": "unavailable", "New.qml": "resolved"}


def test_req_qml022_ac05_export_collision_is_ambiguous_not_first_file_wins(tmp_path):
    """Distinct declarations with one exported name keep competing endpoint identities."""
    result = analysis(tmp_path, {"CMakeLists.txt": source(
        'set_source_files_properties(A.qml B.qml PROPERTIES QT_QML_SOURCE_TYPENAME Shared)\n', files="A.qml B.qml"),
        "A.qml": "Item {}", "B.qml": "Item {}"})
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    resolved = index.resolve_component("Example", "Shared", 2, 3)
    assert resolved.status == "ambiguous" and len(resolved.candidates) == 2


@pytest.mark.parametrize("declaration", [
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME ../Wrong)',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME lower)',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_VERSIONS "2.1;bad")',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_VERSIONS "2.1;2.1")',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_VERSIONS "2.1;02.01")',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_VERSIONS 2.1;2.2)',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_VERSIONS "")',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_INTERNAL_TYPE MAYBE)',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_INTERNAL_TYPE TRUE QT_QML_SINGLETON_TYPE TRUE)',
    'set_source_files_properties(../Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)',
    'set_source_files_properties(Tree.qml DIRECTORY other PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)',
    'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME ${NAME})',
    'if(WIN32)\nset_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\nendif()',
])
def test_req_qml022_ac05_invalid_dynamic_or_scoped_exports_fail_closed(declaration):
    """Malformed values, contradictory flags and unestablished scope cannot authorize providers."""
    result = parse_cmake(source(declaration + "\n"))
    assert result.get("qml_failures")


def test_req_qml022_ac05_later_property_mutation_remains_an_explicit_rejection():
    """The source-local producer cannot silently reinterpret metadata after module use."""
    result = parse_cmake(source() + 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)')
    assert any(f["reason"] == "source_property_after_metadata_use" for f in result["qml_failures"])


def test_req_qml022_ac06_many_export_versions_survive_sanitized_transport(tmp_path):
    """Authoritative per-version records remain complete beyond display-list limits."""
    versions = ";".join(f"1.{minor}" for minor in range(61))
    result, _ = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES '
                      f'QT_QML_SOURCE_TYPENAME BinaryTree QT_QML_SOURCE_VERSIONS "{versions}")\n')
    payload = json.loads(json.dumps(result))
    for item in payload["nodes"] + payload["edges"]:
        item["metadata"] = sanitize_metadata(item.get("metadata", {}))
    index = QtProjectIndex(payload["nodes"], payload["edges"], root=tmp_path)
    assert index.resolve_component("Example", "BinaryTree", 1, 60).target_id == component(result)["id"]
    assert len([n for n in payload["nodes"] if qml_metadata(n).get("kind") == "qt_qml_export"
                and qml_metadata(n)["raw_name"] == "BinaryTree"]) == 61


@pytest.mark.parametrize("corruption", ["missing", "bool_revision", "wrong_source", "wrong_flag",
                                        "source_list", "module_list", "module_id_list", "source_key_list", "source_value_list"])
def test_req_qml022_ac06_corrupt_export_transport_cannot_restore_filename_fallback(tmp_path, corruption):
    """Missing/version-corrupt exports reject before an older basename lookup could run."""
    result, _ = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n')
    payload = copy.deepcopy(result)
    export = next(n for n in payload["nodes"] if qml_metadata(n).get("kind") == "qt_qml_export"
                  and qml_metadata(n).get("raw_name") == "BinaryTree")
    if corruption == "missing":
        payload["nodes"].remove(export)
    else:
        from graphify.extractors.qml_facts import encode_metadata
        subject = next(n for n in payload["nodes"] if n["id"] == qml_metadata(export)["source_id"]) if corruption in {"source_key_list", "source_value_list"} else export
        metadata = qml_metadata(subject)
        metadata.update({"bool_revision": {"minor": True}, "wrong_source": {"source_id": "missing"},
                         "wrong_flag": {"internal": "true"}, "source_list": {"source_id": []},
                         "module_list": {"module_key": []}, "module_id_list": {"module_id": []},
                         "source_key_list": {"module_key": []}, "source_value_list": {"value": []}}[corruption])
        subject["metadata"]["qml"] = encode_metadata(metadata)
    with pytest.raises(ValueError, match="QML_METADATA"):
        QtProjectIndex(payload["nodes"], payload["edges"], root=tmp_path)


@pytest.mark.parametrize("corruption", ["missing_source_edge", "missing_module_edge", "edge_span",
                                        "node_span", "edge_file", "wrong_parent", "matching_shifted_span", "edge_source_list"])
def test_req_qml022_ac06_export_metadata_cannot_replace_actual_producer_ownership(tmp_path, corruption):
    """Export and module membership need real source-owned declaration edges and original spans."""
    from graphify.extractors.qml_facts import encode_metadata
    result, _ = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n')
    payload = copy.deepcopy(result)
    export = next(n for n in payload["nodes"] if qml_metadata(n).get("kind") == "qt_qml_export"
                  and qml_metadata(n).get("raw_name") == "BinaryTree")
    md = qml_metadata(export)
    edge = next(e for e in payload["edges"] if e["source"] == md["source_id"] and e["target"] == export["id"])
    if corruption == "missing_source_edge":
        payload["edges"].remove(edge)
    elif corruption == "missing_module_edge":
        payload["edges"] = [e for e in payload["edges"] if not (e["source"] == md["module_id"] and e["target"] == md["source_id"])]
    elif corruption == "edge_file":
        edge["source_file"] = "Other.cmake"
    elif corruption == "wrong_parent":
        edge["source"] = md["module_id"]
    elif corruption == "edge_source_list":
        edge["source"] = []
    elif corruption == "matching_shifted_span":
        for subject in (export, edge):
            metadata = qml_metadata(subject)
            metadata["span"] = {**metadata["span"], "start_byte": metadata["span"]["start_byte"] + 1}
            subject["metadata"]["qml"] = encode_metadata(metadata)
    else:
        subject = export if corruption == "node_span" else edge
        metadata = qml_metadata(subject)
        metadata["span"] = {**metadata["span"], "start_byte": 0}
        subject["metadata"]["qml"] = encode_metadata(metadata)
    with pytest.raises(ValueError, match="QML_METADATA"):
        QtProjectIndex(payload["nodes"], payload["edges"], root=tmp_path)


def test_req_qml022_ac05_observed_qmldir_and_cmake_name_conflict_remains_ambiguous(tmp_path):
    """Neither a handwritten module export nor CMake silently replaces the other target."""
    result, index = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n',
                          extra={"Example/qmldir": "module Example\nBinaryTree 2.0 Other.qml\n",
                                 "Example/Other.qml": "Item {}"})
    assert index.resolve_component("Example", "BinaryTree", 2, 0).status == "ambiguous"


def test_req_qml022_ac06_export_source_spans_use_original_bom_crlf_unicode_bytes(tmp_path):
    """New export facts point at physical source tokens, never renamed resource spellings."""
    text = '\ufeff' + source('set_source_files_properties(Écran.qml PROPERTIES QT_QML_SOURCE_TYPENAME Screen)\n',
                             files="Écran.qml").replace("\n", "\r\n")
    result = analysis(tmp_path, {"CMakeLists.txt": text, "Écran.qml": "Item {}"})
    export = next(qml_metadata(n) for n in result["nodes"] if qml_metadata(n).get("kind") == "qt_qml_export")
    span = export["span"]
    assert text.encode()[span["start_byte"]:span["end_byte"]] == "Écran.qml".encode()
    assert export["raw_name"] == "Screen" and (export["major"], export["minor"]) == (2, 0)


def test_req_qml022_ac05_outside_source_path_does_not_gain_type_authority(tmp_path):
    """A declared module input outside the admitted corpus cannot borrow a source target."""
    result = analysis(tmp_path, {"CMakeLists.txt": source(files="../Outside.qml"), "Unrelated.qml": "Item {}"})
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    assert index.resolve_component("Example", "Outside", 2, 3).target_id is None


def test_req_qml022_ac06_corrupt_borrowed_export_context_fails_at_production_facade(tmp_path):
    """Incremental joins reject a broken borrowed chain before publishing fresh type edges."""
    result, _ = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n')
    payload = copy.deepcopy(result)
    export = next(n for n in payload["nodes"] if qml_metadata(n).get("kind") == "qt_qml_export"
                  and qml_metadata(n).get("raw_name") == "BinaryTree")
    payload["edges"] = [e for e in payload["edges"] if e["target"] != export["id"]]
    before = copy.deepcopy(payload)
    rejected = extract([tmp_path / "Inside.qml"], root=tmp_path, cache_root=tmp_path / "fresh-context",
                       resolution_context_nodes=payload["nodes"], resolution_context_edges=payload["edges"], parallel=False)
    assert any(f["code"] == "QML_RESOLUTION_FAILED" for f in rejected["qml_failures"])
    assert not [e for e in rejected["edges"] if e.get("context") == "qml_type_resolution"]
    assert payload == before


@pytest.mark.parametrize("active_exports", [False, True])
def test_req_qml022_ac06_export_contract_does_not_tighten_unrelated_legacy_edge_ids(tmp_path, active_exports):
    """A long legitimate QRC ID is independent of new source-export transport keys."""
    from graphify.extractors.qml_resources import parse_qrc
    relative = "/".join(["nested" + str(n) + "x" * 70 for n in range(4)]) + "/resources.qrc"
    assert len(relative.encode()) < 384
    resource = parse_qrc('<RCC><qresource prefix="/ui"><file>Thing.qml</file></qresource></RCC>', relative_file=relative)
    assert not resource.get("error")
    assert any(len(e["source"].encode()) > 384 or len(e["target"].encode()) > 384 for e in resource["edges"])
    result = build(tmp_path, 'set_source_files_properties(Tree.qml PROPERTIES QT_QML_SOURCE_TYPENAME BinaryTree)\n')[0] if active_exports else {"nodes": [], "edges": []}
    nodes, edges = result["nodes"] + resource["nodes"], result["edges"] + resource["edges"]
    before = copy.deepcopy((nodes, edges))
    index = QtProjectIndex(nodes, edges, root=tmp_path)
    assert (nodes, edges) == before
    if active_exports:
        assert index.resolve_component("Example", "BinaryTree", 2, 3).target_id == component(result)["id"]
