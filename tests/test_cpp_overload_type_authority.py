"""INC-QML-15: named SDK constructor signatures require admitted type authority."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_constructors import bind_cpp_constructors
from graphify.extractors.cpp_constructor_type_authority import ConstructorTypeAuthority
from graphify.paths import load_node_link_graph
from tests.test_cpp_overload_identity import constructors, source_pair


def project(root, shadow="using QObject = int;", include=True, transitive=False):
    """Only already admitted AST inputs participate; include text executes nothing."""
    paths = source_pair(root, "Backend(QObject *parent);", "Backend::Backend(QObject *parent) {}")
    alias = root / "alias.hpp"
    alias.write_bytes(shadow.encode())
    paths.append(alias)
    dependency = alias.name
    if transitive:
        bridge = root / "bridge.hpp"
        bridge.write_bytes(b'#include "alias.hpp"\n')
        paths.append(bridge)
        dependency = bridge.name
    if include:
        paths[1].write_bytes(f'#include "{dependency}"\n'.encode() + paths[1].read_bytes())
    return paths


@pytest.mark.parametrize("shadow", ["using QObject = int;", "typedef int QObject;", "class QObject;",
                                   "struct QObject {};", "#if FEATURE\nusing QObject = int;\n#endif\n"])
@pytest.mark.parametrize("transitive", [False, True])
def test_req_qml008_ac03_included_sdk_shadow_cannot_bind_same_spelled_constructor(tmp_path, shadow, transitive):
    """Different source type identities must not merge merely because both parameters spell QObject."""
    result = extract(project(tmp_path, shadow, transitive=transitive), root=tmp_path, cache_root=tmp_path, parallel=False)
    definition = next(node for node in constructors(result) if node["source_file"] == "backend.cpp")
    assert definition["metadata"]["cpp_constructor"]["type_authorized"] is False
    assert not any(edge["target"] == definition["id"] and edge["relation"] == "method" for edge in result["edges"])


@pytest.mark.parametrize("include,shadow", [(False, "using QObject = int;"),
                                           (True, "namespace Unrelated {using QObject = int;}"),
                                           (True, "class Other {public: using QObject = int;};"),
                                           (True, "void ordinary(){using QObject = int;}"),
                                           (True, "using Other = int;")])
def test_req_qml008_ac02_unincluded_or_unrelated_scope_cannot_shadow_sdk_constructor(tmp_path, include, shadow):
    """Available but invisible aliases do not invalidate an otherwise exact constructor."""
    result = extract(project(tmp_path, shadow, include=include), root=tmp_path, cache_root=tmp_path, parallel=False)
    found = constructors(result)
    assert len(found) == 1 and found[0]["definition_file"] == "backend.cpp"


@pytest.mark.parametrize("corruption", ["missing", "complete", "include_encoding", "include_bound", "scope_encoding", "span", "version"])
def test_req_qml008_ac03_direct_constructor_dependency_proof_rejects_corruption(tmp_path, corruption):
    """Malformed admitted transport never turns a hidden source shadow into SDK authority."""
    paths = project(tmp_path)
    direct = [extract_cpp(path) for path in paths]
    nodes = copy.deepcopy([node for result in direct for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in direct for edge in result["edges"]])
    file = next(node for node in nodes if node["label"] == "alias.hpp")
    fact = file["metadata"]["cpp_constructor_types"]
    if corruption == "missing":
        del file["metadata"]["cpp_constructor_types"]
    elif corruption == "complete":
        fact["complete"] = False
    elif corruption == "include_encoding":
        cpp_file = next(node for node in nodes if node["label"] == "backend.cpp")
        cpp_file["metadata"]["cpp_constructor_types"]["includes"][0]["literal_b64"] = "invalid!"
    elif corruption == "include_bound":
        fact["includes"] = [{"literal_b64": "YQ==", "end_byte": 0}] * 51
    elif corruption == "scope_encoding":
        fact["shadows"][0]["scope_b64"] = "invalid!"
    elif corruption == "span":
        fact["shadows"][0]["start_byte"] = True
    else:
        fact["contract_version"] = True
    bind_cpp_constructors(nodes, edges)
    definition = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "definition")
    assert definition["metadata"]["cpp_constructor"].get("owner_bound") is not True


def test_req_qml008_ac03_same_class_later_alias_shadows_constructor_parameter_clause(tmp_path):
    """Whole-class lookup cannot borrow SDK identity from a later member alias."""
    paths = source_pair(tmp_path, "Backend(QObject *parent); using QObject = int;", "Backend::Backend(QObject *parent) {}")
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(node.get("definition_file") for node in constructors(result))


def test_req_qml008_ac03_include_walk_overflow_cannot_hide_sdk_shadow(tmp_path):
    """A long admitted chain rejects authority before bounded traversal can discard an alternative."""
    paths = source_pair(tmp_path, "Backend(QObject *parent);", "Backend::Backend(QObject *parent) {}")
    paths[1].write_bytes(b'#include "dependency0.hpp"\n' + paths[1].read_bytes())
    for index in range(129):
        dependency = tmp_path / f"dependency{index}.hpp"
        dependency.write_bytes(f'#include "dependency{index + 1}.hpp"\n'.encode() if index < 128 else b"using QObject = int;")
        paths.append(dependency)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(node.get("definition_file") for node in constructors(result))


def test_req_qml008_ac02_direct_type_proof_survives_sanitation_export_reload(tmp_path):
    """Producer provenance remains authoritative after the real graph serialization boundary."""
    paths = project(tmp_path, "using Other = int;")
    direct = extract_cpp(paths[2])
    assert next(node for node in direct["nodes"] if node["label"] == "alias.hpp")["metadata"]["cpp_constructor_types"]["complete"]
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    reloaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    nodes = [{"id": identity, **data} for identity, data in reloaded.nodes(data=True)]
    authority = ConstructorTypeAuthority(nodes)
    candidate = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor"))
    assert authority.authorized(candidate, candidate["metadata"]["cpp_constructor"])


@pytest.mark.parametrize("include", ['"unavailable.hpp"', '"../../unadmitted.hpp"', '"C:/private.hpp"', 'HEADER_MACRO'])
def test_req_qml008_ac03_unknown_quoted_dependency_never_authorizes_sdk_signature(tmp_path, include):
    """Missing, escaping, absolute and dynamically expanded headers grant no compiler type identity."""
    paths = source_pair(tmp_path, "Backend(QObject *parent);", "Backend::Backend(QObject *parent) {}")
    paths[1].write_bytes(f"#include {include}\n".encode() + paths[1].read_bytes())
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(node.get("definition_file") for node in constructors(result))


def test_req_qml008_ac02_shadow_transport_spans_address_original_bom_crlf_unicode_bytes(tmp_path):
    """Encoded dependency decisions retain spans against the bytes actually read from disk."""
    path = tmp_path / "alias.hpp"
    path.write_bytes('\ufeff// caf\u00e9 \u96ea\r\n#include "bridge.hpp"\r\nnamespace Nested { using QObject = int; }\r\n'.encode())
    result = extract_cpp(path)
    fact = next(node for node in result["nodes"] if node["label"] == "alias.hpp")["metadata"]["cpp_constructor_types"]
    original = path.read_bytes()
    assert fact["source_size"] == len(original)
    assert len(fact["includes"]) == len(fact["shadows"]) == 1
    for items, expected in ((fact["includes"], b'#include "bridge.hpp"\r\n'), (fact["shadows"], b"using QObject = int;")):
        span = items[0]["span"]
        assert original[span["start_byte"]:span["end_byte"]] == expected


@pytest.mark.parametrize("dependency", ["alias.hpp", "nested/alias.hpp"])
def test_req_qml008_ac03_angle_local_shadow_cannot_grant_sdk_constructor_identity(tmp_path, dependency):
    """An angle include may name an admitted source alias; compiler search order is unavailable."""
    paths = source_pair(tmp_path, "Backend(QObject *parent);", "Backend::Backend(QObject *parent) {}")
    header = tmp_path / dependency
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_bytes(b"using QObject = int;")
    paths.append(header)
    # Even an admitted nested basename is a potential include-directory target.
    literal = header.name
    paths[1].write_bytes(f"#include <{literal}>\n".encode() + paths[1].read_bytes())
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(node.get("definition_file") for node in constructors(result))
    definition = next(node for node in constructors(result) if node["source_file"] == "backend.cpp")
    assert definition["metadata"]["cpp_constructor"]["type_authorized"] is False


def test_req_qml008_ac02_external_sdk_angle_keeps_unincluded_alias_independent(tmp_path):
    """An unavailable Qt SDK header does not import an unrelated admitted alias file."""
    paths = project(tmp_path, include=False)
    paths[1].write_bytes(b"#include <QObject>\n#include <QtCore/QObject>\n" + paths[1].read_bytes())
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    found = constructors(result)
    assert len(found) == 1 and found[0]["definition_file"] == "backend.cpp"


@pytest.mark.parametrize("corruption", ["missing", "corrupt", "duplicate"])
def test_req_qml008_ac03_angle_candidate_rejects_missing_corrupt_or_duplicate_authority(tmp_path, corruption):
    """An admitted angle candidate cannot vanish from the shadow check through damaged metadata."""
    paths = project(tmp_path, include=False)
    paths[1].write_bytes(b"#include <alias.hpp>\n" + paths[1].read_bytes())
    results = [extract_cpp(path) for path in paths]
    nodes = copy.deepcopy([node for result in results for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in results for edge in result["edges"]])
    candidate = next(node for node in nodes if node["label"] == "alias.hpp")
    if corruption == "missing":
        candidate["metadata"].pop("cpp_constructor_types")
    elif corruption == "corrupt":
        candidate["metadata"]["cpp_constructor_types"]["complete"] = False
    else:
        nodes.append(copy.deepcopy(candidate))
    bind_cpp_constructors(nodes, edges)
    definition = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "definition")
    assert definition["metadata"]["cpp_constructor"].get("owner_bound") is not True


@pytest.mark.parametrize("kind", ["missing", "invalid", "overflow"])
def test_req_qml008_ac03_angle_include_transport_limits_reject_sdk_identity(tmp_path, kind):
    """Missing delimiter authority or truncated include decisions grant no SDK signature proof."""
    paths = source_pair(tmp_path, "Backend(QObject *parent);", "Backend::Backend(QObject *parent) {}")
    prefix = b"#include <QObject>\n" * (51 if kind == "overflow" else 1)
    paths[1].write_bytes(prefix + paths[1].read_bytes())
    results = [extract_cpp(path) for path in paths]
    nodes = copy.deepcopy([node for result in results for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in results for edge in result["edges"]])
    cpp = next(node for node in nodes if node["label"] == "backend.cpp")
    include = cpp["metadata"]["cpp_constructor_types"]["includes"][0]
    if kind == "missing":
        include.pop("kind")
    elif kind == "invalid":
        include["kind"] = "expanded"
    bind_cpp_constructors(nodes, edges)
    definition = next(node for node in nodes if node.get("metadata", {}).get("cpp_constructor", {}).get("role") == "definition")
    assert definition["metadata"]["cpp_constructor"].get("owner_bound") is not True


def test_req_qml008_ac03_escaping_angle_literal_cannot_establish_compiler_include_search(tmp_path):
    """A parent traversal has no accepted compiler include root at this analysis boundary."""
    paths = source_pair(tmp_path, "Backend(QObject *parent);", "Backend::Backend(QObject *parent) {}")
    paths[1].write_bytes(b"#include <../alias.hpp>\n" + paths[1].read_bytes())
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(node.get("definition_file") for node in constructors(result))
